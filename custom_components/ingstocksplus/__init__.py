from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DOMAIN,
    CONF_SCAN_INTERVAL,
    CONF_NAME,
    DEFAULT_SCAN_INTERVAL,
)
from .coordinator import INGStocksCoordinator

PLATFORMS = ["sensor"]
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration (YAML hook, unused)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    isin: str = entry.data["isin"]

    if CONF_SCAN_INTERVAL in entry.options:
        scan_interval_min = int(entry.options[CONF_SCAN_INTERVAL])
        interval_source = "options"
    else:
        scan_interval_min = int(entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        interval_source = "data"

    coordinator = INGStocksCoordinator(
        hass=hass,
        isin=isin,
        update_interval=timedelta(minutes=scan_interval_min),
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        raise
    except Exception as err:
        raise ConfigEntryNotReady(str(err)) from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    _LOGGER.info(
        "ING Stocks Plus setup: ISIN=%s, scan_interval=%s min (source=%s)",
        isin,
        scan_interval_min,
        interval_source,
    )

    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply options to coordinator without full reload (interval/name take effect immediately)."""
    coordinator: INGStocksCoordinator | None = (hass.data.get(DOMAIN) or {}).get(entry.entry_id)
    if coordinator is None:
        return
    scan_interval_min = int(
        entry.options.get(CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    )
    coordinator.update_interval = timedelta(minutes=scan_interval_min)
    custom_name = entry.options.get(CONF_NAME, entry.data.get(CONF_NAME))
    if custom_name:
        coordinator.display_name = custom_name
    else:
        coordinator.display_name = (coordinator.data or {}).get("name") or entry.title


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok