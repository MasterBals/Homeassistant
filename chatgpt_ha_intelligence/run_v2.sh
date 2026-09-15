#!/usr/bin/env bash
set -euo pipefail

SUPERVISOR_TOKEN="${SUPERVISOR_TOKEN:-}"
if [[ -z "${SUPERVISOR_TOKEN}" ]]; then
  echo "ERROR: SUPERVISOR_TOKEN is unavailable. The app must run with Home Assistant/Supervisor API access." >&2
  exit 1
fi

SRC="/opt/homeassistant-source/chatgpt_ha_admin_installer/payload/custom_components/chatgpt_ha_admin"
DST="/homeassistant/custom_components/chatgpt_ha_admin"
CFG="/homeassistant/configuration.yaml"
STATE_DIR="/homeassistant/.chatgpt_ha_admin"
BACKUP_DIR="${STATE_DIR}/installer_backups"
STAMP="$(date +%Y%m%d_%H%M%S)"
OPTIONS="/data/options.json"
OPTIONS_BACKUP="/tmp/chatgpt_ha_options.original.json"
INTERNAL_TOKEN_FILE="/data/internal_mcp_token"
RUNTIME_STATE="/data/admin_runtime_state.json"
BRIDGE_PORT=18765
UNIFIED_PORT=8765

BRIDGE_PID=""
PROXY_PID=""
TUNNEL_PID=""
OPTIONS_MUTATED=0

opt() {
  jq -r --arg key "$1" --arg fallback "$2" '.[$key] // $fallback' "${OPTIONS}"
}

cleanup() {
  set +e
  if [[ "${OPTIONS_MUTATED}" == "1" && -f "${OPTIONS_BACKUP}" ]]; then
    cp -f "${OPTIONS_BACKUP}" "${OPTIONS}"
    OPTIONS_MUTATED=0
  fi
  for pid in "${TUNNEL_PID}" "${PROXY_PID}" "${BRIDGE_PID}"; do
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      kill "${pid}" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait_http() {
  local url="$1"
  local label="$2"
  local tries="${3:-60}"
  local i
  for ((i=1; i<=tries; i++)); do
    if curl -fsS --max-time 2 "${url}" >/dev/null 2>&1; then
      echo "${label} is ready."
      return 0
    fi
    sleep 1
  done
  echo "ERROR: ${label} did not become ready: ${url}" >&2
  return 1
}

wait_ha_core() {
  local tries="${1:-90}"
  local i
  for ((i=1; i<=tries; i++)); do
    if curl -fsS --max-time 3 \
      -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
      http://supervisor/core/api/ >/dev/null 2>&1; then
      echo "Home Assistant Core API is ready."
      return 0
    fi
    sleep 2
  done
  echo "ERROR: Home Assistant Core API did not become ready." >&2
  return 1
}

probe_admin_mcp() {
  local response
  response="$(curl -fsS --max-time 10 \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -X POST \
    --data '{"jsonrpc":"2.0","id":"probe","method":"initialize","params":{"protocolVersion":"2026-07-28","capabilities":{},"clientInfo":{"name":"chatgpt-ha-addon-probe","version":"2.1.5"}}}' \
    http://supervisor/core/api/mcp/chatgpt_ha_admin 2>/dev/null || true)"
  [[ -n "${response}" ]] && [[ "$(printf '%s' "${response}" | jq -r '.result.protocolVersion // empty' 2>/dev/null || true)" != "" ]]
}

wait_admin_mcp() {
  local tries="${1:-60}"
  local i
  for ((i=1; i<=tries; i++)); do
    if probe_admin_mcp; then
      echo "Home Assistant Admin MCP is ready."
      return 0
    fi
    sleep 2
  done
  echo "WARNING: Home Assistant Admin MCP did not become ready; Intelligence tools will still start and UnifiedStatus will expose the error." >&2
  return 1
}

mkdir -p "${STATE_DIR}" "${BACKUP_DIR}" /homeassistant/custom_components

WRITE_ENABLED="$(opt write_enabled true)"
ALLOW_SERVICE_CALLS="$(opt allow_service_calls true)"
ALLOW_SENSITIVE_FILES="$(opt allow_sensitive_files false)"
REQUIRE_HASH="$(opt require_hash_for_writes true)"
MAX_READ_BYTES="$(opt max_read_bytes 2000000)"
AUTO_RESTART="$(opt auto_restart false)"
LOG_LEVEL="$(opt log_level INFO)"
TUNNEL_ID="$(opt tunnel_id '')"
RUNTIME_API_KEY="$(opt runtime_api_key '')"

SETTINGS_TMP="${STATE_DIR}/settings.json.new"
cat > "${SETTINGS_TMP}" <<JSON
{
  "write_enabled": ${WRITE_ENABLED},
  "allow_service_calls": ${ALLOW_SERVICE_CALLS},
  "allow_sensitive_files": ${ALLOW_SENSITIVE_FILES},
  "require_hash_for_writes": ${REQUIRE_HASH},
  "max_read_bytes": ${MAX_READ_BYTES}
}
JSON

SETTINGS_SHA="$(sha256sum "${SETTINGS_TMP}" | awk '{print $1}')"
COMPONENT_SHA="$(find "${SRC}" -type f -print | LC_ALL=C sort | while IFS= read -r file; do sha256sum "${file}"; done | sha256sum | awk '{print $1}')"
LOADED_SETTINGS_SHA="$(jq -r '.settings_sha // ""' "${RUNTIME_STATE}" 2>/dev/null || true)"
LOADED_COMPONENT_SHA="$(jq -r '.component_sha // ""' "${RUNTIME_STATE}" 2>/dev/null || true)"

if [[ -f "${STATE_DIR}/settings.json" ]]; then
  if ! cmp -s "${STATE_DIR}/settings.json" "${SETTINGS_TMP}"; then
    cp -a "${STATE_DIR}/settings.json" "${BACKUP_DIR}/settings_${STAMP}.json"
  fi
fi
mv "${SETTINGS_TMP}" "${STATE_DIR}/settings.json"

if [[ ! -f "${CFG}" ]]; then
  echo "ERROR: configuration.yaml not found at ${CFG}" >&2
  exit 1
fi

COMPONENT_CHANGED=0
if [[ ! -d "${DST}" ]] || ! diff -qr "${SRC}" "${DST}" >/dev/null 2>&1; then
  COMPONENT_CHANGED=1
  if [[ -d "${DST}" ]]; then
    cp -a "${DST}" "${BACKUP_DIR}/chatgpt_ha_admin_${STAMP}"
  fi
  rm -rf "${DST}.new"
  cp -a "${SRC}" "${DST}.new"
  rm -rf "${DST}"
  mv "${DST}.new" "${DST}"
fi

CFG_CHANGED=0
if ! grep -Eq '^[[:space:]]*chatgpt_ha_admin[[:space:]]*:' "${CFG}"; then
  cp -a "${CFG}" "${BACKUP_DIR}/configuration_${STAMP}.yaml"
  cat >> "${CFG}" <<'YAML'

# ChatGPT Home Assistant Admin MCP
chatgpt_ha_admin:
YAML
  CFG_CHANGED=1
fi

CHECK="$(curl -fsS --max-time 120 \
  -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
  -H "Content-Type: application/json" \
  -X POST -d '{}' \
  http://supervisor/core/api/config/core/check_config || true)"
RESULT="$(printf '%s' "${CHECK}" | jq -r '.result // empty' 2>/dev/null || true)"

if [[ "${RESULT}" != "valid" ]]; then
  echo "ERROR: Home Assistant config check failed: ${CHECK}" >&2
  if [[ "${CFG_CHANGED}" == "1" && -f "${BACKUP_DIR}/configuration_${STAMP}.yaml" ]]; then
    cp -a "${BACKUP_DIR}/configuration_${STAMP}.yaml" "${CFG}"
  fi
  if [[ "${COMPONENT_CHANGED}" == "1" && -d "${BACKUP_DIR}/chatgpt_ha_admin_${STAMP}" ]]; then
    rm -rf "${DST}"
    cp -a "${BACKUP_DIR}/chatgpt_ha_admin_${STAMP}" "${DST}"
  fi
  exit 1
fi

echo "ChatGPT Home Assistant Admin integration installed and config validated."

RESTART_REQUIRED=0
if [[ "${COMPONENT_CHANGED}" == "1" || "${CFG_CHANGED}" == "1" ]]; then
  RESTART_REQUIRED=1
fi
if [[ "${LOADED_COMPONENT_SHA}" != "${COMPONENT_SHA}" || "${LOADED_SETTINGS_SHA}" != "${SETTINGS_SHA}" ]]; then
  RESTART_REQUIRED=1
fi
if [[ "${AUTO_RESTART}" == "true" ]]; then
  RESTART_REQUIRED=1
fi

if [[ "${RESTART_REQUIRED}" == "1" ]]; then
  echo "Restarting Home Assistant Core once to load the current Admin MCP integration/settings..."
  curl -fsS --max-time 5 \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    -H "Content-Type: application/json" \
    -X POST -d '{}' \
    http://supervisor/core/api/services/homeassistant/restart >/dev/null 2>&1 || true
  wait_ha_core 120
  sleep 3
  jq -n \
    --arg component_sha "${COMPONENT_SHA}" \
    --arg settings_sha "${SETTINGS_SHA}" \
    --arg updated_at "$(date +%Y-%m-%dT%H:%M:%S%z)" \
    '{component_sha:$component_sha,settings_sha:$settings_sha,updated_at:$updated_at}' > "${RUNTIME_STATE}"
fi

wait_admin_mcp 60 || true

umask 077
if [[ ! -s "${INTERNAL_TOKEN_FILE}" ]]; then
  python3 - <<'PY' > "${INTERNAL_TOKEN_FILE}"
import secrets
print(secrets.token_urlsafe(48))
PY
fi
INTERNAL_TOKEN="$(tr -d '\r\n' < "${INTERNAL_TOKEN_FILE}")"
if [[ -z "${INTERNAL_TOKEN}" ]]; then
  echo "ERROR: Failed to create internal MCP token" >&2
  exit 1
fi

cp -f "${OPTIONS}" "${OPTIONS_BACKUP}"
OPTIONS_MUTATED=1
jq \
  --arg token "${INTERNAL_TOKEN}" \
  --arg host "127.0.0.1" \
  --argjson port "${BRIDGE_PORT}" \
  '.mcp_token=$token | .bind_host=$host | .port=$port' \
  "${OPTIONS_BACKUP}" > "${OPTIONS}.new"
mv "${OPTIONS}.new" "${OPTIONS}"

echo "Starting private Intelligence MCP on 127.0.0.1:${BRIDGE_PORT}..."
python3 -u /opt/homeassistant-source/ha_intelligence_bridge/app/main.py &
BRIDGE_PID=$!
wait_http "http://127.0.0.1:${BRIDGE_PORT}/health" "Intelligence MCP" 60

cp -f "${OPTIONS_BACKUP}" "${OPTIONS}"
OPTIONS_MUTATED=0

export INTELLIGENCE_MCP_URL="http://127.0.0.1:${BRIDGE_PORT}/mcp"
export INTELLIGENCE_MCP_TOKEN="${INTERNAL_TOKEN}"
export HA_ADMIN_MCP_URL="http://supervisor/core/api/mcp/chatgpt_ha_admin"
export HA_ADMIN_MCP_TOKEN="${SUPERVISOR_TOKEN}"
export UNIFIED_MCP_HOST="127.0.0.1"
export UNIFIED_MCP_PORT="${UNIFIED_PORT}"
export LOG_LEVEL="${LOG_LEVEL}"

echo "Starting unified Admin + Intelligence MCP on 127.0.0.1:${UNIFIED_PORT}..."
python3 -u /app/unified_mcp.py &
PROXY_PID=$!
wait_http "http://127.0.0.1:${UNIFIED_PORT}/health" "Unified MCP" 60

if [[ -n "${TUNNEL_ID}" || -n "${RUNTIME_API_KEY}" ]]; then
  if [[ -z "${TUNNEL_ID}" || -z "${RUNTIME_API_KEY}" ]]; then
    echo "ERROR: tunnel_id and runtime_api_key must either both be configured or both be empty." >&2
    exit 1
  fi
  if [[ ! "${TUNNEL_ID}" =~ ^tunnel_[0-9a-f]{32}$ ]]; then
    echo "ERROR: tunnel_id must match tunnel_ followed by 32 lowercase hexadecimal characters." >&2
    exit 1
  fi

  export CONTROL_PLANE_TUNNEL_ID="${TUNNEL_ID}"
  export CONTROL_PLANE_API_KEY="${RUNTIME_API_KEY}"
  export MCP_SERVER_URL="http://127.0.0.1:${UNIFIED_PORT}/mcp"

  echo "Starting official OpenAI Secure MCP Tunnel for ${TUNNEL_ID}..."
  /usr/local/bin/tunnel-client-runtime run &
  TUNNEL_PID=$!
  echo "OpenAI tunnel client started. No inbound router port is required."
else
  echo "OpenAI tunnel is not configured yet."
  echo "Set tunnel_id and runtime_api_key in the app configuration, then restart this app."
fi

set +e
if [[ -n "${TUNNEL_PID}" ]]; then
  wait -n "${BRIDGE_PID}" "${PROXY_PID}" "${TUNNEL_PID}"
else
  wait -n "${BRIDGE_PID}" "${PROXY_PID}"
fi
STATUS=$?
set -e

echo "ERROR: One of the managed MCP/tunnel processes exited unexpectedly with status ${STATUS}." >&2
exit "${STATUS}"
