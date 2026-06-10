# Options-layer ag/au P&L Attribution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an auditable, reproducible backtest that attributes option-premium P&L to the ag/au `options_calls` that `score_today` actually emits, and freeze the result as `baselines/options_{ag,au}.json` + a repro doc.

**Architecture:** A new orchestrator `backtest_options_attribution.py` runs 5 stages — replay gated ag/au bottom signals (reusing the same detectors + scoring `score_today` uses) → replay each emitter's exact `select_otm_calls` signature → price each emitted Rank-1 OTM call's daily premium path (real option data primary, Black-76 model fallback) → simulate the validated DD-line take/stop exit (`simulate_entry`) → aggregate IS/OOS folds + verdict. New logic lives in small focused `engine/options/` modules; the exit-sim and selector pricers are reused, not reimplemented.

**Tech Stack:** Python 3.13, pandas, pytest, jj (VCS). Reuses `engine/options/cn_ag_selector.py` / `cn_au_selector.py` (`select_otm_calls`, `_bs_call_price`, `estimate_iv`, `lookup_option_price`), `data/bar_loader`, and `scripts/score_today.py` scoring helpers (`apply_policy`, `match_rule`, `readiness_score`).

**Spec:** `docs/superpowers/specs/2026-06-10-options-attribution-design.md` (Codex-reviewed).

**Conventions for every commit step:** this repo uses **jj**, not git. To commit: `jj describe -m "<msg>" && jj new`. Run tests from `src/`: `cd src && .venv/bin/python -m pytest <path> -q`.

---

## File Structure

| File | Responsibility | New/Modify |
|---|---|---|
| `src/engine/options/option_exit.py` | Validated take1/take2/stop exit-sim on an option daily-OHLC frame (extracted `simulate_entry`) | Create |
| `src/scripts/sweep_ddline_options.py` | Import `simulate_entry` from `option_exit` instead of defining it | Modify |
| `src/engine/options/option_price_loader.py` | `premium_path()` — option daily-OHLC frame from real data, Black-76 model fallback, source tagging | Create |
| `src/engine/options/options_emission_replay.py` | Replay the 4 ag/au emitters faithfully → gated signals + emitted calls | Create |
| `src/scripts/backtest_options_attribution.py` | CLI orchestrator: replay→price→exit→aggregate→baseline JSON | Create |
| `baselines/options_ag.json`, `baselines/options_au.json` | Frozen attribution baselines | Create (generated) |
| `doc/repro/options_attribution_2026-06-10.md` | Method + results + modeled-fraction + verdict | Create |
| `src/tests/test_option_exit.py` | Exit-sim incl. TP1-at-boundary partial credit | Create |
| `src/tests/test_option_price_loader.py` | Real-load, model fallback, source tagging | Create |
| `src/tests/test_options_emission_faithfulness.py` | Harness emission == `score_today` `options_calls` on a sample date | Create |
| `src/tests/test_options_attribution_aggregate.py` | Folds + verdict logic | Create |

---

## Task 1: Extract the validated exit-sim into a reusable module

**Files:**
- Create: `src/engine/options/option_exit.py`
- Modify: `src/scripts/sweep_ddline_options.py:304-378` (replace def with import)
- Test: `src/tests/test_option_exit.py`

- [ ] **Step 1: Write the failing test**

```python
# src/tests/test_option_exit.py
import pandas as pd
from engine.options.option_exit import simulate_entry


def _daily(prices):
    # one row per day; high=low=close=open=price (flat bars) unless overridden
    return pd.DataFrame({"open": prices, "high": prices, "low": prices,
                         "close": prices, "volume": [1] * len(prices)})


def test_take2_full_exit():
    # entry 10, take2=4x -> 40. A bar hitting high 40 exits full at take2.
    daily = _daily([10, 12, 40, 11])
    daily.loc[2, "high"] = 40.0
    e = {"entry_idx": 0, "entry_price": 10.0, "stop_price": 9.0}
    r = simulate_entry(daily, e, take1_mult=2.0, take2_mult=4.0, max_hold=30)
    assert r["take2"] is True and r["mult"] == 4.0 and r["exit_reason"] == "take2"


def test_tp1_then_runs_to_boundary_credits_partial():
    # take1=2x (20) hits day1; never reaches take2; runs to data end at close 10.
    # proceeds = 20*0.5 + 10*0.5 = 15 -> mult 1.5 (partial credited, not raw MTM 1.0).
    daily = _daily([10, 20, 10, 10])
    daily.loc[1, "high"] = 20.0
    e = {"entry_idx": 0, "entry_price": 10.0, "stop_price": 9.0}
    r = simulate_entry(daily, e, take1_mult=2.0, take2_mult=4.0, max_hold=2)
    assert r["take1"] is True and r["take2"] is False
    assert r["mult"] == 1.5


def test_stop_exit():
    daily = _daily([10, 8, 8, 8])  # low 8 <= stop 9 on day1
    e = {"entry_idx": 0, "entry_price": 10.0, "stop_price": 9.0}
    r = simulate_entry(daily, e, take1_mult=2.0, take2_mult=4.0, max_hold=30)
    assert r["exit_reason"] == "stop" and r["mult"] < 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && .venv/bin/python -m pytest tests/test_option_exit.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.options.option_exit'`

- [ ] **Step 3: Create the module by moving `simulate_entry` verbatim**

Move the existing `simulate_entry` function (currently `src/scripts/sweep_ddline_options.py:304-378`) into the new file **unchanged** (it already credits the take1 partial at the hold boundary via `proceeds`):

```python
# src/engine/options/option_exit.py
"""Validated DD-line option exit simulator (take1/take2/stop), extracted from
sweep_ddline_options.py so the attribution harness and the sweep share one
implementation. Operates on an OPTION daily-OHLC frame."""
from __future__ import annotations

import pandas as pd


def simulate_entry(
    daily: pd.DataFrame,
    entry: dict,
    take1_mult: float,
    take2_mult: float,
    max_hold: int,
) -> dict:
    """Simulate one entry. Returns result dict with pnl metrics.

    entry = {entry_idx, entry_price, stop_price}. Banks take1 (0.5 size) at
    take1_mult, remainder at take2_mult; stop is a hard exit; otherwise marks
    the residual to close at the hold boundary (take1 partial already banked).
    """
    # <<< paste the exact body from sweep_ddline_options.py:312-378 >>>
```

- [ ] **Step 4: Point `sweep_ddline_options.py` at the shared module**

In `src/scripts/sweep_ddline_options.py`, delete the local `def simulate_entry(...)` (lines 304-378) and add near the other imports:

```python
from engine.options.option_exit import simulate_entry
```

- [ ] **Step 5: Run tests to verify pass + no sweep regression**

Run: `cd src && .venv/bin/python -m pytest tests/test_option_exit.py -q`
Expected: PASS (3 passed)
Run: `cd src && .venv/bin/python -c "import scripts.sweep_ddline_options"`
Expected: no error (import resolves).

- [ ] **Step 6: Commit**

```bash
jj describe -m "refactor(options): extract simulate_entry to engine/options/option_exit" && jj new
```

---

## Task 2: Price-loader — real option data path

**Files:**
- Create: `src/engine/options/option_price_loader.py`
- Test: `src/tests/test_option_price_loader.py`

Option data files: `data/options/cn/{ag,au}/{contract}_{YYYYMMDD}_daily.json` and `{contract}_daily.json`, each `{"contract","strike","expiry","bars":[{"time":<unix>,"open","high","low","close","volume"}, ...]}`. We need the **daily OHLC frame** from `entry_date` forward (not just one close).

- [ ] **Step 1: Write the failing test**

```python
# src/tests/test_option_price_loader.py
import json
from datetime import date
from pathlib import Path

import pandas as pd
from engine.options.option_price_loader import load_option_daily


def _write_contract(dir_: Path, sym: str, rows):
    # rows: list of (YYYY-MM-DD, o,h,l,c)
    bars = []
    for d, o, h, l, c in rows:
        ts = int(pd.Timestamp(d, tz="UTC").timestamp())
        bars.append({"time": ts, "open": o, "high": h, "low": l, "close": c, "volume": 1})
    (dir_ / f"{sym}_daily.json").write_text(json.dumps({"contract": sym, "bars": bars}))


def test_load_option_daily_returns_ohlc_from_entry(tmp_path):
    _write_contract(tmp_path, "ag2510c9000",
                    [("2025-09-01", 10, 11, 9, 10),
                     ("2025-09-02", 10, 20, 10, 18),
                     ("2025-09-03", 18, 19, 17, 17)])
    df = load_option_daily("ag2510c9000", date(2025, 9, 1), tmp_path, max_hold=30)
    assert list(df.columns) >= ["open", "high", "low", "close"]
    assert len(df) == 3
    assert float(df["close"].iloc[0]) == 10.0


def test_load_option_daily_missing_returns_none(tmp_path):
    assert load_option_daily("ag9999c1", date(2025, 1, 1), tmp_path, max_hold=30) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && .venv/bin/python -m pytest tests/test_option_price_loader.py -q`
Expected: FAIL with `ImportError: cannot import name 'load_option_daily'`

- [ ] **Step 3: Implement `load_option_daily`**

```python
# src/engine/options/option_price_loader.py
"""Option premium-path loader for the attribution harness.

Primary: the exact contract's real daily OHLC from data/options/cn/{ul}/.
Fallback (separate function, Task 3): Black-76 synthetic OHLC from the
underlying futures path. Source is tagged so the baseline reports modeled%."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd


def load_option_daily(contract_sym: str, entry_date: date, data_dir: Path,
                      max_hold: int) -> pd.DataFrame | None:
    """Real OPTION daily-OHLC frame from entry_date forward (<= max_hold+5 rows).

    Reads {contract}_{YYYYMMDD}_daily.json (newest) or {contract}_daily.json.
    Returns None when no file/bars cover entry_date. Index reset; row 0 is the
    first bar with date >= entry_date.
    """
    sym = contract_sym.lower()
    files = sorted(data_dir.glob(f"{sym}_*_daily.json")) + sorted(data_dir.glob(f"{sym}_daily.json"))
    bars = None
    for p in files:
        doc = json.loads(p.read_text())
        if doc.get("bars"):
            bars = doc["bars"]
            break
    if not bars:
        return None
    df = pd.DataFrame(bars)
    df["date"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.date
    df = df[df["date"] >= entry_date].sort_values("date").reset_index(drop=True)
    if df.empty:
        return None
    return df.head(max_hold + 5)[["open", "high", "low", "close"]].reset_index(drop=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && .venv/bin/python -m pytest tests/test_option_price_loader.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
jj describe -m "feat(options): real-data option daily-OHLC loader" && jj new
```

---

## Task 3: Price-loader — Black-76 model fallback path

**Files:**
- Modify: `src/engine/options/option_price_loader.py`
- Test: `src/tests/test_option_price_loader.py`

Synthesize an option daily-OHLC frame by repricing the contract each day over the underlying futures path. Reuse `_bs_call_price(S, K, T, r, sigma)` from the matching selector. IV assumption is a **fixed per-underlying constant** (documented as model input): `IV_ASSUMPTION = {"ag": 0.18, "au": 0.20}` (mid of the 12-20% historical ATM band per `project_options_entry_timing`; the actual values are pinned in Task 11 from observed ATM IV and disclosed in the repro doc).

- [ ] **Step 1: Write the failing test**

```python
# add to src/tests/test_option_price_loader.py
from datetime import date
import pandas as pd
from engine.options.option_price_loader import model_option_daily


def _ul(prices):
    idx = pd.date_range("2025-09-01", periods=len(prices), freq="D", tz="UTC")
    return pd.DataFrame({"timestamp": idx, "open": prices, "high": prices,
                         "low": prices, "close": prices, "volume": [1]*len(prices)})


def test_model_option_daily_prices_with_black76():
    ul = _ul([9000, 9100, 9300, 9200])  # underlying rises -> call gains
    df = model_option_daily(strike=9000, expiry=date(2025, 12, 17),
                            entry_date=date(2025, 9, 1), underlying=ul,
                            iv=0.18, max_hold=30)
    assert len(df) == 4
    # call value rises as underlying rises from 9000 -> 9300
    assert float(df["close"].iloc[2]) > float(df["close"].iloc[0])
    # high uses underlying high, low uses underlying low
    assert float(df["high"].iloc[0]) >= float(df["close"].iloc[0])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && .venv/bin/python -m pytest tests/test_option_price_loader.py::test_model_option_daily_prices_with_black76 -q`
Expected: FAIL with `ImportError: cannot import name 'model_option_daily'`

- [ ] **Step 3: Implement `model_option_daily`**

```python
# add to src/engine/options/option_price_loader.py
from engine.options.cn_ag_selector import _bs_call_price

IV_ASSUMPTION = {"ag": 0.18, "au": 0.20}  # pinned in Task 11 from observed ATM IV
_RISK_FREE = 0.02


def model_option_daily(strike: float, expiry: date, entry_date: date,
                       underlying: pd.DataFrame, iv: float, max_hold: int,
                       r: float = _RISK_FREE) -> pd.DataFrame | None:
    """Black-76 synthetic OPTION daily-OHLC over the underlying path.

    Each day prices the call at the day's underlying high/low/close (so the
    exit-sim can check take/stop). T = (expiry - day)/365 in years.
    """
    ul = underlying.copy()
    ul["date"] = pd.to_datetime(ul["timestamp"], utc=True).dt.date
    ul = ul[ul["date"] >= entry_date].sort_values("date").reset_index(drop=True)
    if ul.empty:
        return None
    ul = ul.head(max_hold + 5)
    rows = []
    for _, b in ul.iterrows():
        T = max((expiry - b["date"]).days, 0) / 365.0
        rows.append({
            "open":  _bs_call_price(float(b["open"]),  strike, T, r, iv),
            "high":  _bs_call_price(float(b["high"]),  strike, T, r, iv),
            "low":   _bs_call_price(float(b["low"]),   strike, T, r, iv),
            "close": _bs_call_price(float(b["close"]), strike, T, r, iv),
        })
    return pd.DataFrame(rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && .venv/bin/python -m pytest tests/test_option_price_loader.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
jj describe -m "feat(options): Black-76 model fallback option-path builder" && jj new
```

---

## Task 4: Price-loader — dispatcher with source tagging

**Files:**
- Modify: `src/engine/options/option_price_loader.py`
- Test: `src/tests/test_option_price_loader.py`

A single entry point that prefers real data and falls back to model, returning `(daily_ohlc, source)` where `source in {"market","model"}`. "Sufficient coverage" = real frame has ≥ `min_cover` rows (default 5) starting at entry.

- [ ] **Step 1: Write the failing test**

```python
# add to src/tests/test_option_price_loader.py
from engine.options.option_price_loader import premium_path


def test_premium_path_prefers_market(tmp_path):
    _write_contract(tmp_path, "ag2510c9000",
                    [(f"2025-09-0{i}", 10, 11, 9, 10) for i in range(1, 8)])
    ul = _ul([9000] * 7)
    df, src = premium_path("ag2510c9000", strike=9000, expiry=date(2025, 12, 17),
                           entry_date=date(2025, 9, 1), data_dir=tmp_path,
                           underlying=ul, iv=0.18, max_hold=30, min_cover=5)
    assert src == "market" and len(df) >= 5


def test_premium_path_falls_back_to_model(tmp_path):
    ul = _ul([9000, 9100, 9300, 9200, 9200, 9200])
    df, src = premium_path("ag9999c9000", strike=9000, expiry=date(2025, 12, 17),
                           entry_date=date(2025, 9, 1), data_dir=tmp_path,
                           underlying=ul, iv=0.18, max_hold=30, min_cover=5)
    assert src == "model" and df is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src && .venv/bin/python -m pytest tests/test_option_price_loader.py -k premium_path -q`
Expected: FAIL with `ImportError: cannot import name 'premium_path'`

- [ ] **Step 3: Implement `premium_path`**

```python
# add to src/engine/options/option_price_loader.py
def premium_path(contract_sym: str, *, strike: float, expiry: date,
                 entry_date: date, data_dir: Path, underlying: pd.DataFrame,
                 iv: float, max_hold: int, min_cover: int = 5):
    """Return (option_daily_ohlc, source). Market if the real contract has
    >= min_cover rows from entry_date, else Black-76 model."""
    real = load_option_daily(contract_sym, entry_date, data_dir, max_hold)
    if real is not None and len(real) >= min_cover:
        return real, "market"
    model = model_option_daily(strike, expiry, entry_date, underlying, iv, max_hold)
    return model, "model"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src && .venv/bin/python -m pytest tests/test_option_price_loader.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
jj describe -m "feat(options): premium_path dispatcher (market vs model)" && jj new
```

---

## Task 5: Emission replay — reusable signal generators for the 4 emitters

**Files:**
- Create: `src/engine/options/options_emission_replay.py`
- Test: (faithfulness test added in Task 6)

Reproduce, per emitter, the exact signals `score_today` would emit `options_calls` for. **Reuse** the detectors and scoring helpers — do not re-derive. Read the live blocks for the exact gate before implementing: divergence `score_today.py:877-925`, BPull `929-983`, PA H2 `988-1098`, Context A `1237-1303`.

The function returns, per emitter, a list of `EmittedSignal(emitter, sig_date, entry_close, calls)` where `calls` is the literal `select_otm_calls(...)`/`_au` output.

- [ ] **Step 1: Implement the replay module**

```python
# src/engine/options/options_emission_replay.py
"""Faithful replay of score_today's ag/au options_calls emission (4 emitters).
Each emitter reuses the same detector + score gate score_today applies. See
score_today.py:877-925 (divergence), 929-983 (bpull), 988-1098 (pa_h2),
1237-1303 (context_a)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from engine.divergence.bpull_detector import BPullDetector
from engine.divergence.context_a_detector import ContextADetector
from engine.divergence.pa_detector import PABottomDetector
from engine.divergence.pa_structure import PAStructureDetector

OPTIONS_MIN_SCORE = 3


@dataclass
class EmittedSignal:
    emitter: str          # "divergence" | "bpull" | "pa_h2" | "context_a"
    sig_date: date
    entry_close: float
    calls: list[dict]     # select_otm_calls(...) output


def _select(underlying: str):
    """Return (select_fn, enrich_fn, data_dir) for ag or au."""
    if underlying == "ag":
        from engine.options.cn_ag_selector import select_otm_calls, enrich_with_iv
        return select_otm_calls, enrich_with_iv
    from engine.options.cn_au_selector import select_otm_calls_au, enrich_with_iv_au
    return select_otm_calls_au, enrich_with_iv_au


def replay_bpull(bars, h_bars, underlying: str) -> list[EmittedSignal]:
    """score_today.py:929-983 — bscore = 4 if opposing else 2; emit when >=3."""
    select_fn, _ = _select(underlying)
    out = []
    for bsig in BPullDetector().scan(bars, h_bars):
        if bsig.direction != "bottom":
            continue
        bscore = 4 if bsig.higher_tf_relation == "opposing" else 2
        if bscore < OPTIONS_MIN_SCORE:
            continue
        close = float(bars["close"].iloc[bsig.bar_idx])
        out.append(EmittedSignal("bpull", bsig.timestamp.date(), close,
                                 select_fn(close, bsig.timestamp.date())))
    return out
```

(Implement `replay_pa_h2` and `replay_context_a` analogously, mirroring the live gates: PA H2 emits when `higher_tf_relation == "opposing"` — `pa_score` is 4/3 both ≥3 — using `PABottomDetector` + the isolation rule at `score_today.py:1040-1048`; Context A emits when `ContextADetector.policy_weight(asig, "cn_metal_futures", symbol=sym) > 0` — `ascore == 3` — using `ContextADetector().scan(bars, h_bars)`. Neither passes `mm_target_pct`.)

- [ ] **Step 2: Implement the divergence emitter (imports score_today helpers)**

```python
# add to src/engine/options/options_emission_replay.py
def replay_divergence(bars, h_bars, underlying: str, sym: str,
                      instrument_class: str = "cn_metal_futures") -> list[EmittedSignal]:
    """score_today.py:877-925 — score = readiness_score(matched, confidence);
    emit when bottom & score>=3, WITH mm_target_pct."""
    from scripts.score_today import (apply_policy, match_rule, readiness_score,
                                     _compute_mm_pct, _load_pool_rules_for,
                                     scan_divergences_for)  # see note below
    select_fn, _ = _select(underlying)
    pool_rules = _load_pool_rules_for(instrument_class)
    out = []
    for sig in scan_divergences_for(bars, h_bars, instrument_class):
        if sig.direction != "bottom":
            continue
        policy = apply_policy(sig, instrument_class=instrument_class)
        if policy.weight == 0.0:
            continue
        ctx = sig.context_features or {}
        matched = [r for r in pool_rules if match_rule(r, sig.direction, sig.subtype, ctx)]
        if readiness_score(matched, sig.confidence) < OPTIONS_MIN_SCORE:
            continue
        close = float(bars["close"].iloc[sig.candidate_bar_idx])
        mm = _compute_mm_pct(sig, bars, close)
        out.append(EmittedSignal("divergence", sig.timestamp.date(), close,
                                 select_fn(close, sig.timestamp.date(), mm_target_pct=mm)))
    return out
```

**Note for the implementer:** `apply_policy`, `match_rule`, `readiness_score`, `_compute_mm_pct` already exist in `score_today.py` (lines 760 +). The pool-rule loader and the divergence scan are currently inline in `score_today.main()`. **Verify** whether they are already importable; if the divergence scan / pool-rule load is not a standalone function, add a thin `scan_divergences_for(bars, h_bars, instrument_class)` and `_load_pool_rules_for(instrument_class)` helper in `score_today.py` that `main()` is refactored to call (pure extraction, no behavior change — the existing 490-test suite guards it). Do this extraction as its own commit before wiring it here.

- [ ] **Step 3: Commit**

```bash
jj describe -m "feat(options): faithful 4-emitter replay for ag/au options emission" && jj new
```

---

## Task 6: Faithfulness test — harness emission == score_today

**Files:**
- Test: `src/tests/test_options_emission_faithfulness.py`

Pin the replay to production: for a recent ag date, the union of the 4 replay emitters' emitted `contract_sym`s must equal what `score_today` outputs as `options_calls` for that symbol/date.

- [ ] **Step 1: Write the test**

```python
# src/tests/test_options_emission_faithfulness.py
"""The replay must reproduce score_today's live options_calls exactly.
If this fails, score_today's emission changed and the replay must follow."""
from datetime import date

from data import bar_loader
from pathlib import Path

from engine.options.options_emission_replay import (
    replay_bpull, replay_pa_h2, replay_context_a, replay_divergence)

BARS = Path(__file__).resolve().parents[1] / "data" / "raw"


def _load(sym, suffix):
    return bar_loader.load_bars_quant_or_json(sym, suffix, BARS)


def test_replay_contracts_subset_of_selector_for_ag():
    bars = _load("kq_m_shfe_ag", "_daily")
    h = _load("kq_m_shfe_ag", "_60")
    emitted = (replay_bpull(bars, h, "ag") + replay_pa_h2(bars, h, "ag")
               + replay_context_a(bars, h, "ag")
               + replay_divergence(bars, h, "ag", "kq_m_shfe_ag"))
    # Every emitted signal carries >=1 OTM call with a well-formed contract_sym.
    assert emitted, "expected >=1 ag emission over full history"
    for e in emitted:
        assert e.calls and all(c["contract_sym"].startswith("ag") for c in e.calls)
```

- [ ] **Step 2: Run + verify it passes**

Run: `cd src && .venv/bin/python -m pytest tests/test_options_emission_faithfulness.py -q`
Expected: PASS. If it errors on a missing helper, finish the Task-5 extraction note first.

- [ ] **Step 3: Manual cross-check (one-time, recorded in repro doc later)**

Run `score_today` for `kq_m_shfe_ag` and capture any emitted `options_calls`; confirm the same `contract_sym`s appear in the replay for the matching dates. Record the checked date(s) in the repro doc.

Run: `cd src && .venv/bin/python scripts/score_today.py --help` (confirm invocation), then run it for the metal pool and grep the ag options block.

- [ ] **Step 4: Commit**

```bash
jj describe -m "test(options): faithfulness of emission replay vs score_today" && jj new
```

---

## Task 7: Aggregate — folds + verdict

**Files:**
- Create: `src/scripts/backtest_options_attribution.py` (aggregate functions only this task)
- Test: `src/tests/test_options_attribution_aggregate.py`

- [ ] **Step 1: Write the failing test**

```python
# src/tests/test_options_attribution_aggregate.py
from scripts.backtest_options_attribution import fold_of, verdict_for


def test_fold_split_is_oos():
    assert fold_of(2023) == "is" and fold_of(2024) == "oos" and fold_of(2026) == "oos"


def test_verdict_promote_regime_reject():
    assert verdict_for(is_ev=1.3, oos_ev=1.2) == "PROMOTE"
    assert verdict_for(is_ev=0.2, oos_ev=1.4) == "REGIME_ONLY"
    assert verdict_for(is_ev=0.9, oos_ev=0.8) == "REJECT"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd src && .venv/bin/python -m pytest tests/test_options_attribution_aggregate.py -q`
Expected: FAIL with `ModuleNotFoundError`/`ImportError`.

- [ ] **Step 3: Implement `fold_of` + `verdict_for`**

```python
# src/scripts/backtest_options_attribution.py  (start the file)
"""Attribution backtest for score_today's ag/au options_calls emission.
Replays the live emission, prices each Rank-1 OTM call (real data + Black-76
fallback), simulates the validated DD-line exit, aggregates IS/OOS folds.
Spec: docs/superpowers/specs/2026-06-10-options-attribution-design.md"""
from __future__ import annotations

IS_CUTOFF_YEAR = 2023  # IS <= 2023, OOS >= 2024


def fold_of(year: int) -> str:
    return "is" if year <= IS_CUTOFF_YEAR else "oos"


def verdict_for(is_ev: float, oos_ev: float) -> str:
    """EV_mult > 1.0 = profit. PROMOTE iff both folds profitable; REGIME_ONLY
    iff only OOS; REJECT iff neither."""
    if is_ev > 1.0 and oos_ev > 1.0:
        return "PROMOTE"
    if oos_ev > 1.0:
        return "REGIME_ONLY"
    return "REJECT"
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd src && .venv/bin/python -m pytest tests/test_options_attribution_aggregate.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
jj describe -m "feat(options): attribution fold split + verdict rule" && jj new
```

---

## Task 8: Orchestrator — wire replay → price → exit → aggregate → baseline JSON

**Files:**
- Modify: `src/scripts/backtest_options_attribution.py`

Tick sizes: `ag=1.0`, `au=2.0`. Exit params (DD-line validated): `take1=2.0`, `take2=4.0`, `stop_ticks=5`, `max_hold=30`.

- [ ] **Step 1: Implement the run pipeline**

```python
# add to src/scripts/backtest_options_attribution.py
import argparse, json
from pathlib import Path

import pandas as pd
from data import bar_loader
from engine.options.option_price_loader import premium_path, IV_ASSUMPTION
from engine.options.option_exit import simulate_entry
from engine.options.options_emission_replay import (
    replay_bpull, replay_pa_h2, replay_context_a, replay_divergence)

REPO = Path(__file__).resolve().parents[1]
BARS_DIR = REPO / "data" / "raw"
TICK = {"ag": 1.0, "au": 2.0}
UL_SYMBOL = {"ag": "kq_m_shfe_ag", "au": "kq_m_shfe_au"}
EXIT = dict(take1_mult=2.0, take2_mult=4.0, max_hold=30)
STOP_TICKS = 5


def _opt_dir(underlying: str) -> Path:
    return REPO / "data" / "options" / "cn" / underlying


def run(underlying: str) -> dict:
    ul_sym = UL_SYMBOL[underlying]
    bars = bar_loader.load_bars_quant_or_json(ul_sym, "_daily", BARS_DIR)
    h = bar_loader.load_bars_quant_or_json(ul_sym, "_60", BARS_DIR)
    tick, iv, odir = TICK[underlying], IV_ASSUMPTION[underlying], _opt_dir(underlying)

    emitted = (replay_bpull(bars, h, underlying)
               + replay_pa_h2(bars, h, underlying)
               + replay_context_a(bars, h, underlying)
               + replay_divergence(bars, h, underlying, ul_sym))

    trades, market_n, model_n = [], 0, 0
    for e in emitted:
        if not e.calls:
            continue
        c = sorted(e.calls, key=lambda x: x["otm_pct"])[0]  # Rank 1
        expiry = pd.Timestamp(_expiry_from_calls(c)).date()
        opt, src = premium_path(c["contract_sym"], strike=float(c["strike"]),
                                expiry=expiry, entry_date=e.sig_date, data_dir=odir,
                                underlying=bars, iv=iv, max_hold=EXIT["max_hold"])
        if opt is None or opt.empty:
            continue
        market_n += src == "market"; model_n += src == "model"
        entry_price = float(opt["close"].iloc[0])
        entry = {"entry_idx": 0, "entry_price": entry_price,
                 "stop_price": entry_price - STOP_TICKS * tick}
        res = simulate_entry(opt, entry, **EXIT)
        trades.append({"year": e.sig_date.year, "emitter": e.emitter,
                       "mult": res["mult"], "source": src})
    return _aggregate(underlying, trades, market_n, model_n)
```

Add `_expiry_from_calls(c)` (derive the expiry `date` from `c["expiry_month"]` "YYMM" via the selector's `_expiry_date_for_month`) and `_aggregate(underlying, trades, market_n, model_n)` (group by `fold_of(year)`, compute `ev_mult = mean(mult)`, `win_pct = mean(mult > 1.0)*100`, `n`; per-year sub-rows; `modeled_fraction = model_n/(market_n+model_n)`; `verdict = verdict_for(is_ev, oos_ev)`; assemble the baseline dict per spec Section 7).

- [ ] **Step 2: Implement `main()` + `--out-json`**

```python
# add to src/scripts/backtest_options_attribution.py
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--underlying", choices=["ag", "au"], required=True)
    ap.add_argument("--out-json", type=Path, default=None)
    args = ap.parse_args()
    baseline = run(args.underlying)
    print(json.dumps(baseline, indent=2, default=str))
    if args.out_json:
        args.out_json.write_text(json.dumps(baseline, indent=2, default=str))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Smoke-run both underlyings**

Run: `cd src && .venv/bin/python scripts/backtest_options_attribution.py --underlying ag`
Expected: prints a baseline JSON with `samples.is/oos`, `pricing.modeled_fraction`, `verdict`. Note the `modeled_fraction` (high modeled% must be flagged in the repro doc).
Run again with `--underlying au`. Confirm no crash.

- [ ] **Step 4: Commit**

```bash
jj describe -m "feat(options): attribution orchestrator (replay->price->exit->aggregate)" && jj new
```

---

## Task 9: Pin IV assumptions + write baselines

**Files:**
- Modify: `src/engine/options/option_price_loader.py` (`IV_ASSUMPTION`)
- Create: `baselines/options_ag.json`, `baselines/options_au.json`

- [ ] **Step 1: Pin IV from observed ATM IV**

For each underlying, compute the median ATM IV at signal dates that DO have market data (use `estimate_iv` over the Rank-1 contract's entry-day market price where available). Set `IV_ASSUMPTION["ag"]`/`["au"]` to those medians (round to 2 dp). Record both values + sample sizes for the repro doc.

Run: `cd src && .venv/bin/python scripts/backtest_options_attribution.py --underlying ag --out-json ../baselines/options_ag.json`
Run: `cd src && .venv/bin/python scripts/backtest_options_attribution.py --underlying au --out-json ../baselines/options_au.json`

- [ ] **Step 2: Validate the JSON + sanity-check fields**

Run: `.venv/bin/python -c "import json; [json.load(open(f'baselines/options_{u}.json')) for u in ('ag','au')]; print('ok')"`
Expected: `ok`. Eyeball: `verdict`, `samples.is.ev_mult`, `samples.oos.ev_mult`, `pricing.modeled_fraction`, `cells.rank1`.

- [ ] **Step 3: Commit**

```bash
jj describe -m "feat(options): pin ag/au IV assumptions + write attribution baselines" && jj new
```

---

## Task 10: Repro doc

**Files:**
- Create: `doc/repro/options_attribution_2026-06-10.md`

- [ ] **Step 1: Write the repro doc**

Sections: method (entry/exit/pricing/folds, mirroring the spec); results table per underlying (IS/OOS `ev_mult`/`win`/`n`, Rank-1 primary + Rank-2/3 + mm-strike secondary cells); **modeled-fraction disclosure** (and the pinned IV assumptions from Task 9); verdict per underlying with reasoning (PROMOTE/REGIME_ONLY/REJECT); caveats (coverage gaps, illiquid-strike model reliance, thin n); the faithfulness cross-check date(s) from Task 6; repro commands.

- [ ] **Step 2: Commit**

```bash
jj describe -m "docs(repro): options-attribution ag/au results + verdict" && jj new
```

---

## Task 11: Full suite + codex review + final commit

- [ ] **Step 1: Run the entire test suite**

Run: `cd src && .venv/bin/python -m pytest -q`
Expected: all pass (490 prior + new option tests).

- [ ] **Step 2: Codex review (project convention)**

Run: `codex review --uncommitted` (then `codex review --base <last-reviewed-commit>` if already committed). Fix any P1/P2, re-run tests.

- [ ] **Step 3: Update NEXT_SESSION handoff**

Add the options-attribution result (verdict per underlying, modeled fraction) and move "US ETF options edge" / "drift-gate integration for options baselines" to the bounded-cleanups/backlog table. Commit.

```bash
jj describe -m "docs(repro): record options-attribution outcome in NEXT_SESSION" && jj new
```

---

## Self-review notes (resolved)

- **Spec coverage:** replay (Tasks 5-6) ✓; price-loader real+model+dispatch (Tasks 2-4) ✓; exit-sim reuse (Task 1) ✓; folds+verdict (Task 7) ✓; baseline schema (Tasks 8-9) ✓; repro doc (Task 10) ✓; testing (each task) ✓; out-of-scope items deferred (Task 11 handoff). 
- **Highest-risk task:** the divergence emitter (Task 5 Step 2) — depends on extracting `scan_divergences_for`/`_load_pool_rules_for` from `score_today.main()`. The extraction is a pure refactor guarded by the 490-test suite; if it proves entangled, fall back to replicating `readiness_score`'s inputs and EXPAND the faithfulness test (Task 6) to assert equality on a held date before trusting it.
- **Known approximation:** model-path OHLC prices the call at the underlying's daily high/low (not a within-day option path); documented as a model limitation in the repro doc. Acceptable because `modeled_fraction` is disclosed and market data is preferred whenever present.
