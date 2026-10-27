"""ING component-api client helpers."""

from __future__ import annotations

import logging
import re
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import API_BASE_URL, API_TIMEOUT

_LOGGER = logging.getLogger(__name__)

ISIN_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


class INGApiError(Exception):
    """Raised when the ING API request fails."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def normalize_isin(value: str) -> str:
    """Normalize and validate ISIN format (ISO 6166)."""
    isin = value.strip().upper()
    if not ISIN_PATTERN.match(isin):
        raise ValueError("invalid_isin")
    return isin


def _client_timeout() -> aiohttp.ClientTimeout:
    return aiohttp.ClientTimeout(total=API_TIMEOUT)


def _session(hass: HomeAssistant) -> aiohttp.ClientSession:
    return async_get_clientsession(hass)


async def async_fetch_instrument_header(
    hass: HomeAssistant,
    isin: str,
) -> dict[str, Any]:
    """Fetch instrument header. Raises INGApiError on failure."""
    url = f"{API_BASE_URL}/components/instrumentheader/{isin}"
    session = _session(hass)
    try:
        async with session.get(url, timeout=_client_timeout()) as resp:
            if resp.status != 200:
                raise INGApiError(
                    f"instrumentheader HTTP {resp.status}",
                    status=resp.status,
                )
            data = await resp.json()
    except (aiohttp.ClientError, TimeoutError, OSError) as err:
        raise INGApiError(f"instrumentheader fetch failed: {err}") from err

    if not isinstance(data, dict) or data.get("price") is None:
        raise INGApiError("No price in instrumentheader")
    return data


async def async_fetch_keyfigures(
    hass: HomeAssistant,
    isin: str,
) -> tuple[dict[str, Any], bool]:
    """Fetch keyfigures. Soft-fails: returns ({}, False) on any non-success."""
    url = f"{API_BASE_URL}/share-ng/keyfigures/{isin}"
    session = _session(hass)
    try:
        async with session.get(url, timeout=_client_timeout()) as resp:
            if resp.status == 404:
                _LOGGER.debug("No keyfigures for %s (HTTP 404).", isin)
                return {}, False
            if resp.status != 200:
                _LOGGER.warning(
                    "Keyfigures unavailable for %s (HTTP %s); continuing with price only.",
                    isin,
                    resp.status,
                )
                return {}, False
            data = await resp.json()
            if isinstance(data, dict):
                return data, True
            return {}, False
    except (aiohttp.ClientError, TimeoutError, OSError) as err:
        _LOGGER.warning(
            "Keyfigures fetch failed for %s: %s; continuing with price only.",
            isin,
            err,
        )
        return {}, False


def map_instrument_data(
    isin: str,
    header: dict[str, Any],
    keyfigures: dict[str, Any],
    keyfigures_available: bool,
) -> dict[str, Any]:
    """Normalize ING API payloads into coordinator data."""
    return {
        "name": header.get("name"),
        "isin": header.get("isin") or isin,
        "currency": header.get("currencySign"),
        "change_percent": header.get("changePercent"),
        "change_absolute": header.get("changeAbsolute"),
        "exchange": header.get("exchangeName"),
        "last_update": header.get("priceChangeDate"),
        "price": header.get("price"),
        "keyfigures_available": bool(keyfigures_available),
        "dividend_yield": keyfigures.get("dividendYield"),
        "dividend_per_share": keyfigures.get("dividendPerShare"),
        "price_earnings_ratio": keyfigures.get("priceEarningsRatio"),
        "market_capitalization": keyfigures.get("marketCapitalization"),
        "market_cap_currency": keyfigures.get("marketCapitalizationCurrencyIsoCode"),
        "52w_low": keyfigures.get("fiftyTwoWeekLow"),
        "52w_high": keyfigures.get("fiftyTwoWeekHigh"),
    }
