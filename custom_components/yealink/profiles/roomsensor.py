"""Yealink RoomSensor Bluetooth profile."""

from __future__ import annotations

from dataclasses import replace

from ..models import RoomSensorData

UUID_TEMPERATURE = "00002a6e-0000-1000-8000-00805f9b34fb"
UUID_HUMIDITY = "00002a6f-0000-1000-8000-00805f9b34fb"
UUID_IRRADIANCE = "00002a77-0000-1000-8000-00805f9b34fb"
UUID_BATTERY = "00002a19-0000-1000-8000-00805f9b34fb"
UUID_OCCUPANCY = "00002a58-0000-1000-8000-00805f9b34fb"

UUID_MANUFACTURER = "00002a29-0000-1000-8000-00805f9b34fb"
UUID_MODEL = "00002a24-0000-1000-8000-00805f9b34fb"
UUID_SERIAL = "00002a25-0000-1000-8000-00805f9b34fb"
UUID_FIRMWARE = "00002a26-0000-1000-8000-00805f9b34fb"
UUID_HARDWARE = "00002a27-0000-1000-8000-00805f9b34fb"
UUID_SOFTWARE = "00002a28-0000-1000-8000-00805f9b34fb"

NOTIFY_UUIDS = (
    UUID_TEMPERATURE,
    UUID_HUMIDITY,
    UUID_IRRADIANCE,
    UUID_BATTERY,
    UUID_OCCUPANCY,
)

MEASUREMENT_UUIDS = NOTIFY_UUIDS

INFO_UUIDS = (
    UUID_MANUFACTURER,
    UUID_MODEL,
    UUID_SERIAL,
    UUID_FIRMWARE,
    UUID_HARDWARE,
    UUID_SOFTWARE,
)


def decode_measurement(
    current: RoomSensorData,
    uuid: str,
    value: bytes,
) -> RoomSensorData:
    """Decode a RoomSensor GATT measurement."""
    uuid = uuid.lower()

    if uuid == UUID_TEMPERATURE and len(value) >= 2:
        return replace(
            current,
            temperature=int.from_bytes(value[:2], "little", signed=True) / 100.0,
        )

    if uuid == UUID_HUMIDITY and len(value) >= 2:
        return replace(
            current,
            humidity=int.from_bytes(value[:2], "little", signed=False) / 100.0,
        )

    if uuid == UUID_IRRADIANCE:
        raw = int.from_bytes(value, "little", signed=False)

        if len(value) == 2:
            # Bluetooth SIG 0x2A77 Irradiance is uint16 with 0.1 W/m².
            # This is radiant power, not illuminance/lux.
            return replace(
                current,
                light_raw=raw,
                light_raw_hex=value.hex(),
                light_encoding="bluetooth_irradiance_uint16",
                illuminance_lux=None,
                light_status=None,
                irradiance_w_m2=raw / 10.0,
            )

        if len(value) >= 3:
            # Physical Yealink RoomSensors use a non-standard payload on
            # UUID 0x2A77. The attached Valid Range descriptor is six bytes,
            # proving that the actual measurement component is uint24. That
            # matches the Bluetooth Illuminance representation: uint24 with
            # 0.01 lux resolution. Observed Yealink values are four bytes;
            # the fourth byte is retained separately as a vendor status byte.
            illuminance_raw = int.from_bytes(value[:3], "little", signed=False)
            status = value[3] if len(value) >= 4 else None
            all_zero = all(byte == 0 for byte in value)
            return replace(
                current,
                light_raw=raw if not all_zero else None,
                light_raw_hex=value.hex(),
                light_encoding="yealink_legacy_illuminance_uint24_status",
                illuminance_lux=None if all_zero else illuminance_raw / 100.0,
                light_status=status,
                irradiance_w_m2=None,
            )

        return replace(
            current,
            light_raw=raw if raw != 0 else None,
            light_raw_hex=value.hex(),
            light_encoding=f"yealink_proprietary_{len(value)}byte",
            illuminance_lux=None,
            light_status=None,
            irradiance_w_m2=None,
        )

    if uuid == UUID_BATTERY and value:
        return replace(
            current,
            battery=int.from_bytes(value[:1], "little", signed=False),
        )

    if uuid == UUID_OCCUPANCY and value:
        return replace(
            current,
            occupancy=int.from_bytes(value, "little", signed=False) != 0,
        )

    return current


def decode_text(value: bytes) -> str:
    """Decode a Device Information Service string."""
    return value.decode("utf-8", errors="replace").rstrip("\x00")
