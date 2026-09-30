"""Binary sensor platform for Yealink devices."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import YealinkConfigEntry
from .entity import YealinkRoomSensorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YealinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Yealink binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            YealinkOccupancySensor(coordinator, entry),
            YealinkConnectionSensor(coordinator, entry),
        ]
    )


class YealinkOccupancySensor(YealinkRoomSensorEntity, BinarySensorEntity):
    """Room occupancy reported by the Yealink PIR sensor."""

    _attr_translation_key = "occupancy"
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, coordinator, entry: YealinkConfigEntry) -> None:
        """Initialize occupancy."""
        super().__init__(coordinator, entry, "occupancy")

    @property
    def is_on(self) -> bool | None:
        """Return occupancy state."""
        return self.coordinator.data.occupancy


class YealinkConnectionSensor(YealinkRoomSensorEntity, BinarySensorEntity):
    """Diagnostic BLE connection state."""

    _attr_translation_key = "connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, entry: YealinkConfigEntry) -> None:
        """Initialize connectivity."""
        super().__init__(coordinator, entry, "connection")

    @property
    def is_on(self) -> bool:
        """Return connection state."""
        return self.coordinator.connected

    @property
    def available(self) -> bool:
        """Keep diagnostic connection state available."""
        return True
