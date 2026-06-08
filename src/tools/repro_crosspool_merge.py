"""Reproduce crosspool-merge-report-2026-05-31.

5 pools (CN_METAL/CN_AGRI/CN_INDEX/US_EQUITY/US_MACRO), bottom×opposing.
Verify:
  §1 — pool contributions (total R, EV, share)
  §1.5 — annual portfolio EV
  §2 — pairwise monthly R correlations (US×US co-move, CN_AGRI×US_EQUITY hedge)
  §4 — top-5 2-pool combinations by Sharpe
"""
from __future__ import annotations

import argparse
import os
from itertools import combinations
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


def load_universe(review_dir: Path) -> pd.DataFrame:
    frames = []
    for pool, csv in POOL_TO_CSV.items():
        df = pd.read_csv(review_dir / csv)
        df["pool"] = pool
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df = df[(df.direction == "bottom") & (df.higher_relation == "opposing")].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.to_period("M")
    return df.sort_values("date").reset_index(drop=True)


def pool_contributions(df: pd.DataFrame) -> pd.DataFrame:
    total = df.realized_r.sum()
    rows = []
    for pool, sub in df.groupby("pool"):
        rows.append(dict(
            pool=pool, n=len(sub),
            total_r=sub.realized_r.sum(),
            ev=sub.realized_r.mean(),
            share_pct=100 * sub.realized_r.sum() / total if total else 0,
        ))
    out = pd.DataFrame(rows).sort_values("total_r", ascending=False).reset_index(drop=True)
    return out


def annual_portfolio(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for year, sub in df.groupby("year"):
        rows.append(dict(year=int(year), n=len(sub),
                         ev=sub.realized_r.mean(),
                         total_r=sub.realized_r.sum()))
    return pd.DataFrame(rows).sort_values("year").reset_index(drop=True)


def monthly_r_per_pool(df: pd.DataFrame) -> pd.DataFrame:
    pivot = df.pivot_table(index="month", columns="pool", values="realized_r", aggfunc="sum").fillna(0)
    return pivot


def correlation_matrix(monthly: pd.DataFrame) -> pd.DataFrame:
    return monthly.corr().round(3)


def two_pool_sharpe(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    pools = sorted(df.pool.unique())
    for a, b in combinations(pools, 2):
        sub = df[df.pool.isin([a, b])]
        r = sub.realized_r.values
        ev = r.mean()
        sd = r.std(ddof=1) if len(r) > 1 else float("nan")
        sharpe = ev / sd * np.sqrt(len(r)) if sd and sd > 0 else float("nan")
        sharpe_per_signal = ev / sd if sd and sd > 0 else float("nan")
        rows.append(dict(pool_a=a, pool_b=b, n=len(sub), ev=ev, std=sd,
                         sharpe_per_sig=sharpe_per_signal, sharpe_total=sharpe))
    return pd.DataFrame(rows).sort_values("sharpe_per_sig", ascending=False).reset_index(drop=True)


def portfolio_sharpe(df: pd.DataFrame) -> float:
    r = df.realized_r.values
    sd = r.std(ddof=1) if len(r) > 1 else float("nan")
    return r.mean() / sd if sd and sd > 0 else float("nan")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--review-dir", type=Path, default=_default_review_dir(),
                   help="review CSV dir (env: DERIVED_ROOT → "
                        "$DERIVED_ROOT/paired-trading/src-data-review)")
    args = p.parse_args()

    df = load_universe(args.review_dir)
    print(f"Loaded n={len(df)} bot×opp trades  ({df.date.min().date()} → {df.date.max().date()})")
    print(f"Report baseline n=102; current n={len(df)} (×{len(df)/102:.1f})\n")

    print("=== §1 — Pool Contributions ===")
    pc = pool_contributions(df)
    pc_print = pc.copy()
    pc_print["total_r"] = pc_print["total_r"].apply(lambda x: f"{x:+.2f}R")
    pc_print["ev"]      = pc_print["ev"].apply(lambda x: f"{x:+.3f}R")
    pc_print["share_pct"] = pc_print["share_pct"].apply(lambda x: f"{x:+.1f}%")
    print(pc_print.to_string(index=False))
    print(f"\nPortfolio total: {df.realized_r.sum():+.2f}R   EV/signal: {df.realized_r.mean():+.3f}R")
    print(f"Portfolio per-signal Sharpe: {portfolio_sharpe(df):.3f}  "
          f"(report: 0.860)")

    print("\n=== §1.5 — Annual Portfolio EV ===")
    ann = annual_portfolio(df)
    ann_print = ann.copy()
    ann_print["ev"]      = ann_print["ev"].apply(lambda x: f"{x:+.3f}R")
    ann_print["total_r"] = ann_print["total_r"].apply(lambda x: f"{x:+.2f}R")
    print(ann_print.to_string(index=False))

    print("\n=== §2 — Monthly R Correlation Matrix ===")
    monthly = monthly_r_per_pool(df)
    print(f"(months: {len(monthly)})")
    print(correlation_matrix(monthly))

    # Highlight key pairs
    cm = correlation_matrix(monthly)
    print("\nKey pair correlations (report claims):")
    pairs = [
        ("US_EQUITY", "US_MACRO", "+0.848 co-move"),
        ("CN_AGRI", "US_EQUITY", "−0.768 hedge"),
        ("CN_INDEX", "US_EQUITY", "+0.312"),
        ("CN_METAL", "CN_AGRI", "+0.006 uncorrelated"),
    ]
    for a, b, claim in pairs:
        if a in cm.index and b in cm.columns:
            actual = cm.loc[a, b]
            print(f"  {a:10s} × {b:10s}  claim={claim:25s}  actual={actual:+.3f}")

    print("\n=== §4 — Top 5 Two-Pool Combinations by Sharpe (per-signal) ===")
    tp = two_pool_sharpe(df)
    tp_print = tp.copy()
    tp_print["ev"]              = tp_print["ev"].apply(lambda x: f"{x:+.3f}R")
    tp_print["std"]             = tp_print["std"].apply(lambda x: f"{x:.3f}")
    tp_print["sharpe_per_sig"]  = tp_print["sharpe_per_sig"].apply(lambda x: f"{x:.3f}")
    tp_print["sharpe_total"]    = tp_print["sharpe_total"].apply(lambda x: f"{x:.2f}")
    print(tp_print.to_string(index=False))

    print("\nUS_MACRO appears in top-4? ",
          all("US_MACRO" in (r.pool_a, r.pool_b) for _, r in tp.head(4).iterrows()))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
