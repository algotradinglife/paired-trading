"""Missed-swing multi-TF MACD state diagnostic.

For each historical swing that the MACD divergence detector MISSED
(labeled by swing_labeler but no matching divergence fired within
`lookback` bars before the head), snapshot the multi-TF MACD state
at the head bar. Aggregating these tells us WHERE the detector's
blind spots concentrate — which guides what new detector type to
add next.

Output:
  Per-missed-swing CSV with state columns:
    symbol, head_idx, head_timestamp, direction, magnitude_pct,
    duration_bars,
    d_dif, d_dea, d_hist, d_trend_side, d_cycle_state,
    d_segment_dir, d_heap_sign,
    h_trend_side, h_dif_sign, h_cycle_state, h_segment_dir,
    l_trend_side, l_dif_sign, l_cycle_state, l_segment_dir
  Where d_/h_/l_ = daily / higher / lower TF state.

  Plus printed aggregates:
    - count by (d_trend_side, h_trend_side, l_trend_side)
    - count by d_cycle_state (was bar in mid-cycle? near zero?)
    - count by d_segment_dir (was bar in trending segment?)

Caveat: multi-TF state lookup uses `<= head_timestamp` slicing on
foreign bars, same as engine's `enrich_with_*_tf`. The bar-timestamp
session leak documented in feedback_multi_tf_sweet_spot_timing_pitfall
applies here too. For DIAGNOSTIC purpose (characterizing where misses
concentrate) this is acceptable. Do NOT use these state distributions
as direct production rule criteria — fix timing infra first.

Usage:
  uv run python scripts/missed_swing_state.py --pool US --threshold 5
  uv run python scripts/missed_swing_state.py --pool CN --threshold 8 \\
      --instrument-class cn_futures -o missed.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from engine.divergence.detector import detect_all_divergences
from engine.features.macd import macd
from engine.features.streams import compute_feature_streams
from engine.fusion.level_state import compute_level_state
from engine.labels.swing_labeler import label_swings
from engine.units.snapshot import compute_unit_metadata

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
DEFAULT_LOOKBACK_BARS = 10

POOLS: dict[str, list[str]] = {
    "US": ["SPY", "QQQ", "IWM", "DIA", "GLD", "GDX", "XLF", "XLK", "TLT", "NVDA"],
    "CN": ["kq_m_cffex_if", "kq_m_cffex_ih", "kq_m_cffex_ic", "kq_m_cffex_im"],
    "CN_COMMODITY": [
        "kq_m_shfe_rb", "kq_m_shfe_cu", "kq_m_shfe_au", "kq_m_shfe_ag",
        "kq_m_dce_m", "kq_m_dce_i", "kq_m_dce_j", "kq_m_dce_jm",
        "kq_m_dce_p", "kq_m_dce_y",
        "kq_m_czce_ta", "kq_m_czce_ma", "kq_m_czce_cf", "kq_m_czce_sr",
        "kq_m_ine_sc",
    ],
}

POOL_INSTRUMENT_CLASS: dict[str, str] = {
    "US": "us_equity",
    "CN": "cn_index_futures",
    "CN_COMMODITY": "cn_futures",
}

# Foreign-TF filename suffixes per topology. The higher loop tries weekly
# first (topology A); falls back to 60 (topology B). The lower loop tries
# 60 (topology A's lower); falls back to 15 (topology B's lower). To avoid
# picking the same file for both sides (CN futures have no weekly, so
# higher=60; if lower also takes 60 the two TFs are identical), the
# lower loop EXCLUDES whatever suffix the higher loop took.
HIGHER_TF_FILES = {"weekly": "W", "60": "1h"}
LOWER_TF_FILES = {"60": "1h", "15": "15m"}


def load_bars(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text())
    df = pd.DataFrame(payload["bars"])
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


def detect_engine_signals(bars: pd.DataFrame, instrument_class: str):
    macd_df = macd(bars["close"], hist_scale=1.0)
    streams = compute_feature_streams(bars["close"], macd_df["dif"], macd_df["dea"], macd_df["hist"])
    units = compute_unit_metadata(macd_df["dif"], macd_df["dea"], macd_df["hist"], streams["dif_proximity_zero"])
    return detect_all_divergences(
        units_df=units, ohlc=bars, dif=macd_df["dif"], hist=macd_df["hist"],
        level_id="D", instrument_class=instrument_class,
    )


def _dif_sign(dif: float, tol: float = 1e-6) -> str:
    if dif > tol:
        return "pos"
    if dif < -tol:
        return "neg"
    return "zero"


def foreign_state_at(foreign_bars: pd.DataFrame, head_ts: pd.Timestamp,
                      level_id: str) -> dict | None:
    """Snapshot foreign-TF state from bars <= head_ts. Returns None if
    not enough bars or no coverage at head_ts."""
    if foreign_bars is None or foreign_bars.empty:
        return None
    sub = foreign_bars[foreign_bars["timestamp"] <= head_ts]
    if len(sub) < 60:
        return None
    try:
        state = compute_level_state(level_id, sub.reset_index(drop=True))
    except (ValueError, KeyError, IndexError):
        return None
    return {
        "trend_side": state.trend_side,
        "dif_sign": _dif_sign(state.dif),
        "cycle_state": state.cycle_state,
        "segment_dir": state.segment_direction,
        "dif": state.dif,
        "dea": state.dea,
        "hist": state.hist,
    }


def daily_state_at(bars: pd.DataFrame, idx: int) -> dict | None:
    """Compute daily state up to bar `idx` (inclusive)."""
    if idx < 60:
        return None
    sub = bars.iloc[:idx + 1].reset_index(drop=True)
    try:
        state = compute_level_state("D", sub)
    except (ValueError, KeyError, IndexError):
        return None
    return {
        "d_dif": state.dif,
        "d_dea": state.dea,
        "d_hist": state.hist,
        "d_dif_sign": _dif_sign(state.dif),
        "d_trend_side": state.trend_side,
        "d_cycle_state": state.cycle_state,
        "d_segment_dir": state.segment_direction,
        "d_heap_sign": state.heap_sign,
    }


def find_missed_swings(bars: pd.DataFrame, instrument_class: str,
                        threshold_pct: float, lookback: int,
                        min_duration: int) -> list[dict]:
    """Label swings, find which ones were missed by the divergence detector."""
    swings = label_swings(bars, reversal_pct=threshold_pct,
                          min_duration_bars=min_duration)
    signals = detect_engine_signals(bars, instrument_class)
    sig_index = {(sig.direction, sig.candidate_bar_idx): sig for sig in signals}

    missed = []
    for sw in swings:
        matching_div = "bottom" if sw.direction == "up" else "top"
        captured = False
        for offset in range(-lookback, 1):
            idx = sw.head_idx + offset
            if idx < 0:
                continue
            if (matching_div, idx) in sig_index:
                captured = True
                break
        if not captured:
            missed.append({
                "head_idx": sw.head_idx,
                "head_timestamp": bars["timestamp"].iloc[sw.head_idx],
                "tail_idx": sw.tail_idx,
                "tail_timestamp": bars["timestamp"].iloc[sw.tail_idx],
                "direction": sw.direction,
                "magnitude_pct": sw.magnitude_pct,
                "duration_bars": sw.duration_bars,
            })
    return missed


def main() -> int:
    p = argparse.ArgumentParser()
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--pool", choices=sorted(POOLS))
    grp.add_argument("--symbols", nargs="+")
    p.add_argument("--instrument-class", choices=["us_equity", "cn_futures", "cn_index_futures", "czce", "cn_metal_futures"],
                   default=None, dest="instrument_class")
    p.add_argument("--bars-dir", type=Path, default=DEFAULT_BARS_DIR)
    p.add_argument("--threshold", type=float, default=5.0,
                   help="swing magnitude threshold in pct (default 5)")
    p.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK_BARS)
    p.add_argument("--min-duration", type=int, default=1)
    p.add_argument("-o", "--output", type=Path, help="per-missed-swing CSV")
    args = p.parse_args()

    symbols = POOLS[args.pool] if args.pool else args.symbols
    if args.instrument_class is not None:
        instrument_class = args.instrument_class
    elif args.pool:
        instrument_class = POOL_INSTRUMENT_CLASS[args.pool]
    else:
        instrument_class = "us_equity"

    print(f"Pool: {args.pool or 'custom'} ({len(symbols)} symbols, class={instrument_class})")
    print(f"Swing threshold: {args.threshold}%   Lookback: {args.lookback} bars")
    print()

    rows = []
    for sym in symbols:
        daily_path = args.bars_dir / f"{sym.lower()}_daily.json"
        if not daily_path.exists():
            print(f"  {sym}: missing daily snapshot, skipped", file=sys.stderr)
            continue
        bars = load_bars(daily_path)

        # Load best-available foreign TFs (one higher, one lower) for the diagnostic.
        higher_bars = None
        higher_level_id = None
        higher_suffix = None
        for suffix, lvl in HIGHER_TF_FILES.items():
            p_ = args.bars_dir / f"{sym.lower()}_{suffix}.json"
            if p_.exists():
                higher_bars = load_bars(p_)
                higher_level_id = lvl
                higher_suffix = suffix
                break
        lower_bars = None
        lower_level_id = None
        for suffix, lvl in LOWER_TF_FILES.items():
            if suffix == higher_suffix:  # don't reuse the higher-TF file as lower
                continue
            p_ = args.bars_dir / f"{sym.lower()}_{suffix}.json"
            if p_.exists():
                lower_bars = load_bars(p_)
                lower_level_id = lvl
                break

        missed = find_missed_swings(bars, instrument_class,
                                     args.threshold, args.lookback,
                                     args.min_duration)
        for m in missed:
            row = {
                "symbol": sym,
                **m,
            }
            d_state = daily_state_at(bars, m["head_idx"])
            if d_state:
                row.update(d_state)
            else:
                row.update({k: None for k in ["d_dif", "d_dea", "d_hist", "d_dif_sign",
                                                "d_trend_side", "d_cycle_state",
                                                "d_segment_dir", "d_heap_sign"]})
            if higher_bars is not None:
                h_state = foreign_state_at(higher_bars, m["head_timestamp"],
                                           higher_level_id or "higher")
                if h_state:
                    row.update({f"h_{k}": v for k, v in h_state.items()})
                    row["higher_tf_level"] = higher_level_id
            if lower_bars is not None:
                l_state = foreign_state_at(lower_bars, m["head_timestamp"],
                                           lower_level_id or "lower")
                if l_state:
                    row.update({f"l_{k}": v for k, v in l_state.items()})
                    row["lower_tf_level"] = lower_level_id
            rows.append(row)
        print(f"  {sym}: {len(missed)} missed swings (of all labeled at threshold {args.threshold}%)")

    if not rows:
        print("\nNo missed swings collected.", file=sys.stderr)
        return 0
    df = pd.DataFrame(rows)
    print(f"\nTotal missed swings: {len(df)}")
    print(f"  by direction: {df['direction'].value_counts().to_dict()}")

    # Aggregate: histogram of multi-TF state configurations
    print("\n=== Missed-swing distribution by daily MACD state ===")
    for col in ["d_trend_side", "d_cycle_state", "d_segment_dir", "d_dif_sign"]:
        if col not in df.columns:
            continue
        print(f"\n  by {col}:")
        for direction in ["up", "down"]:
            sub = df[df["direction"] == direction]
            if sub.empty:
                continue
            vc = sub[col].value_counts(dropna=False).to_dict()
            total = sum(vc.values())
            parts = [f"{k}={v} ({v/total*100:.0f}%)" for k, v in vc.items()]
            print(f"    {direction:>6}: {' | '.join(parts)}")

    if "h_trend_side" in df.columns:
        print("\n=== Higher-TF trend at missed-swing head ===")
        for direction in ["up", "down"]:
            sub = df[df["direction"] == direction]
            if sub.empty or "h_trend_side" not in sub.columns:
                continue
            vc = sub["h_trend_side"].value_counts(dropna=False).to_dict()
            total = sum(vc.values())
            parts = [f"{k}={v} ({v/total*100:.0f}%)" for k, v in vc.items()]
            print(f"  {direction:>6}: {' | '.join(parts)}")

    if "l_trend_side" in df.columns:
        print("\n=== Lower-TF trend at missed-swing head ===")
        for direction in ["up", "down"]:
            sub = df[df["direction"] == direction]
            if sub.empty or "l_trend_side" not in sub.columns:
                continue
            vc = sub["l_trend_side"].value_counts(dropna=False).to_dict()
            total = sum(vc.values())
            parts = [f"{k}={v} ({v/total*100:.0f}%)" for k, v in vc.items()]
            print(f"  {direction:>6}: {' | '.join(parts)}")

    # 3-way cross-tab: daily_trend × higher_trend × lower_trend
    if all(c in df.columns for c in ["d_trend_side", "h_trend_side", "l_trend_side"]):
        print("\n=== 3-TF trend configuration at missed swings ===")
        for direction in ["up", "down"]:
            sub = df[df["direction"] == direction].copy()
            if sub.empty:
                continue
            sub["combo"] = sub["d_trend_side"].astype(str) + "/" + \
                           sub["h_trend_side"].astype(str) + "/" + \
                           sub["l_trend_side"].astype(str)
            vc = sub["combo"].value_counts().head(10).to_dict()
            total = len(sub)
            print(f"\n  {direction} (top 10 configs of {total} missed swings):")
            for combo, n in vc.items():
                print(f"    {combo:<35} n={n}  ({n/total*100:.0f}%)")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.output, index=False)
        print(f"\nPer-swing CSV → {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
