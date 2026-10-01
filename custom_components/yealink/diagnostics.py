"""Diagnostics for the Yealink integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import YealinkConfigEntry
from .const import CONF_DEVICE_TYPE, DEVICE_TYPE_ROOM_SENSOR


TO_REDACT = {"address", "serial_number", "usb_serial", "usb_path"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: YealinkConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a Yealink config entry."""
    coordinator = entry.runtime_data

    if entry.data[CONF_DEVICE_TYPE] == DEVICE_TYPE_ROOM_SENSOR:
        status = {
            "connected": coordinator.connected,
            "available": coordinator.available,
            "last_poll_successful": coordinator.last_poll_successful,
        }
    else:
        status = {
            "connected": coordinator.data.connected,
            "available": coordinator.last_update_success,
            "last_update_success": coordinator.last_update_success,
        }

    return async_redact_data(
        {
            "entry": {
                "title": entry.title,
                "data": dict(entry.data),
            },
            **status,
            "data": asdict(coordinator.data),
        },
        TO_REDACT,
    )
