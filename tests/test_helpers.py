"""Tests for portfolio and market-hours helpers."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from custom_components.ingstocksplus.helpers import (
    compute_portfolio_summary,
    effective_scan_interval_minutes,
    is_market_hours,
    normalize_currency,
)


def test_normalize_currency() -> None:
    assert normalize_currency("€") == "EUR"
    assert normalize_currency("eur") == "EUR"
    assert normalize_currency("$") == "USD"
    assert normalize_currency("USD") == "USD"
    assert normalize_currency(None) is None


def test_is_market_hours_weekday_xetra() -> None:
    now = datetime(2024, 6, 12, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    assert is_market_hours(now) is True


def test_is_market_hours_weekend() -> None:
    now = datetime(2024, 6, 15, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    assert is_market_hours(now) is False


def test_is_market_hours_evening_berlin_us_open() -> None:
    now = datetime(2024, 6, 12, 18, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    assert is_market_hours(now) is True


def test_is_market_hours_night() -> None:
    now = datetime(2024, 6, 12, 3, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    assert is_market_hours(now) is False


def test_effective_scan_interval_off_hours() -> None:
    night = datetime(2024, 6, 12, 3, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    assert (
        effective_scan_interval_minutes(
            15, market_hours_polling=True, now=night, off_market_minutes=60
        )
        == 60
    )
    assert (
        effective_scan_interval_minutes(15, market_hours_polling=False, now=night) == 15
    )


def test_effective_scan_interval_market_open() -> None:
    noon = datetime(2024, 6, 12, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    assert (
        effective_scan_interval_minutes(15, market_hours_polling=True, now=noon) == 15
    )


def _coord(price: float, currency: str, isin: str, name: str) -> MagicMock:
    c = MagicMock()
    c.data = {"price": price, "currency": currency, "isin": isin}
    c.display_name = name
    c.isin = isin
    return c


def _entry(isin: str, quantity: float, title: str) -> MagicMock:
    e = MagicMock()
    e.options = {"quantity": quantity}
    e.data = {"isin": isin}
    e.title = title
    return e


def test_compute_portfolio_same_currency() -> None:
    hass = MagicMock()
    coord_a = _coord(100.0, "€", "AAA", "A")
    coord_b = _coord(50.0, "EUR", "BBB", "B")
    entry_a = _entry("AAA", 2, "A")
    entry_b = _entry("BBB", 4, "B")
    hass.config_entries.async_get_entry.side_effect = lambda eid: {
        "e1": entry_a,
        "e2": entry_b,
    }[eid]

    with patch(
        "custom_components.ingstocksplus.helpers.iter_coordinators",
        return_value=[("e1", coord_a), ("e2", coord_b)],
    ):
        summary = compute_portfolio_summary(hass)

    assert summary["total"] == 400.0
    assert summary["currency"] == "EUR"
    assert summary["currency_mismatch"] is False
    assert summary["position_count"] == 2


def test_compute_portfolio_currency_mismatch() -> None:
    hass = MagicMock()
    coord_a = _coord(100.0, "EUR", "AAA", "A")
    coord_b = _coord(10.0, "USD", "BBB", "B")
    entry_a = _entry("AAA", 1, "A")
    entry_b = _entry("BBB", 1, "B")
    hass.config_entries.async_get_entry.side_effect = lambda eid: {
        "e1": entry_a,
        "e2": entry_b,
    }[eid]

    with patch(
        "custom_components.ingstocksplus.helpers.iter_coordinators",
        return_value=[("e1", coord_a), ("e2", coord_b)],
    ):
        summary = compute_portfolio_summary(hass)

    assert summary["total"] == 100.0
    assert summary["currency"] == "EUR"
    assert summary["currency_mismatch"] is True
    assert len(summary["excluded"]) == 1
    assert summary["excluded"][0]["isin"] == "BBB"
