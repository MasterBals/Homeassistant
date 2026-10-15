"""IBC Energie Wasser Chur integration."""

from __future__ import annotations

from homeassistant.components.application_credentials import (
    ClientCredential,
    async_import_client_credential,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import IBCClient
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
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    PLATFORMS,
)
from .coordinator import IBCDataUpdateCoordinator


type IBCConfigEntry = ConfigEntry[IBCDataUpdateCoordinator]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register IBC's public OAuth client used by the customer portal."""
    await async_import_client_credential(
        hass,
        DOMAIN,
        ClientCredential(OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: IBCConfigEntry) -> bool:
    """Set up IBC Chur from a config entry."""
    config = {**entry.data, **entry.options}

    oauth_session = None
    legacy_access_token = config.get("access_token")
    if "token" in entry.data:
        implementation = (
            await config_entry_oauth2_flow.async_get_config_entry_implementation(
                hass, entry
            )
        )
        oauth_session = config_entry_oauth2_flow.OAuth2Session(
            hass, entry, implementation
        )
        await oauth_session.async_ensure_token_valid()

    client = IBCClient(
        async_get_clientsession(hass),
        oauth_session=oauth_session,
        access_token=legacy_access_token,
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
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IBCConfigEntry) -> bool:
    """Unload an IBC config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: IBCConfigEntry) -> None:
    """Reload IBC after option changes."""
    await hass.config_entries.async_reload(entry.entry_id)
