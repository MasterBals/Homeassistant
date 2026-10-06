# Changelog

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
