"""PA H2 backtest split by swing trend structure.

Core hypothesis: H2 in an uptrend pullback (trend_structure=uptrend + h=opposing)
outperforms H2 in a downtrend (trend_structure=downtrend).

Runs on:
  - US ETF 60min bars (10 symbols: spy, qqq, dia, iwm, gld, gdx, tlt, xlf, xlk, nvda)
  - CN_METAL daily bars (rb, cu, au, ag, sc)

Walk-forward K=2 (default):
  IS  : <= 2022-12-31
  OOS1: 2023-01-01 - 2024-06-30
  OOS2: > 2024-06-30

Walk-forward K=3 (--cutoff3):
  IS  : <= cutoff1
  OOS1: cutoff1+1 - cutoff2
  OOS2: cutoff2+1 - cutoff3
  OOS3: > cutoff3

Usage:
  uv run python scripts/backtest_pa_swing.py --dataset us_60min
  uv run python scripts/backtest_pa_swing.py --dataset us_60min \\
      --cutoff1 2021-12-31 --cutoff2 2023-06-30 --cutoff3 2024-12-31
  uv run python scripts/backtest_pa_swing.py --dataset cn_metal_daily
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from data import bar_loader
from engine.divergence.pa_detector import PABottomDetector, PASignal
from engine.features.swing_context import compute_swing_context

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

DATASETS = {
    "us_60min": dict(
        symbols=["spy", "qqq", "dia", "iwm", "gld", "gdx", "tlt", "xlf", "xlk", "nvda"],
        suffix="_60",
        h_suffix="_daily",
        atr_period=50,
        max_hold=140,
        min_gap=35,
        h_lookback=20,
        swing_n=3,
    ),
    "cn_metal_daily": dict(
        symbols=["kq_m_shfe_rb", "kq_m_shfe_cu", "kq_m_shfe_au",
                 "kq_m_shfe_ag", "kq_m_ine_sc"],
        suffix="_daily",
        h_suffix=None,   # no weekly data available; 60min is lower than daily
        atr_period=14,
        max_hold=30,
        min_gap=10,
        h_lookback=8,
        swing_n=3,
    ),
}


def load_bars(sym: str, bars_dir: Path, suffix: str) -> pd.DataFrame | None:
    return bar_loader.load_bars_quant_or_json(sym, suffix, bars_dir)


def compute_atr(bars: pd.DataFrame, period: int) -> pd.Series:
    hi, lo, pc = bars["high"], bars["low"], bars["close"].shift(1)
    tr = pd.concat([(hi - lo), (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def simulate_trade(bars, entry_idx, stop_mult, atr_series, max_hold):
    if entry_idx + 1 >= len(bars):
        return None
    entry = float(bars["close"].iloc[entry_idx])
    av = float(atr_series.iloc[entry_idx])
    if av <= 0 or not np.isfinite(av):
        return None
    risk = stop_mult * av
    stop = entry - risk
    tp1, tp2 = entry + risk, entry + 2 * risk
    hit_tp1 = False
    for offset in range(1, max_hold + 1):
        idx = entry_idx + offset
        if idx >= len(bars):
            break
        lo = float(bars["low"].iloc[idx])
        hi = float(bars["high"].iloc[idx])
        cl = float(bars["close"].iloc[idx])
        if not hit_tp1:
            if lo <= stop:
                return -1.0
            if hi >= tp1:
                hit_tp1 = True
                if hi >= tp2:
                    return 1.5
        else:
            if lo <= stop:
                return 0.0
            if hi >= tp2:
                return 1.5
            if offset == max_hold:
                return 0.5 + 0.5 * float(np.clip((cl - entry) / risk, -3, 3))
    idx_fin = min(entry_idx + max_hold, len(bars) - 1)
    mark = float(np.clip((float(bars["close"].iloc[idx_fin]) - entry) / risk, -3, 3))
    # TP1 banked but the trade ran to the hold boundary → credit the +0.5R partial
    # exit rather than scoring raw mark-to-market (shared boundary bug; see pa_atop).
    if hit_tp1:
        return 0.5 + 0.5 * mark
    return mark


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="us_60min",
                        choices=list(DATASETS))
    parser.add_argument("--stop-mult", type=float, default=1.5)
    parser.add_argument("--quality", type=float, default=0.3)
    parser.add_argument("--cutoff1", default="2022-12-31")
    parser.add_argument("--cutoff2", default="2024-06-30")
    parser.add_argument("--cutoff3", default=None,
                        help="Enable K=3 walk-forward by adding a third OOS fold cutoff")
    parser.add_argument("--bars-dir", type=Path, default=DEFAULT_BARS_DIR)
    args = parser.parse_args()

    ds = DATASETS[args.dataset]
    cutoff1 = pd.Timestamp(args.cutoff1, tz="UTC")
    cutoff2 = pd.Timestamp(args.cutoff2, tz="UTC")
    cutoff3 = pd.Timestamp(args.cutoff3, tz="UTC") if args.cutoff3 else None

    records = []

    for sym in ds["symbols"]:
        bars = load_bars(sym, args.bars_dir, ds["suffix"])
        if bars is None:
            print(f"  {sym}: no data, skip")
            continue
        h_bars = load_bars(sym, args.bars_dir, ds["h_suffix"]) \
                 if ds["h_suffix"] else None

        atr = compute_atr(bars, ds["atr_period"])
        ctx = compute_swing_context(bars, swing_n=ds["swing_n"])

        det = PABottomDetector(
            min_h_legs=2,
            min_quality=0.1,
            ema_threshold=0.0,
            min_gap=ds["min_gap"],
            h_lookback=ds["h_lookback"],
        )
        sigs = det.scan(bars, h_bars=h_bars, swing_context=ctx)

        for sig in sigs:
            r = simulate_trade(bars, sig.bar_idx, args.stop_mult, atr, ds["max_hold"])
            if r is None:
                continue
            ts = sig.timestamp
            if cutoff3 is None:
                period = ("IS" if ts <= cutoff1 else
                          "OOS1" if ts <= cutoff2 else "OOS2")
            else:
                period = ("IS" if ts <= cutoff1 else
                          "OOS1" if ts <= cutoff2 else
                          "OOS2" if ts <= cutoff3 else "OOS3")
            records.append({
                "symbol": sym,
                "timestamp": ts,
                "period": period,
                "r": r,
                "h_rel": sig.higher_tf_relation,
                **sig.features,
            })

    if not records:
        print("No signals found.")
        return

    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    k3 = cutoff3 is not None
    print(f"\nPA swing-context backtest — {args.dataset}, stop={args.stop_mult}xATR,"
          f" quality>={args.quality}")
    if k3:
        print(f"IS<={args.cutoff1}  OOS1->{args.cutoff2}  OOS2->{args.cutoff3}  OOS3>")
    else:
        print(f"IS<={args.cutoff1}  OOS1->{args.cutoff2}  OOS2>")
    print("=" * 72)

    def report(label, subset, w=30):
        if subset.empty:
            print(f"  {label:{w}s}: n=  0")
            return
        n = len(subset)
        ev = subset["r"].mean()
        hit = (subset["r"] > 0).mean()
        is_s = subset[subset["period"] == "IS"]
        o1   = subset[subset["period"] == "OOS1"]
        o2   = subset[subset["period"] == "OOS2"]
        o3   = subset[subset["period"] == "OOS3"]
        def fmt(g): return f"{g['r'].mean():+.3f}(n={len(g)})" if len(g) else "—"
        line = (f"  {label:{w}s}: n={n:4d}  EV={ev:+.3f}R  hit={hit:.0%}"
                f"  IS={fmt(is_s)}  F1={fmt(o1)}  F2={fmt(o2)}")
        if k3:
            line += f"  F3={fmt(o3)}"
        print(line)

    base = df[df["bar_quality_bull"] >= args.quality]

    print("\n--- By trend_structure (h2+q, all h_rel) ---")
    for ts_val in ["uptrend", "ranging", "downtrend"]:
        sub = base[base["trend_structure"] == ts_val]
        report(f"trend={ts_val}", sub)

    print("\n--- With h=opposing filter ---")
    for ts_val in ["uptrend", "ranging", "downtrend"]:
        sub = base[(base["trend_structure"] == ts_val) & (base["h_rel"] == "opposing")]
        report(f"trend={ts_val} + h=opp", sub)

    print("\n--- By market_regime (h=opposing) ---")
    opp = base[base["h_rel"] == "opposing"]
    for reg in ["trending", "channel", "ranging"]:
        sub = opp[opp["market_regime"] == reg]
        report(f"regime={reg} + h=opp", sub)

    print("\n--- By leg_count_down (h=opposing + uptrend) ---")
    up_opp = base[(base["trend_structure"] == "uptrend") & (base["h_rel"] == "opposing")]
    for legs in [0, 1, 2, 3]:
        sub = up_opp[up_opp["leg_count_down"] == legs]
        report(f"legs={legs}", sub)

    print("\n--- Per-symbol (uptrend + h=opposing) ---")
    up_opp_all = base[(base["trend_structure"] == "uptrend") & (base["h_rel"] == "opposing")]
    for sym, grp in up_opp_all.groupby("symbol"):
        print(f"  {sym}: n={len(grp)}, EV={grp['r'].mean():+.3f}R,"
              f" hit={(grp['r']>0).mean():.0%}")

    out = Path(f"/tmp/pa_swing_{args.dataset}.csv")
    df.to_csv(out, index=False)
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
