"""Strategy A (期货传导法) for au PA H2 bottom signals → call options.

Approach:
  1. Detect PA H2 bottom signals on kq_m_shfe_au futures (daily)
  2. Buy a theoretical 45-DTE OTM call at signal-day close (Black-76 pricing)
  3. Managed exit: staged take-profit + stop

Three stop methods compared:
  stop_frac  — exit when option value < STOP_FRAC × initial premium
  stop_ticks — exit when option value drops N×tick_size from entry (absolute)
  delta_stop — exit when Black-76 delta falls below DELTA_FLOOR

h-filter breakdown:
  opposing   — 60min DIF < 0 at signal (h=opposing ← validated on cn_metal)
  supporting — 60min DIF > 0 at signal (h=supporting)
  all        — no filter

IS/OOS split: IS = signal date < 2024-01-01, OOS = ≥ 2025-01-01

Usage:
    uv run python scripts/backtest_strategy_a_au.py
    uv run python scripts/backtest_strategy_a_au.py --otm 0.03 --take1 2.0 --take2 5.0
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.divergence.pa_detector import PABottomDetector
from scripts.analyze_ag_options_theta import black76_call   # reuse Black-76 impl

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RISK_FREE  = 0.02     # annual risk-free rate
VOL_WINDOW = 30       # days for realized vol estimate
ATR_PERIOD = 14
TICK_SIZE  = 2.0      # practical tick unit for au (yuan/gram) — used in stop_ticks
IS_CUTOFF  = pd.Timestamp("2024-01-01", tz="UTC")
OOS_START  = pd.Timestamp("2025-01-01", tz="UTC")


# ---------------------------------------------------------------------------
# Black-76 delta
# ---------------------------------------------------------------------------

def black76_delta(F: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-76 delta (call) = e^{-rT} N(d1)."""
    if T <= 0 or sigma <= 0 or F <= 0:
        return 1.0 if F > K else 0.0
    d1 = (np.log(F / K) + 0.5 * sigma ** 2 * T) / (sigma * np.sqrt(T))
    return float(np.exp(-r * T) * norm.cdf(d1))


# ---------------------------------------------------------------------------
# Single-signal simulation
# ---------------------------------------------------------------------------

def simulate_one(
    bars: pd.DataFrame,
    entry_idx: int,
    rvol: pd.Series,
    otm_pct: float,
    dte_entry: int,
    take1_mult: float,
    take2_mult: float,
    max_hold: int,
    stop_method: str,      # "stop_frac" | "stop_ticks" | "delta_stop"
    stop_frac: float = 0.30,
    stop_ticks: int = 5,
    delta_floor: float = 0.10,
) -> dict | None:
    """Simulate one call option trade on au futures PA H2 signal.

    Returns result dict with mult, r, exit_reason.
    """
    if entry_idx + 1 >= len(bars):
        return None

    F0 = float(bars["close"].iloc[entry_idx])
    rv = float(rvol.iloc[entry_idx])
    if not np.isfinite(rv) or rv <= 0:
        return None

    K      = F0 * (1 + otm_pct)
    T0     = dte_entry / 365.0
    prem0  = black76_call(F0, K, T0, RISK_FREE, rv)
    if prem0 <= 0:
        return None

    dte_left = dte_entry
    size     = 1.0
    proceeds = 0.0
    t1_done = t2_done = False
    exit_day   = max_hold
    exit_reason = "maxhold"

    for offset in range(1, max_hold + 1):
        j = entry_idx + offset
        if j >= len(bars):
            exit_day    = offset - 1
            exit_reason = "data_end"
            break

        F_now   = float(bars["close"].iloc[j])
        dte_left -= 1
        rv_now  = float(rvol.iloc[j])
        if not np.isfinite(rv_now) or rv_now <= 0:
            rv_now = rv

        T_now   = max(dte_left / 365.0, 1e-6)
        val_now = black76_call(F_now, K, T_now, RISK_FREE, rv_now)

        # Stop check
        stop_triggered = False
        if stop_method == "stop_frac":
            stop_triggered = val_now < prem0 * stop_frac
        elif stop_method == "stop_ticks":
            stop_triggered = val_now < prem0 - stop_ticks * TICK_SIZE
        elif stop_method == "delta_stop":
            d = black76_delta(F_now, K, T_now, RISK_FREE, rv_now)
            stop_triggered = d < delta_floor

        if stop_triggered and size > 0:
            proceeds   += val_now * size
            size        = 0.0
            exit_day    = offset
            exit_reason = "stop"
            break

        # Take-profit: half at take1, rest at take2
        if not t1_done and val_now >= prem0 * take1_mult and size >= 0.5:
            proceeds += val_now * 0.5
            size     -= 0.5
            t1_done   = True

        if not t2_done and val_now >= prem0 * take2_mult and size > 0:
            proceeds  += val_now * size
            size       = 0.0
            t2_done    = True
            exit_day   = offset
            exit_reason = "take2"
            break

    if size > 0:
        j_fin   = min(entry_idx + exit_day, len(bars) - 1)
        F_fin   = float(bars["close"].iloc[j_fin])
        rv_fin  = float(rvol.iloc[j_fin])
        if not np.isfinite(rv_fin):
            rv_fin = rv
        T_fin   = max((dte_entry - exit_day) / 365.0, 1e-6)
        val_fin = black76_call(F_fin, K, T_fin, RISK_FREE, rv_fin)
        proceeds += val_fin * size

    net    = proceeds - prem0
    mult   = proceeds / prem0 if prem0 > 0 else 0.0
    r_val  = net / prem0  # R relative to initial premium as risk unit

    return {
        "prem0":       round(prem0, 2),
        "K":           round(K, 0),
        "proceeds":    round(proceeds, 2),
        "mult":        round(mult, 3),
        "r":           round(r_val, 3),
        "exit_reason": exit_reason,
        "exit_day":    exit_day,
        "take1":       t1_done,
        "take2":       t2_done,
    }


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def _period(ts: pd.Timestamp) -> str:
    if ts < IS_CUTOFF:
        return "IS"
    if ts >= OOS_START:
        return "OOS"
    return "GAP"


def report_table(rows: list[dict], label: str) -> None:
    if not rows:
        print(f"  {label}: n=0")
        return
    df = pd.DataFrame(rows)
    n   = len(df)
    ev  = df["mult"].mean()
    hit = (df["mult"] > 1.0).mean()

    is_df  = df[df["period"] == "IS"]
    oos_df = df[df["period"] == "OOS"]

    is_str  = f"{is_df['mult'].mean():+.3f}x(n={len(is_df)})" if len(is_df) else "—"
    oos_str = f"{oos_df['mult'].mean():+.3f}x(n={len(oos_df)})" if len(oos_df) else "—"

    stop_n = (df["exit_reason"] == "stop").sum()
    t2_n   = (df["exit_reason"] == "take2").sum()

    print(f"  {label:<30}  n={n:3d}  EV={ev:+.3f}x  hit={hit:.0%}  "
          f"stop={stop_n}/{n}  t2={t2_n}  IS={is_str}  OOS={oos_str}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--otm",        type=float, default=0.02,
                    help="OTM fraction (0.02 = 2%% above futures close)")
    ap.add_argument("--dte",        type=int,   default=45)
    ap.add_argument("--take1",      type=float, default=2.0)
    ap.add_argument("--take2",      type=float, default=5.0)
    ap.add_argument("--max-hold",   type=int,   default=60)
    ap.add_argument("--stop-frac",  type=float, default=0.30)
    ap.add_argument("--stop-ticks", type=int,   default=5)
    ap.add_argument("--delta-floor",type=float, default=0.10)
    args = ap.parse_args()

    # Load au daily bars
    au_path = ROOT / "data" / "raw" / "kq_m_shfe_au_daily.json"
    payload = json.loads(au_path.read_text())
    bars = pd.DataFrame(payload["bars"])
    bars["timestamp"] = pd.to_datetime(bars["time"], unit="s", utc=True)
    bars = bars.sort_values("timestamp").reset_index(drop=True)

    # Realized vol
    log_ret = np.log(bars["close"] / bars["close"].shift(1))
    rvol    = log_ret.rolling(VOL_WINDOW).std() * np.sqrt(242)

    # Load 60min for h-filter
    h60_path = ROOT / "data" / "raw" / "kq_m_shfe_au_60.json"
    h60_bars = None
    if h60_path.exists():
        h60_payload = json.loads(h60_path.read_text())
        h60_bars = pd.DataFrame(h60_payload["bars"])
        h60_bars["timestamp"] = pd.to_datetime(h60_bars["time"], unit="s", utc=True)
        h60_bars = h60_bars.sort_values("timestamp").reset_index(drop=True)

    # Detect PA H2 signals
    det  = PABottomDetector(min_h_legs=2, min_quality=0.3, ema_threshold=0.0, min_gap=10)
    sigs = det.scan(bars, h_bars=h60_bars)

    if not sigs:
        print("No PA H2 signals found for au.")
        return 0

    print(f"\nStrategy A (期货传导法) — au PA H2 bottom signals → OTM calls (Black-76)")
    print(f"au futures range: {bars['timestamp'].iloc[0].date()} → {bars['timestamp'].iloc[-1].date()}")
    print(f"PA H2 signals detected: {len(sigs)}")
    print(f"Parameters: OTM={args.otm*100:.0f}%  DTE={args.dte}  "
          f"take1={args.take1}x  take2={args.take2}x  max_hold={args.max_hold}d")
    print(f"Stop methods: stop_frac={args.stop_frac:.0%}  "
          f"stop_ticks={args.stop_ticks}×{TICK_SIZE}={args.stop_ticks*TICK_SIZE:.0f}  "
          f"delta_floor={args.delta_floor:.2f}")
    print(f"IS<{IS_CUTOFF.date()}  OOS≥{OOS_START.date()}")
    print()

    # Show all signals with h-filter info
    print("All signals:")
    print(f"  {'date':<12} {'close':>7} {'rv%':>5} {'h_trend':<12} {'period':<5}")
    for sig in sigs:
        ts   = sig.timestamp
        cl   = float(bars["close"].iloc[sig.bar_idx])
        rv   = float(rvol.iloc[sig.bar_idx])
        h_rel = sig.higher_tf_relation or "—"
        per  = _period(ts)
        rv_str = f"{rv*100:.1f}" if np.isfinite(rv) else "N/A"
        print(f"  {str(ts.date()):<12} {cl:>7.2f} {rv_str:>5} {h_rel:<12} {per:<5}")

    # Partition by h-filter
    h_groups = {
        "all":       sigs,
        "opposing":  [s for s in sigs if s.higher_tf_relation == "opposing"],
        "supporting":[s for s in sigs if s.higher_tf_relation == "supporting"],
    }

    stop_methods = ["stop_frac", "stop_ticks", "delta_stop"]

    print()
    print("=" * 90)
    print("BACKTEST RESULTS  (EV = mean premium multiple, hit = % > 1.0x)")
    print("=" * 90)

    all_results: dict[str, dict[str, list[dict]]] = {
        hk: {sm: [] for sm in stop_methods} for hk in h_groups
    }

    for h_key, sig_list in h_groups.items():
        if not sig_list:
            continue
        print(f"\n── h={h_key} (n={len(sig_list)} signals) ──")

        for stop_method in stop_methods:
            rows: list[dict] = []
            for sig in sig_list:
                i   = sig.bar_idx
                ts  = sig.timestamp
                rv  = float(rvol.iloc[i])
                if not np.isfinite(rv) or rv <= 0:
                    continue

                res = simulate_one(
                    bars, i, rvol,
                    otm_pct=args.otm,
                    dte_entry=args.dte,
                    take1_mult=args.take1,
                    take2_mult=args.take2,
                    max_hold=args.max_hold,
                    stop_method=stop_method,
                    stop_frac=args.stop_frac,
                    stop_ticks=args.stop_ticks,
                    delta_floor=args.delta_floor,
                )
                if res is None:
                    continue

                rows.append({
                    **res,
                    "date":    str(ts.date()),
                    "period":  _period(ts),
                    "h_trend": sig.higher_tf_relation or "none",
                    "F0":      round(float(bars["close"].iloc[i]), 2),
                    "rv_pct":  round(rv * 100, 1),
                })

            all_results[h_key][stop_method] = rows
            report_table(rows, f"{stop_method:<15}")

    # Detailed trade log for best combo: all signals, stop_frac
    print()
    print("=" * 90)
    print("TRADE LOG — h=all  stop_method=stop_frac")
    print("=" * 90)
    rows_log = all_results["all"]["stop_frac"]
    if rows_log:
        df_log = pd.DataFrame(rows_log).sort_values("date")
        print(f"  {'date':<12} {'period':<5} {'h_trend':<12} {'F0':>8} {'rv%':>5} "
              f"{'prem0':>7} {'K':>7} {'mult':>7} {'exit':<10} {'t1':>3} {'t2':>3}")
        for _, row in df_log.iterrows():
            t1 = "✓" if row.get("take1") else "—"
            t2 = "✓" if row.get("take2") else "—"
            print(f"  {row['date']:<12} {row['period']:<5} {row['h_trend']:<12} "
                  f"{row['F0']:>8.1f} {row['rv_pct']:>5.1f} "
                  f"{row['prem0']:>7.2f} {row['K']:>7.0f} "
                  f"{row['mult']:>7.3f}x {row['exit_reason']:<10} {t1:>3} {t2:>3}")

    # IS vs OOS comparison summary
    print()
    print("=" * 90)
    print("IS vs OOS SUMMARY")
    print("=" * 90)
    for h_key in h_groups:
        for stop_method in stop_methods:
            rows = all_results[h_key][stop_method]
            if not rows:
                continue
            df = pd.DataFrame(rows)
            is_r  = df[df["period"] == "IS"]["mult"]
            oos_r = df[df["period"] == "OOS"]["mult"]
            gap_r = df[df["period"] == "GAP"]["mult"]
            is_str  = f"{is_r.mean():+.3f}x(n={len(is_r)})"  if len(is_r)  else "—"
            oos_str = f"{oos_r.mean():+.3f}x(n={len(oos_r)})" if len(oos_r) else "—"
            gap_str = f"{gap_r.mean():+.3f}x(n={len(gap_r)})" if len(gap_r) else ""
            print(f"  h={h_key:<10} {stop_method:<15}  IS={is_str:<20} OOS={oos_str}  {gap_str}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
