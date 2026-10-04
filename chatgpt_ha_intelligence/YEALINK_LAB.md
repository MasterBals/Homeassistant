# Yealink VCM36-W Lab

Version 2.3.0 prepares the ChatGPT Home Assistant MCP app for controlled VCM36-W reverse engineering and pairing work without enabling unknown pairing writes.

## What is included

- Raw USB mapping (`usb: true`) and read-only udev metadata for the VCM36-W.
- `libusb`, `usbutils` and Python `pyusb` for the already verified RC8 USB transport work.
- `NET_ADMIN` plus `hostapd`, `dnsmasq` and `iw` so the otherwise unused Home Assistant Wi-Fi interface can be used as an isolated WPA2-PSK/CCMP lab access point.
- `tcpdump` for passive packet captures.
- MCP tools:
  - `yealink_lab_status`
  - `yealink_usb_inventory`
  - `yealink_ap_preview`
  - `yealink_ap_start`
  - `yealink_ap_stop`
  - `yealink_packet_capture`

The AP has no NAT or Internet forwarding. The default lab subnet is `192.168.187.0/24`; startup refuses to use it if it overlaps an existing route or if the chosen Wi-Fi interface already has a global IP address.

## Safety gates

`yealink_ap_write_enabled` defaults to `false`. Therefore ChatGPT can inspect USB/Wi-Fi readiness and preview the AP but cannot change the Wi-Fi interface until this option is explicitly enabled.

`yealink_protocol_write_enabled` also defaults to `false`. Version 2.3.0 intentionally contains **no tool that sends an RC8 pairing payload or Wi-Fi credentials to the microphone**. This option is reserved as the explicit gate for the later pairing implementation after the remaining `wifimic-config` fields are verified.

## AP configuration

The following app options prepare the simulated Yealink-side network transport:

- `yealink_wifi_interface`: default `wlan0`
- `yealink_ap_ssid`: default `Yealink-Lab`
- `yealink_ap_passphrase`: must contain 8-63 characters before AP start
- `yealink_ap_country`: default `CH`
- `yealink_ap_channel`: default `6`; can later be changed to a supported 5 GHz channel
- `yealink_ap_address`: default `192.168.187.1/24`
- `yealink_ap_dhcp_start`: default `192.168.187.20`
- `yealink_ap_dhcp_end`: default `192.168.187.80`

`yealink_ap_start` starts only the lab-owned `hostapd` and `dnsmasq` processes. `yealink_ap_stop` removes only their processes and the address created by the lab. App shutdown also cleans up a running lab AP.

## Restart-loop fix

The previous startup path wrote the Admin MCP runtime hashes only **after** restarting Home Assistant Core. If the app was interrupted while Core was restarting, the next container start could request the same Core restart again.

Version 2.3.0 writes a persistent `restart_pending` marker in `/data/admin_runtime_state.json` **before** requesting the Core restart. The same component/settings hashes are never restarted twice. Core/API timeouts are degraded states rather than reasons to terminate the whole app. The OpenAI tunnel is restarted with backoff without stopping the MCP app.

## Next protocol step

After 2.3.0 is running, use `yealink_lab_status` first. The next reverse-engineering step remains the existing one: resolve serializer `0x108E6580` and semantically map all eight `/devctl/system/pair/wifimic-config/request` arguments. Only after those fields are verified should an RC8/pairing write tool be added behind `yealink_protocol_write_enabled`.
