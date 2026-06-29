"""Constants for Chur Kultur."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "chur_kultur"
NAME: Final = "Chur Kultur"
SOURCE_URL: Final = "https://www.chur-kultur.ch"
AGENDA_PATH: Final = "/de/agenda-extended"
DEFAULT_TAG_IDS: Final = [
    "-127845656590664",
    "-125542656590664",
    "-125176656590664",
    "-125178656590664",
    "-125115656590664",
    "-126222656590664",
    "-125545656590664",
    "-125518656590664",
    "-100296656590664",
    "-125871656590664",
    "-125541656590664",
]
DEFAULT_DAYS: Final = 30
DEFAULT_MAX_EVENTS: Final = 20
UPDATE_INTERVAL: Final = timedelta(hours=3)

CONF_DAYS: Final = "days"
CONF_MAX_EVENTS: Final = "max_events"
CONF_SEARCH: Final = "search"
CONF_TAG_IDS: Final = "tag_ids"
