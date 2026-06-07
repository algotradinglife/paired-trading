"""Demo: run divergence detector on a saved SPY snapshot and list signals.

Output:
    - Counts of heap / cycle / segment events
    - All detected divergence signals (sorted by bar index)
    - Top 10 highest-confidence signals
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from data import bar_loader
from engine.divergence.detector import detect_all_divergences
from engine.features.macd import macd
from engine.features.streams import compute_feature_streams
from engine.units.snapshot import compute_unit_metadata

DATA_DIR = Path(__file__).resolve().parents[1] / "data"



def _load(snapshot_name: str, quant_root: Path | None) -> tuple[pd.DataFrame, dict] | None:
    if quant_root is not None:
        parsed = bar_loader.parse_snapshot_name(snapshot_name)
        if parsed is not None:
            sym, mic, level = parsed
            try:
                return bar_loader.load_snapshot_quant(sym, mic, level, quant_root)
            except Exception as e:
                print(f"quant load {snapshot_name}: {e} — falling back to JSON", file=sys.stderr)
    path = DATA_DIR / "raw" / snapshot_name
    if not path.exists():
        return None
    return bar_loader.load_snapshot_json(path)


def main(snapshot_name: str = "spy_daily.json", quant_root: Path | None = None) -> int:
    result = _load(snapshot_name, quant_root)
    if result is None:
        print(f"Snapshot not found: {DATA_DIR / 'raw' / snapshot_name}", file=sys.stderr)
        return 2

    df, payload = result
    sym = payload.get("symbol", "?")
    res = payload.get("resolution", "?")
    print(f"Loaded {len(df)} bars of {sym} @ {res}")
    if df.empty:
        print("  No bars in snapshot — exiting.")
        return 1
    print(f"Range: {df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]}")

    # Indicators
    macd_df = macd(df["close"], hist_scale=1.0)

    # Streams + units
    streams = compute_feature_streams(df["close"], macd_df["dif"], macd_df["dea"], macd_df["hist"])
    units = compute_unit_metadata(
        macd_df["dif"], macd_df["dea"], macd_df["hist"], streams["dif_proximity_zero"]
    )

    # Detect divergences
    signals = detect_all_divergences(
        units_df=units,
        ohlc=df,
        dif=macd_df["dif"],
        hist=macd_df["hist"],
        level_id=res,
    )

    # Aggregate counts
    n_heaps = int(units["heap_id"].max() + 1) if (units["heap_id"] >= 0).any() else 0
    n_cycles = int(units["cycle_id"].max() + 1) if (units["cycle_id"] >= 0).any() else 0
    n_segments = int(units["segment_id"].max() + 1) if (units["segment_id"] >= 0).any() else 0

    print(f"\nContainers detected: {n_heaps} heaps, {n_cycles} cycles, {n_segments} segments")
    print(f"Total divergence signals: {len(signals)}")

    if not signals:
        print("\nNo divergence signals detected.")
        return 0

    # Counts by level + subtype
    print("\n=== Signal breakdown ===")
    by_level: dict[str, int] = {}
    by_subtype: dict[str, int] = {}
    for s in signals:
        by_level[s.level] = by_level.get(s.level, 0) + 1
        by_subtype[s.subtype] = by_subtype.get(s.subtype, 0) + 1
    print("By level:")
    for k, v in sorted(by_level.items()):
        print(f"  {k:<16} {v}")
    print("By subtype:")
    for k, v in sorted(by_subtype.items()):
        print(f"  {k:<16} {v}")

    # Top by confidence
    top = sorted(signals, key=lambda s: -s.confidence)[:15]
    print("\n=== Top 15 signals by confidence ===")
    print(f"{'timestamp':<26} {'level':<14} {'subtype':<10} {'dir':<6} {'conf':<6} {'decay':<6} {'ref→cand price':<22} {'ref→cand amp':<22}")
    print("-" * 130)
    for s in top:
        ts = s.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        price_str = f"{s.price_side.reference_value:.2f}→{s.price_side.candidate_value:.2f}"
        amp_str = f"{s.amplitude_side.reference_value:.3f}→{s.amplitude_side.candidate_value:.3f}"
        print(
            f"{ts:<26} {s.level:<14} {s.subtype:<10} {s.direction:<6} "
            f"{s.confidence:<6.3f} {s.amplitude_side.decay_ratio:<6.2f} "
            f"{price_str:<22} {amp_str:<22}"
        )

    # Most recent signals
    print("\n=== Most recent 10 signals (any confidence) ===")
    recent = sorted(signals, key=lambda s: -s.candidate_bar_idx)[:10]
    print(f"{'timestamp':<26} {'level':<14} {'subtype':<10} {'dir':<6} {'conf':<6}")
    print("-" * 70)
    for s in recent:
        ts = s.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        print(f"{ts:<26} {s.level:<14} {s.subtype:<10} {s.direction:<6} {s.confidence:<6.3f}")

    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot", nargs="?", default="spy_daily.json")
    ap.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
                    help="quant-data Parquet root (default: data/quant/)")
    a = ap.parse_args()
    sys.exit(main(a.snapshot, a.quant_data_root))
