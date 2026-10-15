"""Constants for the IBC Chur integration."""

from datetime import timedelta

DOMAIN = "ibc_chur"
PLATFORMS = ["sensor"]

CONF_ACCESS_TOKEN = "access_token"
CONF_SUBJECT_ID = "subject_id"
CONF_METERINGPOINT = "meteringpoint"
CONF_ROLE = "role"
CONF_AGGREGATION = "aggregation"
CONF_HISTORY_DAYS = "history_days"

DEFAULT_BASE_URL = "https://portal.ibc-chur.ch/ebp/api/ebp"
DEFAULT_ROLE = 2
DEFAULT_AGGREGATION = 1
DEFAULT_HISTORY_DAYS = 30
DEFAULT_UPDATE_INTERVAL = timedelta(hours=12)

ATTR_STATISTIC_ID = "statistic_id"
ATTR_METERINGPOINT = "meteringpoint"
