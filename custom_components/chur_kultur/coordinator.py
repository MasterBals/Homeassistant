"""Data update coordinator for Chur Kultur."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ChurKulturApi, ChurKulturApiError
from .const import (
    CONF_DAYS,
    CONF_MAX_EVENTS,
    CONF_SEARCH,
    CONF_TAG_IDS,
    DEFAULT_DAYS,
    DEFAULT_MAX_EVENTS,
    DEFAULT_TAG_IDS,
    DOMAIN,
    UPDATE_INTERVAL,
)
from .parser import CultureEvent

_LOGGER = logging.getLogger(__name__)


class ChurKulturCoordinator(DataUpdateCoordinator[list[CultureEvent]]):
    """Fetch and cache Chur Kultur events."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            config_entry=entry,
        )
        self.api = ChurKulturApi(hass)
        self.entry = entry

    @property
    def days(self) -> int:
        """Return configured future window."""
        return int(
            self.entry.options.get(
                CONF_DAYS, self.entry.data.get(CONF_DAYS, DEFAULT_DAYS)
            )
        )

    @property
    def max_events(self) -> int:
        """Return configured event limit."""
        return int(
            self.entry.options.get(
                CONF_MAX_EVENTS,
                self.entry.data.get(CONF_MAX_EVENTS, DEFAULT_MAX_EVENTS),
            )
        )

    @property
    def tag_ids(self) -> list[str]:
        """Return configured tag ids."""
        return list(
            self.entry.options.get(
                CONF_TAG_IDS, self.entry.data.get(CONF_TAG_IDS, DEFAULT_TAG_IDS)
            )
        )

    @property
    def search(self) -> str:
        """Return configured free text search."""
        return str(
            self.entry.options.get(CONF_SEARCH, self.entry.data.get(CONF_SEARCH, ""))
        )

    async def _async_update_data(self) -> list[CultureEvent]:
        try:
            return await self.api.async_get_events(
                days=self.days,
                tag_ids=self.tag_ids,
                max_events=self.max_events,
                search=self.search,
            )
        except ChurKulturApiError as err:
            raise UpdateFailed(str(err)) from err

    def export(self) -> list[dict[str, str]]:
        """Return serialisable event export."""
        return [event.as_dict() for event in self.data or []]
