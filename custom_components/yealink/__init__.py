"""Yealink Devices integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DEVICE_TYPE,
    CONF_USB_PATH,
    CONF_USB_SERIAL,
    DEVICE_TYPE_ROOM_SENSOR,
    DEVICE_TYPE_VCM36W,
)
from .coordinator import RoomSensorCoordinator
from .vcm36w import Vcm36wCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

type YealinkRuntime = RoomSensorCoordinator | Vcm36wCoordinator
type YealinkConfigEntry = ConfigEntry[YealinkRuntime]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YealinkConfigEntry,
) -> bool:
    """Set up a Yealink device from a config entry."""
    device_type = entry.data[CONF_DEVICE_TYPE]

    if device_type == DEVICE_TYPE_ROOM_SENSOR:
        coordinator = RoomSensorCoordinator(
            hass,
            _LOGGER,
            address=entry.data[CONF_ADDRESS],
        )
        entry.runtime_data = coordinator

        entry.async_on_unload(coordinator.async_start())
        await coordinator.async_initialize()

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True

    if device_type == DEVICE_TYPE_VCM36W:
        coordinator = Vcm36wCoordinator(
            hass,
            _LOGGER,
            serial_number=entry.data.get(CONF_USB_SERIAL),
            discovery_path=entry.data.get(CONF_USB_PATH),
        )
        entry.runtime_data = coordinator
        await coordinator.async_config_entry_first_refresh()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True

    _LOGGER.error("Unsupported Yealink device type: %s", device_type)
    return False


async def async_unload_entry(
    hass: HomeAssistant,
    entry: YealinkConfigEntry,
) -> bool:
    """Unload a Yealink config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and entry.data[CONF_DEVICE_TYPE] == DEVICE_TYPE_ROOM_SENSOR:
        coordinator = entry.runtime_data
        assert isinstance(coordinator, RoomSensorCoordinator)
        await coordinator.async_shutdown()
    return unload_ok
