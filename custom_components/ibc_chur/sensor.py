"""Sensor platform for IBC Chur."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IBCData, IBCDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class IBCSensorEntityDescription(SensorEntityDescription):
    """Describe an IBC sensor."""

    value_fn: Callable[[IBCData], Any]


SENSORS: tuple[IBCSensorEntityDescription, ...] = (
    IBCSensorEntityDescription(
        key="latest_power",
        translation_key="latest_power",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=lambda data: data.latest_power_kw,
    ),
    IBCSensorEntityDescription(
        key="yesterday_energy",
        translation_key="yesterday_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        suggested_display_precision=3,
        value_fn=lambda data: data.yesterday_energy_kwh,
    ),
    IBCSensorEntityDescription(
        key="last_measurement",
        translation_key="last_measurement",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.latest_timestamp,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IBCDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(IBCSensor(coordinator, entry, description) for description in SENSORS)


class IBCSensor(CoordinatorEntity[IBCDataUpdateCoordinator], SensorEntity):
    """Representation of one IBC sensor."""

    entity_description: IBCSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: IBCDataUpdateCoordinator,
        entry: ConfigEntry,
        description: IBCSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.api.meteringpoint}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.api.meteringpoint)},
            name="IBC Smart Meter",
            manufacturer="IBC Energie Wasser Chur",
            model="Kundenportal Lastgang",
            configuration_url="https://portal.ibc-chur.ch/ebp/consumption/meterdata",
        )

    @property
    def native_value(self) -> float | datetime | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key != "yesterday_energy" or self.coordinator.data is None:
            return None
        return {
            "statistic_id": self.coordinator.data.statistic_id,
            "imported_samples_last_refresh": self.coordinator.data.imported_samples,
            "last_imported_day": (
                self.coordinator.data.last_imported_day.isoformat()
                if self.coordinator.data.last_imported_day
                else None
            ),
        }
