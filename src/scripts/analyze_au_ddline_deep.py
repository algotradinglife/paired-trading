"""Strategy B1/B2 deep analysis for au options — IS/OOS + contract breakdown.

Runs a focused parameter sweep on au DD-line strategies, then drills into:
  - IS vs OOS split (IS: entry_date < 2024-01-01, OOS: entry_date >= 2025-01-01)
  - Contract month group (near ≤90d, mid 91-180d, far >180d at entry)
  - OTM% at entry (using au futures price reference)
  - Per-contract top performers

Usage:
    uv run python scripts/analyze_au_ddline_deep.py
    uv run python scripts/analyze_au_ddline_deep.py --strategy B1 --top-n 15
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.sweep_ddline_options import (
    load_all_contracts,
    find_retest_entries,
    find_breakout_entries,
    simulate_entry,
)

TICK_SIZE  = 2.0   # practical au option tick unit (yuan/gram)
IS_CUTOFF  = "2024-01-01"
OOS_START  = "2025-01-01"

# Focused parameter grid (based on ag best-param neighborhood)
FOCUSED_GRID = {
    "stop_ticks":       [4, 5, 6],
    "retest_tol":       [10, 15],
    "bounce_min":       [0.08, 0.12],
    "decline_min":      [0.20, 0.30],
    "peak_window":      [5, 7],
    "trend_window":     [5],
    "cycle_reset_mult": [3.0],
    "take1_mult":       [1.5, 2.0],
    "take2_mult":       [3.0, 4.0],
    "max_hold":         [30],
}


# ---------------------------------------------------------------------------
# Contract metadata from filename
# ---------------------------------------------------------------------------

def _parse_contract(name: str) -> dict:
    """Parse au contract name like 'au2507c880' → expiry month, strike."""
    m = re.match(r"^au(\d{4})c(\d+)$", name)
    if not m:
        return {}
    yymm, strike = m.groups()
    year = 2000 + int(yymm[:2])
    month = int(yymm[2:])
    expiry = pd.Timestamp(year=year, month=month, day=26)  # approximate expiry
    return {"expiry": expiry, "strike": float(strike)}


# ---------------------------------------------------------------------------
# Load au futures for OTM% reference
# ---------------------------------------------------------------------------

def _load_au_futures() -> pd.DataFrame | None:
    p = ROOT / "data" / "raw" / "kq_m_shfe_au_daily.json"
    if not p.exists():
        return None
    payload = json.loads(p.read_text())
    df = pd.DataFrame(payload["bars"])
    df["date"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_localize(None)
    return df.sort_values("date").reset_index(drop=True)


def _futures_price_at(fut_df: pd.DataFrame, trade_date: str) -> float | None:
    """Get au futures close price on or before trade_date."""
    td = pd.Timestamp(trade_date)
    mask = fut_df["date"].dt.normalize() <= td
    if not mask.any():
        return None
    return float(fut_df.loc[mask, "close"].iloc[-1])


# ---------------------------------------------------------------------------
# Period labelling
# ---------------------------------------------------------------------------

def _period(entry_date: str) -> str:
    if entry_date < IS_CUTOFF:
        return "IS"
    if entry_date >= OOS_START:
        return "OOS"
    return "GAP(2024)"


# ---------------------------------------------------------------------------
# DTE-at-entry bucket
# ---------------------------------------------------------------------------

def _dte_bucket(dte_days: int) -> str:
    if dte_days <= 90:
        return "near(≤90d)"
    if dte_days <= 180:
        return "mid(91-180d)"
    return "far(>180d)"


def _otm_bucket(otm_pct: float) -> str:
    if otm_pct < 0:
        return "ITM"
    if otm_pct < 5:
        return "slight(0-5%)"
    if otm_pct < 15:
        return "OTM(5-15%)"
    if otm_pct < 30:
        return "deep(15-30%)"
    return "vdeep(>30%)"


# ---------------------------------------------------------------------------
# Focused sweep
# ---------------------------------------------------------------------------

def run_focused_sweep(
    contracts: dict[str, pd.DataFrame],
    strategy: str,
    verbose: bool = False,
) -> pd.DataFrame:
    keys   = list(FOCUSED_GRID.keys())
    values = list(FOCUSED_GRID.values())
    rows   = []

    total = 1
    for v in values:
        total *= len(v)

    for idx, combo in enumerate(product(*values)):
        params = dict(zip(keys, combo))
        all_trades: list[dict] = []

        for name, daily in contracts.items():
            if strategy in ("B1", "both"):
                entries = find_retest_entries(
                    daily,
                    stop_ticks=params["stop_ticks"],
                    tick_size=TICK_SIZE,
                    retest_tol=params["retest_tol"],
                    bounce_min=params["bounce_min"],
                    decline_min=params["decline_min"],
                    peak_window=params["peak_window"],
                    cycle_reset_mult=params["cycle_reset_mult"],
                )
                for e in entries:
                    t = simulate_entry(daily, e, params["take1_mult"], params["take2_mult"], params["max_hold"])
                    t["contract"] = name
                    all_trades.append(t)

            if strategy in ("B2", "both"):
                entries = find_breakout_entries(
                    daily,
                    stop_ticks=params["stop_ticks"],
                    tick_size=TICK_SIZE,
                    decline_min=params["decline_min"],
                    peak_window=params["peak_window"],
                    trend_window=params["trend_window"],
                    cycle_reset_mult=params["cycle_reset_mult"],
                )
                for e in entries:
                    t = simulate_entry(daily, e, params["take1_mult"], params["take2_mult"], params["max_hold"])
                    t["contract"] = name
                    all_trades.append(t)

        if not all_trades:
            continue

        df = pd.DataFrame(all_trades)
        n       = len(df)
        n_stop  = (df["exit_reason"] == "stop").sum()
        ev_mult = df["mult"].mean()
        ev_r    = df["r"].mean()
        hit     = (df["mult"] > 1.0).mean()

        rows.append({
            **params,
            "n": n, "n_stop": n_stop, "stop_pct": round(n_stop / n * 100, 0),
            "ev_mult": round(ev_mult, 3), "ev_r": round(ev_r, 3),
            "hit_pct": round(hit * 100, 1),
        })

        if verbose and idx % 50 == 0:
            print(f"  [{idx+1}/{total}] best so far ev_mult={max(r['ev_mult'] for r in rows):.3f}")

    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ---------------------------------------------------------------------------
# Drill-down with best params
# ---------------------------------------------------------------------------

def collect_trades(
    contracts: dict[str, pd.DataFrame],
    params: dict,
    strategy: str,
    fut_df: pd.DataFrame | None,
) -> pd.DataFrame:
    trades = []
    for name, daily in contracts.items():
        meta = _parse_contract(name)
        expiry = meta.get("expiry")
        strike = meta.get("strike")

        if strategy in ("B1", "both"):
            entries = find_retest_entries(
                daily,
                stop_ticks=int(params["stop_ticks"]),
                tick_size=TICK_SIZE,
                retest_tol=int(params["retest_tol"]),
                bounce_min=float(params["bounce_min"]),
                decline_min=float(params["decline_min"]),
                peak_window=int(params["peak_window"]),
                cycle_reset_mult=float(params["cycle_reset_mult"]),
            )
            for e in entries:
                t = simulate_entry(daily, e, float(params["take1_mult"]),
                                   float(params["take2_mult"]), int(params["max_hold"]))
                t["contract"] = name
                t["strategy_tag"] = "B1"
                trades.append(t)

        if strategy in ("B2", "both"):
            entries = find_breakout_entries(
                daily,
                stop_ticks=int(params["stop_ticks"]),
                tick_size=TICK_SIZE,
                decline_min=float(params["decline_min"]),
                peak_window=int(params["peak_window"]),
                trend_window=int(params["trend_window"]),
                cycle_reset_mult=float(params["cycle_reset_mult"]),
            )
            for e in entries:
                t = simulate_entry(daily, e, float(params["take1_mult"]),
                                   float(params["take2_mult"]), int(params["max_hold"]))
                t["contract"] = name
                t["strategy_tag"] = "B2"
                trades.append(t)

    if not trades:
        return pd.DataFrame()

    df = pd.DataFrame(trades).sort_values("entry_date")

    # Enrich: period, DTE, OTM%
    df["period"] = df["entry_date"].map(_period)

    for name, daily in contracts.items():
        meta = _parse_contract(name)
        expiry = meta.get("expiry")
        strike = meta.get("strike")
        if expiry is None or strike is None:
            continue
        mask = df["contract"] == name
        if mask.sum() == 0:
            continue
        entry_dates = pd.to_datetime(df.loc[mask, "entry_date"])
        dte_days = (expiry - entry_dates).dt.days.clip(lower=0)
        df.loc[mask, "dte_at_entry"] = dte_days
        df.loc[mask, "strike"] = strike
        df.loc[mask, "expiry_ym"] = expiry.strftime("%Y%m")

        # OTM% from futures price
        if fut_df is not None:
            for idx, edate in zip(df.index[mask], df.loc[mask, "entry_date"]):
                fp = _futures_price_at(fut_df, edate)
                if fp is not None and fp > 0:
                    df.at[idx, "otm_pct"] = (strike - fp) / fp * 100
                    df.at[idx, "fut_price"] = fp

    if "dte_at_entry" in df.columns:
        df["dte_bucket"] = df["dte_at_entry"].fillna(-1).apply(
            lambda x: _dte_bucket(int(x)) if x >= 0 else "unknown"
        )
    if "otm_pct" in df.columns:
        df["otm_bucket"] = df["otm_pct"].apply(
            lambda x: _otm_bucket(x) if pd.notna(x) else "unknown"
        )

    return df


def _report_group(df: pd.DataFrame, label: str, width: int = 35) -> None:
    if df.empty:
        print(f"  {label:{width}s}  n=  0")
        return
    n   = len(df)
    ev  = df["mult"].mean()
    hit = (df["mult"] > 1.0).mean()
    stop_n = (df["exit_reason"] == "stop").sum()
    t2_n   = (df["exit_reason"] == "take2").sum()
    print(f"  {label:{width}s}  n={n:4d}  EV={ev:+.3f}x  hit={hit:.0%}  "
          f"stop={stop_n:3d}  t2={t2_n:3d}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="both", choices=["B1", "B2", "both"])
    ap.add_argument("--top-n",    type=int, default=10)
    ap.add_argument("--verbose",  action="store_true")
    ap.add_argument("--skip-sweep", action="store_true",
                    help="Skip sweep, use hardcoded best params for drill-down only")
    args = ap.parse_args()

    print(f"\n{'='*80}")
    print(f"Strategy B1/B2 Deep Analysis — au  (strategy={args.strategy})")
    print(f"IS: entry_date < {IS_CUTOFF}   OOS: entry_date >= {OOS_START}")
    print(f"{'='*80}")

    print("Loading au contracts...", end=" ", flush=True)
    contracts = load_all_contracts("au")
    print(f"{len(contracts)} loaded")

    fut_df = _load_au_futures()
    if fut_df is None:
        print("WARNING: au futures data not found — OTM% unavailable")

    # -----------------------------------------------------------
    # Focused sweep
    # -----------------------------------------------------------
    if not args.skip_sweep:
        total_combos = 1
        for v in FOCUSED_GRID.values():
            total_combos *= len(v)
        print(f"\nFocused sweep: {total_combos} parameter combinations...")

        results = run_focused_sweep(contracts, args.strategy, verbose=args.verbose)

        if results.empty:
            print("No trades found.")
            return 0

        results = results[results["n"] >= 5].copy()
        results_sorted = results.sort_values("ev_mult", ascending=False)

        print(f"\nValid combos (n≥5): {len(results)}")
        print(f"\nTop {args.top_n} by EV_mult:")
        print(f"{'─'*85}")
        disp_cols = ["stop_ticks", "retest_tol", "bounce_min", "decline_min",
                     "peak_window", "take1_mult", "take2_mult", "max_hold",
                     "n", "stop_pct", "ev_mult", "ev_r", "hit_pct"]
        print(results_sorted.head(args.top_n)[disp_cols].to_string(index=False))

        best_params = results_sorted.iloc[0].to_dict()
        print(f"\nBEST PARAMS  EV={best_params['ev_mult']:.3f}x  "
              f"stop={int(best_params['stop_ticks'])}tk  "
              f"retest={int(best_params['retest_tol'])}tk  "
              f"bounce≥{best_params['bounce_min']*100:.0f}%  "
              f"decline≥{best_params['decline_min']*100:.0f}%  "
              f"peak_win={int(best_params['peak_window'])}  "
              f"take1={best_params['take1_mult']}x  take2={best_params['take2_mult']}x  "
              f"hold≤{int(best_params['max_hold'])}d")
    else:
        # Hardcoded best params (from typical ag-neighbourhood best)
        best_params = {
            "stop_ticks": 5, "retest_tol": 10, "bounce_min": 0.08,
            "decline_min": 0.20, "peak_window": 5, "trend_window": 5,
            "cycle_reset_mult": 3.0, "take1_mult": 2.0, "take2_mult": 4.0,
            "max_hold": 30,
        }
        print(f"Using hardcoded params: {best_params}")

    # -----------------------------------------------------------
    # Drill-down with best params
    # -----------------------------------------------------------
    print(f"\n{'='*80}")
    print("DRILL-DOWN with best params")
    print(f"{'='*80}")

    df = collect_trades(contracts, best_params, args.strategy, fut_df)
    if df.empty:
        print("No trades collected.")
        return 0

    # Overall
    print(f"\n── Overall ({args.strategy}) ──")
    _report_group(df, "ALL trades")

    # IS / OOS
    print(f"\n── By period ──")
    for per in ["IS", "GAP(2024)", "OOS"]:
        _report_group(df[df["period"] == per], per)

    # By strategy tag
    if args.strategy == "both":
        print(f"\n── By strategy ──")
        for st in ["B1", "B2"]:
            _report_group(df[df["strategy_tag"] == st], st)
        print(f"\n── B1 by period ──")
        b1 = df[df["strategy_tag"] == "B1"]
        for per in ["IS", "GAP(2024)", "OOS"]:
            _report_group(b1[b1["period"] == per], f"B1 {per}")
        print(f"\n── B2 by period ──")
        b2 = df[df["strategy_tag"] == "B2"]
        for per in ["IS", "GAP(2024)", "OOS"]:
            _report_group(b2[b2["period"] == per], f"B2 {per}")

    # By DTE bucket
    if "dte_bucket" in df.columns:
        print(f"\n── By DTE-at-entry ──")
        for bkt in ["near(≤90d)", "mid(91-180d)", "far(>180d)"]:
            _report_group(df[df["dte_bucket"] == bkt], bkt)

    # By OTM% bucket
    if "otm_bucket" in df.columns:
        print(f"\n── By OTM%% at entry ──")
        for bkt in ["ITM", "slight(0-5%)", "OTM(5-15%)", "deep(15-30%)", "vdeep(>30%)"]:
            _report_group(df[df["otm_bucket"] == bkt], bkt)

    # By OTM × Period cross-tab (OOS focus)
    oos_df = df[df["period"] == "OOS"]
    if not oos_df.empty and "otm_bucket" in oos_df.columns:
        print(f"\n── OOS only: by OTM%% ──")
        for bkt in ["ITM", "slight(0-5%)", "OTM(5-15%)", "deep(15-30%)", "vdeep(>30%)"]:
            _report_group(oos_df[oos_df["otm_bucket"] == bkt], f"OOS {bkt}")

    # Top contracts by EV (min 3 trades, all periods)
    print(f"\n── Top 20 contracts by EV_mult (n≥3) ──")
    per_contract = (
        df.groupby("contract").agg(
            n=("mult", "count"),
            ev_mult=("mult", "mean"),
            hit_pct=("mult", lambda x: (x > 1.0).mean() * 100),
            stop_pct=("exit_reason", lambda x: (x == "stop").mean() * 100),
        ).query("n >= 3").sort_values("ev_mult", ascending=False)
    )
    print(per_contract.head(20).to_string())

    # Trade log for OOS
    if not oos_df.empty:
        print(f"\n── OOS trade log ──")
        print(f"  {'contract':<25} {'date':<12} {'strat':<4} {'entry':>7} {'stop':>7} "
              f"{'mult':>7} {'exit':<10} {'t1':>3} {'t2':>3}")
        for _, row in oos_df.sort_values("entry_date").iterrows():
            t1 = "✓" if row.get("take1") else "—"
            t2 = "✓" if row.get("take2") else "—"
            print(f"  {str(row['contract']):<25} {row['entry_date']:<12} "
                  f"{row.get('strategy_tag', '?'):<4} "
                  f"{row['entry_price']:>7.1f} {row['stop_price']:>7.1f} "
                  f"{row['mult']:>7.3f}x {row['exit_reason']:<10} {t1:>3} {t2:>3}")

    # Save
    out = Path("/tmp/au_ddline_deep.csv")
    df.to_csv(out, index=False)
    print(f"\nFull trade data saved to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
