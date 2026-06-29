"""Sensors for Chur Abfall."""

from __future__ import annotations

from datetime import date
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_WASTE_TYPES, DOMAIN
from .coordinator import ChurWasteCoordinator
from .parser import WasteEvent


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: ChurWasteCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        NextCollectionSensor(coordinator, entry, None),
        DaysUntilSensor(coordinator, entry),
    ]
    entities.extend(
        NextCollectionSensor(coordinator, entry, waste) for waste in DEFAULT_WASTE_TYPES
    )
    async_add_entities(entities)


class BaseChurSensor(CoordinatorEntity[ChurWasteCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: ChurWasteCoordinator, entry: ConfigEntry, key: str
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Chur Abfall",
        }

    def _events(self, waste_type: str | None = None) -> list[WasteEvent]:
        events = self.coordinator.data or []
        if waste_type:
            events = [
                event
                for event in events
                if event.waste_type.casefold() == waste_type.casefold()
            ]
        return events

    def _attrs_for(self, event: WasteEvent | None) -> dict[str, object]:
        events = self._events(event.waste_type if event else None)[:10]
        attrs: dict[str, object] = {
            "next_events": [
                {
                    "date": e.date.isoformat(),
                    "waste_type": e.waste_type,
                    "street": e.street,
                    "street_id": e.street_id,
                    "days": (e.date - date.today()).days,
                }
                for e in events
            ]
        }
        if event:
            days = (event.date - date.today()).days
            attrs.update(
                {
                    "date": event.date.isoformat(),
                    "swiss_date": event.date.strftime("%d.%m.%Y"),
                    "weekday": event.date.strftime("%A"),
                    "days": days,
                    "street": event.street,
                    "street_id": event.street_id,
                }
            )
        return attrs


class NextCollectionSensor(BaseChurSensor):
    def __init__(
        self,
        coordinator: ChurWasteCoordinator,
        entry: ConfigEntry,
        waste_type: str | None,
    ) -> None:
        key = (waste_type or "next_collection").lower().replace(" ", "_")
        super().__init__(coordinator, entry, key)
        self._waste_type = waste_type
        self._attr_name = (
            f"Nächste {waste_type}abfuhr" if waste_type else "Nächste Abfuhr"
        )
        self._attr_icon = "mdi:trash-can-outline" if not waste_type else "mdi:recycle"

    @property
    def native_value(self) -> str | None:
        events = self._events(self._waste_type)
        return events[0].date.isoformat() if events else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        events = self._events(self._waste_type)
        return self._attrs_for(events[0] if events else None)


class DaysUntilSensor(BaseChurSensor):
    _attr_name = "Tage bis nächste Abfuhr"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: ChurWasteCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "days_until_next")

    @property
    def native_value(self) -> int | None:
        events = self._events()
        return (events[0].date - date.today()).days if events else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        events = self._events()
        return self._attrs_for(events[0] if events else None)
