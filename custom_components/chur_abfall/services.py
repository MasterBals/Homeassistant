"""Services for Chur Abfall."""

from __future__ import annotations

import logging
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from .const import DOMAIN, SERVICE_EXPORT, SERVICE_REFRESH, SERVICE_RELOAD

_LOGGER = logging.getLogger(__name__)


async def _coordinators(hass: HomeAssistant):
    return list(hass.data.get(DOMAIN, {}).values())


def async_setup_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        return

    async def refresh(call: ServiceCall) -> None:
        for coordinator in await _coordinators(hass):
            await coordinator.async_request_refresh()

    async def reload(call: ServiceCall) -> None:
        (
            await hass.config_entries.async_reload(call.data["entry_id"])
            if call.data.get("entry_id")
            else [
                await hass.config_entries.async_reload(entry.entry_id)
                for entry in hass.config_entries.async_entries(DOMAIN)
            ]
        )

    async def export(call: ServiceCall) -> dict[str, object]:
        data = {
            entry_id: coordinator.export()
            for entry_id, coordinator in hass.data.get(DOMAIN, {}).items()
        }
        _LOGGER.info("Chur Abfall export requested: %s entries", len(data))
        return data

    hass.services.async_register(DOMAIN, SERVICE_REFRESH, refresh)
    hass.services.async_register(DOMAIN, SERVICE_RELOAD, reload)
    hass.services.async_register(
        DOMAIN, SERVICE_EXPORT, export, supports_response=SupportsResponse.ONLY
    )


def async_unload_services(hass: HomeAssistant) -> None:
    for service in (SERVICE_REFRESH, SERVICE_RELOAD, SERVICE_EXPORT):
        hass.services.async_remove(DOMAIN, service)
