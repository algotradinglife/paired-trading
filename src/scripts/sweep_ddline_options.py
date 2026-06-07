"""Comprehensive parameter sweep for Xiao DD-line option strategies (Method B).

Strategy B: 期权K线直接法 (DD-line direct approach)
  B1. 一滴不剩 (left-side): W-bottom retest entry; stop = entry - stop_ticks * tick
  B2. 五滴不剩 (right-side): trend-line-through-highs breakout; stop = entry - stop_ticks * tick

(Strategy A = 期货传导法 = Black76/delta futures-signal approach, separate script)

Usage:
    python scripts/sweep_ddline_options.py --commodity ag
    python scripts/sweep_ddline_options.py --commodity au
    python scripts/sweep_ddline_options.py --commodity ag --strategy both --top-n 10
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from itertools import product

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_quant_daily(sym_upper: str) -> pd.DataFrame | None:
    """Load daily bars from Quant Parquet store (SHFE)."""
    p = ROOT / "data" / "quant" / "SHFE" / sym_upper / "daily.parquet"
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df = df.rename(columns={
        "open_price": "open", "high_price": "high",
        "low_price": "low", "close_price": "close",
    })
    df["date"] = pd.to_datetime(df["datetime"]).dt.tz_localize(None)
    df = df.sort_values("date").reset_index(drop=True)
    df = df[df["high"] - df["low"] > 0.5].reset_index(drop=True)
    return df


def load_json_daily(path: Path) -> pd.DataFrame | None:
    """Load daily option bars from JSON snapshot."""
    try:
        payload = json.loads(path.read_text())
        bars = payload.get("bars", payload)
        df = pd.DataFrame(bars)
        if "time" in df.columns:
            df["date"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_localize(None)
        elif "timestamp" in df.columns:
            df["date"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
        else:
            return None
        df = df.sort_values("date").reset_index(drop=True)
        df = df[df["high"] - df["low"] > 0.5].reset_index(drop=True)
        return df
    except Exception:
        return None


def load_all_contracts(commodity: str) -> dict[str, pd.DataFrame]:
    """Load all available daily option contracts for a commodity."""
    contracts: dict[str, pd.DataFrame] = {}
    opt_dir = ROOT / "data" / "options" / "cn" / commodity.lower()
    quant_dir = ROOT / "data" / "quant" / "SHFE"

    # JSON files (commodity.lower prefix, e.g. ag2507c8300)
    for p in sorted(opt_dir.glob("*_daily.json")):
        if "shf_" in p.stem or any(c.isdigit() and p.stem[p.stem.index(c)-1] == '_' for c in ['_']):
            pass
        name = p.stem.replace("_daily", "")
        if "_20" in name or "shf_" in name:
            continue
        df = load_json_daily(p)
        if df is not None and len(df) >= 8:
            contracts[name] = df

    # Quant SHFE (uppercase e.g. AG2309C5600)
    sym_upper = commodity.upper()
    if quant_dir.exists():
        for d in sorted(quant_dir.iterdir()):
            if d.is_dir() and d.name.startswith(sym_upper) and "C" in d.name:
                key = d.name.lower()
                if key in contracts:   # already loaded from JSON — skip parquet read
                    continue
                df = load_quant_daily(d.name)
                if df is not None and len(df) >= 8:
                    contracts[key] = df

    return contracts


# ---------------------------------------------------------------------------
# Strategy B1: 一滴不剩 — W-bottom retest
# ---------------------------------------------------------------------------

def find_retest_entries(
    daily: pd.DataFrame,
    stop_ticks: int,
    tick_size: float,
    retest_tol: int,
    bounce_min: float,
    decline_min: float,
    peak_window: int,
    cycle_reset_mult: float = 3.0,
) -> list[dict]:
    """Detect W-bottom retest entries (B1 一滴不剩 style)."""
    entries = []
    n = len(daily)
    state = "looking"
    init_low_idx = None
    init_low_val = None
    bounce_high_val = None
    cooldown = -1

    for i in range(peak_window, n):
        if i <= cooldown:
            continue

        lo = float(daily["low"].iloc[i])
        hi = float(daily["high"].iloc[i])
        cl = float(daily["close"].iloc[i])

        # Cycle reset: if price explodes well above initial low, start over
        if state != "looking" and init_low_val and hi > init_low_val * cycle_reset_mult:
            state = "looking"
            init_low_idx = None
            init_low_val = None
            bounce_high_val = None

        if state == "looking":
            recent_high = float(daily["high"].iloc[max(0, i - peak_window):i].max())
            if recent_high <= 0:
                continue
            decline_pct = (recent_high - lo) / recent_high
            if decline_pct >= decline_min:
                init_low_idx = i
                init_low_val = lo
                bounce_high_val = cl
                state = "bounce"

        elif state == "bounce":
            bounce_high_val = max(bounce_high_val, hi)
            if init_low_val and init_low_val > 0:
                if (bounce_high_val - init_low_val) / init_low_val >= bounce_min:
                    state = "retest"

        elif state == "retest":
            retest_level = init_low_val + retest_tol * tick_size
            if lo <= retest_level:
                entry_price = max(init_low_val, lo)
                stop_price = entry_price - stop_ticks * tick_size
                recent_high = float(daily["high"].iloc[max(0, init_low_idx - peak_window):init_low_idx].max())
                decline_pct = (recent_high - init_low_val) / recent_high if recent_high > 0 else 0
                bounce_pct = (bounce_high_val - init_low_val) / init_low_val if init_low_val > 0 else 0
                entries.append({
                    "entry_idx": i,
                    "entry_date": str(daily["date"].iloc[i].date()),
                    "entry_price": entry_price,
                    "stop_price": stop_price,
                    "init_low": init_low_val,
                    "bounce_high": bounce_high_val,
                    "decline_pct": round(decline_pct * 100, 1),
                    "bounce_pct": round(bounce_pct * 100, 1),
                    "strategy": "B1(一滴不剩)",
                })
                state = "looking"
                cooldown = i + 3
                init_low_idx = None
                init_low_val = None
                bounce_high_val = None
            elif lo < init_low_val - stop_ticks * tick_size * 5:
                state = "looking"
                init_low_idx = None

    return entries


# ---------------------------------------------------------------------------
# Strategy B2: 五滴不剩 — declining-highs trend line breakout
# ---------------------------------------------------------------------------

def fit_declining_highs_line(highs: list[float]) -> tuple[float, float]:
    """OLS fit through indices 0..n-1 and high values. Returns (slope, intercept)."""
    n = len(highs)
    if n < 2:
        return 0.0, highs[-1] if highs else 0.0
    x = np.arange(n, dtype=float)
    slope, intercept = np.polyfit(x, highs, 1)
    return slope, intercept


def find_breakout_entries(
    daily: pd.DataFrame,
    stop_ticks: int,
    tick_size: float,
    decline_min: float,
    peak_window: int,
    trend_window: int = 5,
    breakout_margin: float = 0.0,
    cycle_reset_mult: float = 3.0,
) -> list[dict]:
    """Detect declining-highs trend line breakouts (B2 五滴不剩 style).

    After a significant decline, track declining highs. When price breaks
    above the projected trend line, enter.
    stop = entry - stop_ticks * tick_size
    """
    entries = []
    n = len(daily)
    state = "looking"
    decline_start_idx = None
    init_low_val = None
    cooldown = -1
    high_track: list[float] = []

    for i in range(peak_window, n):
        if i <= cooldown:
            continue

        lo = float(daily["low"].iloc[i])
        hi = float(daily["high"].iloc[i])
        cl = float(daily["close"].iloc[i])

        if state != "looking" and init_low_val and hi > init_low_val * cycle_reset_mult:
            state = "looking"
            decline_start_idx = None
            init_low_val = None
            high_track = []

        if state == "looking":
            recent_high = float(daily["high"].iloc[max(0, i - peak_window):i].max())
            if recent_high <= 0:
                continue
            decline_pct = (recent_high - lo) / recent_high
            if decline_pct >= decline_min:
                decline_start_idx = i
                init_low_val = lo
                high_track = [hi]
                state = "tracking"

        elif state == "tracking":
            high_track.append(hi)

            # Need enough bars to fit a trend line
            if len(high_track) < 2:
                continue

            # Use last trend_window highs (or all if fewer)
            window_highs = high_track[-trend_window:]
            slope, intercept = fit_declining_highs_line(window_highs)

            # Only use this as a breakout line if it's actually declining
            if slope >= 0:
                # Trend line is no longer declining — reset tracking
                state = "looking"
                decline_start_idx = None
                init_low_val = None
                high_track = []
                continue

            # Projected trend line at current bar (index = len(window_highs) - 1 from start)
            n_window = len(window_highs)
            trend_level = slope * (n_window - 1) + intercept
            breakout_threshold = trend_level + breakout_margin * tick_size

            # Breakout: high crosses above trend line
            if hi > breakout_threshold:
                # Entry at close of breakout bar (or trend_level + 1 tick as limit)
                entry_price = cl
                stop_price = entry_price - stop_ticks * tick_size
                recent_high = float(daily["high"].iloc[max(0, decline_start_idx - peak_window):decline_start_idx].max())
                decline_pct = (recent_high - init_low_val) / recent_high if recent_high > 0 else 0
                entries.append({
                    "entry_idx": i,
                    "entry_date": str(daily["date"].iloc[i].date()),
                    "entry_price": entry_price,
                    "stop_price": stop_price,
                    "init_low": init_low_val,
                    "trend_level": round(trend_level, 1),
                    "decline_pct": round(decline_pct * 100, 1),
                    "strategy": "B2(五滴不剩)",
                })
                state = "looking"
                cooldown = i + 3
                decline_start_idx = None
                init_low_val = None
                high_track = []

    return entries


# ---------------------------------------------------------------------------
# Trade simulation
# ---------------------------------------------------------------------------

def simulate_entry(
    daily: pd.DataFrame,
    entry: dict,
    take1_mult: float,
    take2_mult: float,
    max_hold: int,
) -> dict:
    """Simulate one entry. Returns result dict with pnl metrics."""
    idx = entry["entry_idx"]
    ep = entry["entry_price"]
    sp = entry["stop_price"]
    t1 = ep * take1_mult
    t2 = ep * take2_mult

    risk = ep - sp
    if risk <= 0:
        return {**entry, "mult": 0.0, "r": 0.0, "exit_reason": "no_risk",
                "take1": False, "take2": False, "exit_day": 0}

    size = 1.0
    proceeds = 0.0
    take1_done = take2_done = False
    exit_day = max_hold
    exit_reason = "maxhold"

    for offset in range(1, max_hold + 1):
        j = idx + offset
        if j >= len(daily):
            exit_day = offset - 1
            exit_reason = "data_end"
            break

        lo = float(daily["low"].iloc[j])
        hi = float(daily["high"].iloc[j])
        cl = float(daily["close"].iloc[j])

        if lo <= sp and size > 0:
            proceeds += sp * size
            size = 0.0
            exit_day = offset
            exit_reason = "stop"
            break

        if not take1_done and hi >= t1 and size >= 0.5:
            proceeds += t1 * 0.5
            size -= 0.5
            take1_done = True

        if not take2_done and hi >= t2 and size > 0:
            proceeds += t2 * size
            size = 0.0
            take2_done = True
            exit_day = offset
            exit_reason = "take2"
            break

    if size > 0:
        final_idx = min(idx + exit_day, len(daily) - 1)
        proceeds += float(daily["close"].iloc[final_idx]) * size

    net = proceeds - ep
    mult = proceeds / ep if ep > 0 else 0.0
    r = net / risk

    return {
        **entry,
        "proceeds": round(proceeds, 1),
        "net": round(net, 1),
        "mult": round(mult, 3),
        "r": round(r, 2),
        "exit_reason": exit_reason,
        "take1": take1_done,
        "take2": take2_done,
        "exit_day": exit_day,
    }


# ---------------------------------------------------------------------------
# Sweep runner
# ---------------------------------------------------------------------------

def run_sweep(
    contracts: dict[str, pd.DataFrame],
    strategy: str,
    param_grid: dict,
    tick_size: float,
    verbose: bool = False,
) -> pd.DataFrame:
    """Run parameter sweep across all contracts. Returns results DataFrame."""
    rows = []

    keys = list(param_grid.keys())
    values = list(param_grid.values())

    for combo in product(*values):
        params = dict(zip(keys, combo))
        all_trades: list[dict] = []

        for name, daily in contracts.items():
            if strategy in ("B1", "both"):
                entries = find_retest_entries(
                    daily,
                    stop_ticks=params["stop_ticks"],
                    tick_size=tick_size,
                    retest_tol=params.get("retest_tol", 10),
                    bounce_min=params.get("bounce_min", 0.10),
                    decline_min=params.get("decline_min", 0.30),
                    peak_window=params.get("peak_window", 7),
                    cycle_reset_mult=params.get("cycle_reset_mult", 3.0),
                )
                for e in entries:
                    t = simulate_entry(daily, e, params["take1_mult"], params["take2_mult"], params["max_hold"])
                    t["contract"] = name
                    all_trades.append(t)

            if strategy in ("B2", "both"):
                entries = find_breakout_entries(
                    daily,
                    stop_ticks=params["stop_ticks"],
                    tick_size=tick_size,
                    decline_min=params.get("decline_min", 0.30),
                    peak_window=params.get("peak_window", 7),
                    trend_window=params.get("trend_window", 5),
                    cycle_reset_mult=params.get("cycle_reset_mult", 3.0),
                )
                for e in entries:
                    t = simulate_entry(daily, e, params["take1_mult"], params["take2_mult"], params["max_hold"])
                    t["contract"] = name
                    all_trades.append(t)

        if not all_trades:
            continue

        df = pd.DataFrame(all_trades)
        n = len(df)
        n_stop = (df["exit_reason"] == "stop").sum()
        ev_mult = df["mult"].mean()
        ev_r = df["r"].mean()
        hit_rate = (df["mult"] > 1.0).mean()

        row = {**params, "n": n, "n_stop": n_stop, "stop_pct": round(n_stop / n * 100, 0),
               "ev_mult": round(ev_mult, 3), "ev_r": round(ev_r, 3),
               "hit_pct": round(hit_rate * 100, 1)}
        rows.append(row)

    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commodity", default="ag", choices=["ag", "au", "cu", "rb"])
    parser.add_argument("--strategy", default="both", choices=["B1", "B2", "both"],
                        help="B1=一滴不剩(retest) B2=五滴不剩(breakout) both=run both")
    parser.add_argument("--top-n", type=int, default=15, help="Show top N parameter sets")
    parser.add_argument("--tick-size", type=float, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    tick_map = {"ag": 1.0, "au": 2.0, "cu": 10.0, "rb": 1.0}
    tick_size = args.tick_size or tick_map.get(args.commodity, 1.0)

    print(f"\n{'='*70}")
    print(f"DD-line Parameter Sweep (Strategy B) — {args.commodity.upper()}  tick={tick_size}  strategy={args.strategy}")
    print(f"{'='*70}")

    print("Loading contracts...", end=" ", flush=True)
    contracts = load_all_contracts(args.commodity)
    print(f"{len(contracts)} loaded")

    if not contracts:
        print("No data found.")
        return

    # Show contract summary
    print(f"\nContracts ({len(contracts)}):")
    for name, df in sorted(contracts.items())[:20]:
        d0 = str(df["date"].iloc[0].date())
        d1 = str(df["date"].iloc[-1].date())
        print(f"  {name:<25} {d0} → {d1}  ({len(df)} days)  "
              f"close {df['close'].min():.0f}–{df['close'].max():.0f}")
    if len(contracts) > 20:
        print(f"  ... and {len(contracts) - 20} more")

    # Parameter grid
    param_grid = {
        "stop_ticks":      [4, 5, 6, 8],
        "retest_tol":      [5, 10, 15, 20],
        "bounce_min":      [0.08, 0.12, 0.15],
        "decline_min":     [0.20, 0.30, 0.40],
        "peak_window":     [5, 7, 10],
        "trend_window":    [3, 5, 7],      # for strategy B
        "cycle_reset_mult":[2.5, 3.5],
        "take1_mult":      [1.5, 2.0, 2.5],
        "take2_mult":      [3.0, 4.0, 5.0],
        "max_hold":        [30, 45],
    }

    total_combos = 1
    for v in param_grid.values():
        total_combos *= len(v)
    print(f"\nSweeping {total_combos:,} parameter combinations...")

    results = run_sweep(contracts, args.strategy, param_grid, tick_size, args.verbose)

    if results.empty:
        print("No trades found across all parameter combinations.")
        return

    # Filter: at least 5 trades
    results = results[results["n"] >= 5].copy()
    if results.empty:
        print("All combos produced <5 trades. Loosening filter...")
        return

    print(f"\nValid combinations (n≥5): {len(results)}")

    # Sort by EV_mult descending
    results_sorted = results.sort_values("ev_mult", ascending=False)

    print(f"\n{'─'*90}")
    print(f"TOP {args.top_n} by EV_mult  (strategy={args.strategy})")
    print(f"{'─'*90}")
    cols = ["stop_ticks", "retest_tol", "bounce_min", "decline_min", "peak_window",
            "take1_mult", "take2_mult", "max_hold", "n", "stop_pct", "ev_mult", "ev_r", "hit_pct"]
    top = results_sorted.head(args.top_n)[cols]
    print(top.to_string(index=False))

    print(f"\n{'─'*90}")
    print(f"TOP {args.top_n} by EV_R  (risk-adjusted)")
    print(f"{'─'*90}")
    top_r = results.sort_values("ev_r", ascending=False).head(args.top_n)[cols]
    print(top_r.to_string(index=False))

    # Best combo — drill into individual trades
    best = results_sorted.iloc[0]
    print(f"\n{'='*70}")
    print(f"BEST COMBO  EV={best['ev_mult']:.3f}x  EV_R={best['ev_r']:.2f}R  "
          f"n={best['n']}  stop%={best['stop_pct']:.0f}%")
    print(f"  stop={best['stop_ticks']}tk  retest_tol={best['retest_tol']}tk  "
          f"bounce≥{best['bounce_min']*100:.0f}%  decline≥{best['decline_min']*100:.0f}%  "
          f"peak_win={best['peak_window']}  take1={best['take1_mult']}x  take2={best['take2_mult']}x  "
          f"hold≤{best['max_hold']}d")

    # Re-run best to show individual trades
    best_trades: list[dict] = []
    for name, daily in contracts.items():
        if args.strategy in ("B1", "both"):
            entries = find_retest_entries(
                daily, stop_ticks=int(best["stop_ticks"]), tick_size=tick_size,
                retest_tol=int(best["retest_tol"]), bounce_min=float(best["bounce_min"]),
                decline_min=float(best["decline_min"]), peak_window=int(best["peak_window"]),
                cycle_reset_mult=float(best["cycle_reset_mult"]),
            )
            for e in entries:
                t = simulate_entry(daily, e, float(best["take1_mult"]),
                                   float(best["take2_mult"]), int(best["max_hold"]))
                t["contract"] = name
                best_trades.append(t)
        if args.strategy in ("B2", "both"):
            entries = find_breakout_entries(
                daily, stop_ticks=int(best["stop_ticks"]), tick_size=tick_size,
                decline_min=float(best["decline_min"]), peak_window=int(best["peak_window"]),
                trend_window=int(best["trend_window"]),
                cycle_reset_mult=float(best["cycle_reset_mult"]),
            )
            for e in entries:
                t = simulate_entry(daily, e, float(best["take1_mult"]),
                                   float(best["take2_mult"]), int(best["max_hold"]))
                t["contract"] = name
                best_trades.append(t)

    if best_trades:
        df_best = pd.DataFrame(best_trades).sort_values("entry_date")
        print(f"\n{'─'*95}")
        print(f"{'contract':<22} {'date':<12} {'strategy':<8} {'entry':>7} {'stop':>7} "
              f"{'init_lo':>7} {'mult':>7} {'r':>6} {'reason':<10} {'t1':>3} {'t2':>3}")
        print(f"{'─'*95}")
        for _, r in df_best.iterrows():
            t1 = "✓" if r.get("take1") else "—"
            t2 = "✓" if r.get("take2") else "—"
            contract_short = str(r["contract"])[-18:]
            strat = r.get("strategy", "?")[:7]
            print(f"{contract_short:<22} {r['entry_date']:<12} {strat:<8} "
                  f"{r['entry_price']:>7.1f} {r['stop_price']:>7.1f} "
                  f"{r.get('init_low', 0):>7.1f} {r['mult']:>7.3f}x "
                  f"{r['r']:>6.2f}R {r['exit_reason']:<10} {t1:>3} {t2:>3}")

    # Save full results
    out = Path(f"/tmp/ddline_sweep_{args.commodity}_{args.strategy}.csv")
    results_sorted.to_csv(out, index=False)
    print(f"\nFull results saved to {out}")


if __name__ == "__main__":
    main()
