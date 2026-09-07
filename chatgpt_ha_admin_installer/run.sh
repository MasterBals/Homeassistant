#!/usr/bin/with-contenv bashio
set -euo pipefail

DOMAIN="chatgpt_ha_admin"
SRC="/opt/chatgpt-ha-admin/payload/custom_components/${DOMAIN}"
DST="/homeassistant/custom_components/${DOMAIN}"
CFG="/homeassistant/configuration.yaml"
STATE_DIR="/homeassistant/.chatgpt_ha_admin"
INSTALLER_BACKUP_DIR="${STATE_DIR}/installer_backups"
STAMP="$(date +%Y%m%d_%H%M%S)"

COMPONENT_CHANGED=0
COMPONENT_EXISTED=0
CFG_CHANGED=0
SETTINGS_CHANGED=0

mkdir -p "${STATE_DIR}" "${INSTALLER_BACKUP_DIR}" /homeassistant/custom_components

WRITE_ENABLED="$(bashio::config 'write_enabled')"
ALLOW_SERVICE_CALLS="$(bashio::config 'allow_service_calls')"
ALLOW_SENSITIVE_FILES="$(bashio::config 'allow_sensitive_files')"
REQUIRE_HASH="$(bashio::config 'require_hash_for_writes')"
MAX_READ_BYTES="$(bashio::config 'max_read_bytes')"
AUTO_RESTART="$(bashio::config 'auto_restart')"

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

if [[ ! -f "${STATE_DIR}/settings.json" ]] || ! cmp -s "${SETTINGS_TMP}" "${STATE_DIR}/settings.json"; then
  if [[ -f "${STATE_DIR}/settings.json" ]]; then
    cp -a "${STATE_DIR}/settings.json" "${INSTALLER_BACKUP_DIR}/settings_${STAMP}.json"
  fi
  mv "${SETTINGS_TMP}" "${STATE_DIR}/settings.json"
  SETTINGS_CHANGED=1
else
  rm -f "${SETTINGS_TMP}"
fi

if [[ ! -f "${CFG}" ]]; then
  bashio::log.fatal "configuration.yaml wurde unter ${CFG} nicht gefunden."
  exit 1
fi

if [[ -d "${DST}" ]]; then
  COMPONENT_EXISTED=1
fi

if [[ ! -d "${DST}" ]] || ! diff -qr "${SRC}" "${DST}" >/dev/null 2>&1; then
  bashio::log.info "Installiere/aktualisiere ${DOMAIN} ..."
  if [[ "${COMPONENT_EXISTED}" == "1" ]]; then
    cp -a "${DST}" "${INSTALLER_BACKUP_DIR}/${DOMAIN}_${STAMP}"
  fi
  TMP="${DST}.new"
  rm -rf "${TMP}"
  cp -a "${SRC}" "${TMP}"
  rm -rf "${DST}"
  mv "${TMP}" "${DST}"
  COMPONENT_CHANGED=1
fi

if ! grep -Eq '^[[:space:]]*chatgpt_ha_admin[[:space:]]*:' "${CFG}"; then
  bashio::log.info "Aktiviere ${DOMAIN} in configuration.yaml ..."
  cp -a "${CFG}" "${INSTALLER_BACKUP_DIR}/configuration_${STAMP}.yaml"
  cat >> "${CFG}" <<'YAML'

# ChatGPT Home Assistant Admin MCP
chatgpt_ha_admin:
YAML
  CFG_CHANGED=1
fi

bashio::log.info "Prüfe Home-Assistant-Konfiguration ..."
CHECK="$(curl -fsS --max-time 120 \
  -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{}' \
  http://supervisor/core/api/config/core/check_config || true)"

RESULT="$(printf '%s' "${CHECK}" | jq -r '.result // empty' 2>/dev/null || true)"
if [[ "${RESULT}" != "valid" ]]; then
  bashio::log.error "Home-Assistant-Konfigurationsprüfung war nicht erfolgreich: ${CHECK}"

  if [[ "${CFG_CHANGED}" == "1" ]]; then
    BACKUP_CFG="${INSTALLER_BACKUP_DIR}/configuration_${STAMP}.yaml"
    if [[ -f "${BACKUP_CFG}" ]]; then
      cp -a "${BACKUP_CFG}" "${CFG}"
      bashio::log.warning "configuration.yaml wurde automatisch zurückgesetzt."
    fi
  fi

  if [[ "${COMPONENT_CHANGED}" == "1" ]]; then
    BACKUP_COMPONENT="${INSTALLER_BACKUP_DIR}/${DOMAIN}_${STAMP}"
    rm -rf "${DST}"
    if [[ "${COMPONENT_EXISTED}" == "1" && -d "${BACKUP_COMPONENT}" ]]; then
      cp -a "${BACKUP_COMPONENT}" "${DST}"
      bashio::log.warning "Vorherige Integration wurde automatisch wiederhergestellt."
    else
      bashio::log.warning "Neu installierte Integration wurde wegen des Fehlers entfernt."
    fi
  fi

  if [[ "${SETTINGS_CHANGED}" == "1" && -f "${INSTALLER_BACKUP_DIR}/settings_${STAMP}.json" ]]; then
    cp -a "${INSTALLER_BACKUP_DIR}/settings_${STAMP}.json" "${STATE_DIR}/settings.json"
  fi

  exit 1
fi

bashio::log.info "Konfiguration ist gültig."

if [[ "${COMPONENT_CHANGED}" == "1" || "${CFG_CHANGED}" == "1" || "${SETTINGS_CHANGED}" == "1" ]]; then
  if bashio::var.true "${AUTO_RESTART}"; then
    bashio::log.info "Neustart von Home Assistant wird ausgelöst, damit Integration und Einstellungen aktiv werden."
    curl -fsS --max-time 15 \
      -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
      -H "Content-Type: application/json" \
      -X POST \
      -d '{}' \
      http://supervisor/core/api/services/homeassistant/restart >/dev/null || true
  else
    bashio::log.warning "Installation abgeschlossen. Home Assistant muss einmal neu gestartet werden."
  fi
else
  bashio::log.info "ChatGPT Home Assistant Admin ist bereits aktuell. Kein Neustart erforderlich."
fi

bashio::log.info "Home-Assistant-Seite ist eingerichtet."
bashio::log.info "MCP API-ID: chatgpt_ha_admin"
bashio::log.info "MCP-Pfad: /api/mcp/chatgpt_ha_admin"
