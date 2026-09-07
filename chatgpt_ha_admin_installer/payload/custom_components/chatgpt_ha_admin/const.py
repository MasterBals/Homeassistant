"""Constants for ChatGPT Home Assistant Admin."""

DOMAIN = "chatgpt_ha_admin"
API_ID = DOMAIN
API_NAME = "ChatGPT Home Assistant Admin"
STATE_DIR_NAME = ".chatgpt_ha_admin"
SETTINGS_FILE = "settings.json"
BACKUP_DIR = "backups"
JOURNAL_FILE = "journal.jsonl"

DEFAULT_SETTINGS = {
    "write_enabled": True,
    "allow_service_calls": True,
    "allow_sensitive_files": False,
    "require_hash_for_writes": True,
    "max_read_bytes": 2_000_000,
}

BLOCKED_SERVICE_CALLS = {
    ("homeassistant", "restart"),
    ("homeassistant", "stop"),
    ("homeassistant", "restart_safe_mode"),
}

SENSITIVE_NAMES = {
    "secrets.yaml",
    "auth",
    "auth_provider.homeassistant",
    "onboarding",
    "core.config_entries",
    "core.device_registry",
    "core.entity_registry",
    "core.area_registry",
    "core.restore_state",
}
