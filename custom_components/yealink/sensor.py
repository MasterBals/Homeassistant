"""Sensor platform for Yealink devices."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import YealinkConfigEntry
from .entity import YealinkRoomSensorEntity
from .models import RoomSensorData


@dataclass(frozen=True, kw_only=True)
class YealinkSensorDescription(SensorEntityDescription):
    """Describe a Yealink sensor entity."""

    value_fn: Callable[[RoomSensorData], StateType]


SENSORS: tuple[YealinkSensorDescription, ...] = (
    YealinkSensorDescription(
        key="temperature",
        translation_key="temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: data.temperature,
    ),
    YealinkSensorDescription(
        key="humidity",
        translation_key="humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda data: data.humidity,
    ),
    YealinkSensorDescription(
        key="light_raw",
        translation_key="light_raw",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.light_raw,
    ),
    YealinkSensorDescription(
        key="battery",
        translation_key="battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.battery,
    ),
    YealinkSensorDescription(
        key="signal_strength",
        translation_key="signal_strength",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.rssi,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YealinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Yealink sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        YealinkRoomSensorSensor(coordinator, entry, description)
        for description in SENSORS
    )


class YealinkRoomSensorSensor(YealinkRoomSensorEntity, SensorEntity):
    """A RoomSensor measurement."""

    entity_description: YealinkSensorDescription

    def __init__(
        self,
        coordinator,
        entry: YealinkConfigEntry,
        description: YealinkSensorDescription,
    ) -> None:
        """Initialize a sensor."""
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        """Return the latest value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose raw GATT diagnostics for the provisional light value."""
        if self.entity_description.key != "light_raw":
            return None
        return {
            "raw_hex": self.coordinator.data.light_raw_hex,
            "gatt_characteristic": "0x2A77",
            "measurement": "Irradiance",
            "note": "Raw Yealink value; lux conversion is not yet confirmed",
        }
