"""Approach B — DD线 on daily aggregated option K-lines.

Strategy (Xiao Laoshi 飞天期权, daily view):
  Phase 1 — Decline:  Option falls from peak to a significant low (DD线确定).
  Phase 2 — Bounce:   Option bounces ≥ BOUNCE_MIN% from the low.
  Phase 3 — Retest:   Option returns to within RETEST_TOL ticks of the initial low.
             → Enter at the retest level (DD线支撑).
             → Stop: STOP_TICKS below the initial low (一滴不剩).
             → Target: TAKE1_MULT × entry, TAKE2_MULT × entry.

This is the W-bottom / double-bottom detection on the option K-line chart,
which approximates the DD线 left-side entry without requiring intraday data.

Data flow: 15min option JSON → aggregate to daily active-session bars → apply algorithm.

Usage:
    python scripts/analyze_ag_options_ddline.py
    python scripts/analyze_ag_options_ddline.py --file data/options/cn/ag/ag2310c6100_15min.json
    python scripts/analyze_ag_options_ddline.py --stop-ticks 5 --take1 1.5 --take2 3.0
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data import bar_loader

# ---------------------------------------------------------------------------
# Default parameters
# ---------------------------------------------------------------------------
STOP_TICKS   = 3       # ticks below initial low (一滴不剩)
TICK_SIZE    = 1.0     # yuan/kg for SHFE ag options
RETEST_TOL   = 3       # option must return within N ticks of initial low to trigger
BOUNCE_MIN   = 0.10    # bounce ≥ 10% from initial low before watching for retest
DECLINE_MIN  = 0.30    # initial decline ≥ 30% from recent peak to set DD-line low
PEAK_WINDOW  = 15      # look-back days for recent peak
TAKE1_MULT   = 1.5
TAKE2_MULT   = 2.5
MAX_HOLD     = 30      # trading days


# ---------------------------------------------------------------------------
# Daily bar aggregation from 15min
# ---------------------------------------------------------------------------

def aggregate_to_daily(bars: pd.DataFrame) -> pd.DataFrame:
    """Aggregate 15min option bars to active-session daily OHLC.

    Uses calendar date of each bar (not UTC session grouping).
    Filters to days with non-trivial price range (eliminates flat/illiquid days).
    """
    bars = bars.copy()
    bars["date"] = bars["timestamp"].dt.date
    daily = (
        bars.groupby("date")
        .agg(open=("open", "first"),
             high=("high", "max"),
             low=("low", "min"),
             close=("close", "last"),
             volume=("volume", "sum"))
        .reset_index()
    )
    daily["date"] = pd.to_datetime(daily["date"])
    # Keep only days where price actually moved (range > 0.5 yuan/kg)
    daily = daily[daily["high"] - daily["low"] > 0.5].reset_index(drop=True)
    return daily


# ---------------------------------------------------------------------------
# W-bottom DD-line detection
# ---------------------------------------------------------------------------

def find_dd_entries(
    daily: pd.DataFrame,
    stop_ticks: int,
    tick_size: float,
    retest_tol: int,
    bounce_min: float,
    decline_min: float,
    peak_window: int,
) -> list[dict]:
    """Detect DD-line retest entry opportunities on daily option K-lines.

    Returns list of entry dicts with: entry_idx, entry_price, initial_low,
    bounce_high, decline_pct, bounce_pct.
    """
    entries = []
    n = len(daily)
    state = "looking_for_low"   # states: looking_for_low → waiting_bounce → watching_retest
    initial_low_idx = None
    initial_low_val = None
    bounce_high_val = None
    cooldown_until  = -1

    for i in range(peak_window, n):
        if i <= cooldown_until:
            continue

        close_now = float(daily["close"].iloc[i])
        low_now   = float(daily["low"].iloc[i])
        high_now  = float(daily["high"].iloc[i])

        if state == "looking_for_low":
            # Look for a significant decline from recent peak
            recent_high = float(daily["high"].iloc[max(0, i - peak_window):i].max())
            if recent_high <= 0:
                continue
            decline_pct = (recent_high - low_now) / recent_high
            if decline_pct >= decline_min:
                # Found the DD-line low
                initial_low_idx = i
                initial_low_val = low_now
                bounce_high_val = close_now
                state = "waiting_bounce"

        elif state == "waiting_bounce":
            # Wait for a bounce ≥ bounce_min from the initial low
            bounce_high_val = max(bounce_high_val, high_now)
            if initial_low_val and initial_low_val > 0:
                bounce_pct = (bounce_high_val - initial_low_val) / initial_low_val
                if bounce_pct >= bounce_min:
                    state = "watching_retest"

        elif state == "watching_retest":
            # Watch for a retest of the initial low
            # Trigger: low returns within retest_tol ticks of initial_low_val
            retest_level = initial_low_val + retest_tol * tick_size
            if low_now <= retest_level:
                entry_price = max(initial_low_val, low_now)  # fill at DD-line
                recent_high = float(daily["high"].iloc[max(0, initial_low_idx - peak_window):initial_low_idx].max())
                decline_pct = (recent_high - initial_low_val) / recent_high if recent_high > 0 else 0
                bounce_pct  = (bounce_high_val - initial_low_val) / initial_low_val if initial_low_val > 0 else 0

                entries.append({
                    "entry_idx":    i,
                    "entry_price":  entry_price,
                    "initial_low":  initial_low_val,
                    "bounce_high":  bounce_high_val,
                    "decline_pct":  round(decline_pct * 100, 1),
                    "bounce_pct":   round(bounce_pct * 100, 1),
                    "stop_price":   initial_low_val - stop_ticks * tick_size,
                })
                # Reset to avoid chaining retests
                state = "looking_for_low"
                cooldown_until = i + 3
                initial_low_idx = None
                initial_low_val = None
                bounce_high_val = None

            # If price drops significantly below initial_low (stop territory), reset
            elif low_now < initial_low_val - stop_ticks * tick_size * 3:
                state = "looking_for_low"
                initial_low_idx = None

    return entries


# ---------------------------------------------------------------------------
# Trade simulation (on daily bars)
# ---------------------------------------------------------------------------

def simulate_entry(
    daily: pd.DataFrame,
    entry: dict,
    take1_mult: float,
    take2_mult: float,
    max_hold: int,
) -> dict:
    """Simulate one DD-line entry from entry["entry_idx"]."""
    entry_idx   = entry["entry_idx"]
    entry_price = entry["entry_price"]
    stop_price  = entry["stop_price"]
    take1_price = entry_price * take1_mult
    take2_price = entry_price * take2_mult

    size = 1.0
    proceeds = 0.0
    take1_done = take2_done = False
    exit_day = max_hold
    exit_reason = "maxhold"
    peak_val = entry_price

    for offset in range(1, max_hold + 1):
        idx = entry_idx + offset
        if idx >= len(daily):
            exit_day = offset - 1
            exit_reason = "data_end"
            break

        lo = float(daily["low"].iloc[idx])
        hi = float(daily["high"].iloc[idx])
        cl = float(daily["close"].iloc[idx])
        peak_val = max(peak_val, hi)

        # Stop
        if lo <= stop_price and size > 0:
            proceeds += stop_price * size
            size = 0.0
            exit_day = offset
            exit_reason = "stop"
            break

        # Take1: sell half at take1_mult
        if not take1_done and hi >= take1_price and size >= 0.5:
            proceeds += take1_price * 0.5
            size -= 0.5
            take1_done = True

        # Take2: sell rest at take2_mult
        if not take2_done and hi >= take2_price and size > 0:
            proceeds += take2_price * size
            size = 0.0
            take2_done = True
            exit_day = offset
            exit_reason = "take2"
            break

    if size > 0:
        final_idx = min(entry_idx + exit_day, len(daily) - 1)
        proceeds += float(daily["close"].iloc[final_idx]) * size

    net_pnl = proceeds - entry_price
    mult = proceeds / entry_price if entry_price > 0 else 0.0
    risk = entry_price - stop_price

    return {
        **entry,
        "proceeds":    round(proceeds, 1),
        "net_pnl":     round(net_pnl, 1),
        "mult":        round(mult, 3),
        "peak_val":    round(peak_val, 1),
        "exit_day":    exit_day,
        "exit_reason": exit_reason,
        "take1_done":  take1_done,
        "take2_done":  take2_done,
        "r_multiple":  round(net_pnl / risk, 2) if risk > 0 else 0.0,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="DD-line option entry simulation (daily option K-lines)")
    parser.add_argument("--file", type=Path, default=None,
                        help="15min option JSON file to aggregate (default: all ag *_15min.json)")
    parser.add_argument("--stop-ticks",  type=int,   default=STOP_TICKS)
    parser.add_argument("--tick-size",   type=float, default=TICK_SIZE)
    parser.add_argument("--retest-tol",  type=int,   default=RETEST_TOL)
    parser.add_argument("--bounce-min",  type=float, default=BOUNCE_MIN)
    parser.add_argument("--decline-min", type=float, default=DECLINE_MIN)
    parser.add_argument("--take1",       type=float, default=TAKE1_MULT)
    parser.add_argument("--take2",       type=float, default=TAKE2_MULT)
    parser.add_argument("--max-hold",    type=int,   default=MAX_HOLD)
    parser.add_argument("--all-files",   action="store_true",
                        help="Run on all ag 15min option files")
    args = parser.parse_args()

    opt_dir = Path(__file__).resolve().parents[1] / "data" / "options" / "cn" / "ag"

    if args.all_files:
        files = sorted(opt_dir.glob("*_15min.json"))
    elif args.file:
        files = [args.file]
    else:
        files = [sorted(opt_dir.glob("*_15min.json"))[0]]

    all_rows = []

    for path in files:
        raw = bar_loader.load_bars_json(path)
        daily = aggregate_to_daily(raw)
        if len(daily) < 10:
            continue

        print(f"\n{'='*70}")
        print(f"{path.name}")
        print(f"  {daily['date'].iloc[0].date()} → {daily['date'].iloc[-1].date()}  "
              f"({len(daily)} active days)  "
              f"price {daily['close'].min():.0f}–{daily['close'].max():.0f}")
        print(f"  stop={args.stop_ticks}tk  bounce≥{args.bounce_min*100:.0f}%  "
              f"decline≥{args.decline_min*100:.0f}%  "
              f"take1={args.take1}x  take2={args.take2}x  max_hold={args.max_hold}d")

        entries = find_dd_entries(
            daily,
            stop_ticks=args.stop_ticks,
            tick_size=args.tick_size,
            retest_tol=args.retest_tol,
            bounce_min=args.bounce_min,
            decline_min=args.decline_min,
            peak_window=PEAK_WINDOW,
        )

        if not entries:
            print("  No DD-line entries found.")
            continue

        rows = []
        for e in entries:
            res = simulate_entry(daily, e, args.take1, args.take2, args.max_hold)
            entry_dt = daily["date"].iloc[e["entry_idx"]]
            exit_idx = min(e["entry_idx"] + res["exit_day"], len(daily) - 1)
            exit_dt  = daily["date"].iloc[exit_idx]
            res["entry_date"] = str(entry_dt.date())
            res["exit_date"]  = str(exit_dt.date())
            rows.append(res)
            all_rows.append(res)

        df = pd.DataFrame(rows)
        n_total = len(df)
        n_stop  = (df["exit_reason"] == "stop").sum()
        n_take2 = df["take2_done"].sum()
        n_take1 = df["take1_done"].sum()

        print(f"\n  {'date':<12} {'init_lo':>7} {'entry¥':>7} {'stop¥':>6} "
              f"{'dec%':>5} {'bnc%':>5} {'mult':>7} {'reason':<10} {'t1':>3} {'t2':>3}")
        print(f"  {'-'*68}")
        for _, r in df.iterrows():
            t1 = "✓" if r["take1_done"] else "—"
            t2 = "✓" if r["take2_done"] else "—"
            print(f"  {r['entry_date']:<12} {r['initial_low']:>7.1f} {r['entry_price']:>7.1f} "
                  f"{r['stop_price']:>6.1f} {r['decline_pct']:>4.0f}% {r['bounce_pct']:>4.0f}% "
                  f"{r['mult']:>7.3f}x {r['exit_reason']:<10} {t1:>3} {t2:>3}")

        risk = args.stop_ticks * args.tick_size
        ev_r = df["r_multiple"].mean()
        print(f"\n  n={n_total}  stop={n_stop} ({n_stop/n_total*100:.0f}%)"
              f"  take2={n_take2}  EV={df['mult'].mean():.3f}x  "
              f"per-risk={ev_r:.2f}R  (risk={risk:.0f}¥/kg per entry)")

    if all_rows:
        df_all = pd.DataFrame(all_rows)
        n = len(df_all)
        n_stop = (df_all["exit_reason"] == "stop").sum()
        risk = args.stop_ticks * args.tick_size
        print(f"\n{'='*70}")
        print(f"COMBINED SUMMARY  (all files)")
        print(f"  n={n}  stop={n_stop} ({n_stop/n*100:.0f}%)  "
              f"EV={df_all['mult'].mean():.3f}x  "
              f"per-risk={df_all['r_multiple'].mean():.2f}R")

    return 0


if __name__ == "__main__":
    sys.exit(main())
