"""DataUpdateCoordinator for ING Stocks Plus."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    INGApiError,
    async_fetch_instrument_header,
    async_fetch_keyfigures,
    async_fetch_yahoo_keyfigures,
    map_instrument_data,
    merge_keyfigures_with_yahoo,
)
from .const import API_RETRY_ATTEMPTS, API_RETRY_DELAY_SEC

_LOGGER = logging.getLogger(__name__)


class INGStocksCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        isin: str,
        update_interval: timedelta,
        *,
        yahoo_fallback: bool = True,
    ) -> None:
        self.isin = isin
        self.display_name: str | None = None
        self.yahoo_fallback = yahoo_fallback
        super().__init__(
            hass,
            _LOGGER,
            name=f"ING Stocks Plus {isin}",
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        header: dict[str, Any] = {}
        last_err: Exception | None = None

        for attempt in range(API_RETRY_ATTEMPTS):
            try:
                header = await async_fetch_instrument_header(self.hass, self.isin)
                break
            except INGApiError as err:
                last_err = err
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
            except (TimeoutError, OSError, ConnectionError) as err:
                last_err = err
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

        if not header:
            raise UpdateFailed(f"Fetch error {self.isin}: {last_err}")

        keyfigures, keyfigures_available = await async_fetch_keyfigures(
            self.hass, self.isin
        )
        mapped = map_instrument_data(
            self.isin,
            header,
            keyfigures,
            keyfigures_available,
            keyfigures_source="ing",
        )

        needs_yahoo = self.yahoo_fallback and (
            mapped.get("price_earnings_ratio") is None
            or mapped.get("dividend_per_share") is None
            or mapped.get("dividend_yield") is None
        )
        if needs_yahoo:
            yahoo = await async_fetch_yahoo_keyfigures(self.hass, self.isin)
            mapped = merge_keyfigures_with_yahoo(mapped, yahoo)

        return mapped
