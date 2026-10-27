"""ING Stocks Plus integration setup."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_YAHOO_FALLBACK,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_YAHOO_FALLBACK,
    DOMAIN,
)
from .coordinator import INGStocksCoordinator

PLATFORMS = ["sensor"]
_LOGGER = logging.getLogger(__name__)


def _yahoo_fallback_enabled(entry: ConfigEntry) -> bool:
    if CONF_YAHOO_FALLBACK in entry.options:
        return bool(entry.options[CONF_YAHOO_FALLBACK])
    return bool(entry.data.get(CONF_YAHOO_FALLBACK, DEFAULT_YAHOO_FALLBACK))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    isin: str = entry.data["isin"]

    if CONF_SCAN_INTERVAL in entry.options:
        scan_interval_min = int(entry.options[CONF_SCAN_INTERVAL])
        interval_source = "options"
    else:
        scan_interval_min = int(
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        interval_source = "data"

    yahoo_fallback = _yahoo_fallback_enabled(entry)

    coordinator = INGStocksCoordinator(
        hass=hass,
        isin=isin,
        update_interval=timedelta(minutes=scan_interval_min),
        yahoo_fallback=yahoo_fallback,
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        raise
    except Exception as err:
        raise ConfigEntryNotReady(str(err)) from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    custom_name = entry.options.get(CONF_NAME, entry.data.get(CONF_NAME))
    if custom_name:
        coordinator.display_name = custom_name
    else:
        coordinator.display_name = (coordinator.data or {}).get("name") or entry.title

    _LOGGER.info(
        "ING Stocks Plus setup: ISIN=%s, scan_interval=%s min (source=%s), yahoo_fallback=%s",
        isin,
        scan_interval_min,
        interval_source,
        yahoo_fallback,
    )

    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry so quantity/type/name/interval/fallback changes apply cleanly."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
