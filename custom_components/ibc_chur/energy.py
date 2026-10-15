"""Energy dashboard integration helpers for IBC Chur."""

from __future__ import annotations

import logging

from homeassistant.components.energy import data as energy_data
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def async_ensure_energy_dashboard_source(
    hass: HomeAssistant,
    statistic_id: str,
    *,
    name: str = "IBC Stromnetz",
) -> str:
    """Add IBC grid import to the Energy dashboard when safe."""
    manager = await energy_data.async_get_manager(hass)
    preferences = manager.data or manager.default_preferences()
    sources = list(preferences.get("energy_sources", []))

    for source in sources:
        if (
            source.get("type") == "grid"
            and source.get("stat_energy_from") == statistic_id
        ):
            return "already_configured"

    existing_grids = [source for source in sources if source.get("type") == "grid"]
    if existing_grids:
        _LOGGER.warning(
            "IBC Energy statistic %s was not added automatically because the "
            "Energy dashboard already contains a grid source; this prevents "
            "accidental double counting",
            statistic_id,
        )
        return "skipped_existing_grid"

    grid_source = {
        "type": "grid",
        "stat_energy_from": statistic_id,
        "stat_energy_to": None,
        "stat_cost": None,
        "entity_energy_price": None,
        "number_energy_price": None,
        "stat_compensation": None,
        "entity_energy_price_export": None,
        "number_energy_price_export": None,
        "cost_adjustment_day": 0.0,
        "name": name,
    }
    await manager.async_update({"energy_sources": [*sources, grid_source]})
    _LOGGER.info("Added %s to the Home Assistant Energy dashboard", statistic_id)
    return "added"
