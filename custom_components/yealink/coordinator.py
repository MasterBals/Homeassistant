"""Bluetooth coordinator for Yealink devices."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
import logging
from pathlib import Path
from typing import Any

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.active_update_coordinator import (
    ActiveBluetoothDataUpdateCoordinator,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, format_mac

from .const import DEFAULT_POLL_INTERVAL
from .models import RoomSensorData
from .profiles.roomsensor import (
    INFO_UUIDS,
    MEASUREMENT_UUIDS,
    NOTIFY_UUIDS,
    UUID_FIRMWARE,
    UUID_HARDWARE,
    UUID_MANUFACTURER,
    UUID_MODEL,
    UUID_SERIAL,
    UUID_SOFTWARE,
    decode_measurement,
    decode_text,
)


def _find_usb_bluetooth_adapter() -> str | None:
    """Return the external USB Bluetooth HCI adapter.

    The integrated Raspberry Pi controller is connected through UART, while
    external dongles are exposed below the USB bus with the btusb driver.
    Selecting by bus/driver instead of a fixed hci number keeps this stable
    across reboots where BlueZ may renumber adapters.
    """
    root = Path("/sys/class/bluetooth")
    if not root.exists():
        return None

    for hci in sorted(root.glob("hci*")):
        real = hci.resolve()
        node = real
        usb_backed = False
        while node != node.parent:
            if (node / "idVendor").exists() and (node / "idProduct").exists():
                usb_backed = True
                break
            node = node.parent
        if not usb_backed:
            continue

        try:
            driver = (hci / "device" / "driver").resolve().name
        except (OSError, RuntimeError):
            driver = None
        if driver == "btusb":
            return hci.name

    return None


class RoomSensorCoordinator(
    ActiveBluetoothDataUpdateCoordinator[RoomSensorData]
):
    """Manage one Yealink RoomSensor."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        *,
        address: str,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass=hass,
            logger=logger,
            address=address,
            needs_poll_method=self._needs_poll,
            poll_method=self._do_poll,
            mode=bluetooth.BluetoothScanningMode.ACTIVE,
            connectable=False,
        )
        self._address = format_mac(address)
        self._client: BleakClient | None = None
        self._poll_lock = asyncio.Lock()
        self._shutdown_requested = False
        self._info_loaded = False
        self.last_error: str | None = None
        self.data = RoomSensorData()
        self._cancel_raw_callback = bluetooth.async_register_callback(
            hass,
            self._raw_advertisement,
            {"address": self._address, "connectable": False},
            bluetooth.BluetoothScanningMode.ACTIVE,
            scan_interval=60.0,
            scan_duration=10.0,
        )

    @property
    def connected(self) -> bool:
        """Return whether the BLE connection is active."""
        return self._client is not None and self._client.is_connected

    @property
    def available(self) -> bool:
        """Return whether the RoomSensor is currently usable."""
        return self.connected or super().available

    async def async_initialize(self) -> bool:
        """Perform an initial GATT read from Home Assistant's cached discovery."""
        service_info = bluetooth.async_last_service_info(
            self.hass,
            self._address,
            connectable=False,
        )
        if service_info is None:
            self.logger.debug(
                "No cached Bluetooth service info available for %s; "
                "attempting direct GATT connection",
                self._address,
            )
        else:
            self._last_service_info = service_info

        try:
            self.data = await self._do_poll(service_info)
        except Exception as err:
            self.last_error = f"{type(err).__name__}: {err}"
            self.last_poll_successful = False
            self.logger.exception(
                "%s: Initial RoomSensor GATT read failed",
                self._address,
            )
            self._publish_debug_state("error", service_info)
            return False

        self.last_error = None
        self._available = True
        self.last_poll_successful = True
        self._publish_debug_state("ok", service_info)
        self.async_update_listeners()
        return True

    @callback
    def _raw_advertisement(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        _change: bluetooth.BluetoothChange,
    ) -> None:
        """Observe every advertisement for this configured RoomSensor."""
        self._last_service_info = service_info
        self.data = replace(self.data, rssi=service_info.rssi)
        self._publish_debug_state("advertisement_seen", service_info)

    @callback
    def _needs_poll(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        seconds_since_last_poll: float | None,
    ) -> bool:
        """Return whether the device needs a connection or refresh."""
        self.data = replace(self.data, rssi=service_info.rssi)
        return not self._shutdown_requested and (
            not self.connected
            or seconds_since_last_poll is None
            or seconds_since_last_poll >= DEFAULT_POLL_INTERVAL
        )

    async def _do_poll(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak | None,
    ) -> RoomSensorData:
        """Connect to the RoomSensor and refresh all values."""
        async with self._poll_lock:
            if self._shutdown_requested:
                return self.data

            last_error: Exception | None = None
            for attempt in range(1, 4):
                try:
                    if not self.connected:
                        await self._connect(service_info)

                    await self._read_measurements()
                    if not self._info_loaded:
                        await self._read_device_info()
                        self._info_loaded = True
                        self._update_device_registry()

                    if service_info is not None:
                        self.data = replace(self.data, rssi=service_info.rssi)
                    self.last_error = None
                    return self.data
                except Exception as err:
                    last_error = err
                    self.logger.debug(
                        "%s: RoomSensor GATT attempt %s/3 failed",
                        self._address,
                        attempt,
                        exc_info=True,
                    )
                    await self._disconnect_client()
                    if attempt < 3 and not self._shutdown_requested:
                        await asyncio.sleep(3)

            if last_error is not None:
                self.last_error = f"{type(last_error).__name__}: {last_error}"
                raise last_error
            return self.data

    async def _connect(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak | None,
    ) -> None:
        """Connect through the dedicated external USB Bluetooth adapter."""
        adapter = await self.hass.async_add_executor_job(
            _find_usb_bluetooth_adapter
        )
        if adapter is None:
            raise RuntimeError(
                "No external USB Bluetooth adapter (btusb) available for "
                f"Yealink RoomSensor {self._address}"
            )

        self.logger.debug(
            "%s: connecting Yealink RoomSensor through dedicated adapter %s",
            self._address,
            adapter,
        )
        client = BleakClient(
            self._address,
            disconnected_callback=self._on_disconnect,
            timeout=15.0,
            bluez={"adapter": adapter},
        )
        await client.connect()

        try:
            self._client = client
            for uuid in NOTIFY_UUIDS:
                try:
                    await client.start_notify(uuid, self._notification)
                except Exception:
                    self.logger.debug(
                        "Unable to subscribe to %s on %s",
                        uuid,
                        self._address,
                        exc_info=True,
                    )
        except Exception:
            self._client = None
            await client.disconnect()
            raise

    async def _disconnect_client(self) -> None:
        """Disconnect and clear the current BLE client."""
        client = self._client
        self._client = None
        if client is not None and client.is_connected:
            try:
                await client.disconnect()
            except Exception:
                self.logger.debug(
                    "Error disconnecting from %s during retry",
                    self._address,
                    exc_info=True,
                )

    async def _read_measurements(self) -> None:
        """Read the standard GATT measurements."""
        client = self._client
        if client is None or not client.is_connected:
            raise RuntimeError("RoomSensor is not connected")

        for uuid in MEASUREMENT_UUIDS:
            value = bytes(await client.read_gatt_char(uuid))
            self.data = decode_measurement(self.data, uuid, value)

    async def _read_device_info(self) -> None:
        """Read Device Information Service values when available."""
        client = self._client
        if client is None or not client.is_connected:
            return

        values: dict[str, str] = {}
        for uuid in INFO_UUIDS:
            try:
                values[uuid] = decode_text(bytes(await client.read_gatt_char(uuid)))
            except Exception:
                self.logger.debug(
                    "Unable to read Device Information characteristic %s from %s",
                    uuid,
                    self._address,
                    exc_info=True,
                )

        self.data = replace(
            self.data,
            manufacturer=values.get(UUID_MANUFACTURER, self.data.manufacturer),
            model=values.get(UUID_MODEL, self.data.model),
            serial_number=values.get(UUID_SERIAL, self.data.serial_number),
            firmware=values.get(UUID_FIRMWARE, self.data.firmware),
            hardware=values.get(UUID_HARDWARE, self.data.hardware),
            software=values.get(UUID_SOFTWARE, self.data.software),
        )

    @callback
    def _notification(
        self,
        sender: BleakGATTCharacteristic | int,
        value: bytearray,
    ) -> None:
        """Handle a RoomSensor notification/indication."""
        uuid = getattr(sender, "uuid", None)
        if not isinstance(uuid, str):
            return

        self.data = decode_measurement(self.data, uuid, bytes(value))
        self.async_update_listeners()

    def _on_disconnect(self, _client: BleakClient) -> None:
        """Move disconnect handling onto the Home Assistant event loop."""
        self.hass.loop.call_soon_threadsafe(self._handle_disconnect)

    @callback
    def _handle_disconnect(self) -> None:
        """Clear the active client after a disconnect."""
        self._client = None
        self.async_update_listeners()

    def _update_device_registry(self) -> None:
        """Update device registry metadata learned from GATT."""
        registry = dr.async_get(self.hass)
        device = registry.async_get_device(
            connections={(CONNECTION_BLUETOOTH, self._address)}
        )
        if device is None:
            return

        registry.async_update_device(
            device.id,
            manufacturer=self.data.manufacturer or "Yealink",
            model=self.data.model or "RoomSensor",
            serial_number=self.data.serial_number,
            sw_version=self.data.firmware,
            hw_version=self.data.hardware,
        )

    @callback
    def _publish_debug_state(
        self,
        state: str,
        service_info: bluetooth.BluetoothServiceInfoBleak | None = None,
    ) -> None:
        """Expose temporary runtime diagnostics while stabilizing the integration."""
        suffix = self._address.replace(":", "")[-4:].lower()
        resolved = bluetooth.async_ble_device_from_address(
            self.hass,
            self._address,
            connectable=True,
        )
        self.hass.states.async_set(
            f"sensor.yealink_roomsensor_{suffix}_diagnose",
            state,
            {
                "friendly_name": f"Yealink RoomSensor {suffix.upper()} Diagnose",
                "address": self._address,
                "ble_connected": self.connected,
                "last_poll_successful": self.last_poll_successful,
                "last_error": self.last_error,
                "connectable_device_present": resolved is not None,
                "advertisement_connectable": (
                    service_info.connectable if service_info is not None else None
                ),
                "advertisement_source": (
                    service_info.source if service_info is not None else None
                ),
                "advertisement_name": (
                    service_info.name if service_info is not None else None
                ),
                "rssi": service_info.rssi if service_info is not None else None,
            },
        )

    async def async_shutdown(self) -> None:
        """Stop Bluetooth callbacks and close the connection."""
        self._shutdown_requested = True
        self._async_stop()
        self._cancel_raw_callback()

        async with self._poll_lock:
            client = self._client
            self._client = None

        if client is not None and client.is_connected:
            try:
                await client.disconnect()
            except Exception:
                self.logger.debug(
                    "Error disconnecting from %s",
                    self._address,
                    exc_info=True,
                )
