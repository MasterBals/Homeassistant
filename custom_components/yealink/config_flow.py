"""Config flow for Yealink devices."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.usb import UsbServiceInfo

from .const import (
    CONF_DEVICE_TYPE,
    CONF_USB_PATH,
    CONF_USB_SERIAL,
    DEVICE_TYPE_VCM36W,
    DOMAIN,
    VCM36W_USB_PID,
    VCM36W_USB_VID,
)
from .profiles import detect_device_type, is_supported
from .vcm36w import find_vcm36w_usb_service_info


def _normalize_usb_id(value: str | int | None) -> str:
    """Normalize a USB VID/PID to four uppercase hex characters."""
    if value is None:
        return ""
    if isinstance(value, int):
        return f"{value:04X}"
    text = str(value).upper().removeprefix("0X")
    return text.zfill(4)


class YealinkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Yealink devices."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._address: str | None = None
        self._device_type: str | None = None
        self._title = "Yealink"

        self._usb_info: UsbServiceInfo | None = None
        self._usb_unique_id: str | None = None

    async def async_step_bluetooth(
        self,
        discovery_info: BluetoothServiceInfoBleak,
    ) -> ConfigFlowResult:
        """Handle automatic Bluetooth discovery."""
        device_type = detect_device_type(discovery_info)
        if device_type is None:
            return self.async_abort(reason="unsupported_device")

        await self.async_set_unique_id(format_mac(discovery_info.address))
        self._abort_if_unique_id_configured()

        self._set_device(discovery_info)
        self.context["title_placeholders"] = {
            "name": self._title,
            "address": discovery_info.address,
        }
        return self._create_entry()

    async def async_step_bluetooth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Confirm a discovered Yealink device."""
        if user_input is not None:
            return self._create_entry()

        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": self._title,
                "address": self._address or "",
            },
        )

    async def async_step_usb(
        self,
        discovery_info: UsbServiceInfo,
    ) -> ConfigFlowResult:
        """Handle automatic USB discovery for VCM36-W."""
        vid = _normalize_usb_id(discovery_info.vid)
        pid = _normalize_usb_id(discovery_info.pid)
        if vid != VCM36W_USB_VID or pid not in {VCM36W_USB_PID, "B068"}:
            return self.async_abort(reason="unsupported_device")

        serial = (discovery_info.serial_number or "").strip()
        fallback = f"{vid}:{pid}:{discovery_info.device}"
        unique_id = f"vcm36w:{serial or fallback}"

        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        self._usb_info = discovery_info
        self._usb_unique_id = unique_id
        self._device_type = DEVICE_TYPE_VCM36W
        self._title = discovery_info.description or "Yealink VCM36-W"

        self.context["title_placeholders"] = {
            "name": self._title,
            "serial": serial or "—",
        }

        # HID-only VCM36-W devices are discovered by the Yealink integration
        # itself because Home Assistant's generic USB discovery scans serial
        # TTY devices only. A physically attached, uniquely identified VCM36-W
        # can therefore be created immediately without an extra confirmation
        # step.
        return self.async_create_entry(
            title=self._title,
            data={
                CONF_DEVICE_TYPE: DEVICE_TYPE_VCM36W,
                CONF_USB_PATH: discovery_info.device,
                CONF_USB_SERIAL: serial,
            },
        )

    async def async_step_usb_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Confirm a discovered VCM36-W."""
        if self._usb_info is None:
            return self.async_abort(reason="unsupported_device")

        if user_input is not None:
            serial = (self._usb_info.serial_number or "").strip()
            return self.async_create_entry(
                title=self._title,
                data={
                    CONF_DEVICE_TYPE: DEVICE_TYPE_VCM36W,
                    CONF_USB_PATH: self._usb_info.device,
                    CONF_USB_SERIAL: serial,
                },
            )

        return self.async_show_form(
            step_id="usb_confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": self._title,
                "serial": (self._usb_info.serial_number or "").strip() or "—",
            },
        )

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Allow manual setup from Bluetooth devices or an attached VCM36-W."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            info = self._discovered_devices[address]
            await self.async_set_unique_id(format_mac(address), raise_on_progress=False)
            self._abort_if_unique_id_configured()
            self._set_device(info)
            return self._create_entry()

        configured = self._async_current_ids()
        for info in async_discovered_service_info(self.hass):
            formatted = format_mac(info.address)
            if formatted in configured or not is_supported(info):
                continue
            self._discovered_devices[info.address] = info

        if not self._discovered_devices:
            usb_info = await self.hass.async_add_executor_job(
                find_vcm36w_usb_service_info
            )
            if usb_info is not None:
                return await self.async_step_usb(usb_info)
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            address: f"{info.name or 'Yealink'} ({address})"
                            for address, info in self._discovered_devices.items()
                        }
                    )
                }
            ),
        )

    def _set_device(self, info: BluetoothServiceInfoBleak) -> None:
        """Store selected Bluetooth discovery data."""
        self._discovery_info = info
        self._address = format_mac(info.address)
        self._device_type = detect_device_type(info)
        self._title = info.name or f"Yealink {self._address}"

    def _create_entry(self) -> ConfigFlowResult:
        """Create a Bluetooth config entry."""
        assert self._address is not None
        assert self._device_type is not None
        return self.async_create_entry(
            title=self._title,
            data={
                CONF_ADDRESS: self._address,
                CONF_DEVICE_TYPE: self._device_type,
            },
        )
