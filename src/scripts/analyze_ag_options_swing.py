"""Xiao-style options swing strategy simulation for ag PA H2 signals.

Strategy rules (v1):
  Entry:   Daily PA H2 signal; buy 2% OTM call at next-day open (approx close)
  Filter:  Skip if 30d realized vol > VOL_CAP (options too expensive)
  Stop:    Cut option if value drops to STOP_FRAC of initial premium
  Profit:  Staged — sell 1/3 at TAKE1x, sell 1/3 at TAKE2x, run 1/3
  Roll:    When DTE < ROLL_DTE, sell current + buy same-strike 45-DTE call
  Exit:    Final 1/3 exits at MAX_HOLD or structural signal (modeled as close)

Key difference from futures backtest:
  - Stop is on OPTION premium (not underlying ATR)
  - Profit targets are option multiples (not underlying R-multiples)
  - Rolling modeled explicitly with cost

Usage:
    python scripts/analyze_ag_options_swing.py
    python scripts/analyze_ag_options_swing.py --otm 0.01 --take1 2 --take2 5
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data import bar_loader
from engine.divergence.pa_detector import PABottomDetector
from scripts.analyze_ag_options_theta import compute_atr, black76_call

# ---------------------------------------------------------------------------
# Default parameters
# ---------------------------------------------------------------------------
OTM_PCT    = 0.02    # 浅虚 2% OTM
DTE_ENTRY  = 45      # initial DTE
ROLL_DTE   = 15      # roll when DTE falls below this
ROLL_COST  = 0.003   # roll friction: 0.3% of underlying per roll
STOP_FRAC  = 0.30    # cut option if value < 30% of initial premium (–70% stop)
TAKE1_MULT = 2.0     # first tranche exit at 2x premium
TAKE2_MULT = 4.0     # second tranche exit at 4x premium
VOL_CAP    = 0.40    # skip signal if realized vol > 40%
MAX_HOLD   = 60      # max holding days
ATR_PERIOD = 14
VOL_WINDOW = 30
RISK_FREE  = 0.02
STOP_MULT  = 1.5     # for underlying structural stop reference only


# ---------------------------------------------------------------------------
# Per-day option simulation
# ---------------------------------------------------------------------------

def simulate_option_swing(
    bars: pd.DataFrame,
    entry_idx: int,
    rvol_series: pd.Series,
    otm_pct: float,
    dte_entry: int,
    stop_frac: float,
    take1_mult: float,
    take2_mult: float,
    roll_dte: int,
    roll_cost: float,
    max_hold: int,
    entry_type: str = "close",     # "close" or "low" (signal day's low as entry)
    stop_ticks: int | None = None, # if set: tick-based stop instead of stop_frac
    tick_size: float = 1.0,        # yuan/kg for SHFE ag options
) -> dict | None:
    """Simulate one options swing trade from entry_idx.

    entry_type="low": entry priced at signal day's low (approximates intraday 抓尖).
    stop_ticks: if provided, stop triggers when option value drops by
                stop_ticks × tick_size below entry (overrides stop_frac).
    """
    if entry_idx + 1 >= len(bars):
        return None

    F0_close = float(bars["close"].iloc[entry_idx])
    F0_entry = (float(bars["low"].iloc[entry_idx])
                if entry_type == "low" else F0_close)
    rv = float(rvol_series.iloc[entry_idx])
    if not np.isfinite(rv) or rv <= 0:
        return None

    # Strike anchored to close (underlying reference), entry priced at F0_entry
    K           = F0_close * (1 + otm_pct)
    dte_left    = dte_entry
    prem0       = black76_call(F0_entry, K, dte_left / 365.0, RISK_FREE, rv)
    if prem0 <= 0:
        return None

    # Stop level: tick-based or fraction-based
    if stop_ticks is not None:
        stop_level = prem0 - stop_ticks * tick_size
    else:
        stop_level = prem0 * stop_frac

    total_cost  = prem0          # cumulative premium paid (per unit)
    n_rolls     = 0
    size        = 1.0            # remaining position (starts full)
    proceeds    = 0.0            # realised proceeds from partial exits
    stop_hit    = False
    take1_done  = False
    take2_done  = False
    exit_day    = max_hold
    exit_reason = "maxhold"

    for offset in range(1, max_hold + 1):
        idx = entry_idx + offset
        if idx >= len(bars):
            exit_day = offset - 1
            exit_reason = "data_end"
            break

        F_now = float(bars["close"].iloc[idx])
        dte_left -= 1
        rv_now = float(rvol_series.iloc[idx])
        if not np.isfinite(rv_now) or rv_now <= 0:
            rv_now = rv

        # Roll when DTE too low (and still have position)
        if dte_left < roll_dte and size > 0:
            # Sell remaining at current value, buy new 45-DTE call
            val_now = black76_call(F_now, K, dte_left / 365.0, RISK_FREE, rv_now)
            proceeds  += val_now * size
            roll_prem  = black76_call(F_now, K, dte_entry / 365.0, RISK_FREE, rv_now)
            roll_fee   = F_now * roll_cost
            total_cost += (roll_prem + roll_fee) * size
            prem0       = roll_prem  # new reference for stop/take
            if stop_ticks is not None:
                stop_level = prem0 - stop_ticks * tick_size
            else:
                stop_level = prem0 * stop_frac
            dte_left    = dte_entry
            n_rolls    += 1

        val_now = black76_call(F_now, K, dte_left / 365.0, RISK_FREE, rv_now)

        # Stop: option below stop_level (tick-based or fraction-based)
        if val_now < stop_level and size > 0:
            proceeds   += val_now * size
            size        = 0.0
            stop_hit    = True
            exit_day    = offset
            exit_reason = "stop"
            break

        # Take profit tranche 1: 1/3 at take1_mult × prem
        if not take1_done and val_now >= prem0 * take1_mult and size >= 1/3:
            proceeds   += val_now * (1/3)
            size       -= 1/3
            take1_done  = True

        # Take profit tranche 2: 1/3 at take2_mult × prem
        if not take2_done and val_now >= prem0 * take2_mult and size >= 1/3:
            proceeds   += val_now * (1/3)
            size       -= 1/3
            take2_done  = True

    # Exit remaining position at max_hold close
    if size > 0:
        F_fin    = float(bars["close"].iloc[min(entry_idx + exit_day, len(bars) - 1)])
        rv_fin   = float(rvol_series.iloc[min(entry_idx + exit_day, len(bars) - 1)])
        if not np.isfinite(rv_fin):
            rv_fin = rv
        T_fin    = max(0.0, dte_left / 365.0)
        val_fin  = black76_call(F_fin, K, T_fin, RISK_FREE, rv_fin)
        proceeds += val_fin * size

    net_pnl    = proceeds - total_cost
    mult       = proceeds / total_cost if total_cost > 0 else 0.0

    return {
        "prem0":       round(prem0, 1),
        "prem_pct":    round(prem0 / F0_close * 100, 2),
        "entry_discount": round((F0_close - F0_entry) / F0_close * 100, 2),
        "total_cost":  round(total_cost, 1),
        "proceeds":    round(proceeds, 1),
        "net_pnl":     round(net_pnl, 1),
        "mult":        round(mult, 3),
        "n_rolls":     n_rolls,
        "exit_day":    exit_day,
        "exit_reason": exit_reason,
        "take1_done":  take1_done,
        "take2_done":  take2_done,
        "stop_hit":    stop_hit,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="ag PA H2 options swing simulation")
    parser.add_argument("--otm",     type=float, default=OTM_PCT)
    parser.add_argument("--take1",   type=float, default=TAKE1_MULT)
    parser.add_argument("--take2",   type=float, default=TAKE2_MULT)
    parser.add_argument("--stop",    type=float, default=STOP_FRAC,
                        help="Cut if option value < STOP × initial premium")
    parser.add_argument("--vol-cap", type=float, default=VOL_CAP)
    parser.add_argument("--dte",     type=int,   default=DTE_ENTRY)
    parser.add_argument("--roll",    type=int,   default=ROLL_DTE)
    parser.add_argument("--htf", type=str, default=None,
                        choices=["opposing", "supporting", "none"],
                        help="Filter by higher_tf_relation (none=no 60min data)")
    parser.add_argument("--hopp-only", action="store_true",
                        help="Shortcut for --htf opposing")
    parser.add_argument("--min-conf", type=float, default=0.0,
                        help="Minimum signal confidence (0–1)")
    parser.add_argument("--max-rv", type=float, default=None,
                        help="Only enter when realized vol ≤ MAX_RV (vol sweet-spot upper bound)")
    parser.add_argument("--entry-type", choices=["close", "low"], default="close",
                        help="Entry price basis: close (default) or signal-day low (抓尖 approximation)")
    parser.add_argument("--stop-ticks", type=int, default=None,
                        help="Tick-based stop: cut if option drops N ticks below entry (overrides --stop)")
    parser.add_argument("--tick-size", type=float, default=1.0,
                        help="Option minimum tick in yuan/kg (default 1.0 for SHFE ag)")
    args = parser.parse_args()

    bars_path = Path(__file__).resolve().parents[1] / "data" / "raw" / "kq_m_shfe_ag_daily.json"
    h60_path  = Path(__file__).resolve().parents[1] / "data" / "raw" / "kq_m_shfe_ag_60.json"
    bars = bar_loader.load_bars_json(bars_path)
    h60  = bar_loader.load_bars_json(h60_path) if h60_path.exists() else None

    log_ret = np.log(bars["close"] / bars["close"].shift(1))
    rvol    = log_ret.rolling(VOL_WINDOW).std() * np.sqrt(242)

    det  = PABottomDetector(min_h_legs=2, min_quality=0.3, ema_threshold=0.0, min_gap=10)
    sigs = det.scan(bars, h60)

    htf_filter = "opposing" if args.hopp_only else args.htf
    if htf_filter is not None:
        htf_val = None if htf_filter == "none" else htf_filter
        sigs = [s for s in sigs if s.higher_tf_relation == htf_val]
        print(f"htf={htf_filter} filter: {len(sigs)} signals")
    if args.min_conf > 0:
        sigs = [s for s in sigs if s.confidence >= args.min_conf]
        print(f"min_conf={args.min_conf} filter: {len(sigs)} signals")

    print(f"ag PA H2 options swing  —  "
          f"OTM={args.otm*100:.0f}%  DTE={args.dte}  "
          f"stop={args.stop*100:.0f}%  take1={args.take1}x  take2={args.take2}x  "
          f"vol_cap={args.vol_cap*100:.0f}%  roll<{args.roll}DTE"
          + (f"  [htf={htf_filter}]" if htf_filter else "")
          + (f"  [conf≥{args.min_conf:.2f}]" if args.min_conf > 0 else "")
          + (f"  [rv≤{args.max_rv*100:.0f}%]" if args.max_rv else "")
          + (f"  [entry={args.entry_type}]" if args.entry_type != "close" else "")
          + (f"  [stop={args.stop_ticks}tk]" if args.stop_ticks else ""))

    rows = []
    skipped_vol = 0
    for sig in sigs:
        i  = sig.bar_idx
        rv = float(rvol.iloc[i])
        if not np.isfinite(rv) or rv <= 0:
            continue
        if rv > args.vol_cap:
            skipped_vol += 1
            continue
        if args.max_rv is not None and rv > args.max_rv:
            skipped_vol += 1
            continue

        res = simulate_option_swing(
            bars, i, rvol,
            otm_pct=args.otm,
            dte_entry=args.dte,
            stop_frac=args.stop,
            take1_mult=args.take1,
            take2_mult=args.take2,
            roll_dte=args.roll,
            roll_cost=ROLL_COST,
            max_hold=MAX_HOLD,
            entry_type=args.entry_type,
            stop_ticks=args.stop_ticks,
            tick_size=args.tick_size,
        )
        if res is None:
            continue

        F0 = float(bars["close"].iloc[i])
        ts = bars["timestamp"].iloc[i].date()
        rows.append({
            "date":     str(ts),
            "F0":       round(F0, 0),
            "rv":       round(rv * 100, 1),
            **res,
        })

    if not rows:
        print("No tradeable signals after vol filter.")
        return 0

    df = pd.DataFrame(rows)
    n_total   = len(df)
    n_stop    = (df["exit_reason"] == "stop").sum()
    n_take2   = df["take2_done"].sum()
    n_take1   = df["take1_done"].sum()
    n_maxhold = (df["exit_reason"] == "maxhold").sum()
    n_profit  = (df["mult"] >= 1.0).sum()
    n_double  = (df["mult"] >= 2.0).sum()

    print(f"\nSignals after vol_cap filter: {n_total}  (skipped high-vol: {skipped_vol})")
    print()
    print("=" * 70)
    print("OUTCOME DISTRIBUTION")
    print("=" * 70)
    print(f"  Stopped out (–70%):      {n_stop:>3}  ({n_stop/n_total*100:.0f}%)")
    print(f"  Hit take1 (2x) only:     {n_take1-n_take2:>3}  ({(n_take1-n_take2)/n_total*100:.0f}%)")
    print(f"  Hit take2 (4x):          {n_take2:>3}  ({n_take2/n_total*100:.0f}%)")
    print(f"  Max-hold exit:           {n_maxhold:>3}  ({n_maxhold/n_total*100:.0f}%)")
    print(f"  Profitable (mult≥1.0):   {n_profit:>3}  ({n_profit/n_total*100:.0f}%)")
    print(f"  Doubled (mult≥2.0):      {n_double:>3}  ({n_double/n_total*100:.0f}%)")
    print()
    print("=" * 70)
    print("P&L STATISTICS  (per-option-premium basis)")
    print("=" * 70)
    print(f"  Avg initial premium:     {df['prem_pct'].mean():.2f}% of underlying")
    print(f"  Avg total cost (w/roll): {(df['total_cost']/df['F0']*100).mean():.2f}% of underlying")
    print(f"  Avg rolls per trade:     {df['n_rolls'].mean():.2f}")
    print(f"  Avg hold days:           {df['exit_day'].mean():.1f}")
    print(f"  Avg proceeds multiple:   {df['mult'].mean():.3f}x")
    print(f"  Median multiple:         {df['mult'].median():.3f}x")
    print(f"  Avg net P&L (pts):       {df['net_pnl'].mean():.1f}")
    print()

    # EV breakdown by outcome
    print("=" * 70)
    print("EV BY OUTCOME GROUP")
    print("=" * 70)
    for reason, label in [("stop","Stopped"), ("maxhold","MaxHold")]:
        sub = df[df["exit_reason"] == reason]
        if not sub.empty:
            print(f"  {label:<12} n={len(sub):>2}  avg_mult={sub['mult'].mean():.3f}x")
    for label, mask in [("Take1 only", df["take1_done"] & ~df["take2_done"]),
                        ("Take2 hit",  df["take2_done"])]:
        sub = df[mask]
        if not sub.empty:
            print(f"  {label:<12} n={len(sub):>2}  avg_mult={sub['mult'].mean():.3f}x")
    print()

    # Per-signal detail
    print("=" * 70)
    print("PER-SIGNAL DETAIL")
    print("=" * 70)
    hdr = (f"{'date':<12} {'F0':>7} {'rv':>5} {'prem%':>6} {'days':>5} "
           f"{'rolls':>5} {'mult':>7} {'reason':<10} {'t1':>3} {'t2':>3}")
    print(hdr)
    print("-" * 70)
    for _, r in df.iterrows():
        t1 = "✓" if r["take1_done"] else "—"
        t2 = "✓" if r["take2_done"] else "—"
        print(f"{r['date']:<12} {r['F0']:>7.0f} {r['rv']:>4.0f}% "
              f"{r['prem_pct']:>5.2f}% {r['exit_day']:>5} "
              f"{r['n_rolls']:>5} {r['mult']:>7.3f}x {r['exit_reason']:<10} {t1:>3} {t2:>3}")

    print()
    print(f"Overall EV: {df['mult'].mean():.3f}x  "
          f"(need >1.0 to be profitable; need >1/{1/(1-args.stop):.1f} = {1/(1-args.stop)*args.stop:.2f}x on wins to cover stops)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
