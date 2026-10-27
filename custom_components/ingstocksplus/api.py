"""ING component-api and optional Yahoo Finance fallback helpers."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import API_BASE_URL, API_TIMEOUT

_LOGGER = logging.getLogger(__name__)

ISIN_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
YAHOO_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"
# v7/v10 quote endpoints often require crumbs (401); chart+events stays open
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
}


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
    url = f"{API_BASE_URL}/instrument-header?isinOrSearchTerm={quote(isin)}"
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
    url = f"{API_BASE_URL}/share/keyfigures/{quote(isin)}"
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
    *,
    keyfigures_source: str = "ing",
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
        "keyfigures_source": keyfigures_source,
        "dividend_yield": keyfigures.get("dividendYield"),
        "dividend_per_share": keyfigures.get("dividendPerShare"),
        "price_earnings_ratio": keyfigures.get("priceEarningsRatio"),
        "market_capitalization": keyfigures.get("marketCapitalization"),
        "market_cap_currency": keyfigures.get("marketCapitalizationCurrencyIsoCode"),
        "52w_low": keyfigures.get("fiftyTwoWeekLow"),
        "52w_high": keyfigures.get("fiftyTwoWeekHigh"),
    }


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


async def async_resolve_yahoo_symbol(
    hass: HomeAssistant,
    isin: str,
) -> str | None:
    """Resolve ISIN to a Yahoo Finance symbol via unofficial search."""
    session = _session(hass)
    url = f"{YAHOO_SEARCH_URL}?q={quote(isin)}&quotesCount=5&newsCount=0"
    try:
        async with session.get(
            url, headers=YAHOO_HEADERS, timeout=_client_timeout()
        ) as resp:
            if resp.status != 200:
                _LOGGER.debug("Yahoo search HTTP %s for %s", resp.status, isin)
                return None
            payload = await resp.json()
    except (aiohttp.ClientError, TimeoutError, OSError) as err:
        _LOGGER.debug("Yahoo search failed for %s: %s", isin, err)
        return None

    quotes = payload.get("quotes") if isinstance(payload, dict) else None
    if not isinstance(quotes, list):
        return None

    isin_upper = isin.upper()
    for quote_item in quotes:
        if not isinstance(quote_item, dict):
            continue
        symbol = quote_item.get("symbol")
        if not symbol:
            continue
        if str(quote_item.get("isin") or "").upper() == isin_upper:
            return str(symbol)
        # Prefer equity/ETF quotes when ISIN field is absent
        quote_type = str(quote_item.get("quoteType") or "").upper()
        if quote_type in {"EQUITY", "ETF", "MUTUALFUND"}:
            return str(symbol)

    for quote_item in quotes:
        if isinstance(quote_item, dict) and quote_item.get("symbol"):
            return str(quote_item["symbol"])
    return None


async def async_fetch_yahoo_keyfigures(
    hass: HomeAssistant,
    isin: str,
) -> dict[str, Any]:
    """Fetch dividend fields from Yahoo chart events. Soft-fails to {}.

    P/E is typically provided by ING for equities; Yahoo quote APIs often require
    auth crumbs, so this fallback focuses on dividends via the open chart API.
    """
    symbol = await async_resolve_yahoo_symbol(hass, isin)
    if not symbol:
        return {}

    session = _session(hass)
    url = (
        f"{YAHOO_CHART_URL}/{quote(symbol)}"
        f"?range=1y&interval=1mo&events=div%7Csplit"
    )
    try:
        async with session.get(
            url, headers=YAHOO_HEADERS, timeout=_client_timeout()
        ) as resp:
            if resp.status != 200:
                _LOGGER.debug(
                    "Yahoo chart HTTP %s for %s (%s)", resp.status, isin, symbol
                )
                return {}
            payload = await resp.json()
    except (aiohttp.ClientError, TimeoutError, OSError) as err:
        _LOGGER.debug("Yahoo chart failed for %s (%s): %s", isin, symbol, err)
        return {}

    chart = payload.get("chart", {}) if isinstance(payload, dict) else {}
    result = chart.get("result")
    if not isinstance(result, list) or not result or not isinstance(result[0], dict):
        return {}

    item = result[0]
    meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
    events = item.get("events") if isinstance(item.get("events"), dict) else {}
    dividends = events.get("dividends") if isinstance(events.get("dividends"), dict) else {}

    out: dict[str, Any] = {"yahoo_symbol": symbol}

    if dividends:
        ordered = sorted(
            (d for d in dividends.values() if isinstance(d, dict)),
            key=lambda d: int(d.get("date") or 0),
        )
        last_four = ordered[-4:]
        annual = 0.0
        for div in last_four:
            amount = _safe_float(div.get("amount"))
            if amount is not None:
                annual += amount
        if annual > 0:
            out["dividendPerShare"] = round(annual, 4)
            price = _safe_float(meta.get("regularMarketPrice"))
            if price and price > 0:
                out["dividendYield"] = round((annual / price) * 100, 4)

    return out


def merge_keyfigures_with_yahoo(
    mapped: dict[str, Any],
    yahoo: dict[str, Any],
) -> dict[str, Any]:
    """Fill missing dividend/PE fields from Yahoo; set keyfigures_source."""
    if not yahoo:
        if mapped.get("keyfigures_source") is None:
            mapped["keyfigures_source"] = "ing"
        return mapped

    filled = False
    ing_had = bool(mapped.get("keyfigures_available"))

    for mapped_key, yahoo_key in (
        ("dividend_per_share", "dividendPerShare"),
        ("dividend_yield", "dividendYield"),
        ("price_earnings_ratio", "priceEarningsRatio"),
    ):
        if mapped.get(mapped_key) is None and yahoo.get(yahoo_key) is not None:
            mapped[mapped_key] = yahoo[yahoo_key]
            filled = True

    if yahoo.get("yahoo_symbol"):
        mapped["yahoo_symbol"] = yahoo["yahoo_symbol"]

    if filled and ing_had:
        mapped["keyfigures_source"] = "mixed"
        mapped["keyfigures_available"] = True
    elif filled:
        mapped["keyfigures_source"] = "yahoo"
        mapped["keyfigures_available"] = True
    else:
        mapped["keyfigures_source"] = "ing" if ing_had else mapped.get(
            "keyfigures_source", "ing"
        )

    return mapped
