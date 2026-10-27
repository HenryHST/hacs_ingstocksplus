"""Shared helpers: portfolio aggregation and market-hours polling."""

from __future__ import annotations

import hashlib
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_QUANTITY,
    DEFAULT_QUANTITY,
    DOMAIN,
    OFF_MARKET_SCAN_INTERVAL_MIN,
    POLL_JITTER_MAX_SEC,
)

_BERLIN = ZoneInfo("Europe/Berlin")
_NY = ZoneInfo("America/New_York")

# Xetra cash equity approx. 09:00–17:30 CET/CEST
_XETRA_OPEN = time(9, 0)
_XETRA_CLOSE = time(17, 30)
# US regular session 09:30–16:00 ET
_US_OPEN = time(9, 30)
_US_CLOSE = time(16, 0)


def poll_jitter_seconds(stable_key: str, *, max_sec: int = POLL_JITTER_MAX_SEC) -> int:
    """Deterministic 0..max_sec jitter from entry id / ISIN."""
    if max_sec <= 0:
        return 0
    digest = hashlib.sha256(stable_key.encode("utf-8")).digest()
    return int.from_bytes(digest[:2], "big") % (max_sec + 1)


def iter_coordinators(hass: HomeAssistant) -> list[tuple[str, Any]]:
    """Return (entry_id, coordinator) pairs from hass.data."""
    # Local import avoids circular dependency with coordinator.py
    from .coordinator import INGStocksCoordinator

    out: list[tuple[str, Any]] = []
    for key, value in hass.data.get(DOMAIN, {}).items():
        if isinstance(value, INGStocksCoordinator):
            out.append((key, value))
    return out


def entry_quantity(entry: ConfigEntry) -> float:
    q = entry.options.get(CONF_QUANTITY, entry.data.get(CONF_QUANTITY, DEFAULT_QUANTITY))
    try:
        qf = float(q)
        return qf if qf >= 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


def normalize_currency(value: Any) -> str | None:
    """Normalize currency signs/codes for comparison (€ → EUR)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    mapping = {
        "€": "EUR",
        "eur": "EUR",
        "$": "USD",
        "us$": "USD",
        "usd": "USD",
        "£": "GBP",
        "gbp": "GBP",
        "chf": "CHF",
    }
    lower = text.lower()
    if lower in mapping:
        return mapping[lower]
    if text.upper() in {"EUR", "USD", "GBP", "CHF", "JPY", "CAD", "AUD"}:
        return text.upper()
    return text


def _weekday_session_open(
    local_dt: datetime,
    open_t: time,
    close_t: time,
) -> bool:
    if local_dt.weekday() >= 5:  # Sat/Sun
        return False
    t = local_dt.time()
    return open_t <= t < close_t


def is_market_hours(now: datetime | None = None) -> bool:
    """True if Xetra or US regular session is open."""
    now = now or datetime.now(tz=_BERLIN)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_BERLIN)
    berlin = now.astimezone(_BERLIN)
    ny = now.astimezone(_NY)
    return _weekday_session_open(berlin, _XETRA_OPEN, _XETRA_CLOSE) or _weekday_session_open(
        ny, _US_OPEN, _US_CLOSE
    )


def effective_scan_interval_minutes(
    base_minutes: int,
    *,
    market_hours_polling: bool,
    now: datetime | None = None,
    off_market_minutes: int = OFF_MARKET_SCAN_INTERVAL_MIN,
) -> int:
    """Return poll interval; stretch when markets closed and option enabled."""
    base = max(1, int(base_minutes))
    if not market_hours_polling:
        return base
    if is_market_hours(now):
        return base
    return max(base, int(off_market_minutes))


def compute_portfolio_summary(hass: HomeAssistant) -> dict[str, Any]:
    """Sum position values across entries sharing the primary currency.

    Positions in other currencies are listed under excluded; mixed currencies
    set currency_mismatch True.
    """
    positions: list[dict[str, Any]] = []
    currencies: dict[str, float] = {}

    for entry_id, coordinator in iter_coordinators(hass):
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            continue
        data = coordinator.data or {}
        price = data.get("price")
        try:
            price_f = float(price) if price is not None else None
        except (TypeError, ValueError):
            price_f = None
        qty = entry_quantity(entry)
        currency = normalize_currency(data.get("currency"))
        if price_f is None or qty <= 0:
            continue
        value = round(price_f * qty, 2)
        positions.append(
            {
                "entry_id": entry_id,
                "isin": data.get("isin") or entry.data.get("isin"),
                "name": coordinator.display_name or entry.title,
                "quantity": qty,
                "unit_price": price_f,
                "value": value,
                "currency": currency,
            }
        )
        if currency:
            currencies[currency] = currencies.get(currency, 0.0) + value

    if not positions:
        return {
            "total": None,
            "currency": None,
            "currency_mismatch": False,
            "included": [],
            "excluded": [],
            "position_count": 0,
        }

    primary = max(currencies, key=lambda c: currencies[c]) if currencies else None
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    total = 0.0
    for pos in positions:
        if primary is None or pos["currency"] == primary:
            included.append(pos)
            total += float(pos["value"])
        else:
            excluded.append(pos)

    return {
        "total": round(total, 2) if included else None,
        "currency": primary,
        "currency_mismatch": bool(excluded),
        "included": included,
        "excluded": excluded,
        "position_count": len(included),
    }
