#!/usr/bin/with-contenv bashio
set -e

# Dedicated Home Assistant ingress UI for the structured MCP protocol and Second Brain.
# The actual MCP endpoints remain bound to loopback only.
python3 -u /app/audit_ui.py &

exec /run.sh
