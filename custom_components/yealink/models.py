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
    battery: int | None = None
    occupancy: bool | None = None
    rssi: int | None = None

    manufacturer: str = "Yealink"
    model: str = "RoomSensor"
    serial_number: str | None = None
    firmware: str | None = None
    software: str | None = None
    hardware: str | None = None
