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

from .const import CONF_DEVICE_TYPE, DOMAIN
from .profiles import detect_device_type, is_supported


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

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Allow manual setup from currently discovered Yealink devices."""
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
        """Store selected discovery data."""
        self._discovery_info = info
        self._address = format_mac(info.address)
        self._device_type = detect_device_type(info)
        self._title = info.name or f"Yealink {self._address}"

    def _create_entry(self) -> ConfigFlowResult:
        """Create the config entry."""
        assert self._address is not None
        assert self._device_type is not None
        return self.async_create_entry(
            title=self._title,
            data={
                CONF_ADDRESS: self._address,
                CONF_DEVICE_TYPE: self._device_type,
            },
        )
