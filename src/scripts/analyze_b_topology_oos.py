"""OOS + walk-forward validator for the B-topology v2 CSV.

Reads `data/review/cn_b_topology_signals_all_v2.csv` and applies the same
methodology as `analyze_sweet_spots_pool.py --oos-split / --walk-forward`,
but on B-topology cells (direction × lower_relation × higher_relation,
direction × subtype × higher_relation, etc.) instead of geometry terciles.

Bootstrap CI replication from sweet-spots pool (5000 reps, seed 42).

CLI:
  uv run python scripts/analyze_b_topology_oos.py \\
      --csv data/review/cn_b_topology_signals_all_v2.csv \\
      --horizon 20 --oos-split 0.6
  uv run python scripts/analyze_b_topology_oos.py \\
      --csv data/review/cn_b_topology_signals_all_v2.csv \\
      --horizon 20 --walk-forward 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

N_BOOTSTRAP = 5000
RNG_SEED = 42
MIN_CELL_N = 15
UPLIFT_THRESHOLD_PP = 10.0


def bootstrap_ci(x: np.ndarray, n_boot: int = N_BOOTSTRAP, alpha: float = 0.05):
    if len(x) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(RNG_SEED)
    means = rng.choice(x, size=(n_boot, len(x)), replace=True).mean(axis=1)
    return tuple(float(v) for v in np.quantile(means, [alpha / 2, 1 - alpha / 2]))


def summarize(df, group_cols, baseline_hit):
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
    return summary.sort_values("hit_uplift_pp", ascending=False)


REPORT_SPECS = [
    (["direction"], "Direction baseline"),
    (["direction", "subtype"], "Direction × subtype"),
    (["direction", "higher_relation"], "Direction × higher_relation"),
    (["direction", "lower_relation"], "Direction × lower_relation"),
    (["direction", "lower_relation", "higher_relation"],
     "Direction × lower × higher"),
    (["rule_id"], "Per rule_id (cn_futures policy)"),
]


def _stable_cells_in_split(train, test):
    out: dict[str, set] = {}
    train_baseline = float(train["hit"].mean() * 100) if len(train) else float("nan")
    test_baseline = float(test["hit"].mean() * 100) if len(test) else float("nan")
    for group_cols, title in REPORT_SPECS:
        train_sum = summarize(train, group_cols, train_baseline)
        test_sum = summarize(test, group_cols, test_baseline)
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
        keys = {tuple(row[c] for c in group_cols) for _, row in qualifying.iterrows()}
        out[title] = keys
        if not qualifying.empty:
            print(f"  [{title}]")
            for _, row in qualifying.iterrows():
                k = " / ".join(str(row[c]) for c in group_cols)
                print(f"    {k}  train n={int(row['n_train'])} "
                      f"{row['hit_rate_pct_train']:.1f}% "
                      f"({row['hit_uplift_pp_train']:+.1f}pp)  "
                      f"test n={int(row['n_test'])} "
                      f"{row['hit_rate_pct_test']:.1f}% "
                      f"({row['hit_uplift_pp_test']:+.1f}pp)")
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--horizon", type=int, default=20)
    p.add_argument("--oos-split", type=float, default=None)
    p.add_argument("--walk-forward", type=int, default=None)
    args = p.parse_args()

    if args.oos_split is not None and args.walk_forward is not None:
        print("ERROR: --oos-split and --walk-forward are mutually exclusive", file=sys.stderr)
        return 2
    if args.oos_split is not None and not (0.1 <= args.oos_split <= 0.9):
        print(f"ERROR: --oos-split must be in [0.1, 0.9] (got {args.oos_split})", file=sys.stderr)
        return 2
    if args.walk_forward is not None and args.walk_forward < 3:
        print(f"ERROR: --walk-forward needs K >= 3 to produce ≥ 2 test folds (got {args.walk_forward})",
              file=sys.stderr)
        return 2

    df = pd.read_csv(args.csv)
    df = df[df["horizon"] == args.horizon].copy()
    if df.empty:
        print(f"ERROR: no rows at horizon={args.horizon}", file=sys.stderr)
        return 1
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    print(f"Loaded {len(df)} signals at h={args.horizon} "
          f"({df['date'].min().date()} → {df['date'].max().date()})")

    baseline_hit = float(df["hit"].mean() * 100)
    print(f"Baseline hit_rate={baseline_hit:.1f}%  "
          f"mean={df['signed_return'].mean()*100:+.2f}%")

    if args.oos_split is None and args.walk_forward is None:
        for group_cols, title in REPORT_SPECS:
            s = summarize(df, group_cols, baseline_hit)
            print(f"\n=== {title} ===")
            if s.empty:
                print("(empty)"); continue
            print(s.to_string(index=False))
        return 0

    # Horizon-overlap purge: each row's signed_return was computed `horizon`
    # bars after the signal date. Without dropping train rows whose forward
    # window crosses into the test period, train hit/mean labels leak test
    # prices (codex 2026-05-26).
    #
    # The B-topology CSV lacks a `forward_end_date` column (backtest_cn_b_
    # topology.py predates that fix). We use a CALENDAR heuristic with a
    # buffer sized for the worst-case CN closure (Chinese New Year ≈ 9
    # calendar days closed + horizon trading days):
    #   buffer = horizon × 3 calendar days + 14 (CNY safety)
    # For h=20: ~74 days; for h=5: ~29 days; for h=10: ~44 days. Conservative.
    # Caveat: this over-purges in calendar-dense periods. For perfect
    # accuracy regen the CSV with forward_end_date and switch to that.
    purge_gap_days = pd.Timedelta(days=args.horizon * 3 + 14)

    def _purge_overlap(train_chunk, test_chunk):
        if train_chunk.empty or test_chunk.empty:
            return train_chunk
        cutoff = test_chunk["date"].min()
        kept = train_chunk[train_chunk["date"] < cutoff - purge_gap_days]
        dropped = len(train_chunk) - len(kept)
        if dropped > 0:
            print(f"    purged {dropped} train rows within {purge_gap_days.days} days of test cutoff {cutoff.date()}")
        return kept

    if args.walk_forward is not None:
        K = args.walk_forward
        chunk_size = len(df) // K
        chunks = [df.iloc[i * chunk_size:(i + 1) * chunk_size] for i in range(K - 1)]
        chunks.append(df.iloc[(K - 1) * chunk_size:])
        print(f"\nWalk-forward K={K}: chunk sizes {[len(c) for c in chunks]}")
        for i, c in enumerate(chunks):
            print(f"  chunk[{i}]: n={len(c)}, "
                  f"dates {c['date'].min().date()} → {c['date'].max().date()}")

        per_fold = []
        for k in range(1, K):
            train_cand = pd.concat(chunks[:k], ignore_index=True)
            test = chunks[k]
            train = _purge_overlap(train_cand, test)
            print(f"\nfold{k}: train n={len(train)} (purged from {len(train_cand)}) "
                  f"({train['date'].min().date() if len(train) else 'empty'}→"
                  f"{train['date'].max().date() if len(train) else 'empty'})  "
                  f"test n={len(test)} "
                  f"({test['date'].min().date()}→{test['date'].max().date()})")
            per_fold.append(_stable_cells_in_split(train, test))

        print("\n" + "=" * 70)
        print(f"WALK-FORWARD AGGREGATE: stable cells passing both-side "
              f"+{UPLIFT_THRESHOLD_PP}pp uplift AND n>={MIN_CELL_N} on ALL {K-1} folds")
        print("=" * 70)
        all_titles = set()
        for s in per_fold:
            all_titles.update(s.keys())
        any_stable = False
        for title in sorted(all_titles):
            sets = [s.get(title, set()) for s in per_fold]
            if not sets or any(not s for s in sets):
                continue
            inter = set.intersection(*sets)
            if inter:
                any_stable = True
                print(f"\n{title}:")
                for cell in sorted(inter):
                    print(f"  {' / '.join(str(c) for c in cell)}")
        if not any_stable:
            print("\n(no cell passed all folds)")
        return 0

    # --oos-split (with horizon-overlap purge — codex 2026-05-26)
    cut_idx = int(len(df) * args.oos_split)
    train_cand = df.iloc[:cut_idx].copy()
    test = df.iloc[cut_idx:].copy()
    train = _purge_overlap(train_cand, test)
    print(f"\nOOS split @ {args.oos_split}: train n={len(train)} (purged from {len(train_cand)}) "
          f"({train['date'].min().date() if len(train) else 'empty'}→"
          f"{train['date'].max().date() if len(train) else 'empty'})  "
          f"test n={len(test)} "
          f"({test['date'].min().date()}→{test['date'].max().date()})")

    train_baseline = float(train["hit"].mean() * 100)
    test_baseline = float(test["hit"].mean() * 100)
    print(f"  train baseline hit={train_baseline:.1f}%  "
          f"test baseline hit={test_baseline:.1f}%")

    for group_cols, title in REPORT_SPECS:
        train_sum = summarize(train, group_cols, train_baseline)
        test_sum = summarize(test, group_cols, test_baseline)
        if train_sum.empty or test_sum.empty:
            continue
        merged = train_sum.merge(test_sum, on=group_cols, how="outer",
                                 suffixes=("_train", "_test"))
        merged = merged.fillna({"n_train": 0, "n_test": 0,
                                "hit_uplift_pp_train": 0.0,
                                "hit_uplift_pp_test": 0.0,
                                "mean_ret_pct_train": 0.0,
                                "mean_ret_pct_test": 0.0,
                                "hit_rate_pct_train": 0.0,
                                "hit_rate_pct_test": 0.0})
        print(f"\n=== {title} (train vs test) ===")
        cols = group_cols + ["n_train", "hit_rate_pct_train", "hit_uplift_pp_train",
                             "mean_ret_pct_train",
                             "n_test", "hit_rate_pct_test", "hit_uplift_pp_test",
                             "mean_ret_pct_test"]
        view = merged[cols].copy()
        for c in ("hit_rate_pct_train", "hit_rate_pct_test",
                  "hit_uplift_pp_train", "hit_uplift_pp_test",
                  "mean_ret_pct_train", "mean_ret_pct_test"):
            view[c] = view[c].astype(float).round(2)
        for c in ("n_train", "n_test"):
            view[c] = view[c].astype(int)
        print(view.to_string(index=False))

        stable = merged[(merged["n_train"] >= MIN_CELL_N) &
                        (merged["n_test"] >= MIN_CELL_N) &
                        (merged["hit_uplift_pp_train"] >= UPLIFT_THRESHOLD_PP) &
                        (merged["hit_uplift_pp_test"] >= UPLIFT_THRESHOLD_PP)]
        if not stable.empty:
            print(f"  >>> STABLE cells (both sides +{UPLIFT_THRESHOLD_PP}pp, n>={MIN_CELL_N}):")
            for _, row in stable.iterrows():
                k = " / ".join(str(row[c]) for c in group_cols)
                print(f"    {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
