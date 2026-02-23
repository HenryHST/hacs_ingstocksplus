from __future__ import annotations

import asyncio
import logging
import socket
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    API_BASE_URL,
    API_TIMEOUT,
    API_RETRY_ATTEMPTS,
    API_RETRY_DELAY_SEC,
)

_LOGGER = logging.getLogger(__name__)


class INGStocksCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        isin: str,
        update_interval: timedelta,
    ) -> None:
        self.isin = isin
        self.display_name: str | None = None
        super().__init__(
            hass,
            _LOGGER,
            name=f"ING Stocks Plus {isin}",
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        header_url = f"{API_BASE_URL}/components/instrumentheader/{self.isin}"
        keyfigures_url = f"{API_BASE_URL}/share-ng/keyfigures/{self.isin}"

        # IPv4 force (helps in some HAOS DNS setups)
        session = async_get_clientsession(self.hass, family=socket.AF_INET)

        async def fetch_header() -> dict[str, Any]:
            async with session.get(header_url, timeout=API_TIMEOUT) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"instrumentheader HTTP {resp.status}")
                return await resp.json()

        async def fetch_keyfigures() -> tuple[dict[str, Any], bool]:
            async with session.get(keyfigures_url, timeout=API_TIMEOUT) as resp:
                if resp.status == 404:
                    _LOGGER.debug("No keyfigures for %s (HTTP 404).", self.isin)
                    return {}, False
                if resp.status != 200:
                    raise UpdateFailed(f"keyfigures HTTP {resp.status}")
                data = await resp.json()
                return data if isinstance(data, dict) else {}, isinstance(data, dict)

        header = {}
        keyfigures = {}
        keyfigures_available = False
        for attempt in range(API_RETRY_ATTEMPTS):
            try:
                header_result, (keyfigures, keyfigures_available) = await asyncio.gather(
                    fetch_header(),
                    fetch_keyfigures(),
                )
                header = header_result
                break
            except UpdateFailed:
                raise
            except (asyncio.TimeoutError, OSError, ConnectionError) as err:
                if attempt < API_RETRY_ATTEMPTS - 1:
                    _LOGGER.warning(
                        "Attempt %s/%s failed for %s: %s; retrying in %ss",
                        attempt + 1,
                        API_RETRY_ATTEMPTS,
                        self.isin,
                        err,
                        API_RETRY_DELAY_SEC,
                    )
                    await asyncio.sleep(API_RETRY_DELAY_SEC)
                else:
                    raise UpdateFailed(f"Fetch error {self.isin}: {err}") from err
            except Exception as err:
                raise UpdateFailed(f"Fetch error {self.isin}: {err}") from err

        price = header.get("price")
        if price is None:
            raise UpdateFailed(f"No price in instrumentheader for {self.isin}")

        # >>> 1:1 Attribute-Mapping wie in RalfEs73 sensor.py <<<
        data: dict[str, Any] = {
            "name": header.get("name"),
            "isin": header.get("isin") or self.isin,
            "currency": header.get("currencySign"),
            "change_percent": header.get("changePercent"),
            "change_absolute": header.get("changeAbsolute"),
            "exchange": header.get("exchangeName"),
            "last_update": header.get("priceChangeDate"),
            "price": price,

            # keyfigures meta
            "keyfigures_available": bool(keyfigures_available),

            # keyfigures – wie RalfEs73
            "dividend_yield": keyfigures.get("dividendYield"),
            "dividend_per_share": keyfigures.get("dividendPerShare"),
            "price_earnings_ratio": keyfigures.get("priceEarningsRatio"),
            "market_capitalization": keyfigures.get("marketCapitalization"),
            "market_cap_currency": keyfigures.get("marketCapitalizationCurrencyIsoCode"),
            "52w_low": keyfigures.get("fiftyTwoWeekLow"),
            "52w_high": keyfigures.get("fiftyTwoWeekHigh"),
        }

        return data