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
from .helpers import effective_scan_interval_minutes

_LOGGER = logging.getLogger(__name__)


class INGStocksCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        isin: str,
        update_interval: timedelta,
        *,
        yahoo_fallback: bool = True,
        poll_jitter_seconds: int = 0,
        base_scan_interval_minutes: int = 15,
        market_hours_polling: bool = False,
    ) -> None:
        self.isin = isin
        self.display_name: str | None = None
        self.yahoo_fallback = yahoo_fallback
        self.poll_jitter_seconds = max(0, int(poll_jitter_seconds))
        self.base_scan_interval_minutes = max(1, int(base_scan_interval_minutes))
        self.market_hours_polling = bool(market_hours_polling)
        self.last_error: str | None = None
        self._initial_jitter_done = False
        super().__init__(
            hass,
            _LOGGER,
            name=f"ING Stocks Plus {isin}",
            update_interval=update_interval,
        )

    def _apply_dynamic_interval(self) -> None:
        minutes = effective_scan_interval_minutes(
            self.base_scan_interval_minutes,
            market_hours_polling=self.market_hours_polling,
        )
        seconds = self.poll_jitter_seconds
        new_interval = timedelta(minutes=minutes, seconds=seconds)
        if self.update_interval != new_interval:
            _LOGGER.debug(
                "Update interval for %s set to %s (market_hours_polling=%s)",
                self.isin,
                new_interval,
                self.market_hours_polling,
            )
            self.update_interval = new_interval

    async def _async_fetch_header_with_retry(self) -> dict[str, Any]:
        last_err: Exception | None = None
        for attempt in range(API_RETRY_ATTEMPTS):
            try:
                return await async_fetch_instrument_header(self.hass, self.isin)
            except INGApiError as err:
                last_err = err
            except (TimeoutError, OSError, ConnectionError) as err:
                last_err = err
            if attempt < API_RETRY_ATTEMPTS - 1:
                _LOGGER.warning(
                    "Attempt %s/%s failed for %s: %s; retrying in %ss",
                    attempt + 1,
                    API_RETRY_ATTEMPTS,
                    self.isin,
                    last_err,
                    API_RETRY_DELAY_SEC,
                )
                await asyncio.sleep(API_RETRY_DELAY_SEC)
        raise UpdateFailed(f"Fetch error {self.isin}: {last_err}") from last_err

    async def _async_update_data(self) -> dict[str, Any]:
        # Stagger first poll across entries so many ISINs don't hit APIs together.
        if not self._initial_jitter_done and self.poll_jitter_seconds:
            await asyncio.sleep(self.poll_jitter_seconds)
            self._initial_jitter_done = True
        else:
            self._initial_jitter_done = True

        try:
            # Header is hard-fail (with retries); keyfigures soft-fail — run in parallel.
            header, (keyfigures, keyfigures_available) = await asyncio.gather(
                self._async_fetch_header_with_retry(),
                async_fetch_keyfigures(self.hass, self.isin),
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

            self.last_error = None
            self._apply_dynamic_interval()
            return mapped
        except Exception as err:
            self.last_error = str(err)
            self._apply_dynamic_interval()
            raise
