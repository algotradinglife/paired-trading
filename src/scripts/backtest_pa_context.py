"""PA context backtest — validates Blind Spot A and B1 context classifier.

For each symbol in each pool:
  1. Detect context A and B1 windows on daily bars.
  2. Measure forward return at 10/20/40 bars from each context window.
  3. Compare to ZigZag swing labels: what % of 5%+ up swings had a context
     window within [-10, +5] bars of the swing head?

Usage:
  uv run python scripts/backtest_pa_context.py
  uv run python scripts/backtest_pa_context.py --pool US
  uv run python scripts/backtest_pa_context.py --pool CN_METAL --min-bars 200
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
from engine.divergence.pa_context_classifier import classify_context
from engine.features.macd import macd, ema
from engine.labels.swing_labeler import label_swings

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

US_SYMBOLS = ["spy", "qqq", "iwm", "gld", "tlt", "nvda", "dia", "gdx", "xlf", "xlk"]
CN_METAL_SYMBOLS = ["kq_m_shfe_cu", "kq_m_shfe_au", "kq_m_shfe_ag", "kq_m_ine_sc"]

POOLS: dict[str, list[str]] = {
    "US": US_SYMBOLS,
    "CN_METAL": CN_METAL_SYMBOLS,
}

HORIZONS = [10, 20, 40]
SWING_REVERSAL_PCT = 5.0
RECALL_WINDOW_BEFORE = 10
RECALL_WINDOW_AFTER  = 5


def load_bars(sym: str, bars_dir: Path) -> pd.DataFrame | None:
    return bar_loader.load_bars_quant_or_json(sym, "_daily", bars_dir)


def scan_contexts(
    bars: pd.DataFrame,
    macd_df: pd.DataFrame,
    ema20: pd.Series,
    ema60: pd.Series,
) -> list[tuple[int, str]]:
    """Return deduplicated context windows: first bar of each continuous run."""
    raw: list[tuple[int, str]] = []
    for i in range(len(bars)):
        ctx = classify_context(bars, i, macd_df, ema20, ema60)
        if ctx is not None:
            raw.append((i, ctx))

    if not raw:
        return []

    windows: list[tuple[int, str]] = [raw[0]]
    for j in range(1, len(raw)):
        prev_idx, prev_ctx = raw[j - 1]
        curr_idx, curr_ctx = raw[j]
        if curr_ctx != prev_ctx or curr_idx > prev_idx + 1:
            windows.append(raw[j])
    return windows


def measure_forward(bars: pd.DataFrame, entry_idx: int) -> dict[str, float]:
    close = float(bars["close"].iloc[entry_idx])
    result: dict[str, float] = {}
    for h in HORIZONS:
        end = min(entry_idx + h + 1, len(bars))
        if end <= entry_idx + 1:
            result[f"max_ret_{h}"] = float("nan")
            continue
        fwd_high = float(bars["high"].iloc[entry_idx + 1:end].max())
        result[f"max_ret_{h}"] = (fwd_high / close - 1.0) * 100.0
    return result


def compute_recall(
    swings: list,
    context_bars: list[tuple[int, str]],
    context_filter: str | None = None,
) -> tuple[int, int]:
    """Return (swings_covered, total_up_swings).

    Handles list-of-SwingLabel objects returned by label_swings().
    """
    context_set = {
        idx for idx, ctx in context_bars
        if (context_filter is None or ctx == context_filter)
    }

    up_swings = [
        s for s in swings
        if getattr(s, "direction", None) == "up"
        and getattr(s, "magnitude_pct", 0) >= SWING_REVERSAL_PCT
    ]
    total = len(up_swings)
    covered = sum(
        1 for s in up_swings
        if any(
            s.head_idx - RECALL_WINDOW_BEFORE <= c <= s.head_idx + RECALL_WINDOW_AFTER
            for c in context_set
        )
    )
    return covered, total


def analyse_symbol(sym: str, bars_dir: Path, min_bars: int) -> dict | None:
    bars = load_bars(sym, bars_dir)
    if bars is None or len(bars) < min_bars:
        return None

    macd_df = macd(bars["close"])
    ema20 = ema(bars["close"], 20)
    ema60 = ema(bars["close"], 60)

    context_bars = scan_contexts(bars, macd_df, ema20, ema60)

    swings = label_swings(bars, reversal_pct=SWING_REVERSAL_PCT)

    cov_A,   total = compute_recall(swings, context_bars, context_filter="A")
    cov_B1,  _     = compute_recall(swings, context_bars, context_filter="B1")
    cov_any, _     = compute_recall(swings, context_bars, context_filter=None)

    n_A  = sum(1 for _, c in context_bars if c == "A")
    n_B1 = sum(1 for _, c in context_bars if c == "B1")

    records = []
    for entry_idx, ctx in context_bars:
        if entry_idx + 1 >= len(bars):
            continue
        fwd = measure_forward(bars, entry_idx)
        records.append({"sym": sym, "context": ctx, "bar_idx": entry_idx, **fwd})

    signals_df = pd.DataFrame(records) if records else pd.DataFrame()

    return {
        "sym":        sym,
        "n_A":        n_A,
        "n_B1":       n_B1,
        "n_swings":   total,
        "recall_A":   cov_A  / total if total else float("nan"),
        "recall_B1":  cov_B1 / total if total else float("nan"),
        "recall_any": cov_any / total if total else float("nan"),
        "signals_df": signals_df,
    }


def print_pool_report(pool: str, results: list[dict]) -> None:
    valid = [r for r in results if r is not None]
    if not valid:
        print(f"  No data for pool {pool}")
        return

    dfs = [r["signals_df"] for r in valid if not r["signals_df"].empty]
    all_signals = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

    total_swings = sum(r["n_swings"] for r in valid)
    total_A  = sum(r["n_A"]  for r in valid)
    total_B1 = sum(r["n_B1"] for r in valid)

    print(f"\n{'='*60}")
    print(f"Pool: {pool}")
    print(f"  Context A windows:  {total_A}")
    print(f"  Context B1 windows: {total_B1}")
    print(f"  Total 5%+ up swings (ground truth): {total_swings}")

    if total_swings > 0:
        cov_A   = sum(r["recall_A"]   * r["n_swings"] for r in valid if not np.isnan(r["recall_A"]))
        cov_B1  = sum(r["recall_B1"]  * r["n_swings"] for r in valid if not np.isnan(r["recall_B1"]))
        cov_any = sum(r["recall_any"] * r["n_swings"] for r in valid if not np.isnan(r["recall_any"]))
        print(f"\n  Recall (% of swings with context nearby):")
        print(f"    A only:   {cov_A  / total_swings * 100:.1f}%")
        print(f"    B1 only:  {cov_B1 / total_swings * 100:.1f}%")
        print(f"    A or B1:  {cov_any / total_swings * 100:.1f}%")

    if not all_signals.empty:
        print(f"\n  Forward max return from context entry (enter at close):")
        header = f"  {'Context':<8} {'n':>5}  " + "  ".join(f"MaxRet@{h}d" for h in HORIZONS)
        print(header)
        for ctx in ["A", "B1"]:
            sub = all_signals[all_signals["context"] == ctx]
            if sub.empty:
                continue
            ret_str = "  ".join(
                f"{sub[f'max_ret_{h}'].dropna().mean():+.1f}%"
                if f"max_ret_{h}" in sub.columns
                else "n/a"
                for h in HORIZONS
            )
            print(f"  {ctx:<8} {len(sub):>5}  {ret_str}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", choices=list(POOLS) + ["ALL"], default="ALL")
    ap.add_argument("--bars-dir", default=str(DEFAULT_BARS_DIR))
    ap.add_argument("--min-bars", type=int, default=100)
    args = ap.parse_args()

    bars_dir = Path(args.bars_dir)
    pools_to_run = list(POOLS) if args.pool == "ALL" else [args.pool]

    for pool in pools_to_run:
        print(f"\nRunning pool: {pool}")
        results = []
        for sym in POOLS[pool]:
            print(f"  {sym}...", end="", flush=True)
            r = analyse_symbol(sym, bars_dir, args.min_bars)
            if r is None:
                print(" no data")
            else:
                print(f" A={r['n_A']} B1={r['n_B1']} swings={r['n_swings']}")
                results.append(r)
        print_pool_report(pool, results)

    return 0


if __name__ == "__main__":
    sys.exit(main())
