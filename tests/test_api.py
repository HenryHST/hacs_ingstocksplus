"""Unit tests for ING Stocks Plus API helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ingstocksplus.api import (
    YAHOO_SYMBOL_CACHE_KEY,
    INGApiError,
    async_fetch_instrument_header,
    async_fetch_keyfigures,
    async_fetch_yahoo_keyfigures,
    async_resolve_yahoo_symbol,
    map_instrument_data,
    merge_keyfigures_with_yahoo,
    normalize_isin,
)
from custom_components.ingstocksplus.const import DOMAIN
from custom_components.ingstocksplus.helpers import poll_jitter_seconds


def test_normalize_isin_valid() -> None:
    assert normalize_isin(" ie00b3rbwm25 ") == "IE00B3RBWM25"


@pytest.mark.parametrize("value", ["", "ABC", "IE00B3RBWM2", "IE00B3RBWM25X", "12INVALID!!!"])
def test_normalize_isin_invalid(value: str) -> None:
    with pytest.raises(ValueError, match="invalid_isin"):
        normalize_isin(value)


def test_map_instrument_data() -> None:
    data = map_instrument_data(
        "IE00B3RBWM25",
        {
            "name": "VWRL",
            "isin": "IE00B3RBWM25",
            "currencySign": "€",
            "changePercent": 1.2,
            "changeAbsolute": 0.5,
            "exchangeName": "Xetra",
            "priceChangeDate": "2024-01-01T10:00:00Z",
            "price": 100.5,
        },
        {
            "dividendYield": 1.5,
            "dividendPerShare": 1.1,
            "priceEarningsRatio": 18.0,
            "marketCapitalization": 1e9,
            "marketCapitalizationCurrencyIsoCode": "EUR",
            "fiftyTwoWeekLow": 90.0,
            "fiftyTwoWeekHigh": 110.0,
        },
        True,
    )
    assert data["price"] == 100.5
    assert data["currency"] == "€"
    assert data["keyfigures_available"] is True
    assert data["keyfigures_source"] == "ing"
    assert data["52w_low"] == 90.0
    assert data["dividend_yield"] == 1.5


def test_map_instrument_data_without_keyfigures() -> None:
    data = map_instrument_data(
        "IE00B3RBWM25",
        {"name": "VWRL", "price": 10, "currencySign": "€"},
        {},
        False,
    )
    assert data["keyfigures_available"] is False
    assert data["dividend_yield"] is None
    assert data["isin"] == "IE00B3RBWM25"


def _mock_response(status: int, payload: dict | list | None) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    resp.json = AsyncMock(return_value=payload)
    return resp


@pytest.mark.asyncio
async def test_fetch_header_uses_new_endpoint() -> None:
    session = MagicMock()
    session.get = MagicMock(return_value=_mock_response(200, {"price": 12.3, "name": "X"}))
    hass = MagicMock()

    with patch(
        "custom_components.ingstocksplus.api.async_get_clientsession",
        return_value=session,
    ):
        data = await async_fetch_instrument_header(hass, "IE00B3RBWM25")

    assert data["price"] == 12.3
    called_url = session.get.call_args.args[0]
    assert "instrument-header?isinOrSearchTerm=IE00B3RBWM25" in called_url


@pytest.mark.asyncio
async def test_fetch_header_http_error() -> None:
    session = MagicMock()
    session.get = MagicMock(return_value=_mock_response(404, {}))
    hass = MagicMock()

    with patch(
        "custom_components.ingstocksplus.api.async_get_clientsession",
        return_value=session,
    ), pytest.raises(INGApiError) as exc:
        await async_fetch_instrument_header(hass, "IE00B3RBWM25")
    assert exc.value.status == 404


@pytest.mark.asyncio
async def test_fetch_keyfigures_uses_share_path() -> None:
    session = MagicMock()
    session.get = MagicMock(
        return_value=_mock_response(200, {"priceEarningsRatio": 20.5})
    )
    hass = MagicMock()

    with patch(
        "custom_components.ingstocksplus.api.async_get_clientsession",
        return_value=session,
    ):
        data, available = await async_fetch_keyfigures(hass, "US0378331005")

    assert available is True
    assert data["priceEarningsRatio"] == 20.5
    called_url = session.get.call_args.args[0]
    assert called_url.endswith("/share/keyfigures/US0378331005")
    assert "/share-ng/" not in called_url


@pytest.mark.asyncio
async def test_fetch_keyfigures_404_soft_fail() -> None:
    session = MagicMock()
    session.get = MagicMock(return_value=_mock_response(404, {}))
    hass = MagicMock()

    with patch(
        "custom_components.ingstocksplus.api.async_get_clientsession",
        return_value=session,
    ):
        data, available = await async_fetch_keyfigures(hass, "IE00B3RBWM25")

    assert data == {}
    assert available is False


@pytest.mark.asyncio
async def test_fetch_keyfigures_500_soft_fail() -> None:
    session = MagicMock()
    session.get = MagicMock(return_value=_mock_response(500, {}))
    hass = MagicMock()

    with patch(
        "custom_components.ingstocksplus.api.async_get_clientsession",
        return_value=session,
    ):
        data, available = await async_fetch_keyfigures(hass, "IE00B3RBWM25")

    assert data == {}
    assert available is False


@pytest.mark.asyncio
async def test_yahoo_fallback_fills_gaps() -> None:
    session = MagicMock()

    def _get(url, **_kwargs):
        if "finance/search" in url:
            return _mock_response(
                200,
                {"quotes": [{"symbol": "AAPL", "quoteType": "EQUITY", "isin": "US0378331005"}]},
            )
        if "/v8/finance/chart/" in url:
            return _mock_response(
                200,
                {
                    "chart": {
                        "result": [
                            {
                                "meta": {"regularMarketPrice": 200.0, "symbol": "AAPL"},
                                "events": {
                                    "dividends": {
                                        "1": {"amount": 0.25, "date": 1},
                                        "2": {"amount": 0.25, "date": 2},
                                        "3": {"amount": 0.25, "date": 3},
                                        "4": {"amount": 0.25, "date": 4},
                                    }
                                },
                            }
                        ]
                    }
                },
            )
        return _mock_response(404, {})

    session.get = MagicMock(side_effect=_get)
    hass = MagicMock()

    with patch(
        "custom_components.ingstocksplus.api.async_get_clientsession",
        return_value=session,
    ):
        yahoo = await async_fetch_yahoo_keyfigures(hass, "US0378331005")

    assert yahoo["yahoo_symbol"] == "AAPL"
    assert yahoo["dividendPerShare"] == 1.0
    assert yahoo["dividendYield"] == pytest.approx(0.5)


def test_merge_keyfigures_with_yahoo_mixed() -> None:
    mapped = map_instrument_data(
        "US0378331005",
        {"name": "Apple", "price": 100, "currencySign": "EUR"},
        {"priceEarningsRatio": 30.0},
        True,
    )
    yahoo = {
        "yahoo_symbol": "AAPL",
        "dividendPerShare": 1.0,
        "dividendYield": 0.5,
    }
    merged = merge_keyfigures_with_yahoo(mapped, yahoo)
    assert merged["price_earnings_ratio"] == 30.0  # ING kept
    assert merged["dividend_per_share"] == 1.0
    assert merged["dividend_yield"] == 0.5
    assert merged["keyfigures_source"] == "mixed"
    assert merged["yahoo_symbol"] == "AAPL"


def test_merge_keyfigures_yahoo_only() -> None:
    mapped = map_instrument_data(
        "IE00B3RBWM25",
        {"name": "VWRL", "price": 100, "currencySign": "EUR"},
        {},
        False,
    )
    yahoo = {"yahoo_symbol": "VWRL.L", "dividendPerShare": 2.5}
    merged = merge_keyfigures_with_yahoo(mapped, yahoo)
    assert merged["dividend_per_share"] == 2.5
    assert merged["keyfigures_source"] == "yahoo"
    assert merged["keyfigures_available"] is True


def test_merge_yahoo_error_keeps_ing() -> None:
    mapped = map_instrument_data(
        "US0378331005",
        {"name": "Apple", "price": 100, "currencySign": "EUR"},
        {"priceEarningsRatio": 30.0},
        True,
    )
    merged = merge_keyfigures_with_yahoo(mapped, {})
    assert merged["price_earnings_ratio"] == 30.0
    assert merged["keyfigures_source"] == "ing"


def test_position_value_math() -> None:
    price = 100.123
    quantity = 2.5
    assert round(price * quantity, 2) == 250.31


def test_poll_jitter_is_stable_and_bounded() -> None:
    a = poll_jitter_seconds("entry-abc")
    b = poll_jitter_seconds("entry-abc")
    c = poll_jitter_seconds("entry-xyz")
    assert a == b
    assert 0 <= a <= 30
    assert 0 <= c <= 30


@pytest.mark.asyncio
async def test_yahoo_symbol_cache_hits_search_once() -> None:
    session = MagicMock()
    session.get = MagicMock(
        return_value=_mock_response(
            200,
            {"quotes": [{"symbol": "AAPL", "quoteType": "EQUITY", "isin": "US0378331005"}]},
        )
    )
    hass = MagicMock()
    hass.data = {}

    with patch(
        "custom_components.ingstocksplus.api.async_get_clientsession",
        return_value=session,
    ):
        first = await async_resolve_yahoo_symbol(hass, "US0378331005")
        second = await async_resolve_yahoo_symbol(hass, "US0378331005")

    assert first == "AAPL"
    assert second == "AAPL"
    assert session.get.call_count == 1
    assert "US0378331005" in hass.data[DOMAIN][YAHOO_SYMBOL_CACHE_KEY]
