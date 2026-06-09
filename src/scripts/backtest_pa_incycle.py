"""PA-enhanced in-cycle bottom detector backtest.

Tests whether Brooks-derived PA features (bar quality, H2 count, climax score,
EMA distance) improve EV on the in_cycle + h=opposing bottom signals that the
standard MACD divergence detector misses.

Signal condition:
  - MACD in_cycle state (DIF < 0, inside a bearish heap)
  - Higher-TF DIF is bearish (h=opposing for a bottom signal)
  - PA condition (varies — see FILTERS dict below)

Walk-forward splits match the main backtest (K=2):
  IS  : up to   CUTOFF1
  OOS1: CUTOFF1 – CUTOFF2
  OOS2: > CUTOFF2

Usage:
  uv run python scripts/backtest_pa_incycle.py --pool CN_COMMODITY
  uv run python scripts/backtest_pa_incycle.py --pool CN_METAL --stop-mult 1.5
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
from engine.features.macd import macd as compute_macd
from engine.features.pa_features import compute_pa_features
from engine.features.streams import compute_feature_streams
from engine.units.snapshot import compute_unit_metadata

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
ATR_PERIOD = 14
MAX_HOLD = 30

POOLS: dict[str, list[str]] = {
    "CN_COMMODITY": [
        "kq_m_shfe_rb", "kq_m_shfe_cu", "kq_m_shfe_au", "kq_m_shfe_ag",
        "kq_m_dce_m", "kq_m_dce_i", "kq_m_dce_j", "kq_m_dce_jm",
        "kq_m_dce_p", "kq_m_dce_y",
        "kq_m_czce_ta", "kq_m_czce_ma", "kq_m_czce_cf", "kq_m_czce_sr",
        "kq_m_ine_sc",
    ],
    "CN_METAL": [
        "kq_m_shfe_rb", "kq_m_shfe_cu", "kq_m_shfe_au", "kq_m_shfe_ag",
        "kq_m_ine_sc",
    ],
    "CN_AGRI": [
        "kq_m_dce_m", "kq_m_dce_i", "kq_m_dce_j", "kq_m_dce_jm",
        "kq_m_dce_p", "kq_m_dce_y",
        "kq_m_czce_ta", "kq_m_czce_ma", "kq_m_czce_cf", "kq_m_czce_sr",
    ],
}

# PA filter definitions — each is a lambda(pa_row) -> bool
# Evaluated at the signal bar.
FILTERS: dict[str, object] = {
    "baseline":        lambda p: True,
    # Signal bar quality filters
    "bull_quality≥0.3":    lambda p: p["bar_quality_bull"] >= 0.3,
    "bull_quality≥0.4":    lambda p: p["bar_quality_bull"] >= 0.4,
    "bull_quality≥0.5":    lambda p: p["bar_quality_bull"] >= 0.5,
    # H2 / second-entry
    "h_leg≥1":         lambda p: p["h_leg_count"] >= 1,
    "h_leg≥2":         lambda p: p["h_leg_count"] >= 2,
    # Selling climax
    "climax≥0.4":      lambda p: p["selling_climax_score"] >= 0.4,
    "climax≥0.5":      lambda p: p["selling_climax_score"] >= 0.5,
    # Body compression before signal
    "compression":     lambda p: bool(p["body_compression"]),
    # EMA — price near or below EMA (DIF already <0, this confirms)
    "ema_dist<-0.5":   lambda p: p["ema_distance_norm"] < -0.5,
    "ema_dist<-1.0":   lambda p: p["ema_distance_norm"] < -1.0,
    # Composite: quality + H2
    "quality≥0.3+h2":  lambda p: p["bar_quality_bull"] >= 0.3 and p["h_leg_count"] >= 2,
    "quality≥0.4+h2":  lambda p: p["bar_quality_bull"] >= 0.4 and p["h_leg_count"] >= 2,
    # Composite: quality + climax
    "quality≥0.3+cli": lambda p: p["bar_quality_bull"] >= 0.3 and p["selling_climax_score"] >= 0.4,
    # Composite: quality + not oversold (EMA not too far)
    "quality≥0.3+ema": lambda p: p["bar_quality_bull"] >= 0.3 and p["ema_distance_norm"] > -2.0,
}


def load_bars(sym: str, bars_dir: Path, suffix: str = "_daily") -> pd.DataFrame | None:
    return bar_loader.load_bars_quant_or_json(sym, suffix, bars_dir)


def compute_atr(bars: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    hi, lo, pc = bars["high"], bars["low"], bars["close"].shift(1)
    tr = pd.concat([(hi - lo), (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def simulate_trade(
    bars: pd.DataFrame, entry_idx: int, stop_mult: float, atr_series: pd.Series
) -> float | None:
    if entry_idx + 1 >= len(bars):
        return None
    entry = float(bars["close"].iloc[entry_idx])
    av = float(atr_series.iloc[entry_idx])
    if av <= 0 or not np.isfinite(av):
        return None
    risk = stop_mult * av
    stop = entry - risk
    tp1 = entry + risk
    tp2 = entry + 2 * risk
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
    mark = float(np.clip((float(bars["close"].iloc[idx_fin]) - entry) / risk, -3.0, 3.0))
    # TP1 banked but the trade ran to the hold boundary → credit the +0.5R partial
    # exit rather than scoring raw mark-to-market (shared boundary bug; see pa_atop).
    if hit_tp1:
        return 0.5 + 0.5 * mark
    return mark


def h_trend_at(ts: pd.Timestamp, h_bars: pd.DataFrame, h_dif: pd.Series) -> str | None:
    mask = h_bars["timestamp"] <= ts
    if not mask.any():
        return None
    i = int(mask.values.nonzero()[0][-1])
    v = float(h_dif.iloc[i])
    return "bearish" if v < 0 else ("bullish" if v > 0 else "transition")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", default="CN_COMMODITY")
    parser.add_argument("--stop-mult", type=float, default=1.5)
    parser.add_argument("--min-gap", type=int, default=10)
    parser.add_argument("--cutoff1", default="2022-12-31")
    parser.add_argument("--cutoff2", default="2024-06-30")
    parser.add_argument("--bars-dir", type=Path, default=DEFAULT_BARS_DIR)
    args = parser.parse_args()

    symbols = POOLS.get(args.pool, [])
    cutoff1 = pd.Timestamp(args.cutoff1, tz="UTC")
    cutoff2 = pd.Timestamp(args.cutoff2, tz="UTC")

    # Collect all candidate signal bars with their PA features and trade outcomes
    records: list[dict] = []

    for sym in symbols:
        bars = load_bars(sym, args.bars_dir)
        if bars is None:
            continue
        h_bars = load_bars(sym, args.bars_dir, suffix="_60")
        md = compute_macd(bars["close"], hist_scale=1.0)
        dif = md["dif"]; dea = md["dea"]; hist = md["hist"]
        streams = compute_feature_streams(bars["close"], dif, dea, hist)
        units = compute_unit_metadata(dif, dea, hist, streams["dif_proximity_zero"])
        atr = compute_atr(bars)
        pa = compute_pa_features(bars)

        if h_bars is None:
            print(f"  SKIP {sym}: no 60m bars (h=opposing filter requires 60m data)", file=sys.stderr)
            continue
        h_dif: pd.Series | None = None
        h_md = compute_macd(h_bars["close"], hist_scale=1.0)
        h_dif = h_md["dif"]

        last_sig = -999

        for i in range(30, len(bars)):
            # In-cycle bearish heap condition
            state = units["cycle_state"].iloc[i] if "cycle_state" in units.columns else None
            if state != "in_cycle":
                continue
            if float(dif.iloc[i]) >= 0:
                continue

            # h=opposing (h bearish, we expect a bottom bounce)
            if h_bars is not None and h_dif is not None:
                ht = h_trend_at(bars["timestamp"].iloc[i], h_bars, h_dif)
                if ht != "bearish":
                    continue

            # min gap between signals on same symbol
            if i - last_sig < args.min_gap:
                continue

            r = simulate_trade(bars, i, args.stop_mult, atr)
            if r is None:
                continue

            last_sig = i
            pa_row = pa.iloc[i]
            ts = bars["timestamp"].iloc[i]
            period = (
                "IS" if ts <= cutoff1 else
                "OOS1" if ts <= cutoff2 else
                "OOS2"
            )
            records.append({
                "symbol": sym,
                "timestamp": ts,
                "period": period,
                "r": r,
                **{k: pa_row[k] for k in pa.columns},
            })

    if not records:
        print("No signals found.")
        return

    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    print(f"\nPA-enhanced in_cycle bottom detector — pool={args.pool}, stop={args.stop_mult}×ATR")
    print(f"Periods: IS≤{args.cutoff1}  OOS1={args.cutoff1}→{args.cutoff2}  OOS2>{args.cutoff2}")
    print("=" * 72)

    def report(label: str, subset: pd.DataFrame, width: int = 40) -> None:
        if subset.empty:
            print(f"  {label:{width}s}: n=  0")
            return
        n = len(subset)
        ev = subset["r"].mean()
        hit = (subset["r"] > 0).mean()
        is_sub = subset[subset["period"] == "IS"]
        oos1 = subset[subset["period"] == "OOS1"]
        oos2 = subset[subset["period"] == "OOS2"]
        is_str = f"{is_sub['r'].mean():+.3f}R(n={len(is_sub)})" if len(is_sub) else "—"
        o1_str = f"{oos1['r'].mean():+.3f}R(n={len(oos1)})" if len(oos1) else "—"
        o2_str = f"{oos2['r'].mean():+.3f}R(n={len(oos2)})" if len(oos2) else "—"
        print(f"  {label:{width}s}: n={n:4d}  EV={ev:+.3f}R  hit={hit:.0%}"
              f"  IS={is_str}  F1={o1_str}  F2={o2_str}")

    print()
    for name, fn in FILTERS.items():
        subset = df[df.apply(fn, axis=1)]
        report(name, subset)

    # Per-symbol breakdown for the best-looking filter
    print()
    print("Per-symbol breakdown (bull_quality≥0.4):")
    quality_mask = df["bar_quality_bull"] >= 0.4
    for sym, grp in df[quality_mask].groupby("symbol"):
        ev = grp["r"].mean()
        hit = (grp["r"] > 0).mean()
        print(f"  {sym}: n={len(grp)}, EV={ev:+.3f}R, hit={hit:.0%}")

    # Save results
    out_path = Path(f"/tmp/pa_incycle_{args.pool.lower()}.csv")
    df.to_csv(out_path, index=False)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
