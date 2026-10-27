"""Coordinator update behaviour tests."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ingstocksplus.coordinator import INGStocksCoordinator


@pytest.mark.asyncio
async def test_coordinator_parallel_fetch_and_merge() -> None:
    hass = MagicMock()
    coordinator = INGStocksCoordinator(
        hass,
        "US0378331005",
        timedelta(minutes=15),
        yahoo_fallback=True,
        poll_jitter_seconds=0,
        base_scan_interval_minutes=15,
        market_hours_polling=False,
    )

    header = {
        "name": "Apple",
        "isin": "US0378331005",
        "currencySign": "EUR",
        "price": 180.0,
        "changePercent": 1.0,
        "changeAbsolute": 1.5,
        "exchangeName": "Xetra",
        "priceChangeDate": "2024-01-01T10:00:00Z",
    }
    keyfigures = {"priceEarningsRatio": 30.0}

    with patch(
        "custom_components.ingstocksplus.coordinator.async_fetch_instrument_header",
        new=AsyncMock(return_value=header),
    ), patch(
        "custom_components.ingstocksplus.coordinator.async_fetch_keyfigures",
        new=AsyncMock(return_value=(keyfigures, True)),
    ), patch(
        "custom_components.ingstocksplus.coordinator.async_fetch_yahoo_keyfigures",
        new=AsyncMock(
            return_value={
                "yahoo_symbol": "AAPL",
                "dividendPerShare": 1.0,
                "dividendYield": 0.5,
            }
        ),
    ) as yahoo:
        data = await coordinator._async_update_data()

    assert data["price"] == 180.0
    assert data["price_earnings_ratio"] == 30.0
    assert data["dividend_per_share"] == 1.0
    assert data["keyfigures_source"] == "mixed"
    assert data["yahoo_symbol"] == "AAPL"
    yahoo.assert_awaited_once()
    assert coordinator.last_error is None


@pytest.mark.asyncio
async def test_coordinator_skips_yahoo_when_complete() -> None:
    hass = MagicMock()
    coordinator = INGStocksCoordinator(
        hass,
        "US0378331005",
        timedelta(minutes=15),
        yahoo_fallback=True,
        poll_jitter_seconds=0,
    )
    header = {
        "name": "Apple",
        "isin": "US0378331005",
        "currencySign": "EUR",
        "price": 180.0,
    }
    keyfigures = {
        "priceEarningsRatio": 30.0,
        "dividendPerShare": 1.0,
        "dividendYield": 0.5,
    }

    with patch(
        "custom_components.ingstocksplus.coordinator.async_fetch_instrument_header",
        new=AsyncMock(return_value=header),
    ), patch(
        "custom_components.ingstocksplus.coordinator.async_fetch_keyfigures",
        new=AsyncMock(return_value=(keyfigures, True)),
    ), patch(
        "custom_components.ingstocksplus.coordinator.async_fetch_yahoo_keyfigures",
        new=AsyncMock(return_value={}),
    ) as yahoo:
        data = await coordinator._async_update_data()

    assert data["keyfigures_source"] == "ing"
    yahoo.assert_not_awaited()
