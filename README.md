# Yealink Devices for Home Assistant

Local Home Assistant integration for supported Yealink devices.

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

### Yealink VCM36-W — experimental USB support

Version 0.2.0 adds native USB discovery for VCM36-W devices with:
- USB VID `6993`
- USB PID `B06A`
- Yealink proprietary HID management interface (usage page `0xFF00`)

Current VCM36-W entities:
- USB connection
- Yealink HID management interface (diagnostic)
- USB Audio interface detection

The current implementation is deliberately read-only. It does **not** yet write pairing data to the microphone.

Static analysis of Yealink RoomConnect / Yealink Plug-in Software 2.35.341.0 shows that VCM36-W wireless pairing is provisioned over USB and then uses the Yealink host's wireless AP. The relevant Yealink control layer includes `WiFiMicPair`, `wifimic-config`, external-microphone registration and AP/Wi-Fi configuration.

The exact binary serialization of the `wifimic-config` pairing payload and the subsequent wireless audio session are still being reverse engineered. Pairing writes remain disabled until those fields are verified from a real pairing capture.

## Architecture

RoomSensor uses Home Assistant's Bluetooth stack and `ActiveBluetoothDataUpdateCoordinator`.

VCM36-W uses Home Assistant USB discovery and a read-only local USB coordinator. Product-specific transports remain isolated so Bluetooth RoomSensors and USB/Wi-Fi VCM devices can coexist under the same `yealink` integration domain.

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

A VCM36-W connected by USB to the Home Assistant host should also be discovered automatically.

Manual installation is possible by copying `custom_components/yealink` into Home Assistant's `/config/custom_components/` directory and restarting Home Assistant.

## VCM36-W reverse-engineering status

Confirmed from Yealink software:
- VCM36-W normal USB identity: `6993:B06A`
- firmware/upgrade USB PID: `B068`
- proprietary HID usage page: `0xFF00`
- wireless microphone pairing function is exposed as `USBDEV_FUNC_WIRELESS_MIC_PAIR`
- internal pairing interfaces include `UsbWiFiMicPairInterface` and `CWiFiMicPairChannelInterface`
- pairing control uses `/devctl/system/pair/wifimic-config/request` and `.../report`
- pairing data references AP SSID/password/channel/security plus microphone/host binding data and keys
- after USB provisioning, the VCM36-W joins the Yealink host wireless AP and is registered as an external microphone

Still required before enabling wireless pairing:
1. capture one successful official VCM36-W pairing over USB;
2. decode the exact HID framing and `wifimic-config` binary payload;
3. confirm the post-pair wireless control/audio transport;
4. implement and test the Home Assistant host side without relying on proprietary Yealink binaries.

## Status

Version 0.2.0:
- RoomSensor: working local Bluetooth integration
- VCM36-W: experimental read-only USB discovery/diagnostics
- VCM36-W wireless pairing/audio: under reverse engineering, no unsafe writes enabled

This project is community-developed and is not affiliated with or endorsed by Yealink.
