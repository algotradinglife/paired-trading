"""Pool-level sweet-spot finder — Z1+Z2 hit-rate uplift across multiple symbols.

Companion to scripts/analyze_sweet_spots.py (which runs per-symbol).
Aggregates signals across a pool of symbols to grow per-cell sample
size beyond what single-symbol diagnostics can produce.

Pool conventions (discovered from data/raw/):
  --pool US: 10 US ETFs (SPY, QQQ, IWM, DIA, GLD, GDX, XLF, XLK, TLT, NVDA)
  --pool CN: 4 CN futures with full daily history (kq_m_cffex_if/ih/ic/im)
  --pool CN_COMMODITY: 15 CN commodity futures
  --symbols A B C ...: explicit list (overrides --pool)

Output:
  Pooled per-cell table (n / hit_rate / uplift / CI) for:
    - direction × wick tercile
    - direction × swing tercile
    - direction × wick × swing  (sweet-spot search)
  Highlights cells with hit_uplift ≥ 10pp AND n ≥ 15 (sweet spots),
  and cells with hit_uplift ≤ -10pp AND n ≥ 15 (anti-spots / filter
  candidates).

Usage:
  uv run python scripts/analyze_sweet_spots_pool.py --pool US
  uv run python scripts/analyze_sweet_spots_pool.py --pool CN --instrument-class cn_futures
  uv run python scripts/analyze_sweet_spots_pool.py --symbols SPY QQQ IWM
  uv run python scripts/analyze_sweet_spots_pool.py --pool US --horizon 10 \\
      -o data/review/sweet_spots_pool_us_h10.csv
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
from engine.features.macd import macd
from engine.features.streams import compute_feature_streams
from engine.units.snapshot import compute_unit_metadata

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
N_BOOTSTRAP = 5000
RNG_SEED = 42
MIN_CELL_N = 15
UPLIFT_THRESHOLD_PP = 10.0

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

# Required instrument class per preset pool. Auto-applied when the user
# selects --pool unless they override with --instrument-class.
POOL_INSTRUMENT_CLASS: dict[str, str] = {
    "US": "us_equity",
    "CN": "cn_index_futures",
    "CN_COMMODITY": "cn_futures",
}


def load_bars(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text())
    df = pd.DataFrame(payload["bars"])
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


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
        # Forward-return horizon end date — used by OOS split to drop rows
        # whose forward-return bar spans across the train/test cutoff. Without
        # this, a signal on day cutoff-5 would have its hit computed from a
        # bar in the test period, leaking labels into train summaries
        # (codex 2026-05-25 review).
        forward_end_ts = bars["timestamp"].iloc[sig.candidate_bar_idx + horizon]
        records.append({
            "symbol": symbol,
            "date": sig.timestamp.date().isoformat(),
            "forward_end_date": forward_end_ts.date().isoformat(),
            "direction": sig.direction,
            "level": sig.level,
            "subtype": sig.subtype,
            "confidence": sig.confidence,
            "wick_ratio": ctx.get("candidate_rejection_wick_ratio"),
            "invalidation_level": ctx.get("invalidation_level"),
            "prior_swing_pct": ctx.get("prior_swing_distance_pct"),
            "volume_ratio": ctx.get("candidate_volume_ratio"),
            "signed_return": ret,
            "hit": ret > 0,
        })
    return pd.DataFrame(records)


def tercile_edges(series: pd.Series) -> list[float] | None:
    """Return the [33%, 67%] quantile cut points from `series`. None when
    series is too thin or has no variance."""
    notna = series.dropna()
    if len(notna) < 9:
        return None
    edges = [float(notna.quantile(1 / 3)), float(notna.quantile(2 / 3))]
    if edges[0] >= edges[1]:
        return None
    return edges


def apply_tercile_edges(series: pd.Series, edges: list[float], label_prefix: str) -> pd.Series:
    """Bin `series` into low/mid/high using externally-supplied edges.
    Values outside the train-derived range still get clipped into the
    nearest bin (low or high) — this is the standard treatment for
    test-set tail values that exceed train extrema."""
    labels = [f"{label_prefix}_low", f"{label_prefix}_mid", f"{label_prefix}_high"]
    lo, hi = edges
    result = pd.Series("na", index=series.index, dtype=object)
    notna_mask = series.notna()
    vals = series[notna_mask]
    bins = pd.Series(labels[0], index=vals.index, dtype=object)
    bins[vals >= lo] = labels[1]
    bins[vals >= hi] = labels[2]
    result.loc[notna_mask] = bins
    return result


def tercile_bucket(series: pd.Series, label_prefix: str) -> pd.Series:
    """Convenience wrapper: compute edges and apply in one shot.
    Used for non-OOS mode. For OOS mode, callers should derive edges
    from train explicitly and apply via apply_tercile_edges to both
    sides — otherwise test data leaks into bucket boundaries."""
    edges = tercile_edges(series)
    if edges is None:
        return pd.Series(["na"] * len(series), index=series.index, dtype=object)
    return apply_tercile_edges(series, edges, label_prefix)


def summarize(df: pd.DataFrame, group_cols: list[str], baseline_hit: float) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    g = df.groupby(group_cols, dropna=False)

    def _row(sub):
        rets = sub["signed_return"].to_numpy()
        ci_lo, ci_hi = bootstrap_ci(rets)
        return pd.Series({
            "n": int(len(sub)),
            "hit_rate_pct": float(sub["hit"].mean() * 100),
            "mean_ret_pct": float(sub["signed_return"].mean() * 100),
            "median_ret_pct": float(sub["signed_return"].median() * 100),
            "ci_lo_pct": ci_lo * 100,
            "ci_hi_pct": ci_hi * 100,
            "n_symbols": int(sub["symbol"].nunique()),
        })

    summary = g.apply(_row, include_groups=False).reset_index()
    summary["hit_uplift_pp"] = summary["hit_rate_pct"] - baseline_hit
    summary = summary.sort_values("hit_uplift_pp", ascending=False)
    return summary


def print_table(summary: pd.DataFrame, title: str, group_cols: list[str]) -> None:
    print(f"\n=== {title} ===")
    if summary.empty:
        print("(empty)")
        return
    out_cols = group_cols + ["n", "n_symbols", "hit_rate_pct", "hit_uplift_pp",
                              "mean_ret_pct", "median_ret_pct", "ci_lo_pct", "ci_hi_pct"]
    formatters = {
        "hit_rate_pct": "{:.1f}%".format,
        "hit_uplift_pp": "{:+.1f}pp".format,
        "mean_ret_pct": "{:+.2f}%".format,
        "median_ret_pct": "{:+.2f}%".format,
        "ci_lo_pct": "{:+.2f}%".format,
        "ci_hi_pct": "{:+.2f}%".format,
    }
    print(summary[out_cols].to_string(index=False, formatters=formatters))


def print_sweet_anti_spots(summary: pd.DataFrame, group_cols: list[str]) -> None:
    qualifying = summary[summary["n"] >= MIN_CELL_N]
    sweet = qualifying[qualifying["hit_uplift_pp"] >= UPLIFT_THRESHOLD_PP].copy()
    anti = qualifying[qualifying["hit_uplift_pp"] <= -UPLIFT_THRESHOLD_PP].copy()
    if not sweet.empty:
        print(f"\n  >>> SWEET SPOTS (n≥{MIN_CELL_N}, hit_uplift ≥ +{UPLIFT_THRESHOLD_PP}pp):")
        for _, row in sweet.iterrows():
            key = " / ".join(str(row[c]) for c in group_cols)
            print(f"    {key:<55s}  n={int(row['n']):>3d}  hit={row['hit_rate_pct']:.1f}% "
                  f"({row['hit_uplift_pp']:+.1f}pp)  "
                  f"mean={row['mean_ret_pct']:+.2f}%  CI [{row['ci_lo_pct']:+.2f}, {row['ci_hi_pct']:+.2f}]%")
    if not anti.empty:
        print(f"\n  <<< ANTI-SPOTS / filter candidates (n≥{MIN_CELL_N}, hit_uplift ≤ -{UPLIFT_THRESHOLD_PP}pp):")
        for _, row in anti.iterrows():
            key = " / ".join(str(row[c]) for c in group_cols)
            print(f"    {key:<55s}  n={int(row['n']):>3d}  hit={row['hit_rate_pct']:.1f}% "
                  f"({row['hit_uplift_pp']:+.1f}pp)  "
                  f"mean={row['mean_ret_pct']:+.2f}%  CI [{row['ci_lo_pct']:+.2f}, {row['ci_hi_pct']:+.2f}]%")


def main() -> int:
    p = argparse.ArgumentParser(description="Pool-level sweet-spot finder across multiple symbols")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--pool", choices=sorted(POOLS), help="preset symbol pool")
    grp.add_argument("--symbols", nargs="+", help="explicit symbol list")
    p.add_argument("--instrument-class", choices=["us_equity", "cn_futures", "cn_index_futures", "czce", "cn_metal_futures"],
                   default=None, dest="instrument_class",
                   help="calibration table; auto-inferred from --pool (US→us_equity, "
                        "CN/CN_COMMODITY→cn_futures), defaults to us_equity for --symbols. "
                        "Pass explicitly to override pool default.")
    p.add_argument("--bars-dir", type=Path, default=DEFAULT_BARS_DIR)
    p.add_argument("--horizon", type=int, default=20, choices=[5, 10, 20])
    p.add_argument("--oos-split", type=float, default=None,
                   help="train/test time split fraction (e.g. 0.6 = train first 60%% by date, "
                        "test last 40%%). When set, each sweet-spot table is replaced by a "
                        "train-vs-test comparison so consumers can see which spots generalize.")
    p.add_argument("--walk-forward", type=int, default=None,
                   help="expanding-window walk-forward validation with K time chunks "
                        "(K must be >= 3). For k in 1..K-1: train=chunks[0..k], "
                        "test=chunk[k]. Reports rules that pass +%g pp uplift on "
                        "EVERY test fold. Mutually exclusive with --oos-split."
                        % UPLIFT_THRESHOLD_PP)
    p.add_argument("-o", "--output", type=Path, help="write pooled per-signal CSV to this file")
    args = p.parse_args()
    if args.oos_split is not None and args.walk_forward is not None:
        print("ERROR: --oos-split and --walk-forward are mutually exclusive",
              file=sys.stderr)
        return 2

    symbols = POOLS[args.pool] if args.pool else args.symbols
    # Resolve instrument_class: explicit override > pool default > us_equity fallback
    if args.instrument_class is not None:
        instrument_class = args.instrument_class
        if args.pool and instrument_class != POOL_INSTRUMENT_CLASS.get(args.pool):
            print(f"WARNING: --pool {args.pool} normally uses "
                  f"--instrument-class {POOL_INSTRUMENT_CLASS[args.pool]} but caller "
                  f"override is {instrument_class}", file=sys.stderr)
    elif args.pool:
        instrument_class = POOL_INSTRUMENT_CLASS[args.pool]
    else:
        instrument_class = "us_equity"
    print(f"Pool: {len(symbols)} symbol(s) — {symbols}")
    print(f"Instrument class: {instrument_class}  Horizon: {args.horizon}d")

    frames = []
    for sym in symbols:
        path = args.bars_dir / f"{sym.lower()}_daily.json"
        if not path.exists():
            print(f"  {sym}: missing snapshot, skipped ({path})", file=sys.stderr)
            continue
        bars = load_bars(path)
        sym_df = build_signal_dataframe(sym, bars,
                                        instrument_class=instrument_class,
                                        horizon=args.horizon)
        print(f"  {sym}: {len(sym_df):>4d} signals")
        if not sym_df.empty:
            frames.append(sym_df)

    if not frames:
        print("\nERROR: no signals collected.", file=sys.stderr)
        return 1
    df = pd.concat(frames, ignore_index=True)
    print(f"\nTotal pooled signals: {len(df)} from {df['symbol'].nunique()} symbols")

    baseline_hit = float(df["hit"].mean() * 100)
    baseline_mean = float(df["signed_return"].mean() * 100)
    print(f"Baseline (all pooled signals): hit_rate={baseline_hit:.1f}%  mean={baseline_mean:+.2f}%")

    # Bucket assignment: depends on mode.
    #   - Default: terciles computed on FULL pool (the entire window IS
    #     the in-sample dataset).
    #   - --oos-split: terciles must be computed from TRAIN ONLY and
    #     applied to test — otherwise test feature distribution leaks
    #     into bucket boundaries, invalidating the OOS comparison
    #     (codex 2026-05-25 review).
    if args.oos_split is None:
        df["wick_bucket"] = tercile_bucket(df["wick_ratio"], "wick")
        df["swing_bucket"] = tercile_bucket(df["prior_swing_pct"], "swing")
        df["vol_bucket"] = tercile_bucket(df["volume_ratio"], "vol")

    report_specs = [
        (["direction", "subtype"], "Direction × subtype (MACD-native)"),
        (["direction", "wick_bucket"], "Direction × wick tercile"),
        (["direction", "swing_bucket"], "Direction × prior_swing tercile"),
        (["direction", "vol_bucket"], "Direction × candidate_volume_ratio tercile"),
        (["direction", "subtype", "swing_bucket"], "Direction × subtype × swing"),
        (["direction", "subtype", "wick_bucket"], "Direction × subtype × wick"),
        (["direction", "subtype", "vol_bucket"], "Direction × subtype × volume"),
        (["direction", "wick_bucket", "swing_bucket"], "Direction × wick × swing"),
        (["direction", "wick_bucket", "vol_bucket"], "Direction × wick × volume"),
        (["direction", "subtype", "wick_bucket", "swing_bucket"],
         "SWEET-SPOT SEARCH: direction × subtype × wick × swing"),
        (["direction", "wick_bucket", "swing_bucket", "vol_bucket"],
         "SWEET-SPOT SEARCH: direction × wick × swing × volume"),
    ]

    def _prep_split(train_candidate, test_chunk):
        """Apply leakage protections (horizon-overlap purge + train-only edges)
        to a (train_candidate, test_chunk) pair. Returns (train, test) with
        bucket columns annotated, or (None, None) if either side is unusable."""
        if train_candidate.empty or test_chunk.empty:
            return None, None
        cutoff_date = test_chunk["date"].min()
        train = train_candidate[train_candidate["forward_end_date"] < cutoff_date].copy()
        if train.empty:
            return None, None
        edges_local = {
            "wick_bucket": (tercile_edges(train["wick_ratio"]), "wick", "wick_ratio"),
            "swing_bucket": (tercile_edges(train["prior_swing_pct"]), "swing", "prior_swing_pct"),
            "vol_bucket": (tercile_edges(train["volume_ratio"]), "vol", "volume_ratio"),
        }
        test = test_chunk.copy()
        for bucket_col, (e, prefix, source_col) in edges_local.items():
            if e is None:
                train[bucket_col] = "na"
                test[bucket_col] = "na"
            else:
                train[bucket_col] = apply_tercile_edges(train[source_col], e, prefix)
                test[bucket_col] = apply_tercile_edges(test[source_col], e, prefix)
        return train, test

    def _stable_cells_in_split(train, test, report_specs_local, verbose=False, fold_label=""):
        """For one split, return dict[report_title -> set of cell-key tuples
        that pass +UPLIFT_THRESHOLD_PP on both train and test]."""
        if train is None or test is None:
            return {}
        train_baseline = float(train["hit"].mean() * 100) if len(train) else float("nan")
        test_baseline = float(test["hit"].mean() * 100) if len(test) else float("nan")
        out: dict[str, set] = {}
        for group_cols, title in report_specs_local:
            sub_train, sub_test = train, test
            for mtf_col in ("higher_relation", "lower_relation"):
                if mtf_col in group_cols:
                    sub_train = sub_train[sub_train[mtf_col].notna()]
                    sub_test = sub_test[sub_test[mtf_col].notna()]
            train_sum = summarize(sub_train, group_cols, train_baseline)
            test_sum = summarize(sub_test, group_cols, test_baseline)
            if train_sum.empty or test_sum.empty:
                out[title] = set()
                continue
            merged = train_sum.merge(test_sum, on=group_cols, how="outer",
                                     suffixes=("_train", "_test"))
            merged = merged.fillna({"n_train": 0, "n_test": 0,
                                    "hit_uplift_pp_train": 0.0,
                                    "hit_uplift_pp_test": 0.0})
            qualifying = merged[(merged["n_train"] >= MIN_CELL_N) &
                                (merged["n_test"] >= MIN_CELL_N) &
                                (merged["hit_uplift_pp_train"] >= UPLIFT_THRESHOLD_PP) &
                                (merged["hit_uplift_pp_test"] >= UPLIFT_THRESHOLD_PP)]
            cell_keys = {tuple(row[c] for c in group_cols) for _, row in qualifying.iterrows()}
            out[title] = cell_keys
            if verbose and not qualifying.empty:
                print(f"\n  [{fold_label}] {title} stable cells:")
                for _, row in qualifying.iterrows():
                    key = " / ".join(str(row[c]) for c in group_cols)
                    print(f"    {key}  train n={int(row['n_train'])} "
                          f"{row['hit_rate_pct_train']:.1f}% ({row['hit_uplift_pp_train']:+.1f}pp)  "
                          f"test n={int(row['n_test'])} {row['hit_rate_pct_test']:.1f}% "
                          f"({row['hit_uplift_pp_test']:+.1f}pp)")
        return out

    if args.walk_forward is not None:
        K = args.walk_forward
        if K < 3:
            print(f"ERROR: --walk-forward needs K >= 3 (got {K})", file=sys.stderr)
            return 2
        df_sorted = df.sort_values("date").reset_index(drop=True)
        chunk_size = len(df_sorted) // K
        if chunk_size < MIN_CELL_N:
            print(f"ERROR: walk-forward K={K} yields chunks of {chunk_size} signals "
                  f"each (< MIN_CELL_N={MIN_CELL_N}). Reduce K or grow the pool.",
                  file=sys.stderr)
            return 2
        chunks = [df_sorted.iloc[i * chunk_size:(i + 1) * chunk_size] for i in range(K - 1)]
        chunks.append(df_sorted.iloc[(K - 1) * chunk_size:])
        print(f"\nWalk-forward K={K}: chunk sizes {[len(c) for c in chunks]}")
        for i, c in enumerate(chunks):
            print(f"  chunk[{i}]: n={len(c)}, dates {c['date'].min()} → {c['date'].max()}")

        per_fold_stable: list[dict[str, set]] = []
        for k in range(1, K):
            train_candidate = pd.concat(chunks[:k], ignore_index=True)
            test_chunk = chunks[k]
            train, test = _prep_split(train_candidate, test_chunk)
            if train is None:
                print(f"\nFold {k}: unusable (train or test empty after purge)")
                per_fold_stable.append({})
                continue
            label = f"fold{k}: train {len(train)} ({train['date'].min()}→{train['date'].max()}) " \
                    f"test {len(test)} ({test['date'].min()}→{test['date'].max()})"
            print(f"\n{label}")
            stable = _stable_cells_in_split(train, test, report_specs,
                                            verbose=True, fold_label=f"fold{k}")
            per_fold_stable.append(stable)

        print("\n" + "=" * 70)
        print(f"WALK-FORWARD AGGREGATE: cells passing both-side +{UPLIFT_THRESHOLD_PP}pp uplift "
              f"AND n>={MIN_CELL_N} on ALL {K-1} test folds")
        print("=" * 70)
        all_titles = set()
        for s in per_fold_stable:
            all_titles.update(s.keys())
        any_stable = False
        for title in sorted(all_titles):
            sets = [s.get(title, set()) for s in per_fold_stable]
            if not sets or any(not s for s in sets):
                continue
            intersection = set.intersection(*sets)
            if intersection:
                any_stable = True
                print(f"\n{title}:")
                for cell in sorted(intersection):
                    print(f"  {' / '.join(str(c) for c in cell)}")
        if not any_stable:
            print("\n(no cell passed all folds — none of the discovered patterns "
                  "generalize across windows at the current K)")
        # Honor -o: write pooled CSV (same content as default mode) so the
        # CLI flag isn't silently ignored in walk-forward mode.
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(args.output, index=False)
            print(f"\nPer-signal pooled CSV → {args.output}", file=sys.stderr)
        return 0

    if args.oos_split is None:
        for group_cols, title in report_specs:
            summary = summarize(df, group_cols, baseline_hit)
            print_table(summary, title, group_cols)
            print_sweet_anti_spots(summary, group_cols)
    else:
        if not 0.1 <= args.oos_split <= 0.9:
            print("ERROR: --oos-split must be in [0.1, 0.9]", file=sys.stderr)
            return 2
        # Sort by date and split at the given fraction (by signal count,
        # not calendar days — keeps train/test sample sizes balanced).
        df_sorted = df.sort_values("date").reset_index(drop=True)
        cut_idx = int(len(df_sorted) * args.oos_split)
        cut_idx = max(1, min(cut_idx, len(df_sorted) - 1))
        train_candidate = df_sorted.iloc[:cut_idx]
        test = df_sorted.iloc[cut_idx:]
        if train_candidate.empty or test.empty:
            print(f"ERROR: --oos-split {args.oos_split} leaves "
                  f"train={len(train_candidate)} test={len(test)} — need at least 1 each. "
                  f"Pool {len(df_sorted)} signals is too small to split.",
                  file=sys.stderr)
            return 2
        # Drop train rows whose forward-return window crosses the cutoff —
        # otherwise their `hit` was computed from test-period bars, leaking
        # test labels into train summaries (codex 2026-05-25 review).
        cutoff_date = test["date"].min()
        train = train_candidate[train_candidate["forward_end_date"] < cutoff_date].copy()
        dropped = len(train_candidate) - len(train)
        if dropped > 0:
            print(f"  OOS: dropped {dropped} train signals whose forward-return "
                  f"window crossed cutoff {cutoff_date}", file=sys.stderr)
        if train.empty:
            print(f"ERROR: after horizon-overlap purge, train empty.", file=sys.stderr)
            return 2
        # Derive bucket edges from TRAIN ONLY, apply to both sides
        edges = {
            "wick_bucket": (tercile_edges(train["wick_ratio"]), "wick", "wick_ratio"),
            "swing_bucket": (tercile_edges(train["prior_swing_pct"]), "swing", "prior_swing_pct"),
            "vol_bucket": (tercile_edges(train["volume_ratio"]), "vol", "volume_ratio"),
        }
        train = train.copy()
        test = test.copy()
        for bucket_col, (e, prefix, source_col) in edges.items():
            if e is None:
                train[bucket_col] = "na"
                test[bucket_col] = "na"
            else:
                train[bucket_col] = apply_tercile_edges(train[source_col], e, prefix)
                test[bucket_col] = apply_tercile_edges(test[source_col], e, prefix)
        train_baseline = float(train["hit"].mean() * 100) if len(train) else float("nan")
        test_baseline = float(test["hit"].mean() * 100) if len(test) else float("nan")
        print(f"\nOOS split: train={len(train)} ({train['date'].min()}→{train['date'].max()}) "
              f"test={len(test)} ({test['date'].min()}→{test['date'].max()})")
        print(f"Train baseline hit: {train_baseline:.1f}%   Test baseline hit: {test_baseline:.1f}%")
        for group_cols, title in report_specs:
            train_sum = summarize(train, group_cols, train_baseline)
            test_sum = summarize(test, group_cols, test_baseline)
            # Join train + test on bucket keys; only show cells with test n >= MIN_CELL_N
            merged = train_sum.merge(test_sum, on=group_cols, how="outer",
                                     suffixes=("_train", "_test"))
            merged = merged.fillna({"n_train": 0, "n_test": 0,
                                    "hit_uplift_pp_train": 0.0, "hit_uplift_pp_test": 0.0,
                                    "hit_rate_pct_train": float("nan"),
                                    "hit_rate_pct_test": float("nan")})
            qualifying = merged[(merged["n_train"] >= MIN_CELL_N) &
                                (merged["n_test"] >= MIN_CELL_N)].copy()
            print(f"\n=== OOS: {title} (n_train≥{MIN_CELL_N} AND n_test≥{MIN_CELL_N}) ===")
            if qualifying.empty:
                print("(no cell meets both-side n threshold)")
                continue
            qualifying["train_to_test_hit_drift_pp"] = (
                qualifying["hit_rate_pct_test"] - qualifying["hit_rate_pct_train"]
            )
            qualifying = qualifying.sort_values("hit_uplift_pp_test", ascending=False)
            out_cols = group_cols + [
                "n_train", "hit_rate_pct_train", "hit_uplift_pp_train",
                "n_test", "hit_rate_pct_test", "hit_uplift_pp_test",
                "train_to_test_hit_drift_pp",
            ]
            formatters = {
                "hit_rate_pct_train": "{:.1f}%".format,
                "hit_rate_pct_test": "{:.1f}%".format,
                "hit_uplift_pp_train": "{:+.1f}pp".format,
                "hit_uplift_pp_test": "{:+.1f}pp".format,
                "train_to_test_hit_drift_pp": "{:+.1f}pp".format,
                "n_train": "{:.0f}".format,
                "n_test": "{:.0f}".format,
            }
            print(qualifying[out_cols].to_string(index=False, formatters=formatters))
            # Identify cells that hold up OOS: both sides above +10pp uplift
            holds_up = qualifying[(qualifying["hit_uplift_pp_train"] >= UPLIFT_THRESHOLD_PP) &
                                   (qualifying["hit_uplift_pp_test"] >= UPLIFT_THRESHOLD_PP)]
            if not holds_up.empty:
                print(f"\n  >>> STABLE SWEET SPOTS (both train and test uplift ≥ +{UPLIFT_THRESHOLD_PP}pp):")
                for _, row in holds_up.iterrows():
                    key = " / ".join(str(row[c]) for c in group_cols)
                    print(f"    {key:<55s}  train n={int(row['n_train'])} {row['hit_rate_pct_train']:.1f}% "
                          f"({row['hit_uplift_pp_train']:+.1f}pp)  "
                          f"test n={int(row['n_test'])} {row['hit_rate_pct_test']:.1f}% "
                          f"({row['hit_uplift_pp_test']:+.1f}pp)")
            # Collapses: train was sweet, test isn't
            collapses = qualifying[(qualifying["hit_uplift_pp_train"] >= UPLIFT_THRESHOLD_PP) &
                                    (qualifying["hit_uplift_pp_test"] < UPLIFT_THRESHOLD_PP)]
            if not collapses.empty:
                print(f"\n  XXX COLLAPSED (train sweet, test not):")
                for _, row in collapses.iterrows():
                    key = " / ".join(str(row[c]) for c in group_cols)
                    print(f"    {key:<55s}  train n={int(row['n_train'])} {row['hit_uplift_pp_train']:+.1f}pp  "
                          f"test n={int(row['n_test'])} {row['hit_uplift_pp_test']:+.1f}pp  "
                          f"DRIFT {row['train_to_test_hit_drift_pp']:+.1f}pp")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.oos_split is None:
            df.to_csv(args.output, index=False)
        else:
            # Re-assemble annotated train + test so the exported CSV keeps
            # the train-derived bucket labels and a `split` column for
            # consumer post-hoc filtering. Use locals from the if-branch
            # above (train/test already carry bucket cols).
            train_out = train.assign(split="train")
            test_out = test.assign(split="test")
            pd.concat([train_out, test_out], ignore_index=True).to_csv(args.output, index=False)
        print(f"\nPer-signal pooled CSV → {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
