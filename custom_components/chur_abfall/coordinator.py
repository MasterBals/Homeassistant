"""Data update coordinator for Chur Abfall."""

from __future__ import annotations

from dataclasses import asdict
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ChurWasteApi, ChurWasteApiError
from .const import CONF_STREETS, DOMAIN, UPDATE_INTERVAL
from .parser import Street, WasteEvent

_LOGGER = logging.getLogger(__name__)


class ChurWasteCoordinator(DataUpdateCoordinator[list[WasteEvent]]):
    """Fetch and cache Chur waste events."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            config_entry=entry,
        )
        self.api = ChurWasteApi(hass)
        self.streets = [Street(**item) for item in entry.data[CONF_STREETS]]

    async def _async_update_data(self) -> list[WasteEvent]:
        try:
            return await self.api.async_get_events(self.streets)
        except ChurWasteApiError as err:
            raise UpdateFailed(str(err)) from err

    def export(self) -> list[dict[str, str]]:
        """Return serialisable event export."""
        return [
            {**asdict(event), "date": event.date.isoformat()}
            for event in self.data or []
        ]
