# Changelog

## 2.5.1

- Add continuous passive `O_RDONLY|O_NONBLOCK` capture of the VCM36-W vendor HID channel on `/dev/hidraw*`.
- Capture only devices whose HID report descriptor declares vendor report ID `0xC8`; no writes, `SET_REPORT`, kernel-driver detach, firmware command or pairing command are performed.
- Retain the most recent unique input reports in `/config/yealink_vcm36w_usb_probe.json` with report ID, length, timestamps, repeat count and SHA-256 prefix for RC8 framing analysis.
- Keep protocol writes disabled and preserve the 2.5.0 revisioned Second Brain and verified pairing findings unchanged.

## 2.5.0

- Add explicit Second Brain revision numbers and preserve the original `created_at` / `updated_at` timestamps for every superseded finding.
- Record `change_reason`, `archived_at` and `superseded_reason` so later corrections remain traceable instead of silently replacing earlier conclusions.
- Treat identical upserts as no-ops so repeated checks do not create meaningless history entries.
- Expose `second_brain_status`, `second_brain_search`, `second_brain_get` and `second_brain_upsert` through the Intelligence MCP so verified findings can be persisted during active investigations.
- Add a one-time bootstrap that backfills the verified VCM36-W request/report/RC8 write-path findings and corrects the stale direct-`0x0231` next-step note only when that obsolete text is still present.
- Keep WLAN passwords, tokens and other secrets out of Second Brain; target WLAN credentials remain stored only in Home Assistant add-on options.
- Add a regression test proving that revision 1 remains readable after a corrected revision 2 is stored.
- Align the Unified MCP diagnostic version with add-on version 2.5.0.

## 2.4.4

- Correct the VCM36-W USB vendor ID used by the Yealink lab from the erroneous `1b51` value to the actual Yealink VID `6993` reported by Home Assistant USB discovery and the physical microphone.
- Add a continuous read-only VCM36-W USB/HID probe that records USB interfaces, endpoints, HID report descriptors and declared report IDs.
- Probe supported HID input/feature reports only with `GET_REPORT`; no `SET_REPORT`, WLAN change, firmware write or pairing command is sent.
- Store the private diagnostic snapshot at `/config/yealink_vcm36w_usb_probe.json` so pairing reverse engineering can continue through the existing Admin MCP without exposing a new public write tool.
- Bump the extended Intelligence bridge wrapper to 0.4.3.

## 2.4.3

- Add enhanced network correlation using exact device-registry and entity-state network identities, encoded IPv4 addresses, MAC addresses and Sonos RINCON identifiers.
- Recognise the Home Assistant host itself and keep heuristic device identification separate from confirmed Home Assistant matches.
- Add conservative candidate/family classifications for devices such as NVIDIA Shield, Apple/AirPlay, Logitech Harmony, Arlo, Sonos and Tuya without converting uncertain matches into confirmed devices.
- Bump the extended Intelligence bridge wrapper to 0.4.2.

## 2.4.2

- Exclude Home Assistant Supervisor/container routes from automatic private-network scan targets so `targets: null` selects the real LAN instead of exceeding `max_scan_hosts` on internal `172.30.x.x` networks.
- Correlate discovered IPv4 addresses and MAC addresses exactly with the Home Assistant device registry instead of using substring matching, preventing false matches such as `192.168.1.1` matching `192.168.1.110`.
- Expose the existing `network_scan_unmanaged` implementation as an MCP tool so unknown/unmatched LAN hosts can be queried directly.
- Bump the extended Intelligence bridge wrapper to 0.4.1.

## 2.4.1

- Fix the OpenAI Secure MCP Tunnel repeatedly exiting when the add-on `log_level` option is set to `INFO`, `DEBUG`, `WARNING` or `ERROR`.
- Keep the add-on `LOG_LEVEL` environment variable for the Python services while explicitly removing it from the official `tunnel-client-runtime` process environment.
- Preserve the existing tunnel reconnect/backoff behaviour and all 2.4.0 WLAN/Yealink settings unchanged.

## 2.4.0

- Add separate VCM36-W target WLAN options `yealink_target_wifi_ssid` and `yealink_target_wifi_passphrase` to the ChatGPT MCP add-on configuration.
- Store the WLAN passphrase as a Home Assistant add-on `password` option and keep it out of MCP status payloads and logs.
- Add internal `get_target_wifi_credentials()` handling for future RC8/pairing write tools and the read-only `yealink_wifi_profile_status` MCP tool.
- Validate target SSID length and WPA2-PSK/passphrase format before future protocol use.

## 2.3.0

- Fix the ChatGPT MCP add-on Core-restart loop by persisting a `restart_pending` marker before requesting a Home Assistant Core restart.
- Treat temporary Home Assistant API/Admin MCP startup timeouts as degraded states instead of terminating the whole add-on.
- Restart the OpenAI Secure MCP tunnel with bounded backoff instead of exiting the add-on when the tunnel disconnects.
- Add a guarded Yealink VCM36-W lab with raw USB/udev access, `libusb`/`pyusb`, Wi-Fi AP tooling (`hostapd`, `dnsmasq`, `iw`) and passive packet capture support.
- Add MCP tools for Yealink readiness, USB inventory, AP preview/start/stop and packet capture. AP writes and future RC8/pairing writes are disabled by default.
- Add isolated default Yealink lab subnet `192.168.187.0/24` with overlap and active-interface safety checks and no NAT/Internet forwarding.

## 1.1.0

- Add the Chur Kultur custom integration for filtered events from chur-kultur.ch.
- Add a Chur Kultur Lovelace card with image list and detail popup.

## 1.0.5

- Refine Lovelace card bin artwork with transparent SVGs and waste-type symbols on each bin.
- Animate only the waste items falling into the bin instead of moving the whole bin image.

## 1.0.4

- Bundle and auto-register the Lovelace card from the integration so Home Assistant no longer depends on a manually copied `/config/www` card file.
- Serve the illustrated waste assets from the integration package.

## 1.0.3

- Improve the Lovelace card with visual editor options for selecting waste types.
- Add separate illustrated assets for Karton, Papier, Kompost and Kehricht.
- Show the nearest collection more prominently with relative dates for upcoming collections.

## 1.0.2

- Remove binary brand icon so repository changes can be created in environments that reject binary files in pull requests.

## 1.0.1

- Fix HACS metadata for integration custom repositories.
- Document the required HACS category to avoid adding the repository as an app/add-on repository.

## 1.0.0

- Initial production-ready HACS custom integration for Chur waste collections.
- Adds config flow, sensors, calendar, services, diagnostics and Lovelace card.
