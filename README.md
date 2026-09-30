# Yealink Devices for Home Assistant

Native Bluetooth integration for supported Yealink devices.

## Supported devices

### Yealink RoomSensor
Automatic Bluetooth discovery for devices advertising as `RoomSensor-*` with Yealink manufacturer ID `0x0850`.

Entities:
- Temperature
- Humidity
- Occupancy
- Battery
- Light value (raw GATT Irradiance value, pending final Yealink scaling)
- Bluetooth RSSI (diagnostic, disabled by default)
- Bluetooth connection (diagnostic, disabled by default)

The integration also reads Yealink device metadata such as model, serial number, firmware, software and hardware revision from the standard Device Information Service.

## Architecture

The integration uses Home Assistant's Bluetooth stack and `ActiveBluetoothDataUpdateCoordinator`. It listens for advertisements, opens a managed BLE connection when required, subscribes to GATT notifications and performs periodic health polling.

Product-specific protocol code lives in `custom_components/yealink/profiles/`. New Yealink products can therefore be added without changing the RoomSensor protocol implementation.

Planned device family:
- RoomSensor
- VCM36-W and other Yealink wireless peripherals after their protocol has been captured and documented

## RoomSensor GATT mapping

| Function | GATT characteristic | Decoding |
| --- | --- | --- |
| Temperature | `0x2A6E` | signed little-endian / 100 °C |
| Humidity | `0x2A6F` | unsigned little-endian / 100 % |
| Irradiance / light | `0x2A77` | raw unsigned little-endian value |
| Battery | `0x2A19` | percent |
| Occupancy | `0x2A58` | 0 = clear, non-zero = occupied |

The light characteristic is exposed deliberately as a raw value until the Yealink-specific conversion to lux or another photometric quantity is verified.

## Installation

The intended distribution method is HACS as a custom integration. After installation and a Home Assistant restart, nearby supported RoomSensors should appear automatically under **Settings → Devices & services**.

Manual installation is also possible by copying `custom_components/yealink` into Home Assistant's `/config/custom_components/` directory and restarting Home Assistant.

## Development

The first implementation was validated against a real Yealink RoomSensor:
- Manufacturer: Yealink
- Model: RoomSensor
- Firmware: 8.510.0.65
- Bluetooth manufacturer ID: 0x0850

The design intentionally keeps device detection, transport/coordinator and product profiles separate so future Yealink devices can use BLE, Wi-Fi or another local transport while sharing one Home Assistant integration domain.

## Status

Version 0.1.0 is the first RoomSensor implementation. Temperature, humidity, occupancy and battery have been verified against a physical device. Light reporting is implemented but its final scale still needs validation.

This project is community-developed and is not affiliated with or endorsed by Yealink.
