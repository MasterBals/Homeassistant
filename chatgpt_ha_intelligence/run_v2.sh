#!/usr/bin/env bash
set -euo pipefail

: "${SUPERVISOR_TOKEN:?SUPERVISOR_TOKEN is required; app must run with Home Assistant API access}"

SRC="/opt/homeassistant-source/chatgpt_ha_admin_installer/payload/custom_components/chatgpt_ha_admin"
DST="/homeassistant/custom_components/chatgpt_ha_admin"
CFG="/homeassistant/configuration.yaml"
STATE_DIR="/homeassistant/.chatgpt_ha_admin"
BACKUP_DIR="${STATE_DIR}/installer_backups"
STAMP="$(date +%Y%m%d_%H%M%S)"
OPTIONS="/data/options.json"
OPTIONS_BACKUP="/tmp/chatgpt_ha_options.original.json"
INTERNAL_TOKEN_FILE="/data/internal_mcp_token"
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

cat > "${STATE_DIR}/settings.json.new" <<JSON
{
  "write_enabled": ${WRITE_ENABLED},
  "allow_service_calls": ${ALLOW_SERVICE_CALLS},
  "allow_sensitive_files": ${ALLOW_SENSITIVE_FILES},
  "require_hash_for_writes": ${REQUIRE_HASH},
  "max_read_bytes": ${MAX_READ_BYTES}
}
JSON

if [[ -f "${STATE_DIR}/settings.json" ]]; then
  cp -a "${STATE_DIR}/settings.json" "${BACKUP_DIR}/settings_${STAMP}.json"
fi
mv "${STATE_DIR}/settings.json.new" "${STATE_DIR}/settings.json"

if [[ ! -f "${CFG}" ]]; then
  echo "ERROR: configuration.yaml not found at ${CFG}" >&2
  exit 1
fi

if [[ -d "${DST}" ]]; then
  cp -a "${DST}" "${BACKUP_DIR}/chatgpt_ha_admin_${STAMP}"
fi
rm -rf "${DST}.new"
cp -a "${SRC}" "${DST}.new"
rm -rf "${DST}"
mv "${DST}.new" "${DST}"

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
  if [[ -d "${BACKUP_DIR}/chatgpt_ha_admin_${STAMP}" ]]; then
    rm -rf "${DST}"
    cp -a "${BACKUP_DIR}/chatgpt_ha_admin_${STAMP}" "${DST}"
  fi
  exit 1
fi

echo "ChatGPT Home Assistant Admin integration installed and config validated."

if [[ "${AUTO_RESTART}" == "true" ]]; then
  echo "Restarting Home Assistant because auto_restart is enabled..."
  curl -fsS --max-time 15 \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    -H "Content-Type: application/json" \
    -X POST -d '{}' \
    http://supervisor/core/api/services/homeassistant/restart >/dev/null || true
fi

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
