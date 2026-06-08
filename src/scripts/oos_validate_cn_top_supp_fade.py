"""Out-of-sample validation for CN-top-supp-fade rule.

Background:
  R4 review (doc/r4-review-2026-05-24.md, §4.1 "Statistical Red Flags")
  flagged: "All 233 signals are within the same 2.4y window. No
  cross-validation split."

  CN-top-supp-fade (top + higher_relation=supporting, weight 0.80) was
  shipped at commit 2178d11f based on in-sample n=74, mean -1.59%,
  CI [-3.40%, +0.02%].

  This script splits the same data by time into train/test and re-runs
  the same statistics, with pre-registered pass/fail criteria.

Pre-registered judgment criteria (set BEFORE running):
  CONFIRM        : test mean < 0 AND 95% CI upper bound ≤ +0.5%
  STRONG CONFIRM : test mean ∈ [-3.0%, -0.5%]
  REVERT         : test mean > 0, OR CI upper bound ≥ +1.5%
  INSUFFICIENT   : test n < 15 (defer judgment, accumulate more data)

Splits (3 to detect cherry-picking — agreement required for CONFIRM):
  S1: 50/50 by time          (mid-point of date range)
  S2: 60/40 by time          (train first 60% of time, test last 40%)
  S3: Last 12 months as test (2025-05 → 2026-04, simulates live deploy)

Bootstrap: 5000 resamples with replacement, numpy default_rng(42)
  (matches R4 review reproducibility seed).
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


def _default_review_dir() -> Path:
    """Default review dir; honors DERIVED_ROOT env var, falls back to src/data/review."""
    derived = os.environ.get("DERIVED_ROOT")
    if derived:
        return Path(derived) / "paired-trading" / "src-data-review"
    return Path(__file__).resolve().parents[1] / "data" / "review"


DATA_CSV = _default_review_dir() / "cn_b_topology_signals_all.csv"
OUT_MD = Path(__file__).resolve().parents[2] / "doc" / "cn-top-supp-fade-oos-2026-05-24.md"

HORIZON = 20
N_BOOTSTRAP = 5000
RNG_SEED = 42


def bootstrap_ci(x: np.ndarray, n_boot: int = N_BOOTSTRAP, alpha: float = 0.05) -> tuple[float, float]:
    if len(x) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(RNG_SEED)
    means = rng.choice(x, size=(n_boot, len(x)), replace=True).mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)


def describe(x: np.ndarray) -> dict:
    if len(x) == 0:
        return {"n": 0, "mean_pct": float("nan"), "median_pct": float("nan"),
                "hit_rate_pct": float("nan"), "ci_lo_pct": float("nan"),
                "ci_hi_pct": float("nan")}
    lo, hi = bootstrap_ci(x)
    return {
        "n": len(x),
        "mean_pct": x.mean() * 100,
        "median_pct": float(np.median(x)) * 100,
        "hit_rate_pct": (x > 0).mean() * 100,
        "ci_lo_pct": lo * 100,
        "ci_hi_pct": hi * 100,
    }


def fmt_row(label: str, d: dict) -> str:
    if d["n"] == 0:
        return f"| {label} | 0 | — | — | — | — |"
    return (f"| {label} | {d['n']} | {d['mean_pct']:+.2f}% | "
            f"{d['median_pct']:+.2f}% | {d['hit_rate_pct']:.0f}% | "
            f"[{d['ci_lo_pct']:+.2f}%, {d['ci_hi_pct']:+.2f}%] |")


def judge(d: dict) -> str:
    if d["n"] < 15:
        return f"**INSUFFICIENT** (n={d['n']} < 15)"
    mean = d["mean_pct"]
    hi = d["ci_hi_pct"]
    if mean > 0:
        return f"**REVERT** (test mean +{mean:.2f}% > 0)"
    if hi >= 1.5:
        return f"**REVERT** (CI upper {hi:+.2f}% ≥ +1.5%)"
    if -3.0 <= mean <= -0.5 and hi <= 0.5:
        return f"**STRONG CONFIRM** (mean {mean:+.2f}% in [-3.0, -0.5], CI upper {hi:+.2f}% ≤ +0.5%)"
    if mean < 0 and hi <= 0.5:
        return f"**CONFIRM** (mean {mean:+.2f}% < 0, CI upper {hi:+.2f}% ≤ +0.5%)"
    return f"**MARGINAL** (mean {mean:+.2f}%, CI upper {hi:+.2f}%)"


def split_by_date(df: pd.DataFrame, cutoff: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = df[df["date"].dt.date < cutoff]
    test = df[df["date"].dt.date >= cutoff]
    return train, test


def main() -> int:
    df = pd.read_csv(DATA_CSV, parse_dates=["date"])
    cell = df[(df["horizon"] == HORIZON)
              & (df["direction"] == "top")
              & (df["higher_relation"] == "supporting")].copy()
    cell = cell.sort_values("date").reset_index(drop=True)

    full = describe(cell["signed_return"].to_numpy())

    date_min = cell["date"].min().date()
    date_max = cell["date"].max().date()
    total_days = (date_max - date_min).days
    midpoint_date = date_min + timedelta(days=total_days // 2)
    cutoff_60_date = date_min + timedelta(days=int(total_days * 0.6))
    cutoff_12mo = date(date_max.year - 1, date_max.month, date_max.day)

    splits = [
        ("S1 (50/50 by time)",    midpoint_date),
        ("S2 (60/40 by time)",    cutoff_60_date),
        ("S3 (last 12mo = test)", cutoff_12mo),
    ]

    lines = []
    lines.append("# CN-top-supp-fade — Out-of-Sample Validation")
    lines.append("")
    lines.append(f"**Date:** 2026-05-24  ")
    lines.append(f"**Rule under test:** CN-top-supp-fade (top + higher_relation=supporting, weight 0.80)  ")
    lines.append(f"**In-sample reference (R4):** n=74, mean -1.59%, CI [-3.40%, +0.02%]  ")
    lines.append(f"**Data:** `src/data/review/cn_b_topology_signals_all.csv` h={HORIZON}  ")
    lines.append(f"**Date range:** {date_min} → {date_max}  ")
    lines.append(f"**Bootstrap:** {N_BOOTSTRAP} resamples, numpy default_rng({RNG_SEED})  ")
    lines.append("")
    lines.append("## Pre-registered judgment criteria")
    lines.append("- **STRONG CONFIRM**: test mean ∈ [-3.0%, -0.5%] AND CI upper ≤ +0.5%")
    lines.append("- **CONFIRM**: test mean < 0 AND CI upper ≤ +0.5%")
    lines.append("- **REVERT** (→ weight 1.0 monitor): test mean > 0, OR CI upper ≥ +1.5%")
    lines.append("- **INSUFFICIENT**: test n < 15 (defer judgment)")
    lines.append("- **MARGINAL**: anything in between")
    lines.append("")
    lines.append("## Full-sample sanity check")
    lines.append("| Sample | n | mean | median | hit | 95% CI |")
    lines.append("|---|--:|--:|--:|--:|---|")
    lines.append(fmt_row("Full (matches R4)", full))
    lines.append("")
    print(f"Full: n={full['n']}, mean={full['mean_pct']:+.2f}%, CI [{full['ci_lo_pct']:+.2f}%, {full['ci_hi_pct']:+.2f}%]")

    overall_verdicts = []
    for label, cutoff in splits:
        train_df, test_df = split_by_date(cell, cutoff)
        train_d = describe(train_df["signed_return"].to_numpy())
        test_d = describe(test_df["signed_return"].to_numpy())
        verdict = judge(test_d)
        overall_verdicts.append((label, verdict))
        lines.append(f"## {label}  (cutoff: {cutoff})")
        lines.append("| Sample | n | mean | median | hit | 95% CI |")
        lines.append("|---|--:|--:|--:|--:|---|")
        lines.append(fmt_row("Train", train_d))
        lines.append(fmt_row("Test",  test_d))
        lines.append("")
        lines.append(f"**Verdict:** {verdict}")
        lines.append("")
        print(f"\n{label} (cutoff {cutoff}):")
        print(f"  Train: n={train_d['n']}, mean={train_d['mean_pct']:+.2f}%, CI [{train_d['ci_lo_pct']:+.2f}%, {train_d['ci_hi_pct']:+.2f}%]")
        print(f"  Test:  n={test_d['n']}, mean={test_d['mean_pct']:+.2f}%, CI [{test_d['ci_lo_pct']:+.2f}%, {test_d['ci_hi_pct']:+.2f}%]")
        print(f"  → {verdict}")

    lines.append("## Aggregate verdict")
    lines.append("| Split | Verdict |")
    lines.append("|---|---|")
    for label, verdict in overall_verdicts:
        lines.append(f"| {label} | {verdict} |")
    lines.append("")

    confirms = sum(1 for _, v in overall_verdicts if "CONFIRM" in v)
    reverts = sum(1 for _, v in overall_verdicts if "REVERT" in v)
    insuff = sum(1 for _, v in overall_verdicts if "INSUFFICIENT" in v)
    if reverts >= 1:
        agg = ("**OVERALL: REVERT** — at least one split says revert. "
               "Recommend downgrading CN-top-supp-fade to weight 1.00 with monitor_required=True.")
    elif confirms >= 2 and insuff == 0:
        agg = (f"**OVERALL: CONFIRM** — {confirms}/3 splits confirm. Keep weight 0.80.")
    elif insuff >= 2:
        agg = ("**OVERALL: INSUFFICIENT** — too many splits below n=15. "
               "Defer judgment; accumulate more data and re-run quarterly.")
    else:
        agg = "**OVERALL: MARGINAL** — mixed signals. Consider downgrading to monitor pending more data."
    lines.append(agg)
    lines.append("")
    print(f"\n{agg}")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines))
    print(f"\nReport: {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
