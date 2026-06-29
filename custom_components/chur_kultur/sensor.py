"""Sensors for Chur Kultur."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ChurKulturCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Chur Kultur sensors."""
    async_add_entities(
        [ChurKulturEventsSensor(hass.data[DOMAIN][entry.entry_id], entry)]
    )


class ChurKulturEventsSensor(CoordinatorEntity[ChurKulturCoordinator], SensorEntity):
    """Expose filtered Chur Kultur events."""

    _attr_name = "Chur Kultur Veranstaltungen"
    _attr_has_entity_name = True
    _attr_icon = "mdi:calendar-star"

    def __init__(self, coordinator: ChurKulturCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_events"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Chur Kultur",
        }

    @property
    def native_value(self) -> int:
        """Return number of events."""
        return len(self.coordinator.data or [])

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return event attributes."""
        events = [event.as_dict() for event in self.coordinator.data or []]
        return {
            "events": events,
            "days": self.coordinator.days,
            "max_events": self.coordinator.max_events,
            "tag_ids": self.coordinator.tag_ids,
            "search": self.coordinator.search,
        }
