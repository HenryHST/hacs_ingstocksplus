"""Sensor platform for ING Stocks Plus."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_INSTRUMENT_TYPE,
    CONF_NAME,
    DATA_PORTFOLIO_ADDED,
    DOMAIN,
)
from .coordinator import INGStocksCoordinator
from .helpers import compute_portfolio_summary, entry_quantity, iter_coordinators

KEY_TO_ICON: dict[str, str] = {
    "price": "mdi:chart-line",
    "dividend_yield": "mdi:cash-percent",
    "dividend_per_share": "mdi:cash",
    "price_earnings_ratio": "mdi:calculator-variant",
    "market_capitalization": "mdi:bank",
    "52w_low": "mdi:arrow-expand-vertical",
    "52w_high": "mdi:arrow-expand-vertical",
}

# (key, translation_key, unique_suffix, device_class, fixed_unit|None, precision, diagnostic)
# fixed_unit None + monetary → currency from API; fixed_unit None + non-monetary → no unit
KEYFIGURE_VALUE_SENSORS: list[
    tuple[str, str, str, SensorDeviceClass | None, str | None, int | None, bool]
] = [
    ("dividend_yield", "dividend_yield", "dividend_yield", None, "%", 4, False),
    (
        "dividend_per_share",
        "dividend_per_share",
        "dividend_per_share",
        SensorDeviceClass.MONETARY,
        None,
        3,
        False,
    ),
    ("price_earnings_ratio", "price_earnings_ratio", "price_earnings_ratio", None, None, 2, False),
    ("market_capitalization", "market_capitalization", "market_capitalization", None, None, 0, True),
    ("52w_low", "fifty_two_week_low", "52w_low", SensorDeviceClass.MONETARY, None, 3, False),
    ("52w_high", "fifty_two_week_high", "52w_high", SensorDeviceClass.MONETARY, None, 3, False),
]


def _safe_float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _get_quantity(entry: ConfigEntry) -> float:
    return entry_quantity(entry)


def _get_instrument_type(entry: ConfigEntry) -> str | None:
    """Legacy display attribute only; field removed from config/options UI."""
    value = entry.options.get(
        CONF_INSTRUMENT_TYPE,
        entry.data.get(CONF_INSTRUMENT_TYPE),
    )
    if value is None or value == "":
        return None
    return str(value)


def _currency_unit(coordinator: INGStocksCoordinator) -> str | None:
    return (coordinator.data or {}).get("currency") or None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: INGStocksCoordinator = hass.data[DOMAIN][entry.entry_id]

    custom_name = entry.options.get(CONF_NAME, entry.data.get(CONF_NAME))
    if custom_name:
        coordinator.display_name = custom_name
    else:
        coordinator.display_name = (coordinator.data or {}).get("name") or entry.title

    sensors: list[SensorEntity] = [
        INGStockValueSensor(
            coordinator,
            entry,
            key="price",
            translation_key="price",
            unique_suffix="price",
            device_class=SensorDeviceClass.MONETARY,
            fixed_unit=None,
            precision=2,
        ),
        INGStockValueSensor(
            coordinator,
            entry,
            key="change_percent",
            translation_key="change_percent",
            unique_suffix="change_percent",
            device_class=None,
            fixed_unit="%",
            precision=2,
        ),
        INGStockValueSensor(
            coordinator,
            entry,
            key="change_absolute",
            translation_key="change_absolute",
            unique_suffix="change_absolute",
            device_class=SensorDeviceClass.MONETARY,
            fixed_unit=None,
            precision=3,
        ),
        INGStockLastUpdateSensor(coordinator, entry),
        INGStockPositionValueSensor(coordinator, entry),
    ]

    for key, translation_key, unique_suffix, device_class, unit, precision, diagnostic in (
        KEYFIGURE_VALUE_SENSORS
    ):
        sensors.append(
            INGStockValueSensor(
                coordinator,
                entry,
                key=key,
                translation_key=translation_key,
                unique_suffix=unique_suffix,
                device_class=device_class,
                fixed_unit=unit,
                precision=precision,
                diagnostic=diagnostic,
            )
        )

    sensors.append(
        INGStockTextSensor(
            coordinator,
            entry,
            key="market_cap_currency",
            translation_key="market_cap_currency",
            unique_suffix="market_cap_currency",
        )
    )

    domain_data = hass.data.setdefault(DOMAIN, {})
    portfolio_uid = f"{DOMAIN}_portfolio_total"
    registry = er.async_get(hass)
    if (
        not domain_data.get(DATA_PORTFOLIO_ADDED)
        and registry.async_get_entity_id("sensor", DOMAIN, portfolio_uid) is None
    ):
        sensors.append(INGPortfolioTotalSensor(hass))
        domain_data[DATA_PORTFOLIO_ADDED] = True

    async_add_entities(sensors)


class INGStockBaseSensor(CoordinatorEntity[INGStocksCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: INGStocksCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self.entry = entry

    def _identity_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data or {}
        attrs: dict[str, Any] = {
            "isin": d.get("isin"),
            "exchange": d.get("exchange"),
            "currency": d.get("currency"),
            "keyfigures_source": d.get("keyfigures_source"),
        }
        instrument_type = _get_instrument_type(self.entry)
        if instrument_type is not None:
            attrs["instrument_type"] = instrument_type
        if d.get("yahoo_symbol"):
            attrs["yahoo_symbol"] = d.get("yahoo_symbol")
        return attrs

    @property
    def available(self) -> bool:
        return (
            self.coordinator.last_update_success
            and (self.coordinator.data or {}).get("price") is not None
        )

    @property
    def device_info(self):
        d = self.coordinator.data or {}
        return {
            "identifiers": {(DOMAIN, self.coordinator.isin)},
            "name": self.coordinator.display_name or d.get("name") or self.entry.title,
            "manufacturer": "ING (component-api.wertpapiere.ing.de)",
            "model": self.coordinator.isin,
        }


class INGStockValueSensor(INGStockBaseSensor):
    def __init__(
        self,
        coordinator: INGStocksCoordinator,
        entry: ConfigEntry,
        key: str,
        translation_key: str,
        unique_suffix: str,
        device_class: SensorDeviceClass | None,
        fixed_unit: str | None,
        precision: int | None,
        *,
        diagnostic: bool = False,
    ):
        super().__init__(coordinator, entry)
        self.key = key
        self._precision = precision
        self._fixed_unit = fixed_unit
        self._use_api_currency = (
            device_class == SensorDeviceClass.MONETARY and fixed_unit is None
        )

        self._attr_translation_key = translation_key
        self._attr_device_class = device_class
        self._attr_unique_id = f"{DOMAIN}_{coordinator.isin}_{unique_suffix}"
        if diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

        if device_class == SensorDeviceClass.MONETARY:
            self._attr_state_class = None
        else:
            self._attr_state_class = SensorStateClass.MEASUREMENT

        if not self._use_api_currency:
            self._attr_native_unit_of_measurement = fixed_unit

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self._use_api_currency:
            return _currency_unit(self.coordinator)
        return self._attr_native_unit_of_measurement

    @property
    def icon(self) -> str | None:
        if self.key in ("change_percent", "change_absolute"):
            v = _safe_float((self.coordinator.data or {}).get(self.key))
            if v is None:
                return "mdi:trending-neutral"
            if v > 0:
                return "mdi:trending-up"
            if v < 0:
                return "mdi:trending-down"
            return "mdi:trending-neutral"
        return KEY_TO_ICON.get(self.key, "mdi:finance")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = self._identity_attributes()
        if self.key == "price":
            attrs["quantity"] = _get_quantity(self.entry)
        return attrs

    @property
    def native_value(self):
        value = (self.coordinator.data or {}).get(self.key)
        if value is None:
            return None
        if self._precision is not None:
            f = _safe_float(value)
            if f is not None:
                return round(f, self._precision)
        return value


class INGStockTextSensor(INGStockBaseSensor):
    """Diagnostic text sensor (e.g. market cap currency)."""

    _attr_device_class = None
    _attr_state_class = None
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: INGStocksCoordinator,
        entry: ConfigEntry,
        key: str,
        translation_key: str,
        unique_suffix: str,
    ):
        super().__init__(coordinator, entry)
        self.key = key
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"{DOMAIN}_{coordinator.isin}_{unique_suffix}"

    @property
    def icon(self) -> str | None:
        return "mdi:currency-sign"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._identity_attributes()

    @property
    def native_value(self):
        v = (self.coordinator.data or {}).get(self.key)
        return str(v) if v is not None else None


class INGStockPositionValueSensor(INGStockBaseSensor):
    """Position value (price * quantity). Always created; None when quantity is 0."""

    _attr_translation_key = "position_value"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = None
    _attr_icon = "mdi:briefcase"

    def __init__(self, coordinator: INGStocksCoordinator, entry: ConfigEntry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{DOMAIN}_{coordinator.isin}_position_value"

    @property
    def native_unit_of_measurement(self) -> str | None:
        return _currency_unit(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data or {}
        return self._identity_attributes() | {
            "quantity": _get_quantity(self.entry),
            "unit_price": d.get("price"),
        }

    @property
    def native_value(self):
        price = _safe_float((self.coordinator.data or {}).get("price"))
        quantity = _get_quantity(self.entry)
        if price is None or quantity <= 0:
            return None
        return round(price * quantity, 2)


class INGStockLastUpdateSensor(INGStockBaseSensor):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "last_update"
    _attr_icon = "mdi:clock-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: INGStocksCoordinator, entry: ConfigEntry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{DOMAIN}_{coordinator.isin}_last_update"

    @property
    def native_value(self):
        raw = (self.coordinator.data or {}).get("last_update")
        if not raw:
            return None
        dt = dt_util.parse_datetime(raw)
        return dt_util.as_utc(dt) if dt else None


class INGPortfolioTotalSensor(SensorEntity):
    """Sum of position values across all ING Stocks Plus entries (same currency)."""

    _attr_has_entity_name = True
    _attr_translation_key = "portfolio_total"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = None
    _attr_icon = "mdi:finance"
    _attr_unique_id = f"{DOMAIN}_portfolio_total"
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._unsubs: list[Any] = []

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "portfolio")},
            "name": "ING Stocks Plus Portfolio",
            "manufacturer": "ING Stocks Plus",
            "model": "portfolio",
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._attach_listeners()

    async def async_will_remove_from_hass(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        self.hass.data.get(DOMAIN, {}).pop(DATA_PORTFOLIO_ADDED, None)
        await super().async_will_remove_from_hass()

    def _attach_listeners(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs = []
        for _, coordinator in iter_coordinators(self.hass):
            self._unsubs.append(
                coordinator.async_add_listener(self._handle_coordinator_update)
            )

    def _handle_coordinator_update(self) -> None:
        # New entries may appear after this entity was created
        if len(self._unsubs) != len(iter_coordinators(self.hass)):
            self._attach_listeners()
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return bool(iter_coordinators(self.hass))

    @property
    def native_unit_of_measurement(self) -> str | None:
        return compute_portfolio_summary(self.hass).get("currency")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        summary = compute_portfolio_summary(self.hass)
        return {
            "currency_mismatch": summary.get("currency_mismatch"),
            "position_count": summary.get("position_count"),
            "included": [
                {
                    "isin": p.get("isin"),
                    "name": p.get("name"),
                    "value": p.get("value"),
                    "currency": p.get("currency"),
                }
                for p in summary.get("included") or []
            ],
            "excluded": [
                {
                    "isin": p.get("isin"),
                    "name": p.get("name"),
                    "value": p.get("value"),
                    "currency": p.get("currency"),
                }
                for p in summary.get("excluded") or []
            ],
        }

    @property
    def native_value(self):
        return compute_portfolio_summary(self.hass).get("total")
