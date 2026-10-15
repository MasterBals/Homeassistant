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
    "password",
    "username",
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
    data = coordinator.data
    config = _redact(deepcopy({**entry.data, **entry.options}))
    return {
        "config": config,
        "statistic_id": coordinator.statistic_id,
        "last_update_success": coordinator.last_update_success,
        "data": {
            "latest_power_kw": data.latest_power_kw if data else None,
            "latest_timestamp": data.latest_timestamp.isoformat() if data and data.latest_timestamp else None,
            "latest_day": data.latest_day.isoformat() if data and data.latest_day else None,
            "latest_day_energy_kwh": data.latest_day_energy_kwh if data else None,
            "yesterday_energy_kwh": data.yesterday_energy_kwh if data else None,
            "last_7_days_energy_kwh": data.last_7_days_energy_kwh if data else None,
            "month_energy_kwh": data.month_energy_kwh if data else None,
            "data_age_hours": data.data_age_hours if data else None,
            "tracked_energy_kwh": data.tracked_energy_kwh if data else None,
            "last_imported_day": data.last_imported_day.isoformat() if data and data.last_imported_day else None,
            "imported_samples": data.imported_samples if data else 0,
        },
    }
