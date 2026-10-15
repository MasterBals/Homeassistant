"""Constants for the IBC Chur integration."""

from datetime import timedelta

DOMAIN = "ibc_chur"
PLATFORMS = ["sensor"]

CONF_SUBJECT_ID = "subject_id"
CONF_OBJECT_ID = "object_id"
CONF_METERINGPOINT = "meteringpoint"
CONF_ROLE = "role"
CONF_INVOICE_CATEGORY = "invoice_category"
CONF_AGGREGATION = "aggregation"
CONF_HISTORY_DAYS = "history_days"

DEFAULT_API_ROOT = "https://portal.ibc-chur.ch/ebpapi"
DEFAULT_BASE_URL = f"{DEFAULT_API_ROOT}/ebp"
DEFAULT_SETTINGS_URL = f"{DEFAULT_API_ROOT}/settings"
PORTAL_URL = "https://portal.ibc-chur.ch"
PORTAL_METERDATA_URL = f"{PORTAL_URL}/ebp/consumption/meterdata"

OIDC_DISCOVERY_URL = (
    "https://login.ibc-chur.ch/auth/realms/ibc/.well-known/openid-configuration"
)
OAUTH_CLIENT_ID = "ebp-pkce"
OAUTH_SCOPE = "openid profile email"
OAUTH_REDIRECT_URI = "https://portal.ibc-chur.ch/?kcCallback=1"
OAUTH_REDIRECT_CANDIDATES = (OAUTH_REDIRECT_URI,)
OAUTH_LOCALE = "de"

DEFAULT_ROLE = 2
DEFAULT_INVOICE_CATEGORY = 1
DEFAULT_AGGREGATION = 1
DEFAULT_HISTORY_DAYS = 30
DEFAULT_UPDATE_INTERVAL = timedelta(hours=1)
TOKEN_KEEPALIVE_INTERVAL = timedelta(minutes=10)

ATTR_STATISTIC_ID = "statistic_id"
ATTR_METERINGPOINT = "meteringpoint"
