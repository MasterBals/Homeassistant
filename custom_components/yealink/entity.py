"""Base entity for Yealink devices."""

from __future__ import annotations

from homeassistant.components.bluetooth.passive_update_coordinator import (
    PassiveBluetoothCoordinatorEntity,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers.device_registry import (
    CONNECTION_BLUETOOTH,
    DeviceInfo,
    format_mac,
)

from . import YealinkConfigEntry
from .coordinator import RoomSensorCoordinator


class YealinkRoomSensorEntity(
    PassiveBluetoothCoordinatorEntity[RoomSensorCoordinator]
):
    """Base entity for a Yealink RoomSensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RoomSensorCoordinator,
        entry: YealinkConfigEntry,
        key: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        address = format_mac(entry.data[CONF_ADDRESS])
        self._attr_unique_id = f"{address}_{key}"
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, address)},
            manufacturer="Yealink",
            model="RoomSensor",
            name=entry.title,
        )
