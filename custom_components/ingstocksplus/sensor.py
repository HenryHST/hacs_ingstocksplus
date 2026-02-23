from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_INSTRUMENT_TYPE,
    CONF_QUANTITY,
    DEFAULT_QUANTITY,
    INSTRUMENT_TYPE_AUTO,
)
from .coordinator import INGStocksCoordinator

_LOGGER = logging.getLogger(__name__)

# Icon mapping for value sensors (dynamic icons for change_* handled separately)
KEY_TO_ICON: dict[str, str] = {
    "price": "mdi:chart-line",
    "dividend_yield": "mdi:cash-percent",
    "dividend_per_share": "mdi:cash",
    "price_earnings_ratio": "mdi:calculator-variant",
    "market_capitalization": "mdi:bank",
    "52w_low": "mdi:arrow-expand-vertical",
    "52w_high": "mdi:arrow-expand-vertical",
}

# Keyfigure value sensors: (key, entity_name, unique_suffix, device_class, unit, precision)
# unit uses monetary_unit for €
KEYFIGURE_VALUE_SENSORS: list[tuple[str, str, str, SensorDeviceClass | None, str | None, int | None]] = [
    ("dividend_yield", "Dividendenrendite", "dividend_yield", None, "%", 4),
    ("dividend_per_share", "Dividende je Anteil", "dividend_per_share", SensorDeviceClass.MONETARY, None, 3),
    ("price_earnings_ratio", "KGV", "price_earnings_ratio", None, None, 2),
    ("market_capitalization", "Marktkapitalisierung", "market_capitalization", None, None, 0),
    ("52w_low", "52W Tief", "52w_low", SensorDeviceClass.MONETARY, None, 3),
    ("52w_high", "52W Hoch", "52w_high", SensorDeviceClass.MONETARY, None, 3),
]


def _safe_float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _get_quantity(entry: ConfigEntry) -> float:
    q = entry.options.get(CONF_QUANTITY, entry.data.get(CONF_QUANTITY, DEFAULT_QUANTITY))
    try:
        qf = float(q)
        return qf if qf >= 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


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

    instrument_type = entry.options.get(
        CONF_INSTRUMENT_TYPE,
        entry.data.get(CONF_INSTRUMENT_TYPE, INSTRUMENT_TYPE_AUTO),
    )

    monetary_unit = "€"

    # Preis & Änderungen IMMER anlegen (unabhängig von Keyfigures)
    sensors: list[SensorEntity] = [
        INGStockValueSensor(
            coordinator, entry, instrument_type,
            key="price",
            entity_name="Preis",
            unique_suffix="price",
            device_class=SensorDeviceClass.MONETARY,
            unit=monetary_unit,
            precision=2,
        ),
        INGStockValueSensor(
            coordinator, entry, instrument_type,
            key="change_percent",
            entity_name="Änderung %",
            unique_suffix="change_percent",
            device_class=None,
            unit="%",
            precision=2,
        ),
        INGStockValueSensor(
            coordinator, entry, instrument_type,
            key="change_absolute",
            entity_name="Änderung",
            unique_suffix="change_absolute",
            device_class=SensorDeviceClass.MONETARY,
            unit=monetary_unit,
            precision=3,
        ),
        INGStockLastUpdateSensor(coordinator, entry),
    ]

    # Positionswert nur bei quantity > 0
    if _get_quantity(entry) > 0:
        sensors.append(
            INGStockPositionValueSensor(
                coordinator=coordinator,
                entry=entry,
                instrument_type=instrument_type,
                unit=monetary_unit,
            )
        )

    # Keyfigures-Sensoren: IMMER anlegen, aber werden None wenn API nichts liefert.
    # Dadurch verschwinden Entities nicht mehr aus der Registry.
    for key, entity_name, unique_suffix, device_class, unit, precision in KEYFIGURE_VALUE_SENSORS:
        sensors.append(
            INGStockValueSensor(
                coordinator,
                entry,
                instrument_type,
                key=key,
                entity_name=entity_name,
                unique_suffix=unique_suffix,
                device_class=device_class,
                unit=unit if unit is not None else monetary_unit,
                precision=precision,
            )
        )
    sensors.append(
        INGStockTextSensor(
            coordinator,
            entry,
            instrument_type,
            key="market_cap_currency",
            entity_name="Marktkap.-Währung",
            unique_suffix="market_cap_currency",
        )
    )

    async_add_entities(sensors, True)


class INGStockBaseSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: INGStocksCoordinator, entry: ConfigEntry) -> None:
        self.coordinator = coordinator
        self.entry = entry

    def _base_attributes(self) -> dict[str, Any]:
        """Common attributes shared by all sensors (name, isin, exchange, etc.)."""
        d = self.coordinator.data or {}
        return {
            "name": d.get("name"),
            "isin": d.get("isin"),
            "currency": d.get("currency"),
            "exchange": d.get("exchange"),
            "last_update": d.get("last_update"),
            "change_percent": d.get("change_percent"),
            "change_absolute": d.get("change_absolute"),
            "dividend_yield": d.get("dividend_yield"),
            "dividend_per_share": d.get("dividend_per_share"),
            "price_earnings_ratio": d.get("price_earnings_ratio"),
            "market_capitalization": d.get("market_capitalization"),
            "market_cap_currency": d.get("market_cap_currency"),
            "52w_low": d.get("52w_low"),
            "52w_high": d.get("52w_high"),
        }

    @property
    def available(self) -> bool:
        # Bei fehlenden Keyfigures sollen Entities trotzdem existieren, aber eben None als value haben.
        return self.coordinator.last_update_success and (self.coordinator.data or {}).get("price") is not None

    @property
    def device_info(self):
        d = self.coordinator.data or {}
        return {
            "identifiers": {(DOMAIN, self.coordinator.isin)},
            "name": self.coordinator.display_name or d.get("name") or self.entry.title,
            "manufacturer": "ING (component-api.wertpapiere.ing.de)",
            "model": self.coordinator.isin,
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    async def async_update(self) -> None:
        await self.coordinator.async_request_refresh()


class INGStockValueSensor(INGStockBaseSensor):
    def __init__(
        self,
        coordinator: INGStocksCoordinator,
        entry: ConfigEntry,
        instrument_type: str,
        key: str,
        entity_name: str,
        unique_suffix: str,
        device_class: SensorDeviceClass | None,
        unit: str | None,
        precision: int | None,
    ):
        super().__init__(coordinator, entry)
        self.instrument_type = instrument_type
        self.key = key
        self._precision = precision

        self._attr_name = entity_name
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit

        # 🔒 Stabiler Unique-ID-Suffix (ändert sich nicht, auch wenn entity_name übersetzt/umbenannt wird)
        self._attr_unique_id = f"{DOMAIN}_{coordinator.isin}_{unique_suffix}"

        if device_class == SensorDeviceClass.MONETARY:
            self._attr_state_class = None
        else:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def icon(self) -> str | None:
        if self.key in ("change_percent", "change_absolute"):
            d = self.coordinator.data or {}
            v = _safe_float(d.get(self.key))
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
        attrs = self._base_attributes()
        attrs["instrument_type_selected"] = self.instrument_type
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
    """Text sensor for values like market_cap_currency to keep entity stable."""

    _attr_device_class = None
    _attr_state_class = None

    def __init__(
        self,
        coordinator: INGStocksCoordinator,
        entry: ConfigEntry,
        instrument_type: str,
        key: str,
        entity_name: str,
        unique_suffix: str,
    ):
        super().__init__(coordinator, entry)
        self.instrument_type = instrument_type
        self.key = key
        self._attr_name = entity_name
        self._attr_unique_id = f"{DOMAIN}_{coordinator.isin}_{unique_suffix}"

    @property
    def icon(self) -> str | None:
        return "mdi:currency-sign"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        base = self._base_attributes()
        return {
            k: base[k]
            for k in ("name", "isin", "exchange", "currency", "last_update")
        } | {"instrument_type_selected": self.instrument_type}

    @property
    def native_value(self):
        v = (self.coordinator.data or {}).get(self.key)
        return str(v) if v is not None else None


class INGStockPositionValueSensor(INGStockBaseSensor):
    """Positionswert (price * quantity)."""

    def __init__(
        self,
        coordinator: INGStocksCoordinator,
        entry: ConfigEntry,
        instrument_type: str,
        unit: str,
    ):
        super().__init__(coordinator, entry)
        self.instrument_type = instrument_type
        self._attr_name = "Positionswert"
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = None
        self._attr_unique_id = f"{DOMAIN}_{coordinator.isin}_position_value"

    @property
    def icon(self) -> str | None:
        return "mdi:briefcase"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        base = self._base_attributes()
        d = self.coordinator.data or {}
        return {
            k: base[k]
            for k in ("name", "isin", "exchange", "currency", "last_update")
        } | {
            "instrument_type_selected": self.instrument_type,
            "quantity": _get_quantity(self.entry),
            "unit_price": d.get("price"),
        }

    @property
    def native_value(self):
        d = self.coordinator.data or {}
        price = _safe_float(d.get("price"))
        quantity = _get_quantity(self.entry)
        if price is None or quantity <= 0:
            return None
        return round(price * quantity, 2)


class INGStockLastUpdateSensor(INGStockBaseSensor):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_name = "Letztes Update"
    _attr_icon = "mdi:clock-outline"

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