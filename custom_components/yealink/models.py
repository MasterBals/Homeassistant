"""Data models for Yealink devices."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RoomSensorData:
    """Current RoomSensor data."""

    temperature: float | None = None
    humidity: float | None = None
    light_raw: int | None = None
    light_raw_hex: str | None = None
    light_encoding: str | None = None
    irradiance_w_m2: float | None = None
    battery: int | None = None
    occupancy: bool | None = None
    rssi: int | None = None

    manufacturer: str = "Yealink"
    model: str = "RoomSensor"
    serial_number: str | None = None
    firmware: str | None = None
    software: str | None = None
    hardware: str | None = None


@dataclass(slots=True)
class Vcm36wData:
    """Current locally observable VCM36-W state."""

    connected: bool = False
    usb_path: str | None = None
    serial_number: str | None = None
    manufacturer: str = "Yealink"
    product: str = "VCM36-W"
    has_hid_interface: bool | None = None
    has_audio_interface: bool | None = None
