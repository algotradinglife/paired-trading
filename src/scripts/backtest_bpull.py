"""BPull (Bullish Pullback) detector backtest — full-pool WF validation.

Validates BPullDetector on the full CN_COMMODITY/CN_METAL pools.
Unlike backtest results from the missed-swing analysis (which pre-filtered
to confirmed bottoms), this tests the detector on all bars — the real
signal-frequency vs EV trade-off.

Walk-forward K=2:
  IS  : ≤ CUTOFF1 (2022-12-31)
  OOS1: CUTOFF1 – CUTOFF2 (up to 2024-06-30)
  OOS2: > CUTOFF2

Usage:
  uv run python scripts/backtest_bpull.py --pool CN_COMMODITY
  uv run python scripts/backtest_bpull.py --pool CN_METAL --stop-mult 2.0
  uv run python scripts/backtest_bpull.py --pool CN_COMMODITY --cutoff3 2025-06-30
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from engine.divergence.bpull_detector import BPullDetector, BPullSignal
from data import bar_loader

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

# Detector configurations to compare.
# (label, ema_touch_pct, ema_floor_pct, h_opp_only)
CONFIGS: list[tuple[str, float, float, bool]] = [
    # All h_rel
    ("dif>0 + ema_touch",         0.005, 0.030, False),
    ("dif>0 + ema_touch_tight",   0.002, 0.030, False),
    ("dif>0 + ema_touch_loose",   0.010, 0.030, False),
    # With h=opposing filter
    ("dif>0 + ema_touch | h=opp", 0.005, 0.030, True),
    ("dif>0 + tight | h=opp",     0.002, 0.030, True),
    ("dif>0 + loose | h=opp",     0.010, 0.030, True),
    ("dif>0 + ema_touch + wide_floor | h=opp", 0.005, 0.050, True),
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_bars(sym: str, bars_dir: Path, suffix: str = "_daily") -> pd.DataFrame | None:
    """Load bars via load_bars_quant_or_json (Parquet → fallback JSON).

    The simple JSON loader previously here was wrong: snapshots for
    shfe ag/au/cu / ine sc were truncated to 2026 H1 during migration,
    so h_rel annotation silently failed for ~98% of historical signals
    (see vflush 2026-06-09 incident — same bug pattern).
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
    args = parser.parse_args()

    symbols = POOLS.get(args.pool, [])
    cutoff1 = pd.Timestamp(args.cutoff1, tz="UTC")
    cutoff2 = pd.Timestamp(args.cutoff2, tz="UTC")
    cutoff3 = pd.Timestamp(args.cutoff3, tz="UTC") if args.cutoff3 else None
    k3 = cutoff3 is not None

    # Scan with a permissive base detector (min_gap=1) to collect ALL candidate
    # bars. Per-config filtering + gap enforcement happen later in _filter_with_gap().
    # Using min_gap=5 here would permanently exclude bars that are valid for tighter
    # configs but fall within 5 bars of a loose-only signal (Codex P2, 2026-06-02).
    base_det = BPullDetector(ema_touch_pct=0.020, ema_floor_pct=0.060, min_gap=1)

    all_records: list[dict] = []

    for sym in symbols:
        bars = load_bars(sym, args.bars_dir)
        if bars is None:
            continue
        h_bars = load_bars(sym, args.bars_dir, suffix="_60")
        atr = compute_atr(bars)

        sigs: list[BPullSignal] = base_det.scan(bars, h_bars)

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
                **sig.features,
            })

    if not all_records:
        print("No signals found.")
        return

    df = pd.DataFrame(all_records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    k_str = "K=3" if k3 else "K=2"
    print(f"\nBPull detector — pool={args.pool}, stop={args.stop_mult}×ATR, {k_str}")
    print(f"Periods: IS≤{args.cutoff1}  OOS1={args.cutoff1}→{args.cutoff2}  OOS2>{args.cutoff2}")
    if k3:
        print(f"         OOS2={args.cutoff2}→{args.cutoff3}  OOS3>{args.cutoff3}")
    print("=" * 90)

    def report(label: str, subset: pd.DataFrame, width: int = 36) -> None:
        if subset.empty:
            print(f"  {label:{width}s}: n=  0")
            return
        n = len(subset)
        ev = subset["r"].mean()
        hit = (subset["r"] > 0).mean()
        is_s  = subset[subset["period"] == "IS"]
        oos1  = subset[subset["period"] == "OOS1"]
        oos2  = subset[subset["period"] == "OOS2"]
        is_str  = f"{is_s['r'].mean():+.3f}R(n={len(is_s)})"  if len(is_s)  else "—"
        o1_str  = f"{oos1['r'].mean():+.3f}R(n={len(oos1)})"  if len(oos1)  else "—"
        o2_str  = f"{oos2['r'].mean():+.3f}R(n={len(oos2)})"  if len(oos2)  else "—"
        row = (f"  {label:{width}s}: n={n:4d}  EV={ev:+.3f}R  hit={hit:.0%}"
               f"  IS={is_str}  F1={o1_str}  F2={o2_str}")
        if k3:
            oos3 = subset[subset["period"] == "OOS3"]
            o3_str = f"{oos3['r'].mean():+.3f}R(n={len(oos3)})" if len(oos3) else "—"
            row += f"  F3={o3_str}"
        print(row)

    print("\n--- All h_rel ---")
    for label, touch, floor_pct, h_opp_only in CONFIGS:
        if h_opp_only:
            continue
        subset = _filter_with_gap(df, touch, floor_pct, h_opp_only=False)
        report(label, subset)

    print("\n--- h=opposing filter ---")
    for label, touch, floor_pct, h_opp_only in CONFIGS:
        if not h_opp_only:
            continue
        subset = _filter_with_gap(df, touch, floor_pct, h_opp_only=True)
        report(label, subset)

    print()
    print("h_rel breakdown — dif>0 + ema_touch (all h_rel):")
    base_sub = _filter_with_gap(df, 0.005, 0.030, h_opp_only=False)
    for rel, grp in base_sub.groupby("h_rel", dropna=False):
        ev = grp["r"].mean()
        print(f"  h_rel={rel!r}: n={len(grp)}, EV={ev:+.3f}R, hit={(grp['r']>0).mean():.0%}")

    print()
    print("Per-symbol breakdown — dif>0 + ema_touch | h=opp:")
    opp_sub = _filter_with_gap(df, 0.005, 0.030, h_opp_only=True)
    for sym, grp in opp_sub.groupby("symbol"):
        ev = grp["r"].mean()
        print(f"  {sym}: n={len(grp)}, EV={ev:+.3f}R, hit={(grp['r']>0).mean():.0%}")

    out_path = Path(f"/tmp/bpull_{args.pool.lower()}.csv")
    df.to_csv(out_path, index=False)
    print(f"\nSaved raw signals to {out_path}")


def _filter(
    df: pd.DataFrame,
    ema_touch_pct: float,
    ema_floor_pct: float,
    h_opp_only: bool,
) -> pd.DataFrame:
    """Filter the raw signal dataframe to the given config (no gap enforcement)."""
    mask = (
        (df["ema_touch_pct_actual"] <= ema_touch_pct) &
        (df["ema_floor_actual"] >= -ema_floor_pct)
    )
    if h_opp_only:
        mask &= df["h_rel"] == "opposing"
    return df[mask]


def _filter_with_gap(
    df: pd.DataFrame,
    ema_touch_pct: float,
    ema_floor_pct: float,
    h_opp_only: bool,
    min_gap: int = 10,
) -> pd.DataFrame:
    """Filter + enforce min_gap per symbol in chronological order.

    Must be called after base scan with min_gap=1, so all candidate bars
    are present. Gap enforcement here ensures each config gets the correct
    signal count without contamination from looser-config signals.
    """
    filtered = _filter(df, ema_touch_pct, ema_floor_pct, h_opp_only)
    if filtered.empty:
        return filtered
    rows: list[pd.Series] = []
    for _, grp in filtered.groupby("symbol"):
        grp = grp.sort_values("bar_idx")
        last_idx = -999
        for _, row in grp.iterrows():
            if int(row["bar_idx"]) - last_idx >= min_gap:
                rows.append(row)
                last_idx = int(row["bar_idx"])
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=filtered.columns)


if __name__ == "__main__":
    main()
