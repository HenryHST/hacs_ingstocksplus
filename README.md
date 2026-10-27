# ING Stocks Plus

**ING Stocks Plus** is a custom Home Assistant integration to fetch **stock and ETF data by ISIN**
using ING’s public instrument API, with an optional Yahoo Finance fallback for missing key figures.

The integration is inspired by the original *ING Stocks* integration by **RalfEs73**,
but has been **completely rebuilt and extended** with modern Home Assistant best practices
(DataUpdateCoordinator, Options Flow, CoordinatorEntity, dynamic sensors).

---

## Features

- Fetch **stock & ETF prices** by ISIN (ING `instrument-header`)
- **Configurable scan interval** per instrument (changeable later via Options)
- **Quantity** option with calculated **position value** (`price × quantity`; set quantity **> 0**)
- Key figures from ING (`share/keyfigures`) when available:
  - P/E ratio (KGV)
  - Market capitalization
  - 52-week high / low
- Optional **Yahoo Finance fallback** (no API key) for missing **dividend** fields (chart events); **P/E only from ING** (Yahoo chart has no P/E; no API-key providers)
- **Portfolio total** sensor summing position values (same currency; mismatches flagged)
- Optional **market-hours polling** (slower updates when Xetra and US sessions are closed)
- Service `ingstocksplus.refresh` for manual updates; config-entry **diagnostics**
- Parallel ING fetches, Yahoo symbol cache (24h), per-entry poll jitter (0–30s)
- Material Design icons (dynamic up/down for price changes)
- Efficient polling via **DataUpdateCoordinator**
- Works with **ApexCharts Card**
- HACS-ready (`zip_release`)

---

## Documentation

- German overview with architecture diagrams: [docs/uebersicht.md](docs/uebersicht.md)

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
   - **Quantity** (shares/units; **must be > 0** for a meaningful position value)
   - **Yahoo Finance fallback** (default on): fills missing dividends (not P/E)
   - **Market-hours polling** (optional): use a longer interval outside Xetra/US hours

> Example ISIN: `IE00B3RBWM25`

---

## Options (after setup)

Open the integration options to change:
- Display name
- Scan interval
- Quantity (set **> 0** to enable position value)
- Yahoo Finance fallback
- Market-hours polling

Changes reload the integration so sensors (including position value) stay in sync.

### Service

- `ingstocksplus.refresh` — refresh all instruments, or filter with optional `entry_id` / `isin`

---

## Sensors Created

The following sensors are created **per ISIN**. Key-figure sensors stay registered even when no key figures are available (state is then `unknown` / empty).

| Sensor | Description |
|--------|-------------|
| `price` | Last traded price |
| `change_percent` | Price change in percent |
| `change_absolute` | Absolute price change |
| `last_update` | Timestamp of last update (diagnostic) |
| `position_value` | `price × quantity` (`unknown` when quantity is 0) |
| `portfolio_total` | Sum of position values (shared device; same-currency only) |
| `dividend_yield` | Dividend yield (ING and/or Yahoo) |
| `dividend_per_share` | Dividend per share (often via Yahoo) |
| `price_earnings_ratio` | P/E ratio / KGV |
| `market_capitalization` | Market capitalization (diagnostic) |
| `52w_low` | 52-week low |
| `52w_high` | 52-week high |
| `market_cap_currency` | Market-cap currency code (diagnostic) |

Attributes include `keyfigures_source` (`ing` / `yahoo` / `mixed`) and optionally `yahoo_symbol`.

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
- ETFs often have no ING key figures; Yahoo may still provide dividend data when available
- **P/E (KGV)** is not filled from Yahoo (chart API has no PE); empty PE for ETFs is expected
- Portfolio total uses the dominant currency; other-currency positions appear under `excluded` with `currency_mismatch`
- Yahoo Finance is **unofficial** (chart/search only; quote APIs may require auth) and may change without notice
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

### 1.4.0
- Portfolio total sensor across all entries (currency mismatch attributes)
- Optional market-hours polling (Xetra / US sessions)
- Document P/E as ING-only (no Yahoo PE / no API-key providers)
- Config-entry diagnostics and `ingstocksplus.refresh` service
- Extra unit tests; HACS `zip_release` + GitHub release workflow

### 1.3.3
- Cache Yahoo ISIN→symbol lookups for 24h in `hass.data`
- Fetch ING header and keyfigures in parallel (header still hard-fails)
- Remove `instrument_type` from config/options UI (legacy values still readable)
- Add per-entry poll jitter (0–30s) to stagger updates

### 1.3.2
- Switch ING keyfigures to `/share/keyfigures/{isin}`
- Optional Yahoo Finance fallback for dividend / P/E (config + options)
- Document quantity requirement for position value

### 1.3.1
- Switch price endpoint to `/instrument-header?isinOrSearchTerm={isin}`

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
