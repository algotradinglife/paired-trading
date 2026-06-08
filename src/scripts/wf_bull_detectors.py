"""Walk-forward K=3 OOS validation for DIF>0 bull-cycle detectors.

Combines 6 Scheme B pool backtests, filters to bull-detector signals
(intra_cycle_bull_*) with h=opposing, and runs a K-fold time-split
to estimate OOS EV stability.

Test design (pre-registered):
  - Cell: direction=bottom, higher_relation=opposing, sig_level in {bull_dea, bull_hist, bull_slope}
  - K=3 folds (chronological; fold boundaries shared across pools)
  - Metric: mean realized_r per fold (EV in R)
  - Claim: bull detector EV > 0 on fold1 and fold2
  - MIN_FOLD_N = 5 per fold for a judgment (small-n caveat noted)

Input CSVs (from backtest_rr_pool.py --pool <P> -o <path>):
  data/review/rr_wf_cn_index.csv
  data/review/rr_wf_cn_agri.csv    (or rr_czce_bull.csv as fallback)
  data/review/rr_wf_cn_metal.csv   (or rr_cn_metal_bull.csv as fallback)
  data/review/rr_wf_us_equity.csv
  data/review/rr_wf_us_macro.csv
  data/review/rr_wf_cn_bond.csv

Usage:
  uv run python scripts/wf_bull_detectors.py
  uv run python scripts/wf_bull_detectors.py --k 3 --pool-label all_6
  uv run python scripts/wf_bull_detectors.py --include-non-opposing
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _default_review_dir() -> Path:
    """Default review dir; honors DERIVED_ROOT env var, falls back to src/data/review."""
    derived = os.environ.get("DERIVED_ROOT")
    if derived:
        return Path(derived) / "paired-trading" / "src-data-review"
    return Path(__file__).resolve().parents[1] / "data" / "review"


DATA_DIR = _default_review_dir()

BULL_LEVELS = ["intra_cycle_bull_dea", "intra_cycle_bull_hist", "intra_cycle_bull_slope"]
BULL_LABEL = {"intra_cycle_bull_dea": "DEAD+", "intra_cycle_bull_hist": "HICD+",
              "intra_cycle_bull_slope": "DIFSR+"}

# CSV candidates: new WF-specific files first, fall back to earlier runs
POOL_CSV_CANDIDATES: dict[str, list[str]] = {
    "CN_INDEX":  ["rr_wf_cn_index.csv"],
    "CN_AGRI":   ["rr_wf_cn_agri.csv"],
    "CN_METAL":  ["rr_wf_cn_metal.csv", "rr_cn_metal_bull.csv"],
    "US_EQUITY": ["rr_wf_us_equity.csv"],
    "US_MACRO":  ["rr_wf_us_macro.csv"],
    "CN_BOND":   ["rr_wf_cn_bond.csv"],
}

N_BOOTSTRAP = 2000
RNG_SEED = 42
MIN_FOLD_N = 5


def bootstrap_ci(x: np.ndarray, n_boot: int = N_BOOTSTRAP, alpha: float = 0.05):
    if len(x) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(RNG_SEED)
    means = rng.choice(x, size=(n_boot, len(x)), replace=True).mean(axis=1)
    return tuple(float(v) for v in np.quantile(means, [alpha / 2, 1 - alpha / 2]))


def ev_summary(x: np.ndarray) -> str:
    if len(x) == 0:
        return "n=0 —"
    lo, hi = bootstrap_ci(x)
    hit = (x > 0).mean() * 100
    return f"n={len(x)}  EV={x.mean():+.3f}R  CI=[{lo:+.3f},{hi:+.3f}]  hit={hit:.0f}%"


def load_pools(include_pools: list[str]) -> pd.DataFrame:
    frames = []
    missing = []
    for pool in include_pools:
        candidates = POOL_CSV_CANDIDATES.get(pool, [])
        loaded = False
        for fname in candidates:
            p = DATA_DIR / fname
            if p.exists():
                df = pd.read_csv(p)
                df["pool"] = pool
                frames.append(df)
                print(f"  {pool:12s}: {len(df):4d} trades  ({fname})")
                loaded = True
                break
        if not loaded:
            missing.append(pool)
    if missing:
        print(f"  MISSING pools: {missing}", file=sys.stderr)
    if not frames:
        print("ERROR: no CSV data found", file=sys.stderr)
        sys.exit(1)
    combined = pd.concat(frames, ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"])
    return combined


def time_folds(df: pd.DataFrame, k: int) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """Return K-1 (train, test) folds using chronological splits.

    Fold boundaries are set at equal quantiles of the sorted date series.
    Each test set is one chronological chunk; train is everything before it.
    For K=3: fold1 train=first-third, test=second-third;
              fold2 train=first-two-thirds, test=last-third.
    """
    dates_sorted = df["date"].sort_values().values
    boundaries = [dates_sorted[int(len(dates_sorted) * i / k)] for i in range(1, k)]
    folds = []
    for boundary in boundaries:
        train = df[df["date"] < boundary].copy()
        test_end = boundaries[boundaries.index(boundary) + 1] if boundaries.index(boundary) + 1 < len(boundaries) else df["date"].max() + pd.Timedelta(days=1)
        test = df[(df["date"] >= boundary) & (df["date"] < test_end)].copy()
        folds.append((train, test))
    return folds


def pool_oos_breakdown(cell: pd.DataFrame, k: int, pools: list[str]) -> None:
    """Per-pool OOS EV using fold boundaries computed from the input cell."""
    dates_sorted = cell["date"].sort_values().values
    if len(dates_sorted) < k:
        return
    boundaries = [dates_sorted[int(len(dates_sorted) * i / k)] for i in range(1, k)]

    pool_oos: dict[str, list[float]] = {p: [] for p in pools}
    for fi, boundary in enumerate(boundaries, 1):
        if fi < len(boundaries):
            next_b = boundaries[fi]
            test = cell[(cell["date"] >= boundary) & (cell["date"] < next_b)]
        else:
            test = cell[cell["date"] >= boundary]
        for pool in pools:
            vals = test[test["pool"] == pool]["realized_r"].values
            pool_oos[pool].extend(vals.tolist())

    print(f"\n  {'Pool':<14} {'n':>4}  {'OOS EV':>9}  {'hit%':>5}")
    print("  " + "-" * 36)
    for pool in pools:
        vals = np.array(pool_oos[pool])
        if len(vals) == 0:
            print(f"  {pool:<14} {'0':>4}  {'—':>9}  {'—':>5}")
        else:
            ev = vals.mean()
            hit = (vals > 0).mean() * 100
            print(f"  {pool:<14} {len(vals):>4}  {ev:>+9.3f}R  {hit:>4.0f}%")


def run_wf(df: pd.DataFrame, k: int, cell_filter, cell_name: str):
    """Run K-fold WF on filtered data. Prints per-fold results."""
    cell = cell_filter(df)
    if len(cell) == 0:
        print(f"  {cell_name}: no signals")
        return

    print(f"\n  {cell_name}  (IS n={len(cell)}, EV={cell['realized_r'].mean():+.3f}R)")
    print(f"  {'IS':>6}: {ev_summary(cell['realized_r'].values)}")

    dates_sorted = cell["date"].sort_values().values
    if len(dates_sorted) < k:
        print(f"  Too few signals ({len(dates_sorted)}) for K={k} folds")
        return

    boundaries = [dates_sorted[int(len(dates_sorted) * i / k)] for i in range(1, k)]
    all_test = []
    for fi, boundary in enumerate(boundaries, 1):
        train = cell[cell["date"] < boundary]
        if fi < len(boundaries):
            next_boundary = boundaries[fi]
            test = cell[(cell["date"] >= boundary) & (cell["date"] < next_boundary)]
        else:
            test = cell[cell["date"] >= boundary]

        train_r = train["realized_r"].values
        test_r = test["realized_r"].values
        all_test.append(test_r)

        train_str = f"train n={len(train)} EV={train_r.mean():+.3f}R" if len(train) else "train n=0"
        if len(test_r) < MIN_FOLD_N:
            test_str = f"test n={len(test_r)} INSUFFICIENT (< {MIN_FOLD_N})"
        else:
            lo, hi = bootstrap_ci(test_r)
            test_str = f"test n={len(test_r)} EV={test_r.mean():+.3f}R CI=[{lo:+.3f},{hi:+.3f}]"

        label = f"  fold{fi} (cutoff {pd.Timestamp(boundary).date()}):"
        print(f"  {label:<42} {train_str:<35} {test_str}")

    # Combined OOS: all test folds concatenated
    all_test_r = np.concatenate(all_test) if all_test else np.array([])
    if len(all_test_r) > 0:
        lo, hi = bootstrap_ci(all_test_r)
        pass_fail = "PASS" if all_test_r.mean() > 0 else "FAIL"
        n_pass = sum(t.mean() > 0 for t in all_test if len(t) >= MIN_FOLD_N)
        n_eligible = sum(1 for t in all_test if len(t) >= MIN_FOLD_N)
        print(f"  Combined OOS: {ev_summary(all_test_r)}  → {pass_fail} ({n_pass}/{n_eligible} folds positive)")


def main() -> int:
    p = argparse.ArgumentParser(description="Walk-forward K=3 OOS for bull-cycle detectors")
    p.add_argument("--k", type=int, default=3, help="number of folds (default 3)")
    p.add_argument("--include-non-opposing", action="store_true",
                   help="include h!=opposing signals (default: opposing only)")
    p.add_argument("--pools", nargs="+", default=list(POOL_CSV_CANDIDATES),
                   choices=list(POOL_CSV_CANDIDATES), metavar="POOL")
    args = p.parse_args()

    print(f"Walk-forward OOS: bull-cycle detectors  K={args.k}")
    print(f"Pools: {args.pools}")
    print(f"Filter: bottom × {'all h' if args.include_non_opposing else 'h=opposing'}")
    print()

    print("Loading pool CSVs:")
    df = load_pools(args.pools)
    print(f"\nTotal loaded: {len(df)} trades across {df['symbol'].nunique()} symbols")
    print(f"Date range: {df['date'].min().date()} → {df['date'].max().date()}")

    # Base cell: bottom signals only
    if not args.include_non_opposing:
        base = df[(df["direction"] == "bottom") & (df["higher_relation"] == "opposing")].copy()
        cell_suffix = " (h=opposing)"
    else:
        base = df[df["direction"] == "bottom"].copy()
        cell_suffix = " (all h)"

    print(f"\nBottom signals{cell_suffix}: {len(base)} total")

    # ---- Per-level analysis ----
    print("\n" + "=" * 70)
    print(f"PER-DETECTOR WALK-FORWARD  K={args.k}")
    print("=" * 70)
    for level in BULL_LEVELS:
        label = BULL_LABEL[level]
        run_wf(base, args.k,
               lambda d, lv=level: d[d["sig_level"] == lv],
               f"{label} ({level})")

    # ---- Combined bull detectors ----
    print("\n" + "=" * 70)
    print("COMBINED BULL DETECTORS (all 3 levels)")
    print("=" * 70)
    run_wf(base, args.k,
           lambda d: d[d["sig_level"].isin(BULL_LEVELS)],
           "all_bull_combined")

    # ---- Per-pool OOS breakdown (combined bull) ----
    print("\n" + "=" * 70)
    print("PER-POOL OOS — combined bull (fold boundaries from combined set)")
    print("=" * 70)
    bull_combined = base[base["sig_level"].isin(BULL_LEVELS)].copy()
    if len(bull_combined) >= args.k:
        pool_oos_breakdown(bull_combined, args.k, args.pools)

    # ---- Per-pool OOS breakdown per detector ----
    print("\n" + "=" * 70)
    print("PER-POOL OOS — per detector (fold boundaries from detector set)")
    print("=" * 70)
    for level in BULL_LEVELS:
        lbl = BULL_LABEL[level]
        det_cell = base[base["sig_level"] == level].copy()
        if len(det_cell) < args.k:
            print(f"\n  {lbl}: insufficient data (n={len(det_cell)} < k={args.k})")
            continue
        print(f"\n  {lbl}:")
        pool_oos_breakdown(det_cell, args.k, args.pools)

    # ---- Comparison baseline: heap (intra_cycle) same filter ----
    print("\n" + "=" * 70)
    print("REFERENCE: heap (intra_cycle) for comparison")
    print("=" * 70)
    run_wf(base, args.k,
           lambda d: d[d["sig_level"] == "intra_cycle"],
           "heap (intra_cycle)")

    # ---- Cross-pool per-detector summary ----
    print("\n" + "=" * 70)
    print("PER-POOL PER-DETECTOR SUMMARY (in-sample, h=opposing or all-h filter)")
    print("=" * 70)
    bull_base = base[base["sig_level"].isin(BULL_LEVELS)]
    if len(bull_base) == 0:
        print("  No bull signals in filtered set.")
        return 0
    summary = bull_base.groupby(["pool", "sig_level"])["realized_r"].agg(
        n="count", ev="mean"
    ).reset_index()
    summary = summary.sort_values(["sig_level", "pool"])
    for _, row in summary.iterrows():
        lbl = BULL_LABEL.get(row["sig_level"], row["sig_level"])
        print(f"  {row['pool']:<14} {lbl:<8} n={int(row['n']):3d}  EV={row['ev']:+.3f}R")

    return 0


if __name__ == "__main__":
    sys.exit(main())
