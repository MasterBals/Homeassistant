#!/usr/bin/env bash
set -euo pipefail

SRC="/opt/homeassistant-source/chatgpt_ha_admin_installer/payload/custom_components/chatgpt_ha_admin"
DST="/homeassistant/custom_components/chatgpt_ha_admin"
CFG="/homeassistant/configuration.yaml"
STATE_DIR="/homeassistant/.chatgpt_ha_admin"
BACKUP_DIR="${STATE_DIR}/installer_backups"
STAMP="$(date +%Y%m%d_%H%M%S)"
OPTIONS="/data/options.json"

mkdir -p "${STATE_DIR}" "${BACKUP_DIR}" /homeassistant/custom_components

opt() {
  jq -r --arg key "$1" --arg fallback "$2" '.[$key] // $fallback' "${OPTIONS}"
}

WRITE_ENABLED="$(opt write_enabled true)"
ALLOW_SERVICE_CALLS="$(opt allow_service_calls true)"
ALLOW_SENSITIVE_FILES="$(opt allow_sensitive_files false)"
REQUIRE_HASH="$(opt require_hash_for_writes true)"
MAX_READ_BYTES="$(opt max_read_bytes 2000000)"
AUTO_RESTART="$(opt auto_restart true)"

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
  curl -fsS --max-time 15 \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    -H "Content-Type: application/json" \
    -X POST -d '{}' \
    http://supervisor/core/api/services/homeassistant/restart >/dev/null || true
fi

echo "Starting HA Intelligence Bridge on configured MCP port..."
exec python3 -u /opt/homeassistant-source/ha_intelligence_bridge/app/main.py
