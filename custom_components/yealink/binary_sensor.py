"""Binary sensor platform for Yealink devices."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import YealinkConfigEntry
from .const import CONF_DEVICE_TYPE, DEVICE_TYPE_ROOM_SENSOR, DEVICE_TYPE_VCM36W
from .coordinator import RoomSensorCoordinator
from .entity import YealinkRoomSensorEntity, YealinkVcm36wEntity
from .vcm36w import Vcm36wCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: YealinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Yealink binary sensors."""
    coordinator = entry.runtime_data
    device_type = entry.data[CONF_DEVICE_TYPE]

    if device_type == DEVICE_TYPE_ROOM_SENSOR:
        assert isinstance(coordinator, RoomSensorCoordinator)
        async_add_entities(
            [
                YealinkOccupancySensor(coordinator, entry),
                YealinkConnectionSensor(coordinator, entry),
            ]
        )
        return

    if device_type == DEVICE_TYPE_VCM36W:
        assert isinstance(coordinator, Vcm36wCoordinator)
        async_add_entities(
            [
                YealinkVcmUsbConnectionSensor(coordinator, entry),
                YealinkVcmHidInterfaceSensor(coordinator, entry),
                YealinkVcmAudioInterfaceSensor(coordinator, entry),
            ]
        )


class YealinkOccupancySensor(YealinkRoomSensorEntity, BinarySensorEntity):
    """Room occupancy reported by the Yealink PIR sensor."""

    _attr_translation_key = "occupancy"
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, coordinator, entry: YealinkConfigEntry) -> None:
        super().__init__(coordinator, entry, "occupancy")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.occupancy


class YealinkConnectionSensor(YealinkRoomSensorEntity, BinarySensorEntity):
    """Diagnostic BLE connection state."""

    _attr_translation_key = "connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, entry: YealinkConfigEntry) -> None:
        super().__init__(coordinator, entry, "connection")

    @property
    def is_on(self) -> bool:
        return self.coordinator.connected

    @property
    def available(self) -> bool:
        return True


class YealinkVcmUsbConnectionSensor(YealinkVcm36wEntity, BinarySensorEntity):
    """Whether the VCM36-W is attached over USB."""

    _attr_translation_key = "usb_connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, entry: YealinkConfigEntry) -> None:
        super().__init__(coordinator, entry, "usb_connection")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.connected

    @property
    def available(self) -> bool:
        return True


class YealinkVcmHidInterfaceSensor(YealinkVcm36wEntity, BinarySensorEntity):
    """Whether the VCM exposes the proprietary HID management interface."""

    _attr_translation_key = "hid_interface"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, entry: YealinkConfigEntry) -> None:
        super().__init__(coordinator, entry, "hid_interface")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.has_hid_interface


class YealinkVcmAudioInterfaceSensor(YealinkVcm36wEntity, BinarySensorEntity):
    """Whether the VCM exposes a standards-based USB Audio interface."""

    _attr_translation_key = "usb_audio_interface"

    def __init__(self, coordinator, entry: YealinkConfigEntry) -> None:
        super().__init__(coordinator, entry, "usb_audio_interface")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.has_audio_interface
