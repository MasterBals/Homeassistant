"""Chur Abfall custom integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import ChurWasteCoordinator
from .services import async_setup_services, async_unload_services

PLATFORMS = [Platform.SENSOR, Platform.CALENDAR]
FRONTEND_PATH = Path(__file__).parent / "frontend"
FRONTEND_URL = "/chur_abfall_static"
CARD_URL = f"{FRONTEND_URL}/chur-abfall-card.js?v=1.0.5"
DATA_FRONTEND_REGISTERED = "frontend_registered"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Chur Abfall from a config entry."""
    data = hass.data.setdefault(DOMAIN, {})
    if not data.get(DATA_FRONTEND_REGISTERED):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_URL, str(FRONTEND_PATH), True)]
        )
        frontend.add_extra_js_url(hass, CARD_URL)
        data[DATA_FRONTEND_REGISTERED] = True

    coordinator = ChurWasteCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    data[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_setup_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN]
        data.pop(entry.entry_id, None)
        if not any(key != DATA_FRONTEND_REGISTERED for key in data):
            frontend.remove_extra_js_url(hass, CARD_URL)
            data.pop(DATA_FRONTEND_REGISTERED, None)
            async_unload_services(hass)
    return unload_ok
