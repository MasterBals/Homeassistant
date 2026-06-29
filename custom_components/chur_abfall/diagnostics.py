"""Diagnostics for Chur Abfall."""

from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import CONF_STREETS, DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, object]:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "entry": {
            "title": entry.title,
            "streets": [
                {"id": "***", "name": "***"} for _ in entry.data.get(CONF_STREETS, [])
            ],
        },
        "event_count": len(coordinator.data or []),
        "last_update_success": coordinator.last_update_success,
    }
