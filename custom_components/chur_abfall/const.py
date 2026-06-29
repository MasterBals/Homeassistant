"""Constants for Chur Abfall."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "chur_abfall"
NAME: Final = "Chur Abfall"
SOURCE_URL: Final = "https://www.chur.ch/abfallstrassenabschnitte"
UPDATE_INTERVAL: Final = timedelta(hours=6)
CONF_STREETS: Final = "streets"
CONF_WASTE_TYPES: Final = "waste_types"
DEFAULT_WASTE_TYPES: Final = ["Papier", "Karton", "Kompost", "Kehricht"]
SERVICE_REFRESH: Final = "refresh"
SERVICE_RELOAD: Final = "reload"
SERVICE_EXPORT: Final = "export"
