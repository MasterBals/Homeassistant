"""Settings loader for ChatGPT Home Assistant Admin."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DEFAULT_SETTINGS, SETTINGS_FILE, STATE_DIR_NAME


def load_settings(hass: HomeAssistant) -> dict[str, Any]:
    """Load settings written by the installer app."""
    settings = dict(DEFAULT_SETTINGS)
    path = Path(hass.config.config_dir) / STATE_DIR_NAME / SETTINGS_FILE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return settings
    if isinstance(raw, dict):
        for key, default in DEFAULT_SETTINGS.items():
            if key in raw and isinstance(raw[key], type(default)):
                settings[key] = raw[key]
    return settings
