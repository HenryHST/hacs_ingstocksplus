# ING Stocks Plus

**ING Stocks Plus** is a custom Home Assistant integration to fetch **stock and ETF data by ISIN**
using ING’s public instrument API.

The integration is inspired by the original *ING Stocks* integration by **RalfEs73**,
but has been **completely rebuilt and extended** with modern Home Assistant best practices
(DataUpdateCoordinator, Options Flow, CoordinatorEntity, dynamic sensors).

---

## Features

- Fetch **stock & ETF prices** by ISIN
- **Configurable scan interval** per instrument (changeable later via Options)
- **Quantity** option with calculated **position value** sensor
- **Instrument type** as a display label only (auto / ETF / stock) — does not change API behaviour
- Key figures when the API provides them:
  - Dividend yield / dividend per share
  - P/E ratio
  - Market capitalization
  - 52-week high / low
- Material Design icons (dynamic up/down for price changes)
- Efficient polling via **DataUpdateCoordinator**
- Works with **ApexCharts Card**
- HACS-ready

---

## Installation (via HACS – Custom Repository)

1. Open **HACS**
2. Go to **Integrations**
3. Click **⋮ → Custom repositories**
4. Add:
   - **Repository:**  
     `https://github.com/Sundancer78/hacs_ingstocksplus`
   - **Type:** Integration
5. Install **ING Stocks Plus**
6. **Restart Home Assistant**

---

## Configuration

1. Go to **Settings → Devices & Services**
2. Click **Add Integration**
3. Search for **ING Stocks Plus**
4. Enter:
   - **ISIN** (required; validated against the ING API)
   - **Name** (optional; defaults to the instrument name from the API)
   - **Scan interval** (minutes)
   - **Instrument type** (display only): Automatic / ETF / Stock
   - **Quantity** (shares/units; enables a meaningful position value)

> Example ISIN: `IE00B3RBWM25`

---

## Options (after setup)

Open the integration options to change:
- Display name
- Scan interval
- Instrument type (display only)
- Quantity

Changes reload the integration so sensors (including position value) stay in sync.

---

## Sensors Created

The following sensors are created **per ISIN**. Key-figure sensors stay registered even when the API returns no key figures (state is then `unknown` / empty).

| Sensor | Description |
|--------|-------------|
| `price` | Last traded price |
| `change_percent` | Price change in percent |
| `change_absolute` | Absolute price change |
| `last_update` | Timestamp of last update (diagnostic) |
| `position_value` | `price × quantity` (`unknown` when quantity is 0) |
| `dividend_yield` | Dividend yield |
| `dividend_per_share` | Dividend per share |
| `price_earnings_ratio` | P/E ratio |
| `market_capitalization` | Market capitalization (diagnostic) |
| `52w_low` | 52-week low |
| `52w_high` | 52-week high |
| `market_cap_currency` | Market-cap currency code (diagnostic) |

Monetary sensors use the currency sign returned by the API (not hard-coded).

---

## Example: ApexCharts Card

```yaml
type: custom:apexcharts-card
header:
  show: true
  title: Vanguard FTSE All-World UCITS ETF
  show_states: true
  colorize_states: true

graph_span: 1d

series:
  - entity: sensor.vanguard_ftse_all_world_ucits_etf_price
    name: Price
    type: line
    extend_to: false
    group_by:
      duration: 5min
      func: last
      fill: last
```

---

## Notes & Limitations

- Not all instruments provide key figures (price updates still succeed if key figures fail)
- Scan intervals should be chosen responsibly (recommended: **5–30 minutes**)
- The integration uses an **unofficial public API** and is **not affiliated with ING**
- Requires Home Assistant **2024.1.0** or newer

---

## Credits

- Inspired by **ING Stocks** by *RalfEs73*
- Developed independently by **Sundancer78**

---

## Issues & Feedback

Please report issues or ideas via GitHub:

https://github.com/Sundancer78/hacs_ingstocksplus/issues

---

## Changelog

### 1.3.0
- Soft-fail keyfigures so price updates stay available
- Validate ISIN format and API reachability in the config flow
- Always create position-value sensor; reload on options changes
- Use CoordinatorEntity, trimmed attributes, API currency, diagnostic categories
- Extract `api.py`, add entity translations (EN/DE), tests, and CI
- Document instrument type as display-only; pin HA min version

### 1.2.1
- Maintenance / packaging bump

### 1.2.0
- Added quantity option (float)
- Added calculated position value sensor

### 1.1.1
- Bugfix: attribute handling aligned with original ING Stocks integration
