"""PABottomDetector K=3 walk-forward for US equity (daily bars).

Mirrors the CN_METAL PA standalone backtest but targets US pool.
Signals scanned on daily bars (same as score_today production path).
Stratified by daily DIF sign and h=opposing to identify which sub-cell
is suitable for score_today integration.

Fold boundaries (standard):
  IS  : ≤ 2022-12-31
  F1  : 2023-01-01 – 2023-12-31
  F2  : 2024-01-01 – 2024-12-31
  F3  : 2025-01-01 – present

Usage:
  uv run python scripts/backtest_pa_us_k3.py
  uv run python scripts/backtest_pa_us_k3.py --stop-mult 2.0
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
from engine.features.macd import macd as compute_macd

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
ATR_PERIOD   = 14
MAX_HOLD     = 40
MIN_GAP      = 10
WEEKLY_EMA   = 20

US_SYMBOLS = ["spy", "qqq", "iwm", "gld", "tlt", "nvda", "dia", "gdx", "xlf", "xlk"]

CUTOFF_IS   = pd.Timestamp("2022-12-31", tz="UTC")
CUTOFF_OOS1 = pd.Timestamp("2023-12-31", tz="UTC")
CUTOFF_OOS2 = pd.Timestamp("2024-12-31", tz="UTC")


def load_bars(sym: str, bars_dir: Path, suffix: str = "_daily") -> pd.DataFrame | None:
    return bar_loader.load_bars_quant_or_json(sym, suffix, bars_dir)


def compute_weekly_trend(bars: pd.DataFrame, ema_period: int = WEEKLY_EMA) -> pd.Series:
    """For each daily bar index, return True if weekly close > weekly EMA (uptrend).

    Resamples daily close to weekly (Friday end), computes EMA, then forward-fills
    back to daily index. Uses bar's daily timestamp for alignment.
    """
    ts = bars["timestamp"]
    close = bars["close"]
    indexed = close.copy()
    indexed.index = ts

    weekly_close = indexed.resample("W-FRI").last().dropna()
    weekly_ema   = weekly_close.ewm(span=ema_period, adjust=False).mean()
    weekly_up    = (weekly_close > weekly_ema).astype(float)

    # Reindex to daily timestamps, forward-fill within each week
    daily_up = weekly_up.reindex(ts, method="ffill")
    daily_up.index = bars.index
    return daily_up.fillna(False).astype(bool)


def compute_atr(bars: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    hi, lo, pc = bars["high"], bars["low"], bars["close"].shift(1)
    tr = pd.concat([(hi - lo), (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def simulate_trade(bars, entry_idx, stop_mult, atr_series) -> float | None:
    if entry_idx + 1 >= len(bars):
        return None
    entry = float(bars["close"].iloc[entry_idx])
    av = float(atr_series.iloc[entry_idx])
    if av <= 0 or not np.isfinite(av):
        return None
    risk   = stop_mult * av
    stop   = entry - risk
    tp1    = entry + risk
    tp2    = entry + 2 * risk
    hit_tp1 = False
    for offset in range(1, MAX_HOLD + 1):
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
            if offset == MAX_HOLD:
                mark = (cl - entry) / risk
                return 0.5 + 0.5 * float(np.clip(mark, -3.0, 3.0))
    idx_fin = min(entry_idx + MAX_HOLD, len(bars) - 1)
    mark = (float(bars["close"].iloc[idx_fin]) - entry) / risk
    return float(np.clip(mark, -3.0, 3.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stop-mult", type=float, default=1.5)
    parser.add_argument("--bars-dir",  type=Path,  default=DEFAULT_BARS_DIR)
    parser.add_argument("--min-quality", type=float, default=0.3)
    args = parser.parse_args()

    det = PABottomDetector(
        min_h_legs=2, min_quality=args.min_quality,
        ema_threshold=0.0, min_gap=MIN_GAP,
    )

    all_records: list[dict] = []

    for sym in US_SYMBOLS:
        bars = load_bars(sym, args.bars_dir)
        if bars is None or len(bars) < 100:
            print(f"  [SKIP] {sym}: no daily data")
            continue
        h_bars = load_bars(sym, args.bars_dir, suffix="_60")
        atr    = compute_atr(bars)
        macd_df = compute_macd(bars["close"])

        weekly_up  = compute_weekly_trend(bars)
        sigs: list[PASignal] = det.scan(bars, h_bars)
        n_opp = sum(1 for s in sigs if s.higher_tf_relation == "opposing")
        print(f"  {sym}: signals={len(sigs)}  h=opp={n_opp}")

        for sig in sigs:
            r = simulate_trade(bars, sig.bar_idx, args.stop_mult, atr)
            if r is None:
                continue
            ts = sig.timestamp
            period = (
                "IS"   if ts <= CUTOFF_IS   else
                "OOS1" if ts <= CUTOFF_OOS1 else
                "OOS2" if ts <= CUTOFF_OOS2 else
                "OOS3"
            )
            dif_val = float(macd_df["dif"].iloc[sig.bar_idx])
            w_up    = bool(weekly_up.iloc[sig.bar_idx])
            all_records.append({
                "symbol":    sym,
                "bar_idx":   sig.bar_idx,
                "timestamp": ts,
                "period":    period,
                "r":         r,
                "h_rel":     sig.higher_tf_relation,
                "dif":       round(dif_val, 6),
                "dif_pos":   dif_val > 0,
                "weekly_up": w_up,
                "confidence": sig.confidence,
                **{k: v for k, v in sig.features.items()
                   if k in ("h_leg_count", "bar_quality_bull",
                            "ema_distance_norm", "selling_climax_score")},
            })

    if not all_records:
        print("No signals found.")
        return

    df = pd.DataFrame(all_records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    def row(label: str, sub: pd.DataFrame, width: int = 32) -> None:
        if sub.empty:
            print(f"  {label:{width}s}: n=  0")
            return
        n  = len(sub)
        ev = sub["r"].mean()
        hit = (sub["r"] > 0).mean()
        parts = []
        for p, lbl in [("IS", "IS"), ("OOS1", "F1"), ("OOS2", "F2"), ("OOS3", "F3")]:
            g = sub[sub["period"] == p]
            parts.append(f"{lbl}={g['r'].mean():+.3f}R(n={len(g)})" if len(g) else f"{lbl}=—")
        print(f"  {label:{width}s}: n={n:4d}  EV={ev:+.3f}R  hit={hit:.0%}  " + "  ".join(parts))

    print(f"\n{'='*90}")
    print(f"US Pool — PABottomDetector (daily bars)  K=3 Walk-Forward")
    print(f"stop={args.stop_mult}×ATR  max_hold={MAX_HOLD}  min_gap={MIN_GAP}  min_quality={args.min_quality}")
    print("=" * 90)

    opp    = df[df["h_rel"] == "opposing"]
    dif_neg = df[~df["dif_pos"]]
    dif_pos = df[df["dif_pos"]]
    w_up   = df["weekly_up"]

    print("\n── All signals ──")
    row("All",            df)
    row("h=opposing",     opp)
    row("h=opposing w↑",  opp[w_up])
    row("h=opposing w↓",  opp[~w_up])
    row("h=supporting",   df[df["h_rel"] == "supporting"])
    row("h=neutral/unk",  df[df["h_rel"].isin(["neutral"]) | df["h_rel"].isna()])

    print("\n── DIF<0 (downswing / B1-adjacent) ──")
    row("DIF<0 all",        dif_neg)
    row("DIF<0 h=opp",      dif_neg[dif_neg["h_rel"] == "opposing"])
    row("DIF<0 h=opp w↑",   dif_neg[dif_neg["h_rel"] == "opposing"] [w_up[dif_neg[dif_neg["h_rel"] == "opposing"].index]])
    row("DIF<0 h=opp w↓",   dif_neg[dif_neg["h_rel"] == "opposing"] [~w_up[dif_neg[dif_neg["h_rel"] == "opposing"].index]])
    row("DIF<0 h=sup",      dif_neg[dif_neg["h_rel"] == "supporting"])
    row("DIF<0 h=unk",      dif_neg[dif_neg["h_rel"].isin(["neutral"]) | dif_neg["h_rel"].isna()])

    print("\n── DIF>0 (uptrend consolidation / Context A-adjacent) ──")
    row("DIF>0 all",        dif_pos)
    row("DIF>0 h=opp",      dif_pos[dif_pos["h_rel"] == "opposing"])
    row("DIF>0 h=opp w↑",   dif_pos[dif_pos["h_rel"] == "opposing"] [w_up[dif_pos[dif_pos["h_rel"] == "opposing"].index]])
    row("DIF>0 h=opp w↓",   dif_pos[dif_pos["h_rel"] == "opposing"] [~w_up[dif_pos[dif_pos["h_rel"] == "opposing"].index]])
    row("DIF>0 h=sup",      dif_pos[dif_pos["h_rel"] == "supporting"])
    row("DIF>0 h=unk",      dif_pos[dif_pos["h_rel"].isin(["neutral"]) | dif_pos["h_rel"].isna()])

    print("\n── Weekly trend breakdown (h=opposing) ──")
    pct_up = w_up[opp.index].mean()
    print(f"  Weekly↑ signals: {w_up[opp.index].sum()}/{len(opp)} ({pct_up:.0%})")

    print("\n── Per-symbol (h=opposing) ──")
    for sym, grp in df.groupby("symbol"):
        opp = grp[grp["h_rel"] == "opposing"]
        all_str = f"n={len(grp)} EV={grp['r'].mean():+.3f}R"
        if len(opp):
            fold_parts = []
            for p, lbl in [("IS", "IS"), ("OOS1", "F1"), ("OOS2", "F2"), ("OOS3", "F3")]:
                g = opp[opp["period"] == p]
                if len(g):
                    fold_parts.append(f"{lbl}={g['r'].mean():+.2f}R(n={len(g)})")
            opp_str = f"  h=opp n={len(opp)} EV={opp['r'].mean():+.3f}R [{' '.join(fold_parts)}]"
        else:
            opp_str = "  h=opp —"
        print(f"  {sym}: {all_str}{opp_str}")

    out = Path("/tmp/pa_us_k3.csv")
    df.to_csv(out, index=False)
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
