# PA TOP Path B (A_top put lane) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Discover whether a "sell-the-rally in a confirmed downtrend" put lane (A_top entry) has a walk-forward edge, then conditionally productionize it.

**Architecture:** A new backtest harness `backtest_pa_atop.py` fires on `classify_context_top(...) == "A_top"` (NOT the failed `PATopDetector`), forward-sims a SHORT, tags each trade with daily phase × h_rel × pool, and runs a K=3 walk-forward. The winning cell (if any, with BULL-phase as a negative sanity check) is promoted to a baseline + score_today put emission; otherwise recorded REJECT.

**Tech Stack:** Python 3, pandas, pytest, run from `src/` with `.venv/bin/python`. VCS is **jj** (`jj describe`/`jj new`, never git). Spec: `docs/superpowers/specs/2026-06-10-pa-top-path-b-design.md`.

---

## File Structure

- **Create** `src/scripts/backtest_pa_atop.py` — the A_top discovery harness (one responsibility: scan A_top → short-sim → phase×h_rel×pool K=3 grid).
- **Create** `src/tests/test_backtest_pa_atop.py` — unit tests for the harness's pure helpers.
- **Conditional (promote)** `baselines/pa_atop_<pool>.json`, edits to `src/scripts/backtest_full_stack.py` (`_lane_atop`), `src/scripts/score_today.py` (put emission), `baselines/EXPECTED_LANES.json`.
- **Conditional (reject)** `baselines/pa_atop_<pool>.json` (verdict REJECT) + `doc/repro/pa_atop_wf_2026-06-10.md`.

## Canonical shapes (keep exact)

- A_top entry: `classify_context_top(bars, i, macd_df, ema20, ema60) == "A_top"`.
- Short R sign: a downmove → **positive** R; up to stop → **−1.0**.
- h_rel (TOP/short convention, per `pa_detector.py:69-70`): `"supporting"` = HTF DIF<0 (HTF bearish, **confirms** the short) ; `"opposing"` = HTF DIF>0 ; `"neutral"` = 0.
- phase ∈ {BULL, BEAR, TR, TR_FORMING, UNCLEAR} from `PAStructureDetector().detect(bars, up_to_idx=i).phase`.
- fold period ∈ {IS, OOS1, OOS2, OOS3} from cutoffs (annual default 2022-12-31 / 2023-12-31 / 2024-12-31).

---

## Task 1: Build the A_top harness + unit tests

**Files:** Create `src/scripts/backtest_pa_atop.py`, `src/tests/test_backtest_pa_atop.py`

- [ ] **Step 1: Write failing tests** in `src/tests/test_backtest_pa_atop.py`:

```python
import numpy as np
import pandas as pd
from scripts.backtest_pa_atop import simulate_short, htf_relation_top, fold_period


def _bars(closes, highs=None, lows=None):
    n = len(closes)
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, tz="UTC"),
        "open": closes, "close": closes,
        "high": highs if highs is not None else [c * 1.001 for c in closes],
        "low":  lows if lows is not None else [c * 0.999 for c in closes],
        "volume": [1] * n,
    })


def test_simulate_short_profits_on_downmove():
    # entry at 100, ATR=1, stop_mult=1.5 → stop=101.5, tp1=98.5, tp2=97
    closes = [100, 99, 97, 96, 95]
    bars = _bars(closes, highs=[100.5]*5, lows=[c - 0.2 for c in closes])
    atr = pd.Series([1.0] * 5)
    r = simulate_short(bars, 0, atr, stop_mult=1.5, max_hold=4)
    assert r is not None and r > 0  # price fell → short profits


def test_simulate_short_stopped_on_upmove():
    closes = [100, 100, 100, 100, 100]
    bars = _bars(closes, highs=[102.0]*5, lows=[99.8]*5)  # high 102 ≥ stop 101.5
    atr = pd.Series([1.0] * 5)
    r = simulate_short(bars, 0, atr, stop_mult=1.5, max_hold=4)
    assert r == -1.0


def test_htf_relation_top_convention():
    h_ts = pd.to_datetime(["2024-01-01", "2024-01-02"], utc=True).values
    # HTF DIF < 0 → bearish → SUPPORTS a short
    assert htf_relation_top(pd.Timestamp("2024-01-03", tz="UTC"), h_ts,
                            np.array([-0.5, -0.3])) == "supporting"
    # HTF DIF > 0 → bullish → OPPOSES a short
    assert htf_relation_top(pd.Timestamp("2024-01-03", tz="UTC"), h_ts,
                            np.array([0.5, 0.3])) == "opposing"
    # no HTF bar before ts
    assert htf_relation_top(pd.Timestamp("2023-12-01", tz="UTC"), h_ts,
                            np.array([0.5, 0.3])) is None


def test_fold_period_k3():
    c1 = pd.Timestamp("2022-12-31", tz="UTC")
    c2 = pd.Timestamp("2023-12-31", tz="UTC")
    c3 = pd.Timestamp("2024-12-31", tz="UTC")
    assert fold_period(pd.Timestamp("2022-06-01", tz="UTC"), c1, c2, c3) == "IS"
    assert fold_period(pd.Timestamp("2023-06-01", tz="UTC"), c1, c2, c3) == "OOS1"
    assert fold_period(pd.Timestamp("2024-06-01", tz="UTC"), c1, c2, c3) == "OOS2"
    assert fold_period(pd.Timestamp("2025-06-01", tz="UTC"), c1, c2, c3) == "OOS3"
```

- [ ] **Step 2: Run → FAIL** `cd src && .venv/bin/python -m pytest tests/test_backtest_pa_atop.py -q` (ModuleNotFoundError).

- [ ] **Step 3: Implement `src/scripts/backtest_pa_atop.py`.** Mirror `backtest_pa_standalone.py` + `backtest_pa_top_grid.py`. Full code:

```python
"""A_top sell-the-rally put-lane K=3 discovery backtest.

Fires on classify_context_top(...) == "A_top" (a DIF<0 counter-trend rally in a
downtrend), forward-sims a SHORT, and stratifies by daily phase x h_rel x pool
across a K=3 walk-forward. See docs/superpowers/specs/2026-06-10-pa-top-path-b-design.md.

Usage:
  uv run python scripts/backtest_pa_atop.py --pool US_EQUITY
  uv run python scripts/backtest_pa_atop.py --pool CN_METAL --cutoff3 2024-12-31
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from data import bar_loader
from engine.divergence.pa_context_classifier import classify_context_top
from engine.divergence.pa_structure import PAStructureDetector
from engine.features.macd import macd as compute_macd

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
ATR_PERIOD = 14
MAX_HOLD = 40
MIN_GAP = 10

POOLS: dict[str, list[str]] = {
    "US_EQUITY": ["spy", "qqq", "iwm", "dia", "gld", "gdx", "xlf", "xlk",
                  "nvda", "xlb", "xle", "xlre", "xlu"],
    "CN_METAL": ["kq_m_shfe_rb", "kq_m_shfe_cu", "kq_m_shfe_au",
                 "kq_m_shfe_ag", "kq_m_ine_sc"],
}


def load_bars(sym: str, bars_dir: Path, suffix: str = "_daily") -> pd.DataFrame | None:
    return bar_loader.load_bars_quant_or_json(sym, suffix, bars_dir)


def compute_atr(bars: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    hi, lo, pc = bars["high"], bars["low"], bars["close"].shift(1)
    tr = pd.concat([(hi - lo), (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def simulate_short(bars: pd.DataFrame, entry_idx: int, atr_series: pd.Series,
                   stop_mult: float = 1.5, max_hold: int = MAX_HOLD) -> float | None:
    """Short mirror of simulate_trade. Stop=entry+risk; TP1=entry-risk; TP2=entry-2risk.
    Downmove → +R; stopped → -1.0. (Verbatim port of backtest_pa_top_grid.simulate_short.)"""
    if entry_idx + 1 >= len(bars):
        return None
    entry = float(bars["close"].iloc[entry_idx])
    av = float(atr_series.iloc[entry_idx])
    if av <= 0 or not np.isfinite(av):
        return None
    risk = stop_mult * av
    stop = entry + risk
    tp1, tp2 = entry - risk, entry - 2 * risk
    hit_tp1 = False
    for offset in range(1, max_hold + 1):
        idx = entry_idx + offset
        if idx >= len(bars):
            break
        lo = float(bars["low"].iloc[idx])
        hi = float(bars["high"].iloc[idx])
        cl = float(bars["close"].iloc[idx])
        if not hit_tp1:
            if hi >= stop:
                return -1.0
            if lo <= tp1:
                hit_tp1 = True
                if lo <= tp2:
                    return 1.5
        else:
            if hi >= stop:
                return 0.0
            if lo <= tp2:
                return 1.5
            if offset == max_hold:
                return 0.5 + 0.5 * float(np.clip((entry - cl) / risk, -3, 3))
    idx_fin = min(entry_idx + max_hold, len(bars) - 1)
    return float(np.clip((entry - float(bars["close"].iloc[idx_fin])) / risk, -3, 3))


def htf_relation_top(ts: pd.Timestamp, h_ts: np.ndarray, h_dif: np.ndarray) -> str | None:
    """TOP/short convention: supporting = HTF DIF<0 (bearish, confirms short);
    opposing = HTF DIF>0 (bullish, counter); neutral = 0; None if no HTF bar."""
    ts_np = np.datetime64(ts.to_datetime64())
    mask = h_ts <= ts_np
    if not mask.any():
        return None
    v = float(h_dif[int(np.flatnonzero(mask)[-1])])
    if not np.isfinite(v):
        return None
    if v < 0:
        return "supporting"
    if v > 0:
        return "opposing"
    return "neutral"


def fold_period(ts, c1, c2, c3) -> str:
    if c3 is None:
        return "IS" if ts <= c1 else ("OOS1" if ts <= c2 else "OOS2")
    return ("IS" if ts <= c1 else "OOS1" if ts <= c2 else
            "OOS2" if ts <= c3 else "OOS3")


def scan_symbol(sym, bars, h_bars, atr, macd_df, ema20, ema60, c1, c2, c3, pool):
    """Yield trade records for A_top fires on this symbol."""
    struct_det = PAStructureDetector()
    if h_bars is not None:
        hm = compute_macd(h_bars["close"], hist_scale=1.0)
        h_dif = hm["dif"].values.astype(float)
        h_ts = pd.to_datetime(h_bars["timestamp"]).values
    else:
        h_dif = h_ts = None
    last_idx = -999
    out = []
    for i in range(len(bars)):
        if classify_context_top(bars, i, macd_df, ema20, ema60) != "A_top":
            continue
        if i - last_idx < MIN_GAP:
            continue
        r = simulate_short(bars, i, atr, stop_mult=1.5, max_hold=MAX_HOLD)
        if r is None:
            continue
        last_idx = i
        ts = pd.Timestamp(bars["timestamp"].iloc[i])
        phase = struct_det.detect(bars, up_to_idx=i).phase
        h_rel = (htf_relation_top(ts, h_ts, h_dif) if h_dif is not None else None)
        out.append({"pool": pool, "symbol": sym, "bar_idx": i, "timestamp": ts,
                    "period": fold_period(ts, c1, c2, c3), "r": r,
                    "phase": phase, "h_rel": h_rel})
    return out


def _report(label, sub, k3, width=34):
    if sub.empty:
        print(f"  {label:{width}s}: n=  0"); return
    parts = []
    for p, lbl in [("IS", "IS"), ("OOS1", "F1"), ("OOS2", "F2"), ("OOS3", "F3")]:
        g = sub[sub["period"] == p]
        if len(g):
            parts.append(f"{lbl}={g['r'].mean():+.3f}(n={len(g)})")
    print(f"  {label:{width}s}: n={len(sub):4d}  EV={sub['r'].mean():+.3f}R  "
          f"hit={(sub['r']>0).mean():.0%}  " + "  ".join(parts))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pool", default="US_EQUITY", choices=list(POOLS))
    p.add_argument("--cutoff1", default="2022-12-31")
    p.add_argument("--cutoff2", default="2023-12-31")
    p.add_argument("--cutoff3", default="2024-12-31")
    p.add_argument("--bars-dir", type=Path, default=DEFAULT_BARS_DIR)
    p.add_argument("--htf-suffix", default="_weekly",
                   help="suffix for higher-TF bars used for h_rel. If absent for a "
                        "pool, h_bars=None -> h_rel=None and the phase breakdown still works.")
    args = p.parse_args()
    c1 = pd.Timestamp(args.cutoff1, tz="UTC")
    c2 = pd.Timestamp(args.cutoff2, tz="UTC")
    c3 = pd.Timestamp(args.cutoff3, tz="UTC") if args.cutoff3 else None

    records = []
    for sym in POOLS[args.pool]:
        bars = load_bars(sym, args.bars_dir)
        if bars is None or len(bars) < 80:
            continue
        h_bars = load_bars(sym, args.bars_dir, suffix=args.htf_suffix)
        atr = compute_atr(bars)
        macd_df = compute_macd(bars["close"])
        ema20 = bars["close"].ewm(span=20, adjust=False).mean()
        ema60 = bars["close"].ewm(span=60, adjust=False).mean()
        records.extend(scan_symbol(sym, bars, h_bars, atr, macd_df, ema20, ema60,
                                   c1, c2, c3, args.pool))

    if not records:
        print("No A_top signals found.")
        return
    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    k3 = c3 is not None

    print(f"\nA_top put-lane K=3 — pool={args.pool}  n={len(df)}")
    print(f"Periods: IS<={args.cutoff1}  F1->{args.cutoff2}  F2->{args.cutoff3}  F3>")
    print("=" * 92)
    print("\n--- By phase (sanity: BULL must be NEGATIVE) ---")
    for ph in ["BULL", "TR", "TR_FORMING", "BEAR", "UNCLEAR"]:
        _report(f"phase={ph}", df[df["phase"] == ph], k3)
    print("\n--- By phase x h_rel ---")
    for ph in ["BEAR", "TR", "TR_FORMING"]:
        for hr in ["supporting", "opposing", "neutral"]:
            _report(f"{ph} + h={hr}", df[(df["phase"] == ph) & (df["h_rel"] == hr)], k3)
    out = Path(f"/tmp/pa_atop_{args.pool.lower()}.csv")
    df.to_csv(out, index=False)
    print(f"\nSaved {len(df)} signals → {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run → PASS** `cd src && .venv/bin/python -m pytest tests/test_backtest_pa_atop.py -q` (expect 4 passed).
- [ ] **Step 5: Full suite no regression** `cd src && .venv/bin/python -m pytest tests/ -q`.
- [ ] **Step 6: Commit** `jj describe -m "feat(pa-top): backtest_pa_atop.py — A_top put-lane K=3 discovery harness" && jj new`

---

## Task 2: Run the K=3 discovery + interpret (no code; produces the verdict)

- [ ] **Step 1: Run both pools**
  `cd src && .venv/bin/python scripts/backtest_pa_atop.py --pool US_EQUITY`
  `cd src && .venv/bin/python scripts/backtest_pa_atop.py --pool CN_METAL`
  Capture the "By phase" and "By phase x h_rel" tables.

- [ ] **Step 2: Apply the sanity gate.** Confirm **BULL-phase A_top EV is negative** in each pool. If it is NOT negative, STOP — the reframe premise is suspect; report to the user, do not promote.

- [ ] **Step 3: Identify a promotable cell.** A cell promotes only if **3/3 OOS folds positive** with adequate n (treat any fold n<10 as thin). Expected winner: `BEAR + h=supporting` (HTF bearish confirms). Note the EV/folds.

- [ ] **Step 4: Cross-check robustness** with an alternate cutoff framing (mirror pa_us_60min): rerun with `--cutoff1 2023-12-31 --cutoff2 2024-12-31 --cutoff3 2025-06-30`. The winning cell's OOS folds should stay positive across both framings.

- [ ] **Step 5: Decide** — promote (→ Task 3A) or reject (→ Task 3B). Record the per-cell numbers either way.

---

## Task 3A: Productionize (ONLY if a cell promoted)

- [ ] **Step 1:** Write `baselines/pa_atop_<pool>.json` (schema v2) mirroring `pa_us_60min_us_equity.json`: `schema_version:2`, `lane:"pa_atop"`, `full_stack_lane:"pa_atop"`, `pool`, `symbols_included` (the pool's symbols), `detector_params` (A_top via classify_context_top, stop 1.5xATR, max_hold 40, min_gap 10, winning phase+h_rel), `samples` (is/f1/f2/f3 from the run), `samples_aggregate`, `fold_date_ranges`, `verdict` (PASS/CONDITIONAL/marginal), `policy_weight_assigned`+`recommended`, `repro_command` (the exact backtest_pa_atop command), `production_binding`, `valid_until` (+~150d), `commit_hash`, `last_verified`, `data_snapshot` (today), `requires_verification:false`.
- [ ] **Step 2:** Add a `_lane_atop` emitter to `backtest_full_stack.py` (mirror `_lane_context_a`): fire on A_top in the winning phase, short outcome via the structural stop, so the lane appears in `--out-json` per-(lane,symbol) → drift gate covers it. Smoke-run `--pool <pool> --out-json /tmp/x.json` and confirm `pa_atop` in `lanes`.
- [ ] **Step 3:** Wire `score_today.py` to emit a put signal on the winning A_top cell (mirror the context_A emit path) with a structural stop at resistance populating `invalidation_level` (reject to None if stop ≤ entry). Add to `baselines/EXPECTED_LANES.json`.
- [ ] **Step 4:** Verify: `validate_baselines.py --full` shows `pa_atop` OK within tolerance; drift gate quiet; full suite green.
- [ ] **Step 5:** Commit `jj describe -m "feat(pa-top): promote A_top put lane <pool> (K=3 PASS)" && jj new`

## Task 3B: Record REJECT (ONLY if no cell promoted)

- [ ] **Step 1:** Write `baselines/pa_atop_<pool>.json` with `verdict:"REJECT"`, the per-cell `samples`, and `policy_weight_assigned:0.0`, `verdict_reason` citing the failed cells + BULL-negative confirmation.
- [ ] **Step 2:** Write `doc/repro/pa_atop_wf_2026-06-10.md` with the full per-cell tables from both pools + both cutoff framings.
- [ ] **Step 3:** Commit `jj describe -m "docs(pa-top): A_top put lane REJECT — K=3 no promotable cell" && jj new`. Report to user: B1_top next, or accept no put lane.

---

## Task 4: Codex review + STATUS + finish

- [ ] **Step 1:** `codex review --base <pre-task-1 commit>` (redirect to a file; read only the tail). Fix any P1/P2.
- [ ] **Step 2:** Update `STATUS.md` "PA TOP" section with the outcome (promoted lane + dashboard row, or REJECT verdict).
- [ ] **Step 3:** Commit + (on user OK) push.

---

## Self-review notes
- The harness reuses `simulate_short` verbatim from `backtest_pa_top_grid.py` (DRY note: kept local to keep the harness self-contained, like the other standalone harnesses).
- `h_rel` uses the TOP/short convention (supporting = HTF bearish = confirming) — opposite of the bottom lanes; tests lock it.
- HTF bars for h_rel use `_weekly` suffix (daily signals → weekly HTF). If `_weekly` bars are absent for a pool, `h_bars=None` → `h_rel=None` and the phase-only breakdown still works (the phase sanity gate doesn't depend on h_rel).
- Productionization (Task 3A) is deliberately under-specified on exact weights/cells because those are outputs of Task 2; the implementer fills them from the run. This is a discovery plan, not a fixed-output plan.
