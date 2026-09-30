"""Yealink Devices integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_DEVICE_TYPE, DEVICE_TYPE_ROOM_SENSOR
from .coordinator import RoomSensorCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

type YealinkConfigEntry = ConfigEntry[RoomSensorCoordinator]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YealinkConfigEntry,
) -> bool:
    """Set up a Yealink device from a config entry."""
    device_type = entry.data[CONF_DEVICE_TYPE]
    if device_type != DEVICE_TYPE_ROOM_SENSOR:
        _LOGGER.error("Unsupported Yealink device type: %s", device_type)
        return False

    coordinator = RoomSensorCoordinator(
        hass,
        _LOGGER,
        address=entry.data[CONF_ADDRESS],
    )
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register Bluetooth callbacks after entities are ready. Cached advertisements
    # are replayed, so a nearby RoomSensor normally connects immediately.
    entry.async_on_unload(coordinator.async_start())

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: YealinkConfigEntry,
) -> bool:
    """Unload a Yealink config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok
