"""Diagnostics for IBC Chur."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_SENSITIVE_KEYS = {
    "access_token",
    "refresh_token",
    "id_token",
    "token",
    "authorization",
    "client_secret",
}


def _redact(value: Any, key: str | None = None) -> Any:
    """Recursively remove authentication material from diagnostics."""
    if key is not None and key.lower() in _SENSITIVE_KEYS:
        return "**REDACTED**"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return strictly redacted diagnostics."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    config = _redact(deepcopy({**entry.data, **entry.options}))
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
            "imported_samples": (
                coordinator.data.imported_samples if coordinator.data else 0
            ),
        },
    }
