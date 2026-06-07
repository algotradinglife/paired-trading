"""Export divergence signals from a snapshot as TV-drawable markers.

Outputs one line of JSON per high-confidence signal with the fields the agent
needs to issue MCP `draw_shape` calls:

    {
      "unix_time": 1759930200,
      "price": 673.21,
      "label": "STD ↓",
      "color": "#ff3333",
      "subtype": "standard",
      "direction": "top",
      "confidence": 0.93,
      "level": "intra_cycle",
      "date_str": "2025-10-08"
    }

Use:  uv run python scripts/export_signals_for_tv.py [snapshot_name] [min_conf]
"""

from __future__ import annotations

import json
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


# Color by direction
COLOR_TOP = "#ff3333"      # red — top warning
COLOR_BOTTOM = "#22aa22"    # green — bottom warning

# Y-offset (price) from the candidate's price extreme so labels don't overlap bar
TOP_OFFSET_PCT = 0.012   # 1.2% above top
BOTTOM_OFFSET_PCT = 0.012  # 1.2% below bottom


def subtype_label(subtype: str) -> str:
    return {
        "standard": "STD",
        "weakness": "WK",
        "hidden": "HID",
    }.get(subtype, subtype[:3].upper())


def level_label(level: str) -> str:
    return {
        "intra_cycle": "C",
        "inter_cycle": "CC",
        "inter_segment": "SEG",
    }.get(level, level[:2].upper())


def main(snapshot_name: str = "spy_daily.json", min_conf: float = 0.6,
         quant_root: Path | None = None) -> int:
    # Load bars: prefer quant-data if root given and snapshot name is parseable
    bars: pd.DataFrame | None = None
    level_id = "?"
    if quant_root is not None:
        parsed = bar_loader.parse_snapshot_name(snapshot_name)
        if parsed is not None:
            sym, mic, barstore_level = parsed
            try:
                bars = bar_loader.load_bars_quant(sym, mic, barstore_level, quant_root)
                level_id = bar_loader.BARSTORE_TO_ENGINE_LEVEL.get(barstore_level, barstore_level)
            except Exception as e:
                print(f"quant load {snapshot_name}: {e} — falling back to JSON", file=sys.stderr)
    if bars is None:
        snapshot = DATA_DIR / "raw" / snapshot_name
        if not snapshot.exists():
            print(f"Snapshot not found: {snapshot}", file=sys.stderr)
            return 2
        bars, payload = bar_loader.load_snapshot_json(snapshot)
        level_id = payload.get("resolution", "?")

    close = bars["close"]
    macd_df = macd(close, hist_scale=1.0)
    streams = compute_feature_streams(close, macd_df["dif"], macd_df["dea"], macd_df["hist"])
    units = compute_unit_metadata(
        macd_df["dif"], macd_df["dea"], macd_df["hist"], streams["dif_proximity_zero"]
    )

    signals = detect_all_divergences(
        units_df=units,
        ohlc=bars,
        dif=macd_df["dif"],
        hist=macd_df["hist"],
        level_id=level_id,
    )

    # Filter by minimum confidence and sort
    filtered = [s for s in signals if s.confidence >= min_conf]
    filtered.sort(key=lambda s: -s.confidence)

    print(f"# Snapshot: {snapshot_name}")
    print(f"# Total signals: {len(signals)}  ≥{min_conf}: {len(filtered)}")

    for sig in filtered:
        bar_idx = sig.candidate_bar_idx
        bar_time = int(bars["time"].iloc[bar_idx])
        bar_high = float(bars["high"].iloc[bar_idx])
        bar_low = float(bars["low"].iloc[bar_idx])

        if sig.direction == "top":
            price = bar_high * (1 + TOP_OFFSET_PCT)
            color = COLOR_TOP
            arrow = "↓"
        else:
            price = bar_low * (1 - BOTTOM_OFFSET_PCT)
            color = COLOR_BOTTOM
            arrow = "↑"

        label = f"{level_label(sig.level)}·{subtype_label(sig.subtype)} {arrow} {sig.confidence:.2f}"

        record = {
            "unix_time": bar_time,
            "price": round(price, 2),
            "label": label,
            "color": color,
            "subtype": sig.subtype,
            "direction": sig.direction,
            "confidence": round(sig.confidence, 3),
            "level": sig.level,
            "date_str": sig.timestamp.strftime("%Y-%m-%d"),
            "bar_high": round(bar_high, 2),
            "bar_low": round(bar_low, 2),
        }
        print(json.dumps(record))

    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot", nargs="?", default="spy_daily.json")
    ap.add_argument("min_conf", nargs="?", type=float, default=0.6)
    ap.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
                    help="quant-data Parquet root (default: data/quant/)")
    a = ap.parse_args()
    sys.exit(main(a.snapshot, a.min_conf, a.quant_data_root))
