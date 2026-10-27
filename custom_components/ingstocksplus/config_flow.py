"""Config and options flows for ING Stocks Plus."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)

from .api import INGApiError, async_fetch_instrument_header, normalize_isin
from .const import (
    CONF_ISIN,
    CONF_MARKET_HOURS_POLLING,
    CONF_NAME,
    CONF_QUANTITY,
    CONF_SCAN_INTERVAL,
    CONF_YAHOO_FALLBACK,
    DEFAULT_MARKET_HOURS_POLLING,
    DEFAULT_QUANTITY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_YAHOO_FALLBACK,
    DOMAIN,
)


def _user_schema(
    *,
    isin: str | None = None,
    name: str = "",
    scan_interval: int = DEFAULT_SCAN_INTERVAL,
    quantity: float = DEFAULT_QUANTITY,
    yahoo_fallback: bool = DEFAULT_YAHOO_FALLBACK,
    market_hours_polling: bool = DEFAULT_MARKET_HOURS_POLLING,
    include_isin: bool = True,
) -> vol.Schema:
    fields: dict = {}
    if include_isin:
        fields[vol.Required(CONF_ISIN, default=isin or "")] = TextSelector()
    fields[vol.Optional(CONF_NAME, default=name)] = TextSelector()
    fields[vol.Required(CONF_SCAN_INTERVAL, default=scan_interval)] = NumberSelector(
        NumberSelectorConfig(min=1, max=360, mode=NumberSelectorMode.BOX, step=1)
    )
    # HA NumberSelector step must be "any" or >= 0.001 (not 0.0001).
    fields[vol.Optional(CONF_QUANTITY, default=quantity)] = NumberSelector(
        NumberSelectorConfig(min=0, mode=NumberSelectorMode.BOX, step="any")
    )
    fields[vol.Optional(CONF_YAHOO_FALLBACK, default=yahoo_fallback)] = BooleanSelector()
    fields[vol.Optional(CONF_MARKET_HOURS_POLLING, default=market_hours_polling)] = (
        BooleanSelector()
    )
    return vol.Schema(fields)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                isin = normalize_isin(user_input[CONF_ISIN])
            except ValueError:
                errors["isin"] = "invalid_isin"
                isin = (user_input.get(CONF_ISIN) or "").strip().upper()
            else:
                try:
                    header = await async_fetch_instrument_header(self.hass, isin)
                except INGApiError as err:
                    if err.status == 404:
                        errors["isin"] = "isin_not_found"
                    else:
                        errors["base"] = "cannot_connect"
                else:
                    name = (user_input.get(CONF_NAME) or "").strip()
                    if not name:
                        name = (header.get("name") or "").strip()
                    scan_interval = int(
                        user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                    )
                    quantity = float(user_input.get(CONF_QUANTITY, DEFAULT_QUANTITY))
                    yahoo_fallback = bool(
                        user_input.get(CONF_YAHOO_FALLBACK, DEFAULT_YAHOO_FALLBACK)
                    )
                    market_hours_polling = bool(
                        user_input.get(
                            CONF_MARKET_HOURS_POLLING, DEFAULT_MARKET_HOURS_POLLING
                        )
                    )

                    await self.async_set_unique_id(f"{DOMAIN}_{isin}")
                    self._abort_if_unique_id_configured()

                    title = name if name else f"ING {isin}"
                    return self.async_create_entry(
                        title=title,
                        data={
                            CONF_ISIN: isin,
                            CONF_NAME: name,
                            CONF_SCAN_INTERVAL: scan_interval,
                            CONF_QUANTITY: quantity,
                            CONF_YAHOO_FALLBACK: yahoo_fallback,
                            CONF_MARKET_HOURS_POLLING: market_hours_polling,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(
                isin=(user_input or {}).get(CONF_ISIN),
                name=(user_input or {}).get(CONF_NAME, "") or "",
                scan_interval=int(
                    (user_input or {}).get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ),
                quantity=float((user_input or {}).get(CONF_QUANTITY, DEFAULT_QUANTITY)),
                yahoo_fallback=bool(
                    (user_input or {}).get(CONF_YAHOO_FALLBACK, DEFAULT_YAHOO_FALLBACK)
                ),
                market_hours_polling=bool(
                    (user_input or {}).get(
                        CONF_MARKET_HOURS_POLLING, DEFAULT_MARKET_HOURS_POLLING
                    )
                ),
            ),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlowWithConfigEntry):
    """Options flow for name, interval, quantity, Yahoo, and market-hours polling."""

    async def async_step_init(self, user_input=None) -> FlowResult:
        entry = self.config_entry

        if user_input is not None:
            name = (user_input.get(CONF_NAME) or "").strip()
            scan_interval = int(user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
            quantity = float(user_input.get(CONF_QUANTITY, DEFAULT_QUANTITY))
            yahoo_fallback = bool(
                user_input.get(CONF_YAHOO_FALLBACK, DEFAULT_YAHOO_FALLBACK)
            )
            market_hours_polling = bool(
                user_input.get(CONF_MARKET_HOURS_POLLING, DEFAULT_MARKET_HOURS_POLLING)
            )
            return self.async_create_entry(
                title="",
                data={
                    CONF_NAME: name,
                    CONF_SCAN_INTERVAL: scan_interval,
                    CONF_QUANTITY: quantity,
                    CONF_YAHOO_FALLBACK: yahoo_fallback,
                    CONF_MARKET_HOURS_POLLING: market_hours_polling,
                },
            )

        current_interval = int(
            entry.options.get(
                CONF_SCAN_INTERVAL,
                entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            )
        )
        current_name = str(
            entry.options.get(CONF_NAME, entry.data.get(CONF_NAME, "")) or ""
        )
        current_quantity = float(
            entry.options.get(
                CONF_QUANTITY, entry.data.get(CONF_QUANTITY, DEFAULT_QUANTITY)
            )
        )
        current_yahoo = bool(
            entry.options.get(
                CONF_YAHOO_FALLBACK,
                entry.data.get(CONF_YAHOO_FALLBACK, DEFAULT_YAHOO_FALLBACK),
            )
        )
        current_market = bool(
            entry.options.get(
                CONF_MARKET_HOURS_POLLING,
                entry.data.get(CONF_MARKET_HOURS_POLLING, DEFAULT_MARKET_HOURS_POLLING),
            )
        )

        return self.async_show_form(
            step_id="init",
            data_schema=_user_schema(
                name=current_name,
                scan_interval=current_interval,
                quantity=current_quantity,
                yahoo_fallback=current_yahoo,
                market_hours_polling=current_market,
                include_isin=False,
            ),
        )
