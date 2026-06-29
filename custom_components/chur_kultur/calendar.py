"""Calendar entity for Chur Kultur."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ChurKulturCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Chur Kultur calendar."""
    async_add_entities([ChurKulturCalendar(hass.data[DOMAIN][entry.entry_id], entry)])


class ChurKulturCalendar(CoordinatorEntity[ChurKulturCoordinator], CalendarEntity):
    """Calendar for filtered culture events."""

    _attr_name = "Chur Kultur Kalender"
    _attr_has_entity_name = True

    def __init__(self, coordinator: ChurKulturCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_calendar"

    @property
    def event(self) -> CalendarEvent | None:
        """Return next event."""
        events = self.coordinator.data or []
        if not events:
            return None
        event = events[0]
        return CalendarEvent(
            summary=event.title,
            start=event.date,
            end=event.date + timedelta(days=1),
            location=event.location,
            description=event.summary or event.description,
        )

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return events in date range."""
        return [
            CalendarEvent(
                summary=event.title,
                start=event.date,
                end=event.date + timedelta(days=1),
                location=event.location,
                description=f"{event.summary or event.description}\n\n{event.url}".strip(),
            )
            for event in self.coordinator.data or []
            if start_date.date() <= event.date <= end_date.date()
        ]
