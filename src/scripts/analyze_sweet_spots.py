"""Sweet-spot finder: rank signals by Z1+Z2 context_features for win-rate uplift.

Operationalizes the session-goal directive — "持续寻找高胜率甜区" — by
re-running the detector on a target symbol's DAILY bars and bucketing
the emitted signals into terciles on `candidate_rejection_wick_ratio`
and `prior_swing_distance_pct`. Buckets whose hit-rate beats the
baseline are sweet-spot candidates for downstream filtering.

This is a single-timeframe diagnostic — it does NOT attach multi-TF
context (no `multi_tf_context` / topology enrichment). The Z1+Z2
features being tested live on the candidate bar itself and are
topology-independent. A future variant could add topology enrichment
to look for sweet spots conditioned on multi-TF state.

This is NOT a backtest of an executable strategy; it's diagnostic
evidence about which feature regions are worth filtering on. Downstream
strategies layer their own tip-stop / MM-take / split-take.

Usage:
  uv run python scripts/analyze_sweet_spots.py SPY
  uv run python scripts/analyze_sweet_spots.py kq_m_cffex_if \\
      --instrument-class cn_futures
  uv run python scripts/analyze_sweet_spots.py SPY --horizon 10 -o sweet.csv

Output:
  Per-bucket table with n, hit_rate, mean_signed_return, bootstrap CI.
  Highlights buckets where hit_rate beats baseline by ≥10pp.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from data import bar_loader
from engine.divergence.detector import detect_all_divergences
from engine.features.macd import macd
from engine.features.streams import compute_feature_streams
from engine.units.snapshot import compute_unit_metadata

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
FORWARD_HORIZONS = [5, 10, 20]
N_BOOTSTRAP = 2000
RNG_SEED = 42


def bootstrap_ci(x: np.ndarray, n_boot: int = N_BOOTSTRAP, alpha: float = 0.05) -> tuple[float, float]:
    if len(x) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(RNG_SEED)
    means = rng.choice(x, size=(n_boot, len(x)), replace=True).mean(axis=1)
    return tuple(float(v) for v in np.quantile(means, [alpha / 2, 1 - alpha / 2]))


def signed_forward_return(bars: pd.DataFrame, idx: int, horizon: int, direction: str) -> float | None:
    if idx + horizon >= len(bars):
        return None
    entry = float(bars["close"].iloc[idx])
    target = float(bars["close"].iloc[idx + horizon])
    raw = (target - entry) / entry
    return -raw if direction == "top" else raw


def build_signal_dataframe(symbol: str, bars: pd.DataFrame, *, instrument_class: str, horizon: int) -> pd.DataFrame:
    macd_df = macd(bars["close"], hist_scale=1.0)
    streams = compute_feature_streams(bars["close"], macd_df["dif"], macd_df["dea"], macd_df["hist"])
    units = compute_unit_metadata(macd_df["dif"], macd_df["dea"], macd_df["hist"], streams["dif_proximity_zero"])
    signals = detect_all_divergences(
        units_df=units, ohlc=bars, dif=macd_df["dif"], hist=macd_df["hist"],
        level_id="D", instrument_class=instrument_class,
    )

    records = []
    for sig in signals:
        ret = signed_forward_return(bars, sig.candidate_bar_idx, horizon, sig.direction)
        if ret is None:
            continue
        ctx = sig.context_features or {}
        records.append({
            "symbol": symbol,
            "date": sig.timestamp.date().isoformat(),
            "direction": sig.direction,
            "level": sig.level,
            "subtype": sig.subtype,
            "confidence": sig.confidence,
            "wick_ratio": ctx.get("candidate_rejection_wick_ratio"),
            "invalidation_level": ctx.get("invalidation_level"),
            "prior_swing_pct": ctx.get("prior_swing_distance_pct"),
            "signed_return": ret,
            "hit": ret > 0,
        })
    return pd.DataFrame(records)


def tercile_bucket(series: pd.Series, label_prefix: str) -> pd.Series:
    """Split numeric series into 3 quantile buckets. NaN → 'na'."""
    notna = series.dropna()
    if len(notna) < 9:  # need at least 3 per bucket for sensible terciles
        return pd.Series(["na"] * len(series), index=series.index, dtype=object)
    try:
        cats = pd.qcut(notna, q=3, labels=[f"{label_prefix}_low", f"{label_prefix}_mid", f"{label_prefix}_high"],
                       duplicates="drop")
    except ValueError:
        return pd.Series(["na"] * len(series), index=series.index, dtype=object)
    result = pd.Series("na", index=series.index, dtype=object)
    result.loc[notna.index] = cats.astype(str)
    return result


def report_bucket(df: pd.DataFrame, group_cols: list[str], title: str, baseline_hit: float) -> pd.DataFrame:
    print(f"\n=== {title} ===")
    if df.empty:
        print("(empty)")
        return pd.DataFrame()
    g = df.groupby(group_cols, dropna=False)

    def _summary(sub):
        rets = sub["signed_return"].to_numpy()
        ci_lo, ci_hi = bootstrap_ci(rets)
        return pd.Series({
            "n": int(len(sub)),
            "hit_rate_pct": float(sub["hit"].mean() * 100),
            "mean_ret_pct": float(sub["signed_return"].mean() * 100),
            "median_ret_pct": float(sub["signed_return"].median() * 100),
            "ci_lo_pct": ci_lo * 100,
            "ci_hi_pct": ci_hi * 100,
        })

    summary = g.apply(_summary, include_groups=False).reset_index()
    summary = summary[summary["n"] >= 5].copy()
    summary["hit_uplift_pp"] = summary["hit_rate_pct"] - baseline_hit
    summary = summary.sort_values("hit_uplift_pp", ascending=False)
    out_cols = group_cols + ["n", "hit_rate_pct", "hit_uplift_pp", "mean_ret_pct",
                              "median_ret_pct", "ci_lo_pct", "ci_hi_pct"]
    formatters = {
        "hit_rate_pct": "{:.1f}%".format,
        "hit_uplift_pp": "{:+.1f}pp".format,
        "mean_ret_pct": "{:+.2f}%".format,
        "median_ret_pct": "{:+.2f}%".format,
        "ci_lo_pct": "{:+.2f}%".format,
        "ci_hi_pct": "{:+.2f}%".format,
    }
    print(summary[out_cols].to_string(index=False, formatters=formatters))
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description="Find high-win-rate sweet spots from Z1+Z2 context_features")
    p.add_argument("symbol")
    p.add_argument("--instrument-class", choices=["us_equity", "cn_futures"],
                   default="us_equity", dest="instrument_class")
    p.add_argument("--bars-dir", type=Path, default=DEFAULT_BARS_DIR)
    p.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
                   help="quant-data Parquet root (default: data/quant/)")
    p.add_argument("--horizon", type=int, default=20, choices=[5, 10, 20])
    p.add_argument("-o", "--output", type=Path, help="write per-signal CSV to this file")
    args = p.parse_args()

    bars: pd.DataFrame | None = None
    if args.quant_data_root is not None:
        mic = bar_loader.infer_exchange_mic(args.symbol)
        if mic is not None:
            try:
                bars = bar_loader.load_bars_quant(args.symbol.upper(), mic, "D", args.quant_data_root)
            except Exception as e:
                print(f"quant load {args.symbol}/daily: {e} — falling back to JSON", file=sys.stderr)
    if bars is None:
        path = args.bars_dir / f"{args.symbol.lower()}_daily.json"
        if not path.exists():
            print(f"ERROR: missing snapshot {path}", file=sys.stderr)
            return 2
        bars = bar_loader.load_bars_json(path)

    df = build_signal_dataframe(args.symbol, bars,
                                instrument_class=args.instrument_class,
                                horizon=args.horizon)
    print(f"\n{args.symbol}: {len(df)} signals @ horizon={args.horizon} "
          f"({args.instrument_class}, daily level)")

    if df.empty:
        return 0

    baseline_hit = float(df["hit"].mean() * 100)
    baseline_mean = float(df["signed_return"].mean() * 100)
    print(f"Baseline (all signals): hit_rate={baseline_hit:.1f}%  mean={baseline_mean:+.2f}%")

    # Bucket context features by tercile
    df["wick_bucket"] = tercile_bucket(df["wick_ratio"], "wick")
    df["swing_bucket"] = tercile_bucket(df["prior_swing_pct"], "swing")

    # By direction × wick tercile
    report_bucket(df, ["direction", "wick_bucket"],
                  f"Direction × wick_ratio tercile (h={args.horizon})", baseline_hit)

    # By direction × swing tercile
    report_bucket(df, ["direction", "swing_bucket"],
                  "Direction × prior_swing_distance_pct tercile", baseline_hit)

    # Compound: direction × wick × swing — look for sweet-spot cells
    report_bucket(df, ["direction", "wick_bucket", "swing_bucket"],
                  "SWEET-SPOT SEARCH: direction × wick × swing", baseline_hit)

    # Bonus: subtype (existing) × wick (new) — verify Z1 adds value over subtype alone
    report_bucket(df, ["subtype", "wick_bucket"],
                  "Cross-check: subtype × wick tercile", baseline_hit)

    if args.output:
        df.to_csv(args.output, index=False)
        print(f"\nPer-signal CSV → {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
