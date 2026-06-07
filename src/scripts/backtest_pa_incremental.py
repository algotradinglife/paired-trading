"""Incremental recall: how much do Context A/B1 ADD on top of existing detectors?

For each 5%+ up swing (ZigZag ground truth):
  - existing: covered by any DivergenceSignal (heap/HICD/DIFSR/BPull/etc.)
  - pa: covered by Context A or B1 window
  - both / none

Reports: existing baseline recall, PA incremental gain, and combined recall.
Answers whether PA context is finding genuinely NEW swings or just overlapping.

Usage:
  uv run python scripts/backtest_pa_incremental.py
  uv run python scripts/backtest_pa_incremental.py --pool CN_METAL
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
from engine.divergence.detector import detect_all_divergences
from engine.divergence.multi_tf_context import enrich_with_higher_tf
from engine.divergence.pa_context_classifier import classify_context
from engine.features.macd import macd, ema
from engine.features.streams import compute_feature_streams
from engine.labels.swing_labeler import label_swings
from engine.units.snapshot import compute_unit_metadata

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

US_SYMBOLS       = ["spy", "qqq", "iwm", "gld", "tlt", "nvda", "dia", "gdx", "xlf", "xlk"]
CN_METAL_SYMBOLS = ["kq_m_shfe_cu", "kq_m_shfe_au", "kq_m_shfe_ag", "kq_m_ine_sc"]

POOLS: dict[str, tuple[list[str], str]] = {
    "US":       (US_SYMBOLS,        "us_equity"),
    "CN_METAL": (CN_METAL_SYMBOLS,  "cn_metal_futures"),
}

SWING_REVERSAL_PCT = 5.0
COVER_BEFORE = 10   # bars before swing head to look for signal/context
COVER_AFTER  = 5    # bars after swing head


def load_bars(sym: str, bars_dir: Path, suffix: str = "_daily") -> pd.DataFrame | None:
    return bar_loader.load_bars_quant_or_json(sym, suffix, bars_dir)


def get_existing_signal_bars(bars: pd.DataFrame, macd_df: pd.DataFrame,
                              h_bars: pd.DataFrame | None,
                              instrument_class: str) -> set[int]:
    """Return set of bar indices where any bottom DivergenceSignal fires."""
    streams = compute_feature_streams(
        bars["close"], macd_df["dif"], macd_df["dea"], macd_df["hist"]
    )
    units = compute_unit_metadata(
        macd_df["dif"], macd_df["dea"], macd_df["hist"],
        streams["dif_proximity_zero"]
    )
    signals = detect_all_divergences(
        units_df=units, ohlc=bars, dif=macd_df["dif"],
        hist=macd_df["hist"], level_id="D",
        instrument_class=instrument_class,
    )
    if h_bars is not None:
        signals = enrich_with_higher_tf(signals, bars, h_bars, higher_tf_level_id="60m")

    return {s.candidate_bar_idx for s in signals if s.direction == "bottom"}


def get_pa_context_bars(bars: pd.DataFrame, macd_df: pd.DataFrame,
                         ema20: pd.Series, ema60: pd.Series) -> set[int]:
    """Return set of deduplicated context window start indices (A or B1)."""
    raw: list[tuple[int, str]] = []
    for i in range(len(bars)):
        ctx = classify_context(bars, i, macd_df, ema20, ema60)
        if ctx is not None:
            raw.append((i, ctx))
    if not raw:
        return set()
    # Deduplicate: first bar of each continuous run
    windows = [raw[0]]
    for j in range(1, len(raw)):
        pi, pc = raw[j - 1]
        ci, cc = raw[j]
        if cc != pc or ci > pi + 1:
            windows.append(raw[j])
    return {idx for idx, _ in windows}


def _swing_head_idx(s) -> int | None:
    """Extract head_idx from swing object (object or DataFrame row)."""
    if hasattr(s, "head_idx"):
        return s.head_idx
    if isinstance(s, dict):
        return s.get("head_idx")
    return None


def _swing_direction(s) -> str:
    if hasattr(s, "direction"):
        return s.direction
    if isinstance(s, dict):
        return s.get("direction", "")
    return ""


def _swing_magnitude(s) -> float:
    if hasattr(s, "magnitude_pct"):
        return float(s.magnitude_pct)
    if isinstance(s, dict):
        return float(s.get("magnitude_pct", 0))
    return 0.0


def analyse_symbol(sym: str, bars_dir: Path, instrument_class: str) -> dict | None:
    bars = load_bars(sym, bars_dir)
    if bars is None or len(bars) < 100:
        return None
    h_bars = load_bars(sym, bars_dir, suffix="_60")

    macd_df = macd(bars["close"])
    ema20   = ema(bars["close"], 20)
    ema60   = ema(bars["close"], 60)

    existing_bars = get_existing_signal_bars(bars, macd_df, h_bars, instrument_class)
    pa_bars       = get_pa_context_bars(bars, macd_df, ema20, ema60)

    swings = label_swings(bars, reversal_pct=SWING_REVERSAL_PCT)
    # Handle both list-of-objects and DataFrame return types
    if isinstance(swings, pd.DataFrame):
        swing_list = swings.to_dict("records")
    else:
        swing_list = swings

    up_swings = [
        s for s in swing_list
        if _swing_direction(s) == "up" and _swing_magnitude(s) >= SWING_REVERSAL_PCT
    ]

    counts = {"existing_only": 0, "pa_only": 0, "both": 0, "none": 0}
    for s in up_swings:
        h = _swing_head_idx(s)
        if h is None:
            continue
        window = set(range(h - COVER_BEFORE, h + COVER_AFTER + 1))
        by_existing = bool(existing_bars & window)
        by_pa       = bool(pa_bars & window)
        if by_existing and by_pa:
            counts["both"] += 1
        elif by_existing:
            counts["existing_only"] += 1
        elif by_pa:
            counts["pa_only"] += 1
        else:
            counts["none"] += 1

    total = len(up_swings)
    return {
        "sym":    sym,
        "total":  total,
        **counts,
        "n_existing_signals": len(existing_bars),
        "n_pa_windows":       len(pa_bars),
    }


def print_report(pool: str, results: list[dict]) -> None:
    valid = [r for r in results if r is not None]
    if not valid:
        print(f"  No data for pool {pool}")
        return

    total       = sum(r["total"]         for r in valid)
    existing    = sum(r["existing_only"] + r["both"] for r in valid)
    pa_only     = sum(r["pa_only"]       for r in valid)
    both        = sum(r["both"]          for r in valid)
    covered_any = sum(r["existing_only"] + r["pa_only"] + r["both"] for r in valid)

    print(f"\n{'='*60}")
    print(f"Pool: {pool}  |  5%+ up swings: {total}")
    print(f"\n  Existing detectors:  {existing}/{total} = {existing/total*100:.1f}%")
    print(f"  PA context (A+B1):   {existing - (existing - pa_only - both) + pa_only + both - existing + existing}/{total}")
    # Recompute cleanly
    pa_covered = pa_only + both
    print(f"  PA context (A+B1):   {pa_covered}/{total} = {pa_covered/total*100:.1f}%")
    print(f"\n  Overlap (both):      {both}/{total} = {both/total*100:.1f}%")
    print(f"  PA incremental gain: {pa_only}/{total} = {pa_only/total*100:.1f}%  ← new swings PA finds")
    print(f"  Combined (any):      {covered_any}/{total} = {covered_any/total*100:.1f}%")
    print(f"  Still missed (none): {total - covered_any}/{total} = {(total-covered_any)/total*100:.1f}%")

    print(f"\n  Per-symbol breakdown:")
    print(f"  {'Symbol':<22} {'total':>5} {'exist':>6} {'pa_incr':>8} {'both':>5} {'none':>5}")
    for r in valid:
        t = r["total"]
        e = r["existing_only"] + r["both"]
        i = r["pa_only"]
        b = r["both"]
        n = r["none"]
        print(f"  {r['sym']:<22} {t:>5} {e:>5}({e/t*100:.0f}%) {i:>4}({i/t*100:.0f}%) {b:>4}({b/t*100:.0f}%) {n:>4}({n/t*100:.0f}%)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", choices=list(POOLS) + ["ALL"], default="ALL")
    ap.add_argument("--bars-dir", default=str(DEFAULT_BARS_DIR))
    args = ap.parse_args()

    bars_dir = Path(args.bars_dir)
    pools_to_run = list(POOLS) if args.pool == "ALL" else [args.pool]

    for pool in pools_to_run:
        symbols, instrument_class = POOLS[pool]
        print(f"\nRunning pool: {pool}")
        results = []
        for sym in symbols:
            print(f"  {sym}...", end="", flush=True)
            r = analyse_symbol(sym, bars_dir, instrument_class)
            if r is None:
                print(" no data")
            else:
                print(f" total={r['total']} exist={r['existing_only']+r['both']} pa_only={r['pa_only']} both={r['both']}")
                results.append(r)
        print_report(pool, results)

    return 0


if __name__ == "__main__":
    sys.exit(main())
