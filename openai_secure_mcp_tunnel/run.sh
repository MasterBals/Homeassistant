#!/usr/bin/with-contenv bashio
set -euo pipefail

TUNNEL_ID="$(bashio::config 'tunnel_id')"
RUNTIME_API_KEY="$(bashio::config 'runtime_api_key')"
MCP_SERVER_URL_VALUE="$(bashio::config 'mcp_server_url')"
MCP_BEARER_TOKEN="$(bashio::config 'mcp_bearer_token')"
LOG_LEVEL_VALUE="$(bashio::config 'log_level')"

if [[ -z "${TUNNEL_ID}" ]]; then
  bashio::log.fatal "tunnel_id is required"
  exit 1
fi

if [[ -z "${RUNTIME_API_KEY}" ]]; then
  bashio::log.fatal "runtime_api_key is required"
  exit 1
fi

if [[ -z "${MCP_SERVER_URL_VALUE}" ]]; then
  bashio::log.fatal "mcp_server_url is required"
  exit 1
fi

export CONTROL_PLANE_TUNNEL_ID="${TUNNEL_ID}"
export CONTROL_PLANE_API_KEY="${RUNTIME_API_KEY}"
export MCP_SERVER_URL="${MCP_SERVER_URL_VALUE}"
export LOG_LEVEL="${LOG_LEVEL_VALUE}"
export LOG_FORMAT="json"
export HEALTH_LISTEN_ADDR="127.0.0.1:8080"

if [[ -n "${MCP_BEARER_TOKEN}" ]]; then
  export MCP_AUTH_HEADER="Bearer ${MCP_BEARER_TOKEN}"
  export MCP_EXTRA_HEADERS="Authorization: env:MCP_AUTH_HEADER"
  export MCP_DISCOVERY_EXTRA_HEADERS="Authorization: env:MCP_AUTH_HEADER"
fi

bashio::log.info "Starting official OpenAI tunnel-client"
bashio::log.info "Tunnel ID: ${TUNNEL_ID}"
bashio::log.info "Local MCP server: ${MCP_SERVER_URL_VALUE}"
bashio::log.info "Authentication header: $([[ -n "${MCP_BEARER_TOKEN}" ]] && echo enabled || echo disabled)"

exec /usr/bin/tunnel-client run
