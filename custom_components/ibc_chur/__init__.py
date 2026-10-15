"""IBC Energie Wasser Chur integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .api import IBCClient
from .auth import IBCAuthConnectionError, IBCInvalidAuth, IBCTokenManager
from .const import (
    CONF_AGGREGATION,
    CONF_HISTORY_DAYS,
    CONF_METERINGPOINT,
    CONF_ROLE,
    CONF_SUBJECT_ID,
    DEFAULT_AGGREGATION,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_ROLE,
    DOMAIN,
    PLATFORMS,
    TOKEN_KEEPALIVE_INTERVAL,
)
from .coordinator import IBCDataUpdateCoordinator
from .energy import async_ensure_energy_dashboard_source

_LOGGER = logging.getLogger(__name__)

type IBCConfigEntry = ConfigEntry[IBCDataUpdateCoordinator]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the IBC integration."""
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate older IBC entries to the native token-manager format."""
    if entry.version < 4:
        hass.config_entries.async_update_entry(entry, version=4)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: IBCConfigEntry) -> bool:
    """Set up IBC Chur from a config entry."""
    config = {**entry.data, **entry.options}
    session = async_get_clientsession(hass)

    token_manager = None
    token = entry.data.get("token")
    if isinstance(token, dict) and token.get("access_token"):
        token_manager = IBCTokenManager(hass, entry, session)

    client = IBCClient(
        session,
        token_manager=token_manager,
        access_token=config.get("access_token"),
        subject_id=config[CONF_SUBJECT_ID],
        meteringpoint=config[CONF_METERINGPOINT],
        role=config.get(CONF_ROLE, DEFAULT_ROLE),
        aggregation=config.get(CONF_AGGREGATION, DEFAULT_AGGREGATION),
    )
    coordinator = IBCDataUpdateCoordinator(
        hass,
        entry,
        client,
        history_days=config.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    if token_manager is not None:

        async def _async_keep_token_alive(_now) -> None:
            try:
                await token_manager.async_force_refresh()
            except IBCInvalidAuth:
                _LOGGER.warning("IBC refresh session expired; reauthentication required")
                entry.async_start_reauth(hass)
            except IBCAuthConnectionError as err:
                _LOGGER.debug("IBC token keepalive failed temporarily: %s", err)

        entry.async_on_unload(
            async_track_time_interval(
                hass,
                _async_keep_token_alive,
                TOKEN_KEEPALIVE_INTERVAL,
            )
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    try:
        status = await async_ensure_energy_dashboard_source(
            hass,
            coordinator.statistic_id,
            name="IBC Stromnetz",
        )
        _LOGGER.debug("IBC Energy dashboard configuration status: %s", status)
    except Exception:
        _LOGGER.exception("Could not configure IBC as an Energy dashboard source")

    return True


async def async_unload_entry(hass: HomeAssistant, entry: IBCConfigEntry) -> bool:
    """Unload an IBC config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: IBCConfigEntry) -> None:
    """Reload IBC after option changes."""
    await hass.config_entries.async_reload(entry.entry_id)
