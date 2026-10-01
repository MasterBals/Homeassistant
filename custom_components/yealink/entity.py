"""Base entities for Yealink devices."""

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
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import YealinkConfigEntry
from .const import DOMAIN
from .coordinator import RoomSensorCoordinator
from .vcm36w import Vcm36wCoordinator


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


class YealinkVcm36wEntity(CoordinatorEntity[Vcm36wCoordinator]):
    """Base entity for a Yealink VCM36-W."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: Vcm36wCoordinator,
        entry: YealinkConfigEntry,
        key: str,
    ) -> None:
        """Initialize the VCM36-W entity."""
        super().__init__(coordinator)
        device_key = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{device_key}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_key)},
            manufacturer="Yealink",
            model="VCM36-W",
            name=entry.title,
        )
