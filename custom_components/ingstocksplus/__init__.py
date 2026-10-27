"""ING Stocks Plus integration setup."""

from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_ENTRY_ID,
    ATTR_ISIN,
    CONF_MARKET_HOURS_POLLING,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_YAHOO_FALLBACK,
    DEFAULT_MARKET_HOURS_POLLING,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_YAHOO_FALLBACK,
    DOMAIN,
    SERVICE_REFRESH,
)
from .coordinator import INGStocksCoordinator
from .helpers import (
    effective_scan_interval_minutes,
    iter_coordinators,
    poll_jitter_seconds,
)

PLATFORMS = ["sensor"]
_LOGGER = logging.getLogger(__name__)

SERVICE_REFRESH_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
        vol.Optional(ATTR_ISIN): cv.string,
    }
)


def _yahoo_fallback_enabled(entry: ConfigEntry) -> bool:
    if CONF_YAHOO_FALLBACK in entry.options:
        return bool(entry.options[CONF_YAHOO_FALLBACK])
    return bool(entry.data.get(CONF_YAHOO_FALLBACK, DEFAULT_YAHOO_FALLBACK))


def _market_hours_polling_enabled(entry: ConfigEntry) -> bool:
    if CONF_MARKET_HOURS_POLLING in entry.options:
        return bool(entry.options[CONF_MARKET_HOURS_POLLING])
    return bool(entry.data.get(CONF_MARKET_HOURS_POLLING, DEFAULT_MARKET_HOURS_POLLING))


# Re-export for backward-compatible imports / tests
__all__ = ["async_setup", "async_setup_entry", "async_unload_entry", "poll_jitter_seconds"]


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Set up domain-level services once."""
    hass.data.setdefault(DOMAIN, {})

    async def async_handle_refresh(call: ServiceCall) -> None:
        entry_id = call.data.get(ATTR_ENTRY_ID)
        isin = (call.data.get(ATTR_ISIN) or "").strip().upper() or None
        targets: list[INGStocksCoordinator] = []

        for eid, coordinator in iter_coordinators(hass):
            if entry_id and eid != entry_id:
                continue
            if isin and coordinator.isin.upper() != isin:
                continue
            targets.append(coordinator)

        if (entry_id or isin) and not targets:
            raise HomeAssistantError(
                f"No ING Stocks Plus coordinator matched "
                f"(entry_id={entry_id!r}, isin={isin!r})"
            )

        if not targets:
            targets = [c for _, c in iter_coordinators(hass)]

        if not targets:
            raise HomeAssistantError("No ING Stocks Plus entries are loaded")

        for coordinator in targets:
            await coordinator.async_request_refresh()

        _LOGGER.info(
            "Manual refresh requested for %s coordinator(s)",
            len(targets),
        )

    if not hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REFRESH,
            async_handle_refresh,
            schema=SERVICE_REFRESH_SCHEMA,
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    # Ensure domain services exist even when YAML config is empty
    await async_setup(hass, {})

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
    market_hours_polling = _market_hours_polling_enabled(entry)
    jitter = poll_jitter_seconds(entry.entry_id)
    effective_min = effective_scan_interval_minutes(
        scan_interval_min,
        market_hours_polling=market_hours_polling,
    )

    hass.data.setdefault(DOMAIN, {})

    coordinator = INGStocksCoordinator(
        hass=hass,
        isin=isin,
        update_interval=timedelta(minutes=effective_min, seconds=jitter),
        yahoo_fallback=yahoo_fallback,
        poll_jitter_seconds=jitter,
        base_scan_interval_minutes=scan_interval_min,
        market_hours_polling=market_hours_polling,
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        raise
    except Exception as err:
        raise ConfigEntryNotReady(str(err)) from err

    hass.data[DOMAIN][entry.entry_id] = coordinator

    custom_name = entry.options.get(CONF_NAME, entry.data.get(CONF_NAME))
    if custom_name:
        coordinator.display_name = custom_name
    else:
        coordinator.display_name = (coordinator.data or {}).get("name") or entry.title

    _LOGGER.info(
        "ING Stocks Plus setup: ISIN=%s, scan_interval=%s min (effective=%s) "
        "+ %ss jitter (source=%s), yahoo_fallback=%s, market_hours_polling=%s",
        isin,
        scan_interval_min,
        effective_min,
        jitter,
        interval_source,
        yahoo_fallback,
        market_hours_polling,
    )

    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry so quantity/name/interval/fallback changes apply cleanly."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
