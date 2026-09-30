"""Yealink device profile detection."""

from __future__ import annotations

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from ..const import (
    DEVICE_TYPE_ROOM_SENSOR,
    ROOM_SENSOR_NAME_PREFIX,
    YEALINK_MANUFACTURER_ID,
)


def detect_device_type(service_info: BluetoothServiceInfoBleak) -> str | None:
    """Return the supported Yealink device type for a Bluetooth advertisement."""
    name = service_info.name or ""
    if (
        name.startswith(ROOM_SENSOR_NAME_PREFIX)
        and YEALINK_MANUFACTURER_ID in service_info.manufacturer_data
    ):
        return DEVICE_TYPE_ROOM_SENSOR
    return None


def is_supported(service_info: BluetoothServiceInfoBleak) -> bool:
    """Return whether a discovered device is supported."""
    return detect_device_type(service_info) is not None
