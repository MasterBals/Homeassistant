"""Calendar entity for Chur Abfall."""

from __future__ import annotations

from datetime import datetime
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ChurWasteCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([ChurWasteCalendar(hass.data[DOMAIN][entry.entry_id], entry)])


class ChurWasteCalendar(CoordinatorEntity[ChurWasteCoordinator], CalendarEntity):
    _attr_name = "Chur Abfall Kalender"
    _attr_has_entity_name = True

    def __init__(self, coordinator: ChurWasteCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_calendar"

    @property
    def event(self) -> CalendarEvent | None:
        events = self.coordinator.data or []
        if not events:
            return None
        event = events[0]
        return CalendarEvent(
            summary=f"{event.waste_type}: {event.street}",
            start=event.date,
            end=event.date,
        )

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [
            CalendarEvent(
                summary=f"{event.waste_type}: {event.street}",
                start=event.date,
                end=event.date,
                description=f"Street-ID: {event.street_id}",
            )
            for event in self.coordinator.data or []
            if start_date.date() <= event.date <= end_date.date()
        ]
