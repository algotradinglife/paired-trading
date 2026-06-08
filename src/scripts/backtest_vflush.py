"""VFlush bottom detector backtest — CN_METAL pool walk-forward validation.

Tests whether VFlush patterns (V-shape vertical flush exhaustion) detect
swing bottoms with positive EV. Targets the recall gap where PA H2 fails:
75% of missed CN_METAL bottoms have h_leg_count < 2 and bar_quality_bull < 0.1.

Walk-forward K=2:
  IS  : <= CUTOFF1 (2022-12-31)
  OOS1: CUTOFF1 -- CUTOFF2 (up to 2024-06-30)
  OOS2: > CUTOFF2

Walk-forward K=3 (--cutoff3 set):
  OOS2: CUTOFF2 -- CUTOFF3 (up to 2025-06-30)
  OOS3: > CUTOFF3

Usage:
  uv run python scripts/backtest_vflush.py
  uv run python scripts/backtest_vflush.py --h-opp-only
  uv run python scripts/backtest_vflush.py --cutoff3 2025-06-30
  uv run python scripts/backtest_vflush.py --h-opp-only --cutoff3 2025-06-30
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from engine.divergence.vflush_detector import VFlushDetector, VFlushSignal
from engine.divergence.pa_detector import PABottomDetector, PASignal
from data import bar_loader

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
ATR_PERIOD = 14
MAX_HOLD = 20   # 20-bar look-ahead (as specified in task)

CN_METAL = [
    "kq_m_shfe_cu",
    "kq_m_shfe_au",
    "kq_m_shfe_ag",
    "kq_m_ine_sc",
]

# Detector configurations to test.
# (label, VFlushDetector kwargs, h_opp_only)
# Note: lookback_climax_thr=99.0 disables lookback-only path (backtest shows EV<0).
#       Set lookback_climax_thr to a real value (e.g. 0.4) to enable it.
CONFIGS: list[tuple[str, dict, bool]] = [
    # All h_rel — base scans with lookback disabled (recommended production config)
    ("vflush_base",              {"max_h_legs": 1, "min_ema_pct": -0.02, "min_climax": 0.3, "lookback_climax_thr": 99.0},  False),
    ("vflush_strict_climax",     {"max_h_legs": 1, "min_ema_pct": -0.02, "min_climax": 0.4, "lookback_climax_thr": 99.0},  False),
    ("vflush_strict_ema",        {"max_h_legs": 1, "min_ema_pct": -0.04, "min_climax": 0.3, "lookback_climax_thr": 99.0},  False),
    ("vflush_h0_only",           {"max_h_legs": 0, "min_ema_pct": -0.02, "min_climax": 0.3, "lookback_climax_thr": 99.0},  False),
    # With h=opposing filter
    ("vflush_base | h=opp",       {"max_h_legs": 1, "min_ema_pct": -0.02, "min_climax": 0.3, "lookback_climax_thr": 99.0},  True),
    ("vflush_strict_cli | h=opp", {"max_h_legs": 1, "min_ema_pct": -0.02, "min_climax": 0.4, "lookback_climax_thr": 99.0},  True),
    ("vflush_strict_ema | h=opp", {"max_h_legs": 1, "min_ema_pct": -0.04, "min_climax": 0.3, "lookback_climax_thr": 99.0},  True),
    ("vflush_h0 | h=opp",         {"max_h_legs": 0, "min_ema_pct": -0.02, "min_climax": 0.3, "lookback_climax_thr": 99.0},  True),
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_bars(sym: str, bars_dir: Path, suffix: str = "_daily") -> pd.DataFrame | None:
    """Load bars via load_bars_quant_or_json (Parquet → fallback JSON).

    The simple JSON loader previously here was wrong: snapshots for
    shfe ag/au/cu / ine sc were truncated to 2026 H1 during migration,
    so h_rel annotation silently failed for ~98% of historical signals
    and produced false 'DRIFT' verdicts (see vflush 2026-06-09 incident).
    """
    return bar_loader.load_bars_quant_or_json(sym, suffix, bars_dir)


def compute_atr(bars: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    hi, lo, pc = bars["high"], bars["low"], bars["close"].shift(1)
    tr = pd.concat([(hi - lo), (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


# ---------------------------------------------------------------------------
# Trade simulation
# ---------------------------------------------------------------------------

def simulate_trade(
    bars: pd.DataFrame,
    entry_idx: int,
    stop_mult: float,
    atr_series: pd.Series,
    max_hold: int = MAX_HOLD,
) -> float | None:
    """Simulate a long trade from signal bar close.

    Entry: close of signal bar (entry_idx)
    Stop:  entry - stop_mult * ATR14
    TP1:   entry + 1.0 * risk  (scale out halfway)
    TP2:   entry + 2.0 * risk  → yields 1.5R total
    Cap:   ±3R
    """
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
                mark = (cl - entry) / risk
                return 0.5 + 0.5 * float(np.clip(mark, -3.0, 3.0))
    # Reached max_hold without TP or stop
    idx_fin = min(entry_idx + max_hold, len(bars) - 1)
    mark = (float(bars["close"].iloc[idx_fin]) - entry) / risk
    return float(np.clip(mark, -3.0, 3.0))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stop-mult", type=float, default=1.5)
    parser.add_argument("--cutoff1", default="2022-12-31")
    parser.add_argument("--cutoff2", default="2024-06-30")
    parser.add_argument("--cutoff3", default="2025-06-30",
                        help="Enable K=3 walk-forward with third OOS fold")
    parser.add_argument("--bars-dir", type=Path, default=DEFAULT_BARS_DIR)
    parser.add_argument("--h-opp-only", action="store_true",
                        help="Only report signals with higher_tf_relation=opposing")
    args = parser.parse_args()

    cutoff1 = pd.Timestamp(args.cutoff1, tz="UTC")
    cutoff2 = pd.Timestamp(args.cutoff2, tz="UTC")
    cutoff3 = pd.Timestamp(args.cutoff3, tz="UTC") if args.cutoff3 else None
    k3 = cutoff3 is not None

    # Collect all VFlush signals across symbols.
    # Scan with most permissive config (min_gap=1, max_h_legs=1, min_climax=0.1)
    # then filter per config in Python for efficient multi-config comparison.
    all_records: list[dict] = []

    # Also collect PA H2 signals for overlap analysis.
    pa_signals_by_sym: dict[str, list[PASignal]] = {}

    for sym in CN_METAL:
        bars = load_bars(sym, args.bars_dir)
        if bars is None:
            print(f"  [WARN] No daily bars for {sym}, skipping.")
            continue
        h_bars = load_bars(sym, args.bars_dir, suffix="_60")
        atr = compute_atr(bars)

        # Base VFlush scan: most permissive (min_gap=1, min_climax=0.1, max_h=1)
        base_det = VFlushDetector(
            max_h_legs=1,
            min_ema_pct=-0.02,
            min_climax=0.1,
            climax_lookback=3,
            lookback_climax_thr=0.3,
            min_gap=1,
        )
        sigs: list[VFlushSignal] = base_det.scan(bars, h_bars)

        for sig in sigs:
            r = simulate_trade(bars, sig.bar_idx, args.stop_mult, atr)
            if r is None:
                continue
            ts = sig.timestamp
            if k3:
                period = (
                    "IS"   if ts <= cutoff1 else
                    "OOS1" if ts <= cutoff2 else
                    "OOS2" if ts <= cutoff3 else
                    "OOS3"
                )
            else:
                period = (
                    "IS"   if ts <= cutoff1 else
                    "OOS1" if ts <= cutoff2 else
                    "OOS2"
                )
            all_records.append({
                "symbol": sym,
                "bar_idx": sig.bar_idx,
                "timestamp": ts,
                "period": period,
                "r": r,
                "h_rel": sig.higher_tf_relation,
                "confidence": sig.confidence,
                **sig.features,
            })

        # PA H2 scan for overlap analysis
        pa_det = PABottomDetector(
            min_h_legs=2, min_quality=0.3, ema_threshold=0.0,
            min_gap=10, require_climax=False,
        )
        pa_sigs = pa_det.scan(bars, h_bars)
        pa_signals_by_sym[sym] = pa_sigs

    if not all_records:
        print("No VFlush signals found.")
        return

    df = pd.DataFrame(all_records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    k_str = "K=3" if k3 else "K=2"
    print(f"\nVFlush bottom detector backtest — pool=CN_METAL, stop={args.stop_mult}x ATR, {k_str}")
    print(f"Periods: IS<={args.cutoff1}  OOS1={args.cutoff1}->{args.cutoff2}  OOS2>{args.cutoff2}")
    if k3:
        print(f"         OOS2={args.cutoff2}->{args.cutoff3}  OOS3>{args.cutoff3}")
    print("=" * 90)

    def report(label: str, subset: pd.DataFrame, width: int = 30) -> None:
        if subset.empty:
            print(f"  {label:{width}s}: n=  0")
            return
        n = len(subset)
        ev = subset["r"].mean()
        hit = (subset["r"] > 0).mean()
        is_sub  = subset[subset["period"] == "IS"]
        oos1    = subset[subset["period"] == "OOS1"]
        oos2    = subset[subset["period"] == "OOS2"]
        is_str  = f"{is_sub['r'].mean():+.3f}R(n={len(is_sub)})"  if len(is_sub)  else "—"
        o1_str  = f"{oos1['r'].mean():+.3f}R(n={len(oos1)})"      if len(oos1)    else "—"
        o2_str  = f"{oos2['r'].mean():+.3f}R(n={len(oos2)})"      if len(oos2)    else "—"
        row = (f"  {label:{width}s}: n={n:4d}  EV={ev:+.3f}R  hit={hit:.0%}"
               f"  IS={is_str}  F1={o1_str}  F2={o2_str}")
        if k3:
            oos3   = subset[subset["period"] == "OOS3"]
            o3_str = f"{oos3['r'].mean():+.3f}R(n={len(oos3)})"   if len(oos3)    else "—"
            row   += f"  F3={o3_str}"
        print(row)

    # --- Filter mode ---
    if args.h_opp_only:
        print("\n--- VFlush (h=opposing only) ---")
        for label, det_kwargs, h_opp_only in CONFIGS:
            if not h_opp_only:
                continue
            subset = _apply_config_filter(df, det_kwargs, h_opp_only=True)
            report(label, subset)
    else:
        print("\n--- VFlush (all h_rel) ---")
        for label, det_kwargs, h_opp_only in CONFIGS:
            if h_opp_only:
                continue
            subset = _apply_config_filter(df, det_kwargs, h_opp_only=False)
            report(label, subset)

        print("\n--- VFlush (h=opposing filter) ---")
        for label, det_kwargs, h_opp_only in CONFIGS:
            if not h_opp_only:
                continue
            subset = _apply_config_filter(df, det_kwargs, h_opp_only=True)
            report(label, subset)

    # --- Per-symbol breakdown for base config + h=opp ---
    print()
    print("Per-symbol breakdown — vflush_base | h=opposing:")
    best = _apply_config_filter(df, {"max_h_legs": 1, "min_ema_pct": -0.02, "min_climax": 0.3},
                                h_opp_only=True)
    for sym, grp in best.groupby("symbol"):
        ev  = grp["r"].mean()
        hit = (grp["r"] > 0).mean()
        is_grp   = grp[grp["period"] == "IS"]
        oos1_grp = grp[grp["period"] == "OOS1"]
        oos2_grp = grp[grp["period"] == "OOS2"]
        is_s  = f"IS={is_grp['r'].mean():+.3f}R(n={len(is_grp)})"   if len(is_grp)   else "IS=—"
        o1_s  = f"F1={oos1_grp['r'].mean():+.3f}R(n={len(oos1_grp)})" if len(oos1_grp) else "F1=—"
        o2_s  = f"F2={oos2_grp['r'].mean():+.3f}R(n={len(oos2_grp)})" if len(oos2_grp) else "F2=—"
        line  = f"  {sym}: n={len(grp)}, EV={ev:+.3f}R, hit={hit:.0%}  {is_s}  {o1_s}  {o2_s}"
        if k3:
            oos3_grp = grp[grp["period"] == "OOS3"]
            o3_s = f"F3={oos3_grp['r'].mean():+.3f}R(n={len(oos3_grp)})" if len(oos3_grp) else "F3=—"
            line += f"  {o3_s}"
        print(line)

    # --- h_rel breakdown ---
    print()
    print("h_rel breakdown — vflush_base (all h_rel):")
    base_all = _apply_config_filter(df, {"max_h_legs": 1, "min_ema_pct": -0.02, "min_climax": 0.3},
                                    h_opp_only=False)
    for rel, grp in base_all.groupby("h_rel", dropna=False):
        ev  = grp["r"].mean()
        hit = (grp["r"] > 0).mean()
        is_grp   = grp[grp["period"] == "IS"]
        oos1_grp = grp[grp["period"] == "OOS1"]
        oos2_grp = grp[grp["period"] == "OOS2"]
        is_s  = f"IS={is_grp['r'].mean():+.3f}R(n={len(is_grp)})"   if len(is_grp)   else "IS=—"
        o1_s  = f"F1={oos1_grp['r'].mean():+.3f}R(n={len(oos1_grp)})" if len(oos1_grp) else "F1=—"
        o2_s  = f"F2={oos2_grp['r'].mean():+.3f}R(n={len(oos2_grp)})" if len(oos2_grp) else "F2=—"
        print(f"  h_rel={rel!r}: n={len(grp)}, EV={ev:+.3f}R, hit={hit:.0%}  {is_s}  {o1_s}  {o2_s}")

    # --- Overlap analysis with PA H2 ---
    print()
    print("Overlap analysis — VFlush vs PA H2 (within ±3 bars):")
    _report_overlap(best, pa_signals_by_sym)

    # --- Trigger-type breakdown ---
    print()
    print("Trigger breakdown — vflush_base | h=opp:")
    if not best.empty and "current_fire" in best.columns:
        for fire_type, grp in best.groupby("current_fire"):
            lbl = "current_bar_climax" if fire_type else "lookback_climax_only"
            ev  = grp["r"].mean()
            print(f"  {lbl}: n={len(grp)}, EV={ev:+.3f}R, hit={(grp['r']>0).mean():.0%}")

    out_path = Path("/tmp/vflush_cn_metal.csv")
    df.to_csv(out_path, index=False)
    print(f"\nSaved raw signals to {out_path}")


def _apply_config_filter(
    df: pd.DataFrame,
    det_kwargs: dict,
    h_opp_only: bool,
    min_gap: int = 10,
) -> pd.DataFrame:
    """Filter base-scan records to a specific config, then enforce min_gap per symbol."""
    mask = pd.Series(True, index=df.index)

    max_h          = det_kwargs.get("max_h_legs", 1)
    min_ema        = det_kwargs.get("min_ema_pct", -0.02)
    min_cli        = det_kwargs.get("min_climax", 0.3)
    lb_thr         = det_kwargs.get("lookback_climax_thr", 99.0)

    mask &= df["h_leg_count"] <= max_h
    mask &= df["ema_distance_norm"] < min_ema
    # Exhaustion gate: current bar OR recent lookback (lookback disabled if lb_thr=99.0)
    mask &= (
        (df["selling_climax_score"] >= min_cli) |
        (df["recent_climax_max"] >= lb_thr)
    )

    if h_opp_only:
        mask &= df["h_rel"] == "opposing"

    filtered = df[mask]
    if filtered.empty:
        return filtered

    rows: list = []
    for _, grp in filtered.groupby("symbol"):
        grp = grp.sort_values("bar_idx")
        last_idx = -999
        for _, row in grp.iterrows():
            if int(row["bar_idx"]) - last_idx >= min_gap:
                rows.append(row)
                last_idx = int(row["bar_idx"])
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=filtered.columns)


def _report_overlap(
    vflush_df: pd.DataFrame,
    pa_signals_by_sym: dict[str, list[PASignal]],
    window: int = 3,
) -> None:
    """Report what fraction of VFlush signals are within ±window bars of a PA H2 signal."""
    if vflush_df.empty:
        print("  No VFlush signals to compare.")
        return

    overlap_count = 0
    total = len(vflush_df)

    for _, row in vflush_df.iterrows():
        sym    = str(row["symbol"])
        vf_idx = int(row["bar_idx"])
        pa_sigs = pa_signals_by_sym.get(sym, [])
        is_overlap = any(
            abs(pa_sig.bar_idx - vf_idx) <= window for pa_sig in pa_sigs
        )
        if is_overlap:
            overlap_count += 1

    pct = overlap_count / total * 100 if total > 0 else 0.0
    print(f"  VFlush signals total:    {total}")
    print(f"  Overlap with PA H2 (±{window} bars): {overlap_count} ({pct:.1f}%)")
    print(f"  Non-overlapping VFlush:  {total - overlap_count} ({100-pct:.1f}%)")


if __name__ == "__main__":
    main()
