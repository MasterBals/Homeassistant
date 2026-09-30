"""Diagnostics for the Yealink integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import YealinkConfigEntry

TO_REDACT = {"address", "serial_number"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: YealinkConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a Yealink config entry."""
    coordinator = entry.runtime_data
    return async_redact_data(
        {
            "entry": {
                "title": entry.title,
                "data": dict(entry.data),
            },
            "connected": coordinator.connected,
            "available": coordinator.available,
            "last_poll_successful": coordinator.last_poll_successful,
            "data": asdict(coordinator.data),
        },
        TO_REDACT,
    )
