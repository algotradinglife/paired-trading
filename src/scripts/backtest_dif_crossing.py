"""Walk-forward backtest of DIF-crossing capitulation detector.

Signal definition:
  - DIF crosses below zero from positive (d_trend_side: bullish→transition on bar T)
  - DEA still positive at bar T (Song '预警' stage: DIF down, DEA not yet crossed)
  - Higher-TF trend is bearish (h=opposing — opposing the local up move we expect)
  - Fire a BOTTOM signal (expect price to bounce from this exhaustion)

Compare two variants:
  A. Standard MACD (12,26,9) — DIF crossing
  B. Secondary fast MACD overlay (6,13,5) — DIF crossing

Higher-TF: use 60min bars (topology B) or weekly if available.

Usage:
  uv run python scripts/backtest_dif_crossing.py --pool CN_COMMODITY --stop-mult 1.5
  uv run python scripts/backtest_dif_crossing.py --pool CN_METAL --stop-mult 1.5
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from engine.features.macd import macd

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
    "CN_METAL": ["kq_m_shfe_rb", "kq_m_shfe_cu", "kq_m_shfe_au", "kq_m_shfe_ag", "kq_m_ine_sc"],
    "CN_AGRI": [
        "kq_m_dce_m", "kq_m_dce_i", "kq_m_dce_j", "kq_m_dce_jm",
        "kq_m_dce_p", "kq_m_dce_y",
        "kq_m_czce_ta", "kq_m_czce_ma", "kq_m_czce_cf", "kq_m_czce_sr",
    ],
}


def load_bars(sym: str, bars_dir: Path) -> pd.DataFrame | None:
    candidates = list(bars_dir.glob(f"**/{sym}_daily.json"))
    if not candidates:
        return None
    payload = json.loads(candidates[0].read_text())
    df = pd.DataFrame(payload["bars"])
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


def load_bars_60min(sym: str, bars_dir: Path) -> pd.DataFrame | None:
    # Raw snapshots use "_60.json" suffix (e.g. kq_m_shfe_ag_60.json)
    candidates = list(bars_dir.glob(f"**/{sym}_60.json"))
    if not candidates:
        candidates = list(bars_dir.glob(f"**/{sym}_60min.json"))
    if not candidates:
        return None
    payload = json.loads(candidates[0].read_text())
    df = pd.DataFrame(payload["bars"])
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


def compute_atr(bars: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    high, low, close = bars["high"], bars["low"], bars["close"]
    prev_c = close.shift(1)
    tr = pd.concat([high - low,
                    (high - prev_c).abs(),
                    (low - prev_c).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def simulate_trade(
    bars: pd.DataFrame,
    entry_idx: int,
    stop_mult: float,
    atr_series: pd.Series,
) -> tuple[str, float] | None:
    """Returns (outcome, realized_r) for a BOTTOM trade."""
    if entry_idx + 1 >= len(bars):
        return None
    entry = float(bars["close"].iloc[entry_idx])
    atr_val = float(atr_series.iloc[entry_idx])
    if atr_val <= 0 or not np.isfinite(atr_val):
        return None
    risk_r = stop_mult * atr_val
    stop_level = entry - risk_r
    tp1_level = entry + risk_r
    tp2_level = entry + 2 * risk_r

    reached_tp1 = False
    bars_to_tp1: int | None = None

    for offset in range(1, MAX_HOLD + 1):
        idx = entry_idx + offset
        if idx >= len(bars):
            break
        lo = float(bars["low"].iloc[idx])
        hi = float(bars["high"].iloc[idx])
        cl = float(bars["close"].iloc[idx])

        if not reached_tp1:
            if lo <= stop_level:
                return "full_stop", -1.0
            if hi >= tp1_level:
                reached_tp1 = True
                bars_to_tp1 = offset
                if hi >= tp2_level:
                    return "tp1_tp2", 1.5
        else:
            if lo <= stop_level:
                return "tp1_stop", 0.0
            if hi >= tp2_level:
                return "tp1_tp2", 1.5
            if offset == MAX_HOLD:
                mark = (cl - entry) / risk_r
                realized = 0.5 * 1.0 + 0.5 * float(np.clip(mark, -3.0, 3.0))
                return "tp1_max", realized

    idx_final = min(entry_idx + MAX_HOLD, len(bars) - 1)
    cl_final = float(bars["close"].iloc[idx_final])
    mark = float(np.clip((cl_final - entry) / risk_r, -3.0, 3.0))
    # TP1 banked but ran to the hold boundary → credit +0.5R partial exit (shared boundary bug).
    if reached_tp1:
        return "tp1_max", 0.5 + 0.5 * mark
    return "max_hold", mark


def get_h_trend(ts: pd.Timestamp, h_bars: pd.DataFrame, h_dif: pd.Series) -> str | None:
    """Get higher-TF DIF trend side at or before ts."""
    mask = h_bars["timestamp"] <= ts
    if not mask.any():
        return None
    idx = mask.values.nonzero()[0][-1]
    val = float(h_dif.iloc[idx])
    if val > 0:
        return "bullish"
    elif val < 0:
        return "bearish"
    return "transition"


def detect_dif_crossings(
    bars: pd.DataFrame,
    dif: pd.Series,
    dea: pd.Series,
    h_bars: pd.DataFrame | None,
    h_dif: pd.Series | None,
    min_bar: int = 30,
) -> list[int]:
    """Return bar indices where DIF just crossed below zero with DEA>0 + h=opposing."""
    signals = []
    for i in range(1, len(bars)):
        if i < min_bar:
            continue
        if dif.iloc[i] < 0 and dif.iloc[i - 1] >= 0:  # DIF just crossed below zero
            if float(dea.iloc[i]) > 0:  # DEA still positive
                # h=opposing: we expect price to go UP (bottom signal), so h must be bearish
                if h_bars is not None and h_dif is not None:
                    ts = bars["timestamp"].iloc[i]
                    h_trend = get_h_trend(ts, h_bars, h_dif)
                    if h_trend != "bearish":
                        continue
                signals.append(i)
    return signals


def dedup_signals(signals: list[int], min_gap: int = 10) -> list[int]:
    """Remove signals too close to a prior signal."""
    if not signals:
        return []
    result = [signals[0]]
    for s in signals[1:]:
        if s - result[-1] >= min_gap:
            result.append(s)
    return result


def walk_forward_split(timestamps: pd.Series, cutoff_date: str) -> tuple[list[bool], list[bool]]:
    cutoff = pd.Timestamp(cutoff_date, tz="UTC")
    is_mask = timestamps <= cutoff
    oos_mask = timestamps > cutoff
    return is_mask.tolist(), oos_mask.tolist()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", default="CN_COMMODITY")
    parser.add_argument("--stop-mult", type=float, default=1.5)
    parser.add_argument("--min-gap", type=int, default=10,
                        help="Min bars between signals on same symbol")
    parser.add_argument("--bars-dir", type=Path, default=DEFAULT_BARS_DIR)
    # Walk-forward cutoffs (K=2 for now, can extend)
    parser.add_argument("--cutoff1", default="2022-12-31")
    parser.add_argument("--cutoff2", default="2024-06-30")
    args = parser.parse_args()

    symbols = POOLS.get(args.pool, [])
    if not symbols:
        print(f"Unknown pool: {args.pool}")
        return

    all_trades: list[dict] = []

    for sym in symbols:
        bars = load_bars(sym, args.bars_dir)
        if bars is None:
            print(f"  SKIP {sym}: no daily bars")
            continue

        h_bars = load_bars_60min(sym, args.bars_dir)
        macd_d = macd(bars["close"], hist_scale=1.0)
        dif_d = macd_d["dif"]
        dea_d = macd_d["dea"]
        atr_d = compute_atr(bars)

        h_macd = None
        h_dif_s = None
        if h_bars is not None:
            h_macd = macd(h_bars["close"], hist_scale=1.0)
            h_dif_s = h_macd["dif"]

        # Detect DIF crossings
        raw_sigs = detect_dif_crossings(bars, dif_d, dea_d, h_bars, h_dif_s)
        sigs = dedup_signals(raw_sigs, args.min_gap)

        for bar_idx in sigs:
            trade = simulate_trade(bars, bar_idx, args.stop_mult, atr_d)
            if trade is None:
                continue
            outcome, r = trade
            ts = bars["timestamp"].iloc[bar_idx]
            all_trades.append({
                "symbol": sym,
                "bar_idx": bar_idx,
                "timestamp": ts,
                "dif_at_cross": float(dif_d.iloc[bar_idx]),
                "dea_at_cross": float(dea_d.iloc[bar_idx]),
                "outcome": outcome,
                "r": r,
            })

    if not all_trades:
        print("No signals found.")
        return

    df = pd.DataFrame(all_trades)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    print(f"\nPool: {args.pool} | stop_mult={args.stop_mult} | min_gap={args.min_gap}")
    print("=" * 60)

    def report(label: str, subset: pd.DataFrame):
        if len(subset) == 0:
            print(f"  {label}: n=0")
            return
        ev = subset["r"].mean()
        hit = (subset["r"] > 0).mean()
        outcomes = subset["outcome"].value_counts().to_dict()
        print(f"  {label}: n={len(subset)}, EV={ev:.3f}R, hit={hit:.0%} | {outcomes}")

    # IS = before cutoff1 and OOS = after
    is_mask = df["timestamp"] <= pd.Timestamp(args.cutoff1, tz="UTC")
    oos1_mask = (df["timestamp"] > pd.Timestamp(args.cutoff1, tz="UTC")) & \
                (df["timestamp"] <= pd.Timestamp(args.cutoff2, tz="UTC"))
    oos2_mask = df["timestamp"] > pd.Timestamp(args.cutoff2, tz="UTC")

    print(f"\nIS (≤ {args.cutoff1}):")
    report("All", df[is_mask])

    print(f"\nFold1 OOS ({args.cutoff1} → {args.cutoff2}):")
    report("All", df[oos1_mask])

    print(f"\nFold2 OOS (> {args.cutoff2}):")
    report("All", df[oos2_mask])

    print("\nFull history:")
    report("All", df)

    print("\nBy year:")
    df["year"] = df["timestamp"].dt.year
    for yr, grp in df.groupby("year"):
        ev = grp["r"].mean()
        hit = (grp["r"] > 0).mean()
        print(f"  {yr}: n={len(grp)}, EV={ev:.3f}R, hit={hit:.0%}")

    print("\nBy symbol:")
    for sym, grp in df.groupby("symbol"):
        ev = grp["r"].mean()
        hit = (grp["r"] > 0).mean()
        print(f"  {sym}: n={len(grp)}, EV={ev:.3f}R, hit={hit:.0%}")

    out_path = Path(f"/tmp/dif_crossing_backtest_{args.pool.lower()}.csv")
    df.to_csv(out_path, index=False)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
