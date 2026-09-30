"""Bluetooth coordinator for Yealink devices."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
import logging
from typing import Any

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak_retry_connector import establish_connection

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
            connectable=True,
        )
        self._address = format_mac(address)
        self._client: BleakClient | None = None
        self._poll_lock = asyncio.Lock()
        self._shutdown_requested = False
        self._info_loaded = False
        self.data = RoomSensorData()

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
            connectable=True,
        )
        if service_info is None:
            self.logger.debug(
                "No cached Bluetooth service info available for %s",
                self._address,
            )
            return False

        self._last_service_info = service_info
        try:
            self.data = await self._do_poll(service_info)
        except Exception:
            self.last_poll_successful = False
            self.logger.exception(
                "%s: Initial RoomSensor GATT read failed",
                self._address,
            )
            return False

        self._available = True
        self.last_poll_successful = True
        self.async_update_listeners()
        return True

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
        service_info: bluetooth.BluetoothServiceInfoBleak,
    ) -> RoomSensorData:
        """Connect to the RoomSensor and refresh all values."""
        async with self._poll_lock:
            if self._shutdown_requested:
                return self.data

            if not self.connected:
                await self._connect(service_info)

            await self._read_measurements()
            if not self._info_loaded:
                await self._read_device_info()
                self._info_loaded = True
                self._update_device_registry()

            self.data = replace(self.data, rssi=service_info.rssi)
            return self.data

    async def _connect(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
    ) -> None:
        """Open a managed BLE connection and subscribe to updates."""
        client = await establish_connection(
            BleakClient,
            service_info.device,
            self._address,
            disconnected_callback=self._on_disconnect,
        )

        try:
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
            await client.disconnect()
            raise

        self._client = client

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

    async def async_shutdown(self) -> None:
        """Stop Bluetooth callbacks and close the connection."""
        self._shutdown_requested = True
        self._async_stop()

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
