"""Demo: full pipeline on a saved SPY snapshot.

Pipeline:
    OHLCV → MACD + EMAs → 5 base streams → 6 form confidences → 3 vector units

Output:
    - Last 10 bars table with streams, forms, and unit attribution
    - Latest bar confidence bars + unit/cycle/segment summary
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from data import bar_loader
from engine.features.macd import macd, overlay_emas
from engine.features.streams import compute_feature_streams
from engine.forms.detectors import compute_form_confidences
from engine.units.snapshot import compute_unit_metadata

DATA_DIR = Path(__file__).resolve().parents[1] / "data"



def _load(snapshot_name: str, quant_root: Path | None) -> tuple[pd.DataFrame, dict] | None:
    """Load snapshot from BarStore if supported, otherwise from JSON."""
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
    print(f"Loaded {len(df)} bars of {payload.get('symbol')} @ {payload.get('resolution')}")
    if df.empty:
        print("  No bars in snapshot — exiting.")
        return 1
    print(f"Range: {df['timestamp'].iloc[0]}  ->  {df['timestamp'].iloc[-1]}")

    # Indicators
    macd_df = macd(df["close"], hist_scale=1.0)
    ema_df = overlay_emas(df["close"])

    # Streams
    streams = compute_feature_streams(
        close=df["close"],
        dif=macd_df["dif"],
        dea=macd_df["dea"],
        hist=macd_df["hist"],
    )

    # Forms
    forms = compute_form_confidences(streams, df["close"], ema_df["ema52"])

    # Units
    units = compute_unit_metadata(
        dif=macd_df["dif"],
        dea=macd_df["dea"],
        hist=macd_df["hist"],
        dif_proximity_zero=streams["dif_proximity_zero"],
    )

    # Last 10 bars view
    last = pd.concat(
        [
            df[["timestamp", "close"]].tail(10).reset_index(drop=True),
            macd_df[["dif", "dea", "hist"]].tail(10).reset_index(drop=True),
            forms[["high_position_void", "hidden", "hidden_subtype", "zero_inverted"]].tail(10).reset_index(drop=True),
            units[
                [
                    "heap_id",
                    "heap_sign",
                    "heap_peak_so_far",
                    "is_continuous_gap_heap",
                    "cycle_id",
                    "cycle_state",
                    "cycle_peak_dif_so_far",
                    "cycle_reference_heap_id",
                    "segment_id",
                    "segment_direction",
                ]
            ].tail(10).reset_index(drop=True),
        ],
        axis=1,
    )

    pd.set_option("display.width", 280)
    pd.set_option("display.max_columns", 30)
    pd.set_option("display.float_format", lambda x: f"{x:.3f}")

    print("\nLast 10 bars — indicators + key forms + units:\n")
    print(last.to_string(index=False))

    # Aggregate counts so far
    print("\n=== Pipeline counts over full series ===")
    n_heaps = (units["heap_id"].max() + 1) if (units["heap_id"] >= 0).any() else 0
    n_cycles = (units["cycle_id"].max() + 1) if (units["cycle_id"] >= 0).any() else 0
    n_segments = (units["segment_id"].max() + 1) if (units["segment_id"] >= 0).any() else 0
    print(f"  total bars:    {len(df)}")
    print(f"  total heaps:   {n_heaps}")
    print(f"  total cycles:  {n_cycles}")
    print(f"  total segments:{n_segments}")
    print(f"  continuous-gap heaps: {(units.groupby('heap_id')['is_continuous_gap_heap'].any().sum() - (1 if -1 in units['heap_id'].values else 0)):.0f}")

    # Latest bar deep dive
    last_row = last.iloc[-1]
    print("\n=== Latest bar status ===")
    print(f"timestamp                 {last_row['timestamp']}")
    print(f"close = {last_row['close']:.2f}  DIF = {last_row['dif']:+.3f}  Hist = {last_row['hist']:+.3f}")
    print()
    print("Unit attribution:")
    print(f"  heap_id={int(last_row['heap_id'])}  sign={int(last_row['heap_sign']):+d}  peak={last_row['heap_peak_so_far']:.3f}  gap={bool(last_row['is_continuous_gap_heap'])}")
    print(f"  cycle_id={int(last_row['cycle_id'])}  state={last_row['cycle_state']}  peak_dif={last_row['cycle_peak_dif_so_far']:.3f}  ref_heap={int(last_row['cycle_reference_heap_id'])}")
    print(f"  segment_id={int(last_row['segment_id'])}  direction={last_row['segment_direction']}")
    print()
    print("Active form confidences:")
    for col in ["high_position_void", "hidden", "zero_inverted"]:
        v = last_row[col]
        bar = "█" * int(v * 20)
        print(f"  {col:<22} {v:.3f}  {bar}")
    print(f"  hidden_subtype: {last_row['hidden_subtype']}")

    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot", nargs="?", default="spy_daily.json")
    ap.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
                    help="quant-data Parquet root (default: data/quant/)")
    a = ap.parse_args()
    sys.exit(main(a.snapshot, a.quant_data_root))
