"""PA standalone bottom detector backtest.

Tests whether PA patterns (H2+quality) can detect swing bottoms with
positive EV WITHOUT requiring MACD divergence state. This is the recall-
expansion complement to the MACD divergence detector.

Compared to backtest_pa_incycle.py (which filters MACD in_cycle signals),
this script fires on PA structure alone — targeting the ~89% of swing
bottoms MACD divergence misses.

Walk-forward K=2:
  IS  : ≤ CUTOFF1 (2022-12-31)
  OOS1: CUTOFF1 – CUTOFF2 (up to 2024-06-30)
  OOS2: > CUTOFF2

Usage:
  uv run python scripts/backtest_pa_standalone.py --pool CN_COMMODITY
  uv run python scripts/backtest_pa_standalone.py --pool CN_METAL --stop-mult 2.0
  uv run python scripts/backtest_pa_standalone.py --pool CN_AGRI
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
from engine.features.pa_features import compute_pa_features

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
    "CN_METAL_CORE": [  # cu/au/ag only — sc/rb excluded for isolation niche analysis
        "kq_m_shfe_cu", "kq_m_shfe_au", "kq_m_shfe_ag",
    ],
    "CN_AGRI": [
        "kq_m_dce_m", "kq_m_dce_i", "kq_m_dce_j", "kq_m_dce_jm",
        "kq_m_dce_p", "kq_m_dce_y",
        "kq_m_czce_ta", "kq_m_czce_ma", "kq_m_czce_cf", "kq_m_czce_sr",
    ],
    # sr/p/ma/ta/m — 5 symbols with positive h=opp lift in full-data analysis
    "CN_AGRI_POS": [
        "kq_m_dce_m", "kq_m_dce_p",
        "kq_m_czce_ta", "kq_m_czce_ma", "kq_m_czce_sr",
    ],
}

# Detector configurations to test.
# Each entry: (label, PABottomDetector kwargs, h_opp_filter)
CONFIGS: list[tuple[str, dict, bool]] = [
    # Standalone PA — all h_rel
    ("h2+q03",           {"min_h_legs": 2, "min_quality": 0.3},                     False),
    ("h2+q04",           {"min_h_legs": 2, "min_quality": 0.4},                     False),
    ("h2+q03+climax",    {"min_h_legs": 2, "min_quality": 0.3,
                          "require_climax": True, "climax_threshold": 0.4},          False),
    ("h3+q03",           {"min_h_legs": 3, "min_quality": 0.3},                     False),
    # With h=opposing filter
    ("h2+q03 | h=opp",   {"min_h_legs": 2, "min_quality": 0.3},                     True),
    ("h2+q04 | h=opp",   {"min_h_legs": 2, "min_quality": 0.4},                     True),
    ("h2+q03+cli | h=opp", {"min_h_legs": 2, "min_quality": 0.3,
                             "require_climax": True, "climax_threshold": 0.4},       True),
    ("h2+q03+ema≤-1 | h=opp", {"min_h_legs": 2, "min_quality": 0.3,
                                "ema_threshold": -1.0},                              True),
    ("h3+q03 | h=opp",   {"min_h_legs": 3, "min_quality": 0.3},                     True),
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_bars(sym: str, bars_dir: Path, suffix: str = "_daily") -> pd.DataFrame | None:
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", default="CN_COMMODITY")
    parser.add_argument("--stop-mult", type=float, default=1.5)
    parser.add_argument("--cutoff1", default="2022-12-31")
    parser.add_argument("--cutoff2", default="2024-06-30")
    parser.add_argument("--cutoff3", default=None,
                        help="Enable K=3 walk-forward by adding a third OOS fold cutoff")
    parser.add_argument("--bars-dir", type=Path, default=DEFAULT_BARS_DIR)
    parser.add_argument("--isolation-lookback", type=int, default=10,
                        help="Lookback window for isolation filter (bars)")
    args = parser.parse_args()

    symbols = POOLS.get(args.pool, [])
    cutoff1 = pd.Timestamp(args.cutoff1, tz="UTC")
    cutoff2 = pd.Timestamp(args.cutoff2, tz="UTC")
    cutoff3 = pd.Timestamp(args.cutoff3, tz="UTC") if args.cutoff3 else None
    k3 = cutoff3 is not None

    # For each detector config, collect all (bar_idx, r, period, symbol, h_rel) records.
    # We scan each symbol once with the most permissive config, then filter in Python.
    # To do this efficiently, scan once per symbol and store full PA features + h_rel.

    all_records: list[dict] = []

    for sym in symbols:
        bars = load_bars(sym, args.bars_dir)
        if bars is None:
            continue
        h_bars = load_bars(sym, args.bars_dir, suffix="_60")
        atr = compute_atr(bars)
        pa = compute_pa_features(bars)

        # Scan with the most permissive detector (h_leg>=2, quality>=0.1, ema<0).
        # min_gap=1 here — gap enforcement happens per-config in _apply_config_filter
        # so tighter-config signals are not excluded by loose-config gaps (same fix
        # applied to backtest_bpull.py, 2026-06-02).
        base_det = PABottomDetector(
            min_h_legs=2, min_quality=0.1, ema_threshold=0.0,
            min_gap=1, require_climax=False,
        )
        sigs: list[PASignal] = base_det.scan(bars, h_bars)

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

    if not all_records:
        print("No signals found.")
        return

    df = pd.DataFrame(all_records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    k_str = "K=3" if k3 else "K=2"
    print(f"\nPA standalone bottom detector — pool={args.pool}, stop={args.stop_mult}×ATR, {k_str}")
    print(f"Periods: IS≤{args.cutoff1}  OOS1={args.cutoff1}→{args.cutoff2}  OOS2>{args.cutoff2}")
    if k3:
        print(f"         OOS2={args.cutoff2}→{args.cutoff3}  OOS3>{args.cutoff3}")
    print("=" * 80)

    def report(label: str, subset: pd.DataFrame, width: int = 28) -> None:
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
        row = (f"  {label:{width}s}: n={n:4d}  EV={ev:+.3f}R  hit={hit:.0%}"
               f"  IS={is_str}  F1={o1_str}  F2={o2_str}")
        if k3:
            oos3 = subset[subset["period"] == "OOS3"]
            o3_str = f"{oos3['r'].mean():+.3f}R(n={len(oos3)})" if len(oos3) else "—"
            row += f"  F3={o3_str}"
        print(row)

    print("\n--- Standalone (all h_rel) ---")
    for label, det_kwargs, h_opp_only in CONFIGS:
        if h_opp_only:
            continue
        subset = _apply_config_filter(df, det_kwargs, h_opp_only=False)
        report(label, subset)

    print("\n--- With h=opposing filter ---")
    for label, det_kwargs, h_opp_only in CONFIGS:
        if not h_opp_only:
            continue
        subset = _apply_config_filter(df, det_kwargs, h_opp_only=True)
        report(label, subset)

    # Per-symbol breakdown for the best-looking filter
    print()
    print("Per-symbol breakdown — h2+q03 | h=opposing:")
    best_subset = _apply_config_filter(df, {"min_h_legs": 2, "min_quality": 0.3},
                                       h_opp_only=True)
    for sym, grp in best_subset.groupby("symbol"):
        ev = grp["r"].mean()
        hit = (grp["r"] > 0).mean()
        print(f"  {sym}: n={len(grp)}, EV={ev:+.3f}R, hit={hit:.0%}")

    # h_rel breakdown (all signals, h2+q03)
    print()
    print("h_rel breakdown — h2+q03 (all h_rel):")
    base_subset = _apply_config_filter(df, {"min_h_legs": 2, "min_quality": 0.3},
                                       h_opp_only=False)
    for rel, grp in base_subset.groupby("h_rel", dropna=False):
        ev = grp["r"].mean()
        print(f"  h_rel={rel!r}: n={len(grp)}, EV={ev:+.3f}R, hit={(grp['r']>0).mean():.0%}")

    # --- Isolation filter analysis ---
    # "no_recent_pa": no quality≥0.1 PA signal from same symbol within past N bars.
    # The base scan (min_gap=1, min_quality=0.1) captures all candidate bars so the
    # dataframe itself is the reference set for checking prior PA activity.
    df["isolated"] = _compute_isolation_flag(df, lookback=args.isolation_lookback)

    print()
    print(f"--- Isolation filter (no_recent_pa in past {args.isolation_lookback} bars) — h2+q03 | h=opp ---")
    opp_all = _apply_config_filter(df, {"min_h_legs": 2, "min_quality": 0.3},
                                   h_opp_only=True)
    iso   = opp_all[opp_all["isolated"]]
    noniso = opp_all[~opp_all["isolated"]]
    report("isolated (no_recent_pa)",     iso,    width=28)
    report("non-isolated (recent PA≥0.1)", noniso, width=28)
    print()
    print("Per-symbol — isolated | h=opp:")
    for sym, grp in iso.groupby("symbol"):
        ev = grp["r"].mean()
        print(f"  {sym}: n={len(grp)}, EV={ev:+.3f}R, hit={(grp['r']>0).mean():.0%}")

    # h3 isolation comparison
    print()
    print(f"--- h3+q03 | h=opp isolation comparison ---")
    h3_all = _apply_config_filter(df, {"min_h_legs": 3, "min_quality": 0.3},
                                  h_opp_only=True)
    h3_iso = h3_all[h3_all["isolated"]]
    h3_noniso = h3_all[~h3_all["isolated"]]
    report("h3 isolated (no_recent_pa)", h3_iso, width=28)
    report("h3 non-isolated",            h3_noniso, width=28)

    out_path = Path(f"/tmp/pa_standalone_{args.pool.lower()}.csv")
    df.to_csv(out_path, index=False)
    print(f"\nSaved raw signals to {out_path}")


def _apply_config_filter(
    df: pd.DataFrame,
    det_kwargs: dict,
    h_opp_only: bool,
    min_gap: int = 10,
) -> pd.DataFrame:
    """Filter + enforce min_gap per symbol in chronological order.

    Must be called after base scan with min_gap=1, so all candidate bars
    are present. Gap enforcement ensures each config gets correct signal count
    without contamination from looser-config signals (same fix as bpull backtest).
    """
    mask = pd.Series(True, index=df.index)

    min_h = det_kwargs.get("min_h_legs", 2)
    min_q = det_kwargs.get("min_quality", 0.3)
    ema_thr = det_kwargs.get("ema_threshold", 0.0)
    req_climax = det_kwargs.get("require_climax", False)
    climax_thr = det_kwargs.get("climax_threshold", 0.4)

    mask &= df["h_leg_count"] >= min_h
    mask &= df["bar_quality_bull"] >= min_q
    mask &= df["ema_distance_norm"] < ema_thr

    if req_climax:
        # Use recent_climax_max_5: max climax score in the 5 bars BEFORE the signal.
        # The signal bar itself (bull bar) will always have low climax_score, so
        # we check prior bars for exhaustion context.
        mask &= df["recent_climax_max_5"] >= climax_thr

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


def _compute_isolation_flag(df: pd.DataFrame, lookback: int = 10) -> pd.Series:
    """Return a boolean Series: True if no quality≥0.1 signal in past `lookback` bars.

    Uses the full base-scan dataframe (min_quality=0.1) as the reference set.
    Per-symbol, chronological: a signal is "isolated" if its bar_idx differs
    from the immediately preceding signal's bar_idx by more than `lookback`.
    """
    result = pd.Series(False, index=df.index)
    for _, grp in df.groupby("symbol"):
        grp_sorted = grp.sort_values("bar_idx")
        prev_bar = -999
        for idx, row in grp_sorted.iterrows():
            cur_bar = int(row["bar_idx"])
            result[idx] = (cur_bar - prev_bar) > lookback
            prev_bar = cur_bar
    return result


if __name__ == "__main__":
    main()
