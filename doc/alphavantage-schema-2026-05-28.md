# alphavantage schema discovery (Stage A) — 2026-05-28

**Purpose**: empirically verify alphavantage's actual response schemas
for daily / intraday / historical options before committing to a vendor
migration (architecture v0.3 §14.2-adjacent decision; user direction
change 2026-05-28).

**Credits spent**: ~5.2 (4 successful calls + 1 failed MLK-Day call).

**Verdict**: **GO** — schemas cover everything we need (incl. all Greeks +
IV + open_interest for options). Migration is technically feasible.

---

## 1. Endpoints exercised

| qveris tool_id | endpoint | sample size |
|---|---|---:|
| `alphavantage.time_series.daily.v1` | `TIME_SERIES_DAILY` (SPY) | 17.5 KB / 100 bars |
| `alphavantage.time_series.daily.v1` | `TIME_SERIES_DAILY_ADJUSTED` (SPY) | 22.7 KB / 100 bars |
| `alphavantage.time_series.intraday.retrieve.v1` | 5min SPY trailing (default) | 18.2 KB / ~80 bars |
| `alphavantage.time_series.intraday.retrieve.v1` | 5min SPY month=2024-01 full | 230 KB / 1638 bars |
| `alphavantage.historical_options.query.v1.467a92c0` | SPY 2024-01-16 chain | 3.4 MB / 8238 contracts |

Raw responses saved to `doc/samples/alphavantage_*.json`.

---

## 2. Daily (TIME_SERIES_DAILY_ADJUSTED)

**Recommended endpoint**: `TIME_SERIES_DAILY_ADJUSTED` (not plain
`TIME_SERIES_DAILY`). It returns the raw OHLC AND the split coefficient
AND the dividend amount as separate fields — we can derive
"split-only adjusted" locally to match current polygon convention.

### Response shape

```json
{
  "Meta Data": {
    "1. Information": "Daily Time Series with Splits and Dividend Events",
    "2. Symbol": "SPY",
    "3. Last Refreshed": "2026-05-27",
    "4. Output Size": "Compact",
    "5. Time Zone": "US/Eastern"
  },
  "Time Series (Daily)": {
    "2026-05-27": {
      "1. open": "750.88",
      "2. high": "751.38",
      "3. low": "748.22",
      "4. close": "750.46",
      "5. adjusted close": "750.46",
      "6. volume": "39724615",
      "7. dividend amount": "0.0000",
      "8. split coefficient": "1.0"
    }
  }
}
```

### Gotchas

- **All numeric fields are strings** — must `float()` convert.
- **Date keys are ISO `YYYY-MM-DD` in US/Eastern** — must normalize to
  XNYS session_close UTC via `data.calendars` (already in Step 0
  loader pattern).
- **Default `outputsize=compact` returns 100 bars** only; full history
  requires `outputsize=full` (one call returns ~25 years).
- **No date-range filter** — get either trailing 100 days or full
  history. For incremental updates, fetch `compact` and dedupe.
- **`5. adjusted close` is split+dividend adjusted** — different from
  our polygon "split_only" convention. Use `8. split coefficient` to
  derive split-only ourselves.

### Field → BarFrame mapping

| alphavantage | BarFrame.df column |
|---|---|
| date key (ISO US/Eastern) | `timestamp` after XNYS session_close lookup → UTC |
| `1. open` | `open` (float) |
| `2. high` | `high` (float) |
| `3. low` | `low` (float) |
| `4. close` | `close` (float) — RAW close |
| `6. volume` | `volume` (float) |
| `5. adjusted close` | (dropped — we derive split-only locally) |
| `7. dividend amount` | (dropped at v1; future: regime context dividend events) |
| `8. split coefficient` | (consumed by loader for split adjustment; not stored) |

---

## 3. Intraday (TIME_SERIES_INTRADAY)

### Response shape

```json
{
  "Meta Data": {
    "1. Information": "Intraday (5min) open, high, low, close prices and volume",
    "2. Symbol": "SPY",
    "3. Last Refreshed": "2024-01-31 15:55:00",
    "4. Interval": "5min",
    "5. Output Size": "Full size",
    "6. Time Zone": "US/Eastern"
  },
  "Time Series (5min)": {
    "2024-01-31 15:55:00": {
      "1. open": "470.6016",
      "2. high": "471.0590",
      "3. low": "469.9593",
      "4. close": "469.9885",
      "5. volume": "13995574"
    }
  }
}
```

### Gotchas

- **Intervals supported**: `1min` / `5min` / `15min` / `30min` /
  `60min` only. NOT 10min, 4h, etc.
- **Timestamps are PERIOD-END** in US/Eastern (e.g. `15:55:00` =
  bar covering 15:50–15:55) — convenient, no offset needed beyond
  US/Eastern → UTC conversion.
- **Default returns trailing 30 days at full size**. Historical
  pulls require `month=YYYY-MM` (one full month per call).
- **`extended_hours=true`** includes pre/post-market bars.
  `extended_hours=false` returns RTH (regular trading hours) only.
- **No adjusted close on intraday** — only raw OHLC. Splits applied
  at the source if you set `adjusted=true` (default).
- **`adjusted` flag is split+dividend** (same gotcha as daily). For
  split-only intraday we'd need to apply the split coefficient
  ourselves from the daily call's `split coefficient` field.
- **5min historical depth**: alphavantage's spec says "20+ years
  intraday". Each month = 1 call × 1.3 credits. 5y × 12mo = 60 calls
  per symbol per TF.

### Field → BarFrame mapping

| alphavantage | BarFrame.df column |
|---|---|
| timestamp key (ET local, period-end) | `timestamp` → UTC |
| `1. open` … `5. volume` | same as daily |

### Per-symbol-per-TF backfill cost estimate

| TF | months × symbols | calls | credits |
|---|---:|---:|---:|
| daily | 1 × 10 = 10 | 10 | 13 |
| 60min | 60 × 10 = 600 | 600 | 780 |
| 15min | 60 × 10 = 600 | 600 | 780 |
| 5min | 60 × 10 = 600 | 600 | 780 |
| 1min | 60 × 10 = 600 | 600 | 780 |
| **subtotal (no options)** | | **2,410** | **~3,133** |

---

## 4. Historical Options (HISTORICAL_OPTIONS)

**This is the headline win — polygon path can't match this.**

### Response shape

```json
{
  "endpoint": "Historical Options",
  "message": "success",
  "data": [
    {
      "contractID": "SPY240116C00390000",
      "symbol": "SPY",
      "expiration": "2024-01-16",
      "strike": "390.00",
      "type": "call",
      "last": "84.10",
      "mark": "84.97",
      "bid": "84.86",
      "bid_size": "100",
      "ask": "85.07",
      "ask_size": "100",
      "volume": "1",
      "open_interest": "1",
      "date": "2024-01-16",
      "implied_volatility": "0.01488",
      "delta": "1.00000",
      "gamma": "0.00000",
      "theta": "-0.05694",
      "vega": "0.00000",
      "rho": "0.01068"
    },
    {
      "contractID": "SPY240116P00390000",
      "symbol": "SPY",
      "expiration": "2024-01-16",
      "strike": "390.00",
      "type": "put",
      ...
    }
  ]
}
```

### What's there ✅

- **All Greeks**: delta, gamma, theta, vega, rho
- **Implied volatility** (decimal, not %)
- **Bid / ask / last / mark** prices + bid_size / ask_size
- **Volume + open_interest**
- **contractID** in OCC standard format: `<sym><YYMMDD><C|P><strike×1000 padded to 8>`
- **expiration** ISO `YYYY-MM-DD`
- **strike** as decimal string
- **type** as enum `"call"` / `"put"`
- **date** = trading date (matches `date` param)

### Sample size (SPY 2024-01-16)

- **8,238 total contracts** (4,119 calls + 4,119 puts)
- **36 unique expirations**: 2024-01-16 (0DTE same-day-expiry) → 2026-12-18 (~3y LEAPS)
- First expiry (0DTE): **114 strikes** from $390 to $545 (range covers ~22% above/below SPY's ~$475 spot at that time)

### Cost characteristics

- **1 call = 1 full chain for 1 date** = 1.3 credits
- **Response size**: 3.4 MB raw JSON for SPY one day. Storage at scale:
  - 10 ETFs × 252 trading days × 5y × 3.4 MB ≈ **42 GB** (compressed parquet would be 1/3 to 1/5 of this, so ~10 GB)
- **Latency**: ~7.8s per call. Backfill is rate-limited (alphavantage typically ~5 calls/min on free tier; qveris credits don't say what their throttle is).

### Recommended backfill scope (NOT full date range)

42 GB for full coverage is overkill for research. Two pragmatic options:

- **Event-triggered backfill**: only pull chain for dates where an
  exhaustion / divergence / regime event fired. ~few hundred days per
  symbol = ~500 × 10 × 3.4 MB = 17 GB raw. Manageable.
- **Sparse uniform backfill**: every Nth trading day (e.g. weekly chain
  snapshots) to characterize IV surface evolution. ~50 days/year × 5y
  × 10 × 3.4 MB = 8.5 GB raw.

Both can be Step 8a-triggered (when strategy actually needs the data).

### Field → OptionContract dataclass (proposed schema)

```python
@dataclass(frozen=True)
class OptionContract:
    # Identification
    contract_id: str          # "SPY240116C00390000" OCC format
    underlying: str           # "SPY"
    expiration: date          # 2024-01-16
    strike: float             # 390.00
    option_type: Literal["call", "put"]

    # Snapshot (per date)
    date: date                # 2024-01-16
    last: float | None
    mark: float | None
    bid: float | None
    ask: float | None
    bid_size: int
    ask_size: int
    volume: int
    open_interest: int

    # Greeks
    implied_volatility: float
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
```

This is NOT in scope for Step 0 / Step 3 — it's a Step 8a-era
artifact when US options strategy lands. Architecture impact:
add `data/options_chain.py` alongside `data/bar_frame.py`,
similar provenance + manifest pattern.

---

## 5. Cross-cutting observations

### 5.1 All values are strings

Every alphavantage field comes back as a string — including numerics.
Loader must `float()` / `int()` convert. BarFrame validator already
catches non-numeric dtype (Step 0 codex P2 fix), so the loader either
converts or the BarFrame construction fails loudly.

### 5.2 Time zone normalization

| Endpoint | timestamp tz | format |
|---|---|---|
| daily | US/Eastern (date-only) | `"2024-01-15"` |
| intraday | US/Eastern (date+time, period-end) | `"2024-01-15 15:55:00"` |
| options | US/Eastern (date-only, snapshot date) | `"2024-01-16"` |

Loader normalizes everything to UTC + period_end via `data.calendars`
(same pattern as polygon Step 0 loader).

### 5.3 Compact vs Full vs Month

| Endpoint | Default | Full historical |
|---|---|---|
| daily | 100 bars (compact) | `outputsize=full` (~25 years) |
| intraday | trailing 30 days | `month=YYYY-MM` per call |
| options | one date | one `date` per call |

Incremental updates favor `compact` (daily) or trailing month
(intraday). Full backfills batch over months/dates.

### 5.4 Reliability vs cost

Per qveris stats:
- daily 88-100% success (variable; need retry)
- intraday 100% success (in recent calls)
- options 100% success

1.3 credits/call is cheap relative to other vendors qveris exposes
(massive_stocks is 6.5/call, eodhd is 6.5/call). At 3,710 credits
remaining, we have headroom for full US-OHLC backfill + meaningful
options sampling without re-topping.

---

## 6. GO / NO-GO checklist

| Requirement | Status |
|---|:---:|
| Schema for daily | ✅ GO — TIME_SERIES_DAILY_ADJUSTED returns raw OHLC + split coefficient |
| Schema for intraday (1/5/15/30/60min) | ✅ GO — period-end timestamps, US/Eastern, full month per call |
| Schema for options with Greeks | ✅ GO — delta/gamma/theta/vega/rho + IV + OI all present |
| Historical depth | ✅ — daily 25+ years, intraday 20+ years (per spec; not exhaustively verified), options 15+ years per spec |
| Period-end stamping | ✅ — intraday is already period-end; daily/options are date-only (we look up session_close) |
| Adjustment policy controllable | ✅ — daily ADJUSTED variant gives raw + split coefficient; we derive split-only locally |
| Pre/post-market | ✅ — `extended_hours=true` on intraday |
| Cost feasibility | ✅ — full US OHLC backfill ~3,100 credits; options backfill is event-triggered |

**Verdict**: **GO — proceed to Stage B (loader implementation)**.

---

## 7. Open items for Stage B design

1. **Where to persist raw responses**: keep current `data/raw/<sym>_*.json`
   path but in alphavantage shape, OR convert to polygon-shape on the
   way down? My recommendation in pre-stage assessment was polygon-shape
   (P1 — minimizes script breakage). Reconfirm before Stage B.
2. **Loader CLI vs Python API**: qveris CLI returns OSS URLs for large
   responses. Loader should fetch+follow vs go through subprocess each
   call?
3. **Rate limiting**: how much can we parallelize? qveris doesn't
   document throttle; test empirically during Stage C.
4. **Backfill orchestration**: a script (similar to `fetch_qveris.py`)
   that walks 10 symbols × 5 TFs × N months, dedupes incremental, writes
   to disk. Build during Stage B.
5. **Options chain compression**: 3.4 MB / day / symbol is heavy. Use
   parquet with snappy + drop redundant fields (`symbol` is constant
   per file, `date` is filename-derivable) — defer to Step 8a.
6. **Differences vs polygon**: P2 from pre-stage assessment — all
   backtest numbers WILL shift. Plan a "polygon-vs-alphavantage diff
   report" during Stage C end-to-end validation.

---

## 8. Decision needed before Stage B

**Confirm**:
- Use **`TIME_SERIES_DAILY_ADJUSTED`** as canonical (we want raw OHLC + split coefficient)? (Claude recommends YES)
- Continue with **alphavantage as the SOLE US data source** (not parallel-run with polygon)? (Per user direction 2026-05-28: YES)
- **Defer options backfill** until Step 8a strategy needs it? (Claude recommends YES — 42 GB storage and credit-heavy is wasteful before need is concrete)

If all 3 are YES, proceed to Stage B (~1.5 days work).
