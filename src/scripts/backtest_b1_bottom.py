"""K=3 walk-forward backtest for B1BottomDetector.

Fold boundaries:
  IS  : ≤ 2022-12-31
  OOS1: 2023-01-01 – 2023-12-31  (F1)
  OOS2: 2024-01-01 – 2024-12-31  (F2)
  OOS3: 2025-01-01 – present     (F3)

Usage:
  uv run python scripts/backtest_b1_bottom.py
  uv run python scripts/backtest_b1_bottom.py --stop-mult 2.0
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from engine.divergence.b1_bottom_detector import B1BottomDetector, B1BottomSignal

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
ATR_PERIOD = 14
MAX_HOLD = 40

CN_METAL_SYMBOLS: list[str] = [
    "kq_m_shfe_cu",
    "kq_m_shfe_au",
    "kq_m_shfe_ag",
    "kq_m_ine_sc",
]

CUTOFF_IS   = pd.Timestamp("2022-12-31", tz="UTC")
CUTOFF_OOS1 = pd.Timestamp("2023-12-31", tz="UTC")
CUTOFF_OOS2 = pd.Timestamp("2024-12-31", tz="UTC")
# OOS3 = everything after CUTOFF_OOS2


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_bars(sym: str, bars_dir: Path, suffix: str = "_daily") -> pd.DataFrame | None:
    candidates = list(bars_dir.glob(f"**/{sym}{suffix}.json"))
    if not candidates:
        return None
    payload = json.loads(candidates[0].read_text())
    df = pd.DataFrame(payload["bars"])
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


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
    parser.add_argument("--stop-mult", type=float, default=1.5)
    parser.add_argument("--bars-dir", type=Path, default=DEFAULT_BARS_DIR)
    args = parser.parse_args()

    det = B1BottomDetector(min_gap=10)
    all_records: list[dict] = []

    for sym in CN_METAL_SYMBOLS:
        bars = load_bars(sym, args.bars_dir)
        if bars is None:
            print(f"  [SKIP] {sym}: no daily bars found")
            continue
        h_bars = load_bars(sym, args.bars_dir, suffix="_60")
        atr = compute_atr(bars)

        sigs: list[B1BottomSignal] = det.scan(bars, h_bars)

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

    print(f"\nCN_METAL B1 Bottom — K=3 Walk-Forward")
    print(f"stop={args.stop_mult}×ATR  max_hold={MAX_HOLD}  min_gap=10")
    print("=" * 90)

    def report(label: str, subset: pd.DataFrame, width: int = 28) -> None:
        if subset.empty:
            print(f"  {label:{width}s}: n=  0")
            return
        n = len(subset)
        ev = subset["r"].mean()
        hit = (subset["r"] > 0).mean()
        is_s = subset[subset["period"] == "IS"]
        oos1 = subset[subset["period"] == "OOS1"]
        oos2 = subset[subset["period"] == "OOS2"]
        oos3 = subset[subset["period"] == "OOS3"]
        is_str = f"{is_s['r'].mean():+.3f}R(n={len(is_s)})"  if len(is_s)  else "—"
        o1_str = f"{oos1['r'].mean():+.3f}R(n={len(oos1)})"  if len(oos1)  else "—"
        o2_str = f"{oos2['r'].mean():+.3f}R(n={len(oos2)})"  if len(oos2)  else "—"
        o3_str = f"{oos3['r'].mean():+.3f}R(n={len(oos3)})"  if len(oos3)  else "—"
        print(
            f"  {label:{width}s}: n={n:4d}  EV={ev:+.3f}R  hit={hit:.0%}"
            f"  IS={is_str}  F1={o1_str}  F2={o2_str}  F3={o3_str}"
        )

    print()
    report("All signals",       df)
    report("h=opposing",        df[df["h_rel"] == "opposing"])
    report("h=supporting",      df[df["h_rel"] == "supporting"])
    report("h=neutral/unknown", df[df["h_rel"].isin(["neutral", None]) | df["h_rel"].isna()])

    print()
    print("Per-symbol breakdown — all h_rel:")
    for sym, grp in df.groupby("symbol"):
        ev = grp["r"].mean()
        n = len(grp)
        opp = grp[grp["h_rel"] == "opposing"]
        opp_str = f"  h=opp n={len(opp)} EV={opp['r'].mean():+.3f}R" if len(opp) else ""
        print(f"  {sym}: n={n}, EV={ev:+.3f}R, hit={(grp['r']>0).mean():.0%}{opp_str}")

    print()
    print("Period distribution:")
    for period, grp in df.groupby("period"):
        ev = grp["r"].mean()
        print(f"  {period}: n={len(grp)}, EV={ev:+.3f}R, hit={(grp['r']>0).mean():.0%}")

    out_path = Path("/tmp/b1_bottom_cn_metal.csv")
    df.to_csv(out_path, index=False)
    print(f"\nSaved raw signals to {out_path}")


if __name__ == "__main__":
    main()
