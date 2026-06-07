"""Measured-move and MA target hit-rate study for US h=opposing bottom signals.

For each daily divergence bottom signal with h=opposing (60-min HTF):
  - B1 = first bottom price (price_side.reference_value)
  - H1 = max(high) between B1 and signal bottom bars
  - B2 = second bottom price (price_side.candidate_value)
  - MM_target  = B2 + (H1 - B1)   — full measured move (AB=CD)
  - MM50_target = midpoint between entry and MM_target (50% of leg)
  - EMA20, EMA60 at signal date

Reports forward hit rates at 20 / 40 / 60 bar horizons, broken down by
signal level and MM% magnitude buckets. Goal: validate whether MM target
is reliable enough to drive OTM strike selection.

Usage:
  uv run python scripts/backtest_mm_targets.py
  uv run python scripts/backtest_mm_targets.py --pool CN_METAL
  uv run python scripts/backtest_mm_targets.py --min-conf 0.4
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from engine.divergence.detector import detect_all_divergences
from engine.divergence.multi_tf_context import enrich_with_higher_tf
from engine.features.macd import macd
from engine.features.streams import compute_feature_streams
from engine.units.snapshot import compute_unit_metadata

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

US_SYMBOLS = ["spy", "qqq", "iwm", "gld", "tlt", "nvda", "dia", "gdx", "xlf", "xlk"]
CN_METAL_SYMBOLS = [
    "kq_m_shfe_cu", "kq_m_shfe_au", "kq_m_shfe_ag", "kq_m_ine_sc",
]

POOLS: dict[str, tuple[list[str], str]] = {
    "US":       (US_SYMBOLS,        "us_equity"),
    "CN_METAL": (CN_METAL_SYMBOLS,  "cn_metal_futures"),
}

HORIZONS = [20, 40, 60]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_bars(sym: str, bars_dir: Path, suffix: str = "_daily") -> pd.DataFrame | None:
    candidates = list(bars_dir.glob(f"**/{sym}{suffix}.json"))
    if not candidates:
        return None
    payload = json.loads(candidates[0].read_text())
    raw = payload.get("bars", payload) if isinstance(payload, dict) else payload
    df = pd.DataFrame(raw)
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Feature helpers
# ---------------------------------------------------------------------------

def compute_emas(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema60 = close.ewm(span=60, adjust=False).mean()
    return ema20, ema60


# ---------------------------------------------------------------------------
# Per-signal MM analysis
# ---------------------------------------------------------------------------

def analyse_signal(
    sig,
    bars: pd.DataFrame,
    ema20: pd.Series,
    ema60: pd.Series,
    instrument_class: str,
) -> dict | None:
    ref_idx = sig.reference_bar_idx
    cand_idx = sig.candidate_bar_idx

    # Need room for forward look
    if cand_idx + max(HORIZONS) >= len(bars):
        return None

    # Price anchors
    b1 = float(sig.price_side.reference_value)   # first bottom low
    b2 = float(sig.price_side.candidate_value)   # signal bottom low
    entry = float(bars["close"].iloc[cand_idx])   # entry = close at signal

    # H1: max(high) strictly between the two bottoms (exclude B1 bar itself)
    if cand_idx <= ref_idx + 1:
        return None
    h1 = float(bars["high"].iloc[ref_idx + 1:cand_idx].max())

    mm_height = h1 - b1
    if mm_height <= 0:
        return None

    mm_target = b2 + mm_height
    mm_pct = (mm_target / entry - 1.0) * 100.0   # relative to entry close

    e20 = float(ema20.iloc[cand_idx])
    e60 = float(ema60.iloc[cand_idx])

    # Forward high series
    fwd_highs = bars["high"].iloc[cand_idx + 1:]

    ctx = sig.multi_tf_context or {}
    h_rel = ctx.get("higher_relation", "unknown")

    record: dict = {
        "symbol": None,           # filled by caller
        "date": bars["timestamp"].iloc[cand_idx].date().isoformat(),
        "level": sig.level,
        "confidence": sig.confidence,
        "h_rel": h_rel,
        "instrument_class": instrument_class,
        # structural geometry
        "b1": b1,
        "h1": h1,
        "b2": b2,
        "entry": entry,
        "mm_target": round(mm_target, 4),
        "mm_pct": round(mm_pct, 2),
        "mm50_target": round(entry + (mm_target - entry) * 0.5, 4),
        "ema20": round(e20, 4),
        "ema60": round(e60, 4),
        "ema20_pct": round((e20 / entry - 1.0) * 100.0, 2),
        "ema60_pct": round((e60 / entry - 1.0) * 100.0, 2),
        "below_ema20": e20 > entry,
        "below_ema60": e60 > entry,
    }

    # Hit rates at each horizon
    running_max = entry
    for h in HORIZONS:
        end = cand_idx + h
        if end >= len(bars):
            for key in [f"hit_mm_{h}", f"hit_mm50_{h}", f"hit_ema20_{h}", f"hit_ema60_{h}"]:
                record[key] = None
            continue
        slice_high = float(bars["high"].iloc[cand_idx + 1: end + 1].max())
        record[f"hit_mm_{h}"]   = slice_high >= mm_target
        record[f"hit_mm50_{h}"] = slice_high >= (entry + (mm_target - entry) * 0.5)
        record[f"hit_ema20_{h}"] = (e20 > entry) and (slice_high >= e20)
        record[f"hit_ema60_{h}"] = (e60 > entry) and (slice_high >= e60)
        # Also track max return (for how far the move actually went)
        record[f"max_ret_pct_{h}"] = round((slice_high / entry - 1.0) * 100.0, 2)

    return record


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def _pct(hits: pd.Series) -> str:
    """Format a boolean (0/1) series as a hit-rate percentage."""
    v = hits.dropna()
    if len(v) == 0:
        return "  n/a"
    return f"{v.mean() * 100:5.1f}%"


def _mean_val(series: pd.Series) -> str:
    """Format a numeric series (already in %) as a plain mean."""
    v = series.dropna()
    if len(v) == 0:
        return "  n/a"
    return f"{v.mean():5.1f}%"


def print_hit_table(df: pd.DataFrame, label: str) -> None:
    n = len(df)
    if n == 0:
        print(f"  {label}: no signals")
        return
    print(f"\n  {label}  (n={n})")
    header = f"  {'Horizon':>8}  {'Hit@MM':>8}  {'Hit@MM50':>9}  {'Hit@EMA20':>10}  {'Hit@EMA60':>10}  {'MaxRet':>8}"
    print(header)
    for h in HORIZONS:
        row = (
            f"  {h:>5} bars"
            f"  {_pct(df[f'hit_mm_{h}']):>8}"
            f"  {_pct(df[f'hit_mm50_{h}']):>9}"
            f"  {_pct(df[f'hit_ema20_{h}']):>10}"
            f"  {_pct(df[f'hit_ema60_{h}']):>10}"
            f"  {_mean_val(df[f'max_ret_pct_{h}']):>8}"
        )
        print(row)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", default="US", choices=list(POOLS))
    parser.add_argument("--min-conf", type=float, default=0.3)
    parser.add_argument("--h-opp-only", action="store_true", default=True,
                        help="Only analyse h=opposing signals (default on)")
    parser.add_argument("--all-h", action="store_true",
                        help="Include all h_rel values (overrides --h-opp-only)")
    parser.add_argument("--bars-dir", type=Path, default=DEFAULT_BARS_DIR)
    args = parser.parse_args()

    h_opp_only = args.h_opp_only and not args.all_h
    symbols, instrument_class = POOLS[args.pool]

    all_records: list[dict] = []

    for sym in symbols:
        bars = load_bars(sym, args.bars_dir)
        if bars is None:
            print(f"  {sym}: missing daily data, skipped", file=sys.stderr)
            continue
        h_bars = load_bars(sym, args.bars_dir, suffix="_60")

        macd_df = macd(bars["close"], hist_scale=1.0)
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

        ema20, ema60 = compute_emas(bars["close"])

        n_sym = 0
        for sig in signals:
            if sig.direction != "bottom":
                continue
            if sig.confidence < args.min_conf:
                continue
            ctx = sig.multi_tf_context or {}
            h_rel = ctx.get("higher_relation", "unknown")
            if h_opp_only and h_rel != "opposing":
                continue

            rec = analyse_signal(sig, bars, ema20, ema60, instrument_class)
            if rec is None:
                continue
            rec["symbol"] = sym
            all_records.append(rec)
            n_sym += 1

        print(f"  {sym}: {n_sym} signals")

    if not all_records:
        print("No signals found.")
        return

    df = pd.DataFrame(all_records)
    opp = df[df["h_rel"] == "opposing"] if h_opp_only else df

    h_filter = "h=opposing" if h_opp_only else "all h_rel"
    print(f"\n{'='*70}")
    print(f"Pool: {args.pool} | {h_filter} | min_conf={args.min_conf}")
    print(f"Total signals: {len(opp)}")
    print(f"{'='*70}")

    # MM geometry summary
    print(f"\nMM Geometry (from entry close):")
    print(f"  MM%   mean={opp['mm_pct'].mean():.1f}%  "
          f"median={opp['mm_pct'].median():.1f}%  "
          f"p25={opp['mm_pct'].quantile(0.25):.1f}%  "
          f"p75={opp['mm_pct'].quantile(0.75):.1f}%")
    print(f"  EMA20% above entry: mean={opp[opp['below_ema20']]['ema20_pct'].mean():.1f}%  "
          f"({opp['below_ema20'].mean()*100:.0f}% of signals below EMA20)")
    print(f"  EMA60% above entry: mean={opp[opp['below_ema60']]['ema60_pct'].mean():.1f}%  "
          f"({opp['below_ema60'].mean()*100:.0f}% of signals below EMA60)")

    # Overall hit rates
    print_hit_table(opp, "All signals")

    # By level
    print(f"\nBy signal level:")
    for lvl in sorted(opp["level"].unique()):
        sub = opp[opp["level"] == lvl]
        print_hit_table(sub, lvl)

    # By MM% bucket
    print(f"\nBy MM% bucket (target size):")
    bins = [0, 2, 4, 6, 10, 100]
    labels = ["<2%", "2-4%", "4-6%", "6-10%", ">10%"]
    opp = opp.copy()
    opp["mm_bucket"] = pd.cut(opp["mm_pct"], bins=bins, labels=labels)
    for bucket in labels:
        sub = opp[opp["mm_bucket"] == bucket]
        if len(sub) > 0:
            print_hit_table(sub, f"MM {bucket}")

    # By signal level for h=opposing — max return at 40 bars
    print(f"\nMax return distribution at 40 bars (h=opposing):")
    if "max_ret_pct_40" in opp.columns:
        mr = opp["max_ret_pct_40"].dropna()
        print(f"  mean={mr.mean():.1f}%  median={mr.median():.1f}%  "
              f"p25={mr.quantile(0.25):.1f}%  p75={mr.quantile(0.75):.1f}%  "
              f"p90={mr.quantile(0.90):.1f}%")

    # EMA20 as natural first target (when below EMA20)
    below20 = opp[opp["below_ema20"]]
    if len(below20) > 0:
        print(f"\nWhen signal is BELOW EMA20 (n={len(below20)}):")
        print_hit_table(below20, "Below EMA20 subgroup")


if __name__ == "__main__":
    main()
