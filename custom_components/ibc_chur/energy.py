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
    cost_statistic_id: str | None = None,
    name: str = "IBC Stromnetz",
) -> str:
    """Add or migrate the IBC grid import in the Energy dashboard.

    The delayed IBC readings are external statistics so their original hourly
    timestamps remain intact. Existing non-IBC grid sources are never replaced.
    Earlier development statistics created by this same integration are migrated
    to the current corrected statistic IDs automatically.
    """
    manager = await energy_data.async_get_manager(hass)
    preferences = manager.data or manager.default_preferences()
    sources = list(preferences.get("energy_sources", []))

    changed = False
    for index, source in enumerate(sources):
        if source.get("type") != "grid":
            continue
        current = source.get("stat_energy_from")
        if current == statistic_id:
            desired_cost = cost_statistic_id
            if source.get("stat_cost") != desired_cost:
                updated = dict(source)
                updated["stat_cost"] = desired_cost
                updated["entity_energy_price"] = None
                updated["number_energy_price"] = None
                sources[index] = updated
                changed = True
            if changed:
                await manager.async_update({"energy_sources": sources})
                return "updated_cost"
            return "already_configured"

        if isinstance(current, str) and current.startswith(
            "ibc_chur:energy_consumption"
        ):
            updated = dict(source)
            updated["stat_energy_from"] = statistic_id
            updated["stat_cost"] = cost_statistic_id
            updated["entity_energy_price"] = None
            updated["number_energy_price"] = None
            updated["name"] = name
            sources[index] = updated
            await manager.async_update({"energy_sources": sources})
            _LOGGER.info(
                "Migrated Energy dashboard from %s to %s", current, statistic_id
            )
            return "migrated"

    existing_grids = [source for source in sources if source.get("type") == "grid"]
    if existing_grids:
        _LOGGER.warning(
            "IBC Energy statistic %s was not added automatically because the "
            "Energy dashboard already contains a non-IBC grid source; this "
            "prevents accidental double counting",
            statistic_id,
        )
        return "skipped_existing_grid"

    grid_source = {
        "type": "grid",
        "stat_energy_from": statistic_id,
        "stat_energy_to": None,
        "stat_cost": cost_statistic_id,
        "entity_energy_price": None,
        "number_energy_price": None,
        "stat_compensation": None,
        "entity_energy_price_export": None,
        "number_energy_price_export": None,
        "cost_adjustment_day": 0.0,
        "name": name,
    }
    await manager.async_update({"energy_sources": [*sources, grid_source]})
    _LOGGER.info(
        "Added %s with cost statistic %s to the Energy dashboard",
        statistic_id,
        cost_statistic_id,
    )
    return "added"
