"""Unit tests for ING Stocks Plus API helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ingstocksplus.api import (
    INGApiError,
    async_fetch_instrument_header,
    async_fetch_keyfigures,
    map_instrument_data,
    normalize_isin,
)


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


def _mock_response(status: int, payload: dict | None) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    resp.json = AsyncMock(return_value=payload)
    return resp


@pytest.mark.asyncio
async def test_fetch_header_success() -> None:
    session = MagicMock()
    session.get = MagicMock(return_value=_mock_response(200, {"price": 12.3, "name": "X"}))
    hass = MagicMock()

    with patch(
        "custom_components.ingstocksplus.api.async_get_clientsession",
        return_value=session,
    ):
        data = await async_fetch_instrument_header(hass, "IE00B3RBWM25")

    assert data["price"] == 12.3


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
async def test_fetch_keyfigures_success() -> None:
    session = MagicMock()
    session.get = MagicMock(
        return_value=_mock_response(200, {"dividendYield": 2.0})
    )
    hass = MagicMock()

    with patch(
        "custom_components.ingstocksplus.api.async_get_clientsession",
        return_value=session,
    ):
        data, available = await async_fetch_keyfigures(hass, "IE00B3RBWM25")

    assert available is True
    assert data["dividendYield"] == 2.0


def test_position_value_math() -> None:
    price = 100.123
    quantity = 2.5
    assert round(price * quantity, 2) == 250.31
