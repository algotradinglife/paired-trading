"""Reproduce crosspool-walkforward-report-2026-05-31.

Filter: bottom × higher_relation=opposing across 5 Scheme-B pools.
Split chronologically into K=3 equal chunks, then do two OOS folds:
  Fold 1: train Chunk 0, test (OOS) Chunk 1
  Fold 2: train Chunk 0+1, test (OOS) Chunk 2

Metrics per fold (test set):
  n, EV/signal, Sharpe, max drawdown (1R per signal, equal-weight), max
  consecutive losses, win rate, and per-pool breakdown.

The report's n=102 came from a much narrower filter than our current
rr_b_*.csv files; this script reports current totals and lets the reader
judge whether the structural conclusion still holds.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd


def _default_review_dir() -> Path:
    """Default review dir; honors DERIVED_ROOT env var, falls back to data/review."""
    derived = os.environ.get("DERIVED_ROOT")
    if derived:
        return Path(derived) / "paired-trading" / "src-data-review"
    return Path("data/review")


POOL_TO_CSV = {
    "CN_METAL":  "rr_b_cn_metal.csv",
    "CN_AGRI":   "rr_b_cn_agri.csv",
    "CN_INDEX":  "rr_b_cn_index.csv",
    "US_EQUITY": "rr_b_us_equity.csv",
    "US_MACRO":  "rr_b_us_macro.csv",
}


def load_pool_trades(review_dir: Path) -> pd.DataFrame:
    frames = []
    for pool, csv in POOL_TO_CSV.items():
        df = pd.read_csv(review_dir / csv)
        df["pool"] = pool
        frames.append(df)
    all_df = pd.concat(frames, ignore_index=True)
    bot_opp = all_df[(all_df.direction == "bottom") &
                     (all_df.higher_relation == "opposing")].copy()
    bot_opp["date"] = pd.to_datetime(bot_opp["date"])
    return bot_opp.sort_values("date").reset_index(drop=True)


def metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return dict(n=0, ev=float("nan"), sharpe=float("nan"),
                    maxdd=float("nan"), max_losses=0, win=float("nan"))
    r = df.realized_r.values
    ev = r.mean()
    sd = r.std(ddof=1) if len(r) > 1 else float("nan")
    sharpe = ev / sd * np.sqrt(len(r)) if sd and sd > 0 else float("nan")
    cumulative = np.cumsum(r)
    peak = np.maximum.accumulate(cumulative)
    dd = cumulative - peak
    maxdd = dd.min()
    # consecutive losses
    is_loss = r < 0
    max_streak = cur = 0
    for x in is_loss:
        cur = cur + 1 if x else 0
        max_streak = max(max_streak, cur)
    win_rate = (r > 0).mean() * 100
    return dict(n=len(r), ev=ev, sharpe=sharpe, maxdd=maxdd,
                max_losses=max_streak, win=win_rate)


def per_pool_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for pool, sub in df.groupby("pool"):
        rows.append(dict(pool=pool, n=len(sub), ev=sub.realized_r.mean()))
    return pd.DataFrame(rows).sort_values("ev", ascending=False).reset_index(drop=True)


def fmt_metrics(m: dict, label: str) -> str:
    return (f"  {label:18s} n={m['n']:4d}  EV={m['ev']:+.3f}R  Sharpe={m['sharpe']:5.2f}  "
            f"DD={m['maxdd']:+.2f}R  maxL={m['max_losses']:2d}  win={m['win']:5.1f}%")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--review-dir", type=Path, default=_default_review_dir(),
                   help="review CSV dir (env: DERIVED_ROOT → "
                        "$DERIVED_ROOT/paired-trading/src-data-review)")
    args = p.parse_args()

    df = load_pool_trades(args.review_dir)
    n = len(df)
    print(f"Loaded {n} bot×opp trades across {df.pool.nunique()} pools "
          f"({df.date.min().date()} → {df.date.max().date()})")
    print(f"Report baseline n=102; current n={n} (×{n/102:.1f})")

    K = 3
    chunk_size = n // K
    cuts = [0, chunk_size, 2 * chunk_size, n]
    chunks = [df.iloc[cuts[i]:cuts[i+1]].copy() for i in range(K)]
    for i, c in enumerate(chunks):
        print(f"  Chunk {i}: n={len(c)}  {c.date.iloc[0].date()} → {c.date.iloc[-1].date()}")

    print("\n=== In-Sample (all data) ===")
    print(fmt_metrics(metrics(df), "IS"))
    print("\nPool breakdown (IS):")
    print(per_pool_breakdown(df).to_string(index=False))

    print("\n=== Fold 1: train chunk0, test chunk1 ===")
    test1 = chunks[1]
    print(fmt_metrics(metrics(test1), "Fold1 OOS"))
    print("Pool breakdown (Fold1 OOS):")
    print(per_pool_breakdown(test1).to_string(index=False))

    print("\n=== Fold 2: train chunks0+1, test chunk2 ===")
    test2 = chunks[2]
    print(fmt_metrics(metrics(test2), "Fold2 OOS"))
    print("Pool breakdown (Fold2 OOS):")
    print(per_pool_breakdown(test2).to_string(index=False))

    print("\n=== §4 — IS vs OOS Comparison ===")
    is_m = metrics(df)
    f1m = metrics(test1)
    f2m = metrics(test2)
    print(f"  EV    IS=+{is_m['ev']:.3f}R   F1=+{f1m['ev']:.3f}R   F2=+{f2m['ev']:.3f}R")
    print(f"  Sharpe IS={is_m['sharpe']:.2f}    F1={f1m['sharpe']:.2f}    F2={f2m['sharpe']:.2f}")
    print(f"  MaxDD IS={is_m['maxdd']:.2f}R    F1={f1m['maxdd']:.2f}R    F2={f2m['maxdd']:.2f}R")
    print(f"  Win%  IS={is_m['win']:.1f}     F1={f1m['win']:.1f}     F2={f2m['win']:.1f}")

    # Verdict
    f1_pass_ev = f1m["ev"] > 0
    f2_pass_ev = f2m["ev"] > 0
    f1_pass_sharpe = f1m["sharpe"] > 0.6
    f2_pass_sharpe = f2m["sharpe"] > 0.6

    print("\n=== Verdict ===")
    print(f"  Folds with EV > 0    : {sum([f1_pass_ev, f2_pass_ev])}/2")
    print(f"  Folds with Sharpe>0.6: {sum([f1_pass_sharpe, f2_pass_sharpe])}/2")
    pp1 = per_pool_breakdown(test1)
    pp2 = per_pool_breakdown(test2)
    pos1 = (pp1.ev > 0).sum()
    pos2 = (pp2.ev > 0).sum()
    print(f"  Pools positive F1    : {pos1}/{len(pp1)}")
    print(f"  Pools positive F2    : {pos2}/{len(pp2)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
