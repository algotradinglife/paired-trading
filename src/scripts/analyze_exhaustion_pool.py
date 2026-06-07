"""Forward-return precision study for ExhaustionEvents.

Companion to scripts/analyze_sweet_spots_pool.py (which targets
DivergenceSignal). Pools exhaustion events across a symbol pool, computes
signed forward returns at multiple horizons, and breaks down precision
by direction / wick tercile / confidence band.

Headline metrics:
  - n_events
  - hit_rate (sign of forward return matches predicted direction)
  - mean_signed_return (forward return signed by predicted direction)
  - 95% bootstrap CI on the mean (5000 resamples, RNG seed 42)

Methodology mirrors `analyze_sweet_spots_pool.py` so numbers are
directly comparable to validated divergence sweet spots.

Usage:
  uv run python scripts/analyze_exhaustion_pool.py --pool US
  uv run python scripts/analyze_exhaustion_pool.py --pool US --horizons 5 10 20 \\
      -o data/review/exhaustion_pool_us.csv
  uv run python scripts/analyze_exhaustion_pool.py --pool US --strat-horizon 10

Notes:
  - Weekly bars are synthesized from daily via `pd.resample('W-FRI')` so
    state lookup is leak-free regardless of pool. data/raw weekly snapshots
    (where they exist) are stamped at week-start with full-week OHLC and
    would otherwise leak into a mid-week daily candidate.
  - In strict mode, the script REQUIRES the lower (1h) snapshot. Higher
    (W) is always synthesized.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from engine.divergence.exhaustion import detect_exhaustion_events
from engine.features.macd import macd
from engine.features.streams import compute_feature_streams
from engine.units.snapshot import compute_unit_metadata

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
N_BOOTSTRAP = 5000
RNG_SEED = 42
DEFAULT_HORIZONS = [5, 10, 20]

POOLS: dict[str, list[str]] = {
    "US": ["SPY", "QQQ", "IWM", "DIA", "GLD", "GDX", "XLF", "XLK", "TLT", "NVDA"],
    "CN": ["kq_m_cffex_if", "kq_m_cffex_ih", "kq_m_cffex_ic", "kq_m_cffex_im"],
    "CN_COMMODITY": [
        "kq_m_shfe_rb", "kq_m_shfe_cu", "kq_m_shfe_au", "kq_m_shfe_ag",
        "kq_m_dce_m", "kq_m_dce_i", "kq_m_dce_j", "kq_m_dce_jm",
        "kq_m_dce_p", "kq_m_dce_y",
        "kq_m_czce_ta", "kq_m_czce_ma", "kq_m_czce_cf", "kq_m_czce_sr",
        "kq_m_czce_sa",
        "kq_m_ine_sc",
    ],
}

# Topology mapping per pool — same data files used by build_analysis_output
TOPOLOGY_FILES = {
    "D": "_daily.json",
    "1h": "_60.json",
    "W": "_weekly.json",
}


def load_bars(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text())
    df = pd.DataFrame(payload["bars"])
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


def resample_to_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """Build no-leak weekly OHLCV bars from daily.

    Why: data/raw weekly snapshots (where they exist) are stamped at
    week-start with full-week OHLC, which is forward-looking from a
    mid-week daily candidate's perspective. Resampling from daily here
    produces a no-leak weekly proxy.

    Timestamp semantics (codex 2026-05-27): the resample label is the
    period end (Friday 00:00 UTC) which is BEFORE the actual Friday
    daily bar (e.g. SPY daily is stamped 04:00 UTC Friday). Using that
    label would let `_state_at(weekly_bars[timestamp <= daily_ts])`
    include the weekly bar at any mid-Friday daily candidate even
    though the weekly aggregate already incorporates that Friday's
    OHLC. So we OVERRIDE the synthetic weekly timestamp with the
    LATEST constituent daily timestamp — the weekly bar is "knowable"
    only at or after its closing daily bar's own timestamp.
    """
    if daily.empty:
        return daily.copy()
    df = daily.set_index("timestamp").sort_index()
    grouper = pd.Grouper(freq="W-FRI", label="right", closed="right")
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in df.columns:
        agg["volume"] = "sum"
    grouped = df.groupby(grouper)
    weekly = grouped.agg(agg).dropna(subset=["open"])
    if weekly.empty:
        return weekly.reset_index()
    # Override label with last constituent daily timestamp per group.
    # `.values` strips tz; reattach the input frame's tz so downstream
    # `bars["timestamp"] <= cutoff` comparisons with the tz-aware daily
    # candidates stay valid.
    last_ts = grouped.apply(lambda g: g.index.max() if len(g) else pd.NaT)
    src_tz = daily["timestamp"].dt.tz
    new_index = pd.to_datetime(last_ts.reindex(weekly.index).values, utc=src_tz is not None)
    if src_tz is not None and new_index.tz is None:
        new_index = new_index.tz_localize(src_tz)
    weekly.index = new_index
    weekly.index.name = "timestamp"
    return weekly.reset_index()


def bootstrap_ci(x: np.ndarray, *, n_boot: int = N_BOOTSTRAP, alpha: float = 0.05) -> tuple[float, float]:
    if len(x) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(RNG_SEED)
    means = rng.choice(x, size=(n_boot, len(x)), replace=True).mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)


def signed_forward_return(bars: pd.DataFrame, idx: int, horizon: int, direction: str) -> float | None:
    """Forward return signed by predicted reversal direction.
    Returns None when there aren't enough bars after the event.
    For a 'top' event, a downward move is a 'hit' → positive signed return."""
    if idx + horizon >= len(bars):
        return None
    entry = float(bars["close"].iloc[idx])
    target = float(bars["close"].iloc[idx + horizon])
    if entry == 0:
        return None
    raw = (target - entry) / entry
    return -raw if direction == "top" else raw


def collect_events_for_symbol(
    symbol: str,
    bars_dir: Path,
    *,
    horizons: list[int],
    min_bars_in_segment: int,
    strict_alignment: bool,
) -> list[dict]:
    daily = bars_dir / f"{symbol.lower()}_daily.json"
    if not daily.exists():
        print(f"  {symbol}: missing daily snapshot, skipped", file=sys.stderr)
        return []
    bars = load_bars(daily)
    hourly = bars_dir / f"{symbol.lower()}_60.json"
    # Strict mode requires a foreign hourly snapshot. Weekly is always
    # synthesized from daily (no leak by construction) so the only
    # missing-snapshot case the strict gate actually cares about is 1h.
    if strict_alignment and not hourly.exists():
        raise FileNotFoundError(
            f"{symbol}: strict_alignment=True requires the lower (1h) "
            f"snapshot at {hourly}. Pass --no-strict to relax."
        )
    higher_bars = resample_to_weekly(bars)
    lower_bars = load_bars(hourly) if hourly.exists() else None

    macd_df = macd(bars["close"], hist_scale=1.0)
    streams = compute_feature_streams(
        bars["close"], macd_df["dif"], macd_df["dea"], macd_df["hist"],
    )
    units = compute_unit_metadata(
        macd_df["dif"], macd_df["dea"], macd_df["hist"], streams["dif_proximity_zero"],
    )

    events = detect_exhaustion_events(
        bars, units, level_id="D",
        higher_bars=higher_bars, higher_level_id="W" if higher_bars is not None else None,
        lower_bars=lower_bars, lower_level_id="1h" if lower_bars is not None else None,
        min_bars_in_segment=min_bars_in_segment,
        strict_alignment=strict_alignment,
    )

    rows: list[dict] = []
    for e in events:
        row: dict[str, object] = {
            "symbol": symbol,
            "candidate_bar_idx": e.candidate_bar_idx,
            "timestamp": e.timestamp.isoformat(),
            "direction": e.direction,
            "wick_ratio": e.wick_ratio,
            "confidence": e.confidence,
            "bars_in_segment": e.bars_in_segment,
            "n_completed_cycles": e.n_completed_cycles,
            "volume_ratio": e.volume_ratio if e.volume_ratio is not None else float("nan"),
        }
        for h in horizons:
            row[f"ret_h{h}"] = signed_forward_return(bars, e.candidate_bar_idx, h, e.direction)
        rows.append(row)
    return rows


def summarize_cell(df: pd.DataFrame, ret_col: str, *, label: str) -> dict:
    vals = df[ret_col].dropna().to_numpy()
    n = len(vals)
    if n == 0:
        return {"cell": label, "n": 0, "hit_rate_pct": float("nan"),
                "mean_signed_return_pct": float("nan"),
                "ci_lo_pct": float("nan"), "ci_hi_pct": float("nan")}
    hits = float(np.mean(vals > 0))
    mean_ret = float(np.mean(vals))
    lo, hi = bootstrap_ci(vals)
    return {
        "cell": label,
        "n": n,
        "hit_rate_pct": hits * 100.0,
        "mean_signed_return_pct": mean_ret * 100.0,
        "ci_lo_pct": lo * 100.0,
        "ci_hi_pct": hi * 100.0,
    }


def tercile_split(s: pd.Series) -> pd.Series:
    """Split a numeric series into low/mid/high terciles by quantile.

    Mirrors `analyze_sweet_spots_pool.tercile_bucket`: when the [33%, 67%]
    cut points tie (no variance / heavy ties), returns a series of "na"
    so stratification gracefully degrades instead of pd.cut() raising
    ValueError on duplicate bin edges.
    """
    notna = s.dropna()
    if notna.empty:
        return pd.Series("na", index=s.index, dtype=object)
    lo = float(notna.quantile(1 / 3))
    hi = float(notna.quantile(2 / 3))
    if lo >= hi:
        return pd.Series("na", index=s.index, dtype=object)
    out = pd.Series("na", index=s.index, dtype=object)
    notna_mask = s.notna()
    vals = s[notna_mask]
    bins = pd.Series("low", index=vals.index, dtype=object)
    bins[vals >= lo] = "mid"
    bins[vals >= hi] = "high"
    out.loc[notna_mask] = bins
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Forward-return precision for ExhaustionEvents")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--pool", choices=sorted(POOLS))
    g.add_argument("--symbols", nargs="+")
    p.add_argument("--bars-dir", type=Path, default=DEFAULT_BARS_DIR)
    p.add_argument("--horizons", type=int, nargs="+", default=DEFAULT_HORIZONS,
                   help="forward-return horizons in bars (default: 5 10 20)")
    p.add_argument("--strat-horizon", type=int, default=None,
                   help="horizon used for confidence/wick stratification "
                        "(default: largest in --horizons). Must be in --horizons.")
    p.add_argument("--min-bars-in-segment", type=int, default=20)
    p.add_argument("--no-strict", action="store_true",
                   help="strict_alignment=False (relax 3-TF gate)")
    p.add_argument("-o", "--output", type=Path)
    args = p.parse_args()

    symbols = POOLS[args.pool] if args.pool else args.symbols
    strict = not args.no_strict
    if any(h <= 0 for h in args.horizons):
        print(f"--horizons must be positive integers; got {args.horizons}",
              file=sys.stderr)
        return 2
    if args.strat_horizon is None:
        strat_h = max(args.horizons)
    else:
        if args.strat_horizon not in args.horizons:
            print(f"--strat-horizon {args.strat_horizon} not in --horizons "
                  f"{args.horizons}", file=sys.stderr)
            return 2
        strat_h = args.strat_horizon

    print(f"Pool: {args.pool or 'custom'} ({len(symbols)} symbols)")
    print(f"min_bars_in_segment={args.min_bars_in_segment}, strict_alignment={strict}")
    print(f"Horizons: {args.horizons}")
    print()

    all_rows: list[dict] = []
    for sym in symbols:
        all_rows.extend(collect_events_for_symbol(
            sym, args.bars_dir,
            horizons=args.horizons,
            min_bars_in_segment=args.min_bars_in_segment,
            strict_alignment=strict,
        ))
    df = pd.DataFrame(all_rows)
    if df.empty:
        print("No events.")
        return 0
    print(f"Total events: {len(df)} (top={len(df[df.direction=='top'])} bottom={len(df[df.direction=='bottom'])})")
    print()

    # Per-symbol counts
    by_sym = df.groupby("symbol").size().sort_values(ascending=False)
    print("Per symbol:")
    for sym, n in by_sym.items():
        print(f"  {sym:8s} {n}")
    print()

    # Pool summary per direction per horizon
    cells: list[dict] = []
    for h in args.horizons:
        for direction in ["top", "bottom", "all"]:
            sub = df if direction == "all" else df[df["direction"] == direction]
            label = f"h={h}  {direction:6s}"
            cells.append(summarize_cell(sub, f"ret_h{h}", label=label))

    print(f"{'cell':<20} {'n':>5} {'hit%':>7} {'mean%':>8} {'CI95':>20}")
    print("-" * 65)
    for c in cells:
        ci = f"[{c['ci_lo_pct']:+.2f}, {c['ci_hi_pct']:+.2f}]" if not pd.isna(c['ci_lo_pct']) else "—"
        print(f"{c['cell']:<20} {c['n']:>5d} {c['hit_rate_pct']:>6.1f}% {c['mean_signed_return_pct']:>+7.2f}% {ci:>20}")
    print()

    strat_col = f"ret_h{strat_h}"
    # Restrict the stratification frame to events that have a forward return
    # at the chosen horizon. Otherwise unlabeled rows (e.g. very recent
    # events without enough future bars) would shift tercile edges without
    # contributing to the reported hit/mean (codex review).
    labeled = df[df[strat_col].notna()].copy()

    # Stratify on confidence (top tercile vs lower)
    if len(labeled) >= 6:
        labeled["conf_tercile"] = tercile_split(labeled["confidence"])
        print(f"Confidence tercile (h={strat_h}, labeled n={len(labeled)}):")
        print(f"{'cell':<24} {'n':>5} {'hit%':>7} {'mean%':>8} {'CI95':>20}")
        print("-" * 65)
        for direction in ["top", "bottom"]:
            for terc in ["low", "mid", "high"]:
                sub = labeled[(labeled["direction"] == direction) & (labeled["conf_tercile"] == terc)]
                c = summarize_cell(sub, strat_col, label=f"{direction:6s} conf={terc}")
                ci = f"[{c['ci_lo_pct']:+.2f}, {c['ci_hi_pct']:+.2f}]" if not pd.isna(c['ci_lo_pct']) else "—"
                print(f"{c['cell']:<24} {c['n']:>5d} {c['hit_rate_pct']:>6.1f}% {c['mean_signed_return_pct']:>+7.2f}% {ci:>20}")
        print()

    # Stratify on wick_ratio tercile
    if len(labeled) >= 6:
        labeled["wick_tercile"] = tercile_split(labeled["wick_ratio"])
        print(f"Wick-ratio tercile (h={strat_h}, labeled n={len(labeled)}):")
        print(f"{'cell':<24} {'n':>5} {'hit%':>7} {'mean%':>8} {'CI95':>20}")
        print("-" * 65)
        for direction in ["top", "bottom"]:
            for terc in ["low", "mid", "high"]:
                sub = labeled[(labeled["direction"] == direction) & (labeled["wick_tercile"] == terc)]
                c = summarize_cell(sub, strat_col, label=f"{direction:6s} wick={terc}")
                ci = f"[{c['ci_lo_pct']:+.2f}, {c['ci_hi_pct']:+.2f}]" if not pd.isna(c['ci_lo_pct']) else "—"
                print(f"{c['cell']:<24} {c['n']:>5d} {c['hit_rate_pct']:>6.1f}% {c['mean_signed_return_pct']:>+7.2f}% {ci:>20}")
        print()

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(args.output, index=False)
        print(f"Per-event CSV → {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
