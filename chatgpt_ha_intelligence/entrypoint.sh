#!/usr/bin/with-contenv bashio
set -e

# Import the legacy /config Second Brain once into persistent add-on /data storage.
python3 -u /app/migrate_second_brain.py || true

# Dedicated Home Assistant ingress UI for the structured MCP protocol and Second Brain.
# The actual MCP endpoints remain bound to loopback only.
python3 -u /app/audit_ui.py &

# Continuous read-only VCM36-W USB/HID probe. It only reads descriptors and uses
# HID GET_REPORT requests; no SET_REPORT or pairing write is performed here.
python3 -u /app/yealink_usb_probe.py &

exec /run.sh
