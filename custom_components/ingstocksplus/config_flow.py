"""Config and options flows for ING Stocks Plus."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .api import INGApiError, async_fetch_instrument_header, normalize_isin
from .const import (
    CONF_INSTRUMENT_TYPE,
    CONF_ISIN,
    CONF_NAME,
    CONF_QUANTITY,
    CONF_SCAN_INTERVAL,
    DEFAULT_QUANTITY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    INSTRUMENT_TYPE_AUTO,
    INSTRUMENT_TYPE_OPTIONS,
)


def _user_schema(
    *,
    isin: str | None = None,
    name: str = "",
    scan_interval: int = DEFAULT_SCAN_INTERVAL,
    instrument_type: str = INSTRUMENT_TYPE_AUTO,
    quantity: float = DEFAULT_QUANTITY,
    include_isin: bool = True,
) -> vol.Schema:
    fields: dict = {}
    if include_isin:
        fields[vol.Required(CONF_ISIN, default=isin or "")] = TextSelector()
    fields[vol.Optional(CONF_NAME, default=name)] = TextSelector()
    fields[
        vol.Required(CONF_SCAN_INTERVAL, default=scan_interval)
    ] = NumberSelector(
        NumberSelectorConfig(min=1, max=360, mode=NumberSelectorMode.BOX, step=1)
    )
    fields[vol.Required(CONF_INSTRUMENT_TYPE, default=instrument_type)] = SelectSelector(
        SelectSelectorConfig(
            options=INSTRUMENT_TYPE_OPTIONS,
            mode=SelectSelectorMode.DROPDOWN,
            translation_key=CONF_INSTRUMENT_TYPE,
        )
    )
    fields[vol.Optional(CONF_QUANTITY, default=quantity)] = NumberSelector(
        NumberSelectorConfig(min=0, mode=NumberSelectorMode.BOX, step=0.0001)
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
                    instrument_type = user_input.get(
                        CONF_INSTRUMENT_TYPE, INSTRUMENT_TYPE_AUTO
                    )
                    quantity = float(user_input.get(CONF_QUANTITY, DEFAULT_QUANTITY))

                    await self.async_set_unique_id(f"{DOMAIN}_{isin}")
                    self._abort_if_unique_id_configured()

                    title = name if name else f"ING {isin}"
                    return self.async_create_entry(
                        title=title,
                        data={
                            CONF_ISIN: isin,
                            CONF_NAME: name,
                            CONF_SCAN_INTERVAL: scan_interval,
                            CONF_INSTRUMENT_TYPE: instrument_type,
                            CONF_QUANTITY: quantity,
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
                instrument_type=(user_input or {}).get(
                    CONF_INSTRUMENT_TYPE, INSTRUMENT_TYPE_AUTO
                ),
                quantity=float((user_input or {}).get(CONF_QUANTITY, DEFAULT_QUANTITY)),
            ),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlowWithConfigEntry):
    """Options flow for name, interval, display type, and quantity."""

    async def async_step_init(self, user_input=None) -> FlowResult:
        entry = self.config_entry

        if user_input is not None:
            name = (user_input.get(CONF_NAME) or "").strip()
            scan_interval = int(user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
            instrument_type = user_input.get(CONF_INSTRUMENT_TYPE, INSTRUMENT_TYPE_AUTO)
            quantity = float(user_input.get(CONF_QUANTITY, DEFAULT_QUANTITY))
            return self.async_create_entry(
                title="",
                data={
                    CONF_NAME: name,
                    CONF_SCAN_INTERVAL: scan_interval,
                    CONF_INSTRUMENT_TYPE: instrument_type,
                    CONF_QUANTITY: quantity,
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
        current_type = entry.options.get(
            CONF_INSTRUMENT_TYPE,
            entry.data.get(CONF_INSTRUMENT_TYPE, INSTRUMENT_TYPE_AUTO),
        )
        current_quantity = float(
            entry.options.get(
                CONF_QUANTITY, entry.data.get(CONF_QUANTITY, DEFAULT_QUANTITY)
            )
        )

        return self.async_show_form(
            step_id="init",
            data_schema=_user_schema(
                name=current_name,
                scan_interval=current_interval,
                instrument_type=current_type,
                quantity=current_quantity,
                include_isin=False,
            ),
        )
