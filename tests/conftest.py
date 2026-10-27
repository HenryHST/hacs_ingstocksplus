"""Test bootstrap: path setup and lightweight Home Assistant stubs."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ensure_module(name: str) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    module = ModuleType(name)
    sys.modules[name] = module
    return module


class _Subscriptable:
    """Stand-in base that supports PEP 585-style subscripting."""

    def __class_getitem__(cls, _item):
        return cls


def pytest_configure() -> None:
    """Provide minimal homeassistant stubs when the package is not installed."""
    try:
        import homeassistant  # noqa: F401
        return
    except ImportError:
        pass

    ha = _ensure_module("homeassistant")
    ha.__path__ = []  # type: ignore[attr-defined]

    core = _ensure_module("homeassistant.core")
    core.HomeAssistant = MagicMock  # type: ignore[attr-defined]

    helpers = _ensure_module("homeassistant.helpers")
    helpers.__path__ = []  # type: ignore[attr-defined]

    aiohttp_client = _ensure_module("homeassistant.helpers.aiohttp_client")
    aiohttp_client.async_get_clientsession = MagicMock()  # type: ignore[attr-defined]

    update_coordinator = _ensure_module("homeassistant.helpers.update_coordinator")
    update_coordinator.DataUpdateCoordinator = _Subscriptable  # type: ignore[attr-defined]
    update_coordinator.UpdateFailed = Exception  # type: ignore[attr-defined]
    update_coordinator.CoordinatorEntity = _Subscriptable  # type: ignore[attr-defined]

    config_entries = _ensure_module("homeassistant.config_entries")
    config_entries.ConfigEntry = object  # type: ignore[attr-defined]
    config_entries.ConfigFlow = object  # type: ignore[attr-defined]
    config_entries.OptionsFlow = object  # type: ignore[attr-defined]
    config_entries.OptionsFlowWithConfigEntry = object  # type: ignore[attr-defined]

    exceptions = _ensure_module("homeassistant.exceptions")
    exceptions.ConfigEntryNotReady = Exception  # type: ignore[attr-defined]

    data_entry_flow = _ensure_module("homeassistant.data_entry_flow")
    data_entry_flow.FlowResult = dict  # type: ignore[attr-defined]

    selector = _ensure_module("homeassistant.helpers.selector")
    for name in (
        "NumberSelector",
        "NumberSelectorConfig",
        "NumberSelectorMode",
        "SelectSelector",
        "SelectSelectorConfig",
        "SelectSelectorMode",
        "TextSelector",
    ):
        setattr(selector, name, MagicMock)

    components = _ensure_module("homeassistant.components")
    components.__path__ = []  # type: ignore[attr-defined]
    sensor_mod = _ensure_module("homeassistant.components.sensor")
    sensor_mod.SensorEntity = object  # type: ignore[attr-defined]
    sensor_mod.SensorDeviceClass = MagicMock()  # type: ignore[attr-defined]
    sensor_mod.SensorStateClass = MagicMock()  # type: ignore[attr-defined]

    entity = _ensure_module("homeassistant.helpers.entity")
    entity.EntityCategory = MagicMock()  # type: ignore[attr-defined]

    entity_platform = _ensure_module("homeassistant.helpers.entity_platform")
    entity_platform.AddEntitiesCallback = object  # type: ignore[attr-defined]

    util = _ensure_module("homeassistant.util")
    util.__path__ = []  # type: ignore[attr-defined]
    dt = _ensure_module("homeassistant.util.dt")
    dt.parse_datetime = MagicMock()  # type: ignore[attr-defined]
    dt.as_utc = MagicMock()  # type: ignore[attr-defined]
