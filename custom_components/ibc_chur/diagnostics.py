"""Diagnostics for IBC Chur."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ACCESS_TOKEN, DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return redacted diagnostics."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    config = {**entry.data, **entry.options}
    if CONF_ACCESS_TOKEN in config:
        config[CONF_ACCESS_TOKEN] = "**REDACTED**"
    return {
        "config": config,
        "statistic_id": coordinator.statistic_id,
        "last_update_success": coordinator.last_update_success,
        "data": {
            "latest_power_kw": coordinator.data.latest_power_kw if coordinator.data else None,
            "latest_timestamp": (
                coordinator.data.latest_timestamp.isoformat()
                if coordinator.data and coordinator.data.latest_timestamp
                else None
            ),
            "yesterday_energy_kwh": (
                coordinator.data.yesterday_energy_kwh if coordinator.data else None
            ),
            "last_imported_day": (
                coordinator.data.last_imported_day.isoformat()
                if coordinator.data and coordinator.data.last_imported_day
                else None
            ),
        },
    }
