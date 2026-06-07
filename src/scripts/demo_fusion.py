"""Demo: end-to-end multi-timeframe fusion on SPY 60min / D / W.

Loads the three saved snapshots, runs each through the full pipeline, then
propagates confidence bidirectionally and prints the synthesized cross-level
view — the "simple clear conclusion" the project produces for downstream
trading systems to consume.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from data import bar_loader
from engine.fusion.snapshot import run_fusion, to_schema
from engine.fusion.topology import topology_for_us_stock

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


# Map snapshot filename → level_id used by topology
SNAPSHOTS = {
    "spy_60.json": "1h",
    "spy_daily.json": "D",
}

# Quant mode: (barstore_level, engine_level_id) pairs for fusion topology
_QUANT_LEVELS = [("D", "D"), ("60min", "1h")]


def main(symbol: str = "SPY", exchange: str = "XNYS",
         quant_root: Path | None = None) -> int:
    bars_per_level: dict[str, pd.DataFrame] = {}

    if quant_root is not None:
        for barstore_level, engine_level in _QUANT_LEVELS:
            try:
                df = bar_loader.load_bars_quant(symbol, exchange, barstore_level, quant_root)
                bars_per_level[engine_level] = df
            except Exception as e:
                print(f"quant load {symbol}/{barstore_level}: {e}", file=sys.stderr)
    else:
        for fname, level_id in SNAPSHOTS.items():
            path = DATA_DIR / "raw" / fname
            if not path.exists():
                print(f"Skip — missing snapshot: {path.name}", file=sys.stderr)
                continue
            bars_per_level[level_id] = bar_loader.load_bars_json(path)

    if not bars_per_level:
        print("No snapshots loaded.", file=sys.stderr)
        return 2

    topology = topology_for_us_stock()
    print(f"Loaded {len(bars_per_level)} timeframes: {list(bars_per_level)}")

    states, fused, summary = run_fusion(bars_per_level, topology)

    # Per-level snapshot
    print("\n=== Per-level snapshots ===")
    print(f"{'level':<6} {'time':<26} {'side':<11} {'close':<10} {'DIF':<10} {'Hist':<10} {'cycle_state':<14} {'seg_dir':<8}")
    print("-" * 110)
    for level_id, state in states.items():
        ts = state.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"{level_id:<6} {ts:<26} {state.trend_side:<11} {state.close:<10.2f} "
            f"{state.dif:<+10.3f} {state.hist:<+10.3f} {state.cycle_state:<14} {state.segment_direction:<8}"
        )

    # Form confidences (local vs fused)
    print("\n=== Form confidences: local → fused ===")
    forms = [
        "high_position",
        "high_position_void",
        "hidden",
        "zero_stick",
        "zero_inverted",
        "near_zero_axis",
    ]
    print(f"{'level':<6}", end="")
    for f in forms:
        print(f" {f[:18]:>20}", end="")
    print()
    print("-" * 130)
    for level_id, fls in fused.items():
        print(f"{level_id:<6}", end="")
        for f in forms:
            local = fls.form_confidences_local[f]
            fused_v = fls.form_confidences_fused[f]
            arrow = "↑" if fused_v > local + 0.01 else ("↓" if fused_v < local - 0.01 else "·")
            cell = f"{local:.3f}{arrow}{fused_v:.3f}"
            print(f" {cell:>20}", end="")
        print()

    # Most-recent / strongest divergence per level
    print("\n=== Divergence signals per level ===")
    for level_id, state in states.items():
        if state.strongest_divergence:
            sig = state.strongest_divergence
            ts = sig.timestamp.strftime("%Y-%m-%d")
            print(
                f"  {level_id:<5}  strongest: {ts} {sig.level} {sig.subtype} "
                f"{sig.direction} conf={sig.confidence:.2f}"
            )
        else:
            print(f"  {level_id:<5}  no divergence detected")

    # Cross-level summary
    print("\n=== Cross-level synthesis ===")
    print(f"alignment_strength:  {summary.alignment_strength:.2f}")
    print(f"dominant_trend:      {summary.dominant_trend}")
    print(f"primary_label:       {summary.primary_label}")
    print(f"primary_confidence:  {summary.primary_confidence:.3f}")
    if summary.secondary_labels:
        print("secondary_labels:")
        for label, conf in summary.secondary_labels[:6]:
            bar = "█" * int(conf * 20)
            print(f"  {conf:.3f}  {bar} {label}")

    # Schema serialization
    print("\n=== Output schema (MultiTimeframeFusion, JSON snippet) ===")
    sched = to_schema(states, fused, summary, system_ts=datetime.now(timezone.utc))
    j = sched.model_dump_json(indent=2)
    # Truncate for display
    lines = j.split("\n")
    print("\n".join(lines[:25]))
    if len(lines) > 25:
        print(f"... ({len(lines) - 25} more lines)")

    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="SPY", help="symbol for quant mode (default: SPY)")
    ap.add_argument("--exchange", default="XNYS", help="MIC exchange for quant mode (default: XNYS)")
    ap.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
                    help="quant-data Parquet root (default: data/quant/)")
    a = ap.parse_args()
    sys.exit(main(a.symbol, a.exchange, a.quant_data_root))
