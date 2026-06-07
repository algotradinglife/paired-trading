"""Reproduce the §1 annual filter-lift table from hopp-stability-crosspool-report-2026-05-31.

For each of the 5 Scheme-B pools, load the per-trade rr_*.csv, filter to bottom
signals, split by higher_relation == 'opposing' vs not, compute annual EV
(mean realized_r), and emit the cross-pool lift table.

The report numbers we are checking:
  Year   n(opp)  EV_opp   n(non)  EV_non   Lift
  2021   20      +0.879R  49      +0.408R  +0.471R
  2022   24      +0.938R  42      +0.119R  +0.818R
  2023   10      +1.071R  68      +0.318R  +0.753R
  2024   21      +0.598R  56      +0.705R  -0.107R
  2025   21      +0.978R  67      +0.187R  +0.791R
  2026   6       +0.547R  21      +0.671R  -0.123R  (YTD)
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd


def _default_review_dir() -> Path:
    derived = os.environ.get("DERIVED_ROOT")
    if derived:
        return Path(derived) / "paired-trading" / "src-data-review"
    return Path("data/review")


DEFAULT_REVIEW = _default_review_dir()

# Pool -> CSV filename. CN_INDEX only has rr_wf_cn_index.csv (walk-forward),
# the others use rr_b_*.csv (B-topology, full sample).
POOL_TO_CSV = {
    "CN_METAL":  "rr_b_cn_metal.csv",
    "CN_AGRI":   "rr_b_cn_agri.csv",
    "CN_INDEX":  "rr_b_cn_index.csv",
    "US_EQUITY": "rr_b_us_equity.csv",
    "US_MACRO":  "rr_b_us_macro.csv",
}


def load_pool(review_dir: Path, pool: str) -> pd.DataFrame:
    csv = review_dir / POOL_TO_CSV[pool]
    df = pd.read_csv(csv)
    df["pool"] = pool
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    return df


def annual_lift(df: pd.DataFrame) -> pd.DataFrame:
    bottom = df[df["direction"] == "bottom"].copy()
    bottom["is_opp"] = bottom["higher_relation"] == "opposing"

    rows = []
    for year, sub in bottom.groupby("year"):
        opp  = sub[sub.is_opp]
        non  = sub[~sub.is_opp]
        rows.append({
            "year": int(year),
            "n_opp": len(opp),
            "ev_opp": opp.realized_r.mean() if len(opp) else float("nan"),
            "n_non": len(non),
            "ev_non": non.realized_r.mean() if len(non) else float("nan"),
        })
    out = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
    out["lift"] = out["ev_opp"] - out["ev_non"]
    return out


def per_pool_2024(df: pd.DataFrame) -> pd.DataFrame:
    bottom = df[(df.direction == "bottom") & (df.year == 2024)].copy()
    bottom["is_opp"] = bottom["higher_relation"] == "opposing"
    rows = []
    for pool, sub in bottom.groupby("pool"):
        opp  = sub[sub.is_opp]
        non  = sub[~sub.is_opp]
        rows.append({
            "pool": pool,
            "n_opp": len(opp),
            "ev_opp": opp.realized_r.mean() if len(opp) else float("nan"),
            "n_non": len(non),
            "ev_non": non.realized_r.mean() if len(non) else float("nan"),
        })
    out = pd.DataFrame(rows).sort_values("pool").reset_index(drop=True)
    out["lift"] = out["ev_opp"] - out["ev_non"]
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--review-dir", type=Path, default=DEFAULT_REVIEW,
                   help=f"directory holding rr_*.csv (default: {DEFAULT_REVIEW})")
    args = p.parse_args()

    frames = []
    for pool in POOL_TO_CSV:
        try:
            frames.append(load_pool(args.review_dir, pool))
        except FileNotFoundError as e:
            print(f"  MISSING: {pool} ({e})")
    if not frames:
        return 1
    all_df = pd.concat(frames, ignore_index=True)
    print(f"Loaded {len(all_df)} trades across {all_df.pool.nunique()} pools "
          f"({all_df.year.min()}-{all_df.year.max()})\n")

    print("=== §1 Annual Lift (Bottom · h=opposing vs non-opposing) ===")
    al = annual_lift(all_df)
    al_print = al.copy()
    al_print["ev_opp"] = al_print["ev_opp"].apply(lambda x: f"{x:+.3f}R")
    al_print["ev_non"] = al_print["ev_non"].apply(lambda x: f"{x:+.3f}R")
    al_print["lift"]   = al_print["lift"].apply(lambda x: f"{x:+.3f}R")
    print(al_print.to_string(index=False))

    print("\n=== §2 Per-Pool 2024 Lift (Bottom) ===")
    pp = per_pool_2024(all_df)
    pp_print = pp.copy()
    pp_print["ev_opp"] = pp_print["ev_opp"].apply(lambda x: f"{x:+.3f}R")
    pp_print["ev_non"] = pp_print["ev_non"].apply(lambda x: f"{x:+.3f}R")
    pp_print["lift"]   = pp_print["lift"].apply(lambda x: f"{x:+.3f}R")
    print(pp_print.to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
