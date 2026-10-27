"""Diagnostics support for ING Stocks Plus."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_MARKET_HOURS_POLLING,
    CONF_NAME,
    CONF_QUANTITY,
    CONF_SCAN_INTERVAL,
    CONF_YAHOO_FALLBACK,
    DEFAULT_MARKET_HOURS_POLLING,
    DEFAULT_QUANTITY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_YAHOO_FALLBACK,
    DOMAIN,
)
from .coordinator import INGStocksCoordinator
from .helpers import compute_portfolio_summary, is_market_hours


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry (no secrets)."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    data: dict[str, Any] = {}
    if isinstance(coordinator, INGStocksCoordinator) and coordinator.data:
        # Copy and drop nothing sensitive — API has no tokens
        data = dict(coordinator.data)

    entry_info = {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "isin": entry.data.get("isin"),
        "name": entry.options.get(CONF_NAME, entry.data.get(CONF_NAME)),
        "scan_interval": entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        ),
        "quantity": entry.options.get(
            CONF_QUANTITY, entry.data.get(CONF_QUANTITY, DEFAULT_QUANTITY)
        ),
        "yahoo_fallback": entry.options.get(
            CONF_YAHOO_FALLBACK,
            entry.data.get(CONF_YAHOO_FALLBACK, DEFAULT_YAHOO_FALLBACK),
        ),
        "market_hours_polling": entry.options.get(
            CONF_MARKET_HOURS_POLLING,
            entry.data.get(CONF_MARKET_HOURS_POLLING, DEFAULT_MARKET_HOURS_POLLING),
        ),
    }

    coordinator_info: dict[str, Any] = {}
    if isinstance(coordinator, INGStocksCoordinator):
        coordinator_info = {
            "isin": coordinator.isin,
            "display_name": coordinator.display_name,
            "last_update_success": coordinator.last_update_success,
            "last_error": coordinator.last_error,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
            "base_scan_interval_minutes": coordinator.base_scan_interval_minutes,
            "market_hours_polling": coordinator.market_hours_polling,
            "yahoo_fallback": coordinator.yahoo_fallback,
            "markets_open_now": is_market_hours(),
        }

    portfolio = compute_portfolio_summary(hass)
    # Avoid dumping full included/excluded lists with entry internals twice
    portfolio_brief = {
        "total": portfolio.get("total"),
        "currency": portfolio.get("currency"),
        "currency_mismatch": portfolio.get("currency_mismatch"),
        "position_count": portfolio.get("position_count"),
        "excluded_count": len(portfolio.get("excluded") or []),
    }

    return {
        "entry": entry_info,
        "coordinator": coordinator_info,
        "data": data,
        "portfolio": portfolio_brief,
    }
