"""Constants for ING Stocks Plus."""

DOMAIN = "ingstocksplus"

# ING API (public, unofficial)
API_BASE_URL = "https://component-api.wertpapiere.ing.de/api/v1"
API_TIMEOUT = 20
API_RETRY_ATTEMPTS = 2
API_RETRY_DELAY_SEC = 5

# Yahoo ISIN→symbol cache TTL and poll stagger
YAHOO_SYMBOL_CACHE_TTL_SEC = 24 * 60 * 60
POLL_JITTER_MAX_SEC = 30

# Off-hours polling when market_hours_polling is enabled
OFF_MARKET_SCAN_INTERVAL_MIN = 60

CONF_ISIN = "isin"
CONF_NAME = "name"
CONF_SCAN_INTERVAL = "scan_interval"
# Legacy only: still read from existing entries; no longer shown in config/options
CONF_INSTRUMENT_TYPE = "instrument_type"
CONF_QUANTITY = "quantity"
CONF_YAHOO_FALLBACK = "yahoo_fallback"
CONF_MARKET_HOURS_POLLING = "market_hours_polling"

DEFAULT_SCAN_INTERVAL = 15
DEFAULT_QUANTITY = 0.0
DEFAULT_YAHOO_FALLBACK = True
DEFAULT_MARKET_HOURS_POLLING = False
DEFAULT_INSTRUMENT_TYPE = "auto"

SERVICE_REFRESH = "refresh"

ATTR_ENTRY_ID = "entry_id"
ATTR_ISIN = "isin"

# hass.data keys that are not coordinators
DATA_YAHOO_CACHE = "yahoo_symbol_cache"
DATA_PORTFOLIO_ADDED = "portfolio_sensor_added"
