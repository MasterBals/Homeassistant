"""ChatGPT Home Assistant Admin integration."""

from __future__ import annotations

from homeassistant.components import persistent_notification
from homeassistant.core import EVENT_HOMEASSISTANT_STOP, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, llm
from homeassistant.helpers.typing import ConfigType

from .api import ChatGPTHomeAssistantAdminAPI
from .const import API_ID, API_NAME, DOMAIN
from .settings import load_settings

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up ChatGPT Home Assistant Admin from YAML."""
    if DOMAIN in hass.data:
        return True

    api = ChatGPTHomeAssistantAdminAPI(
        hass=hass,
        id=API_ID,
        name=API_NAME,
        settings=load_settings(hass),
    )
    unregister = llm.async_register_api(hass, api)
    hass.data[DOMAIN] = {"api": api, "unregister": unregister}

    persistent_notification.async_create(
        hass,
        "ChatGPT Home Assistant Admin ist aktiv.\n\n"
        "MCP-Endpunkt: `/api/mcp/chatgpt_ha_admin`\n\n"
        "Der Endpunkt verwendet die Home-Assistant-Authentifizierung und verlangt einen Administrator:Innen-Zugang.",
        title="ChatGPT Home Assistant Admin",
        notification_id=DOMAIN,
    )

    @callback
    def _unregister(_event) -> None:
        unregister()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _unregister)
    return True
