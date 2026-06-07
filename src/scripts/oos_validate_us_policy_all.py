"""Out-of-sample validation for the entire us_equity policy.

Same harness as scripts/oos_validate_cn_policy_all.py, applied to US.
Closes the R1/R2/R3 in-sample-only gap that the CN OOS (R4 §4.1)
flagged: every US rule weight was set on the same 5y/10-symbol window
without train/test separation.

Rules under test (precedence order from _apply_us_equity):
  1. F2-strong-bottom            (boost 1.20)
  2. F3-candidate-counter-trend  (boost 1.15)
  3. F4-options-asymmetric       (pass-through 1.00, options hint)
  4. B1-top-higher-opposing      (boost 1.30, added in R3)
  5. F1-top-lagging-soft         (de-weight 0.70)
  6. F8-bottom-weakness-baseline (boost 1.10)

CSV note: `data/review/b_topology_signals_all.csv` was generated 2026-05-23
BEFORE B1 was added to the policy. Its `rule_id` column tags old-B1
signals as F1 (legacy precedence). This script ignores that column and
re-classifies every signal under the CURRENT precedence ladder.

Splits (3 distinct, anti-cherry-pick):
  S1: 50/50 by time
  S2: 40/60 by time (early cut)
  S3: Last 12 months as test (live-deploy simulation)

Bootstrap: 5000 resamples, numpy default_rng(42).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

DATA_CSV = Path(__file__).resolve().parents[1] / "data" / "review" / "b_topology_signals_all.csv"
OUT_MD = Path(__file__).resolve().parents[2] / "doc" / "us-policy-oos-2026-05-24.md"

HORIZON = 20
N_BOOTSTRAP = 5000
RNG_SEED = 42
MIN_TEST_N = 15
CI_NEAR_ZERO_BAND = 0.5

# From engine/divergence/downstream_policies
LABEL_CANDIDATE_THRESHOLD = 0.65
LABEL_CONFIRMED_THRESHOLD = 0.80


def _conf_band(c: float) -> str:
    if c >= LABEL_CONFIRMED_THRESHOLD:
        return "confirmed"
    if c >= LABEL_CANDIDATE_THRESHOLD:
        return "candidate"
    if c >= 0.50:
        return "forming"
    if c >= 0.30:
        return "watching"
    return "dormant"


def classify_us(row: pd.Series) -> str | None:
    """Replicate _apply_us_equity precedence on a single CSV row.

    Returns the rule_id that would fire on this signal under the CURRENT
    policy (post-R3 with B1). Returns None for baseline.
    """
    direction = row["direction"]
    subtype = row["subtype"]
    lower = row["lower_relation"]
    higher = row["higher_relation"]
    band = _conf_band(float(row["confidence"]))

    if direction == "bottom" and lower == "leading" and higher == "opposing":
        return "F2-strong-bottom"
    if band == "candidate" and higher == "opposing":
        return "F3-candidate-counter-trend"
    if direction == "top" and lower == "leading" and higher == "opposing":
        return "F4-options-asymmetric"
    if direction == "top" and higher == "opposing":
        return "B1-top-higher-opposing"
    if direction == "top" and lower == "lagging":
        return "F1-top-lagging-soft"
    if direction == "bottom" and subtype == "weakness":
        return "F8-bottom-weakness-baseline"
    return None


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Rule:
    rule_id: str
    description: str
    claim: str  # "negative" | "positive" | "ambiguous"
    weight: float
    r_review_summary: str


def _cell_for(df: pd.DataFrame, rule_id: str) -> pd.DataFrame:
    return df[df["_rule"] == rule_id]


RULES: list[Rule] = [
    Rule(
        rule_id="F2-strong-bottom",
        description="bottom + lower=leading + higher=opposing (R1)",
        claim="positive",
        weight=1.20,
        r_review_summary="R1: validated multi-TF reversal, n≈30 single-TF baseline",
    ),
    Rule(
        rule_id="F3-candidate-counter-trend",
        description="confidence ∈ candidate band + higher=opposing (R1)",
        claim="positive",
        weight=1.15,
        r_review_summary="R1: 14/14 perfect in 5y sample — itself a fit flag",
    ),
    Rule(
        rule_id="F4-options-asymmetric",
        description="top + lower=leading + higher=opposing (R1)",
        claim="positive",
        weight=1.00,
        r_review_summary="R1: 24/25 ≈ 96% small-win, options-asymmetric pattern",
    ),
    Rule(
        rule_id="B1-top-higher-opposing",
        description="top + higher=opposing (residual after F4/F3) (R3)",
        claim="positive",
        weight=1.30,
        r_review_summary="R3: 27% stop-hit vs F1's 72%, h=20 +33.8% under SL-10%",
    ),
    Rule(
        rule_id="F1-top-lagging-soft",
        description="top + lower=lagging (residual after F4/B1) (R1)",
        claim="negative",
        weight=0.70,
        r_review_summary="R1: edge-significant downside; R3 stop-hit 72-94%",
    ),
    Rule(
        rule_id="F8-bottom-weakness-baseline",
        description="bottom + subtype=weakness (residual after F2) (R2)",
        claim="positive",
        weight=1.10,
        r_review_summary="R2: n=123 workhorse, R3 +73.5% EV at SL -3%",
    ),
]


# ---------------------------------------------------------------------------
# Shared stats helpers (identical to cn harness)
# ---------------------------------------------------------------------------

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


def judge(d: dict, claim: str) -> str:
    n = d["n"]
    if n < MIN_TEST_N:
        return f"**INSUFFICIENT** (n={n} < {MIN_TEST_N})"
    mean = d["mean_pct"]
    lo, hi = d["ci_lo_pct"], d["ci_hi_pct"]
    if claim == "negative":
        if mean > 0:
            return f"**REJECT** (test mean +{mean:.2f}% > 0)"
        if hi >= 1.5:
            return f"**REJECT** (CI upper {hi:+.2f}% ≥ +1.5%)"
        if -3.0 <= mean <= -0.5 and hi <= CI_NEAR_ZERO_BAND:
            return f"**STRONG CONFIRM** (mean {mean:+.2f}% in [-3.0, -0.5], CI upper {hi:+.2f}% ≤ +{CI_NEAR_ZERO_BAND}%)"
        if mean < 0 and hi <= CI_NEAR_ZERO_BAND:
            return f"**CONFIRM** (mean {mean:+.2f}% < 0, CI upper {hi:+.2f}% ≤ +{CI_NEAR_ZERO_BAND}%)"
        return f"**MARGINAL** (mean {mean:+.2f}%, CI upper {hi:+.2f}%)"
    if claim == "positive":
        if mean < 0:
            return f"**REJECT** (test mean {mean:+.2f}% < 0)"
        if lo <= -1.5:
            return f"**REJECT** (CI lower {lo:+.2f}% ≤ -1.5%)"
        if 0.5 <= mean <= 6.0 and lo >= -CI_NEAR_ZERO_BAND:
            return f"**STRONG CONFIRM** (mean {mean:+.2f}% in [0.5, 6.0], CI lower {lo:+.2f}% ≥ -{CI_NEAR_ZERO_BAND}%)"
        if mean > 0 and lo >= -CI_NEAR_ZERO_BAND:
            return f"**CONFIRM** (mean {mean:+.2f}% > 0, CI lower {lo:+.2f}% ≥ -{CI_NEAR_ZERO_BAND}%)"
        return f"**MARGINAL** (mean {mean:+.2f}%, CI lower {lo:+.2f}%)"
    crosses_zero = (lo <= 0 <= hi)
    if crosses_zero:
        return f"**CONFIRM** (CI [{lo:+.2f}%, {hi:+.2f}%] crosses zero — pass-through justified)"
    if hi < 0:
        return f"**UPGRADE-DEWEIGHT** (CI [{lo:+.2f}%, {hi:+.2f}%] entirely negative)"
    if lo > 0:
        return f"**UPGRADE-BOOST** (CI [{lo:+.2f}%, {hi:+.2f}%] entirely positive)"
    return f"**UNCLEAR** (CI [{lo:+.2f}%, {hi:+.2f}%])"


def split_by_date(df: pd.DataFrame, cutoff: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = df[df["date"].dt.date < cutoff]
    test = df[df["date"].dt.date >= cutoff]
    return train, test


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    df_all = pd.read_csv(DATA_CSV, parse_dates=["date"])
    df = df_all[df_all["horizon"] == HORIZON].copy()
    if df.empty:
        print(f"ERROR: no rows at horizon={HORIZON}")
        return 1

    # Re-classify each signal under CURRENT precedence (CSV's rule_id is stale)
    df["_rule"] = df.apply(classify_us, axis=1)

    # Distribution sanity check
    print("Re-classified rule distribution (h=20):")
    print(df["_rule"].fillna("(baseline)").value_counts().to_string())
    print()

    date_min = df["date"].min().date()
    date_max = df["date"].max().date()
    total_days = (date_max - date_min).days
    splits = [
        ("S1 50/50 by time",     date_min + timedelta(days=total_days // 2)),
        ("S2 40/60 by time",     date_min + timedelta(days=int(total_days * 0.4))),
        ("S3 last 12mo as test", date(date_max.year - 1, date_max.month, date_max.day)),
    ]

    lines: list[str] = []
    lines.append("# us_equity Policy — Full OOS Validation")
    lines.append("")
    lines.append(f"**Date:** 2026-05-24  ")
    lines.append(f"**Scope:** all rules in `engine/divergence/downstream_policies._apply_us_equity`  ")
    lines.append(f"**Data:** `src/data/review/b_topology_signals_all.csv` h={HORIZON}, "
                 f"{date_min} → {date_max} (~5y, 10 symbols)  ")
    lines.append(f"**Bootstrap:** {N_BOOTSTRAP} resamples, numpy default_rng({RNG_SEED})  ")
    lines.append(f"**Pre-registered min test n:** {MIN_TEST_N}  ")
    lines.append("")
    lines.append("## Note on rule classification")
    lines.append("CSV's `rule_id` column was generated 2026-05-23 BEFORE B1 was added to "
                 "the policy. Signals are re-classified under the CURRENT precedence:")
    lines.append("F2 → F3 → F4 → **B1** → F1 → F8 → baseline. Old-F1 signals with "
                 "higher=opposing now route to B1.")
    lines.append("")
    lines.append("**Re-classified distribution (h=20):**")
    lines.append("")
    lines.append("```")
    counts = df["_rule"].fillna("(baseline)").value_counts()
    for rid, n in counts.items():
        lines.append(f"  {rid:35s} {n:4d}")
    lines.append("```")
    lines.append("")
    lines.append("## Pre-registered judgment criteria (same as CN harness)")
    lines.append("- **claim=negative** STRONG CONFIRM: mean ∈ [-3.0, -0.5%], CI upper ≤ +0.5%")
    lines.append("- **claim=positive** STRONG CONFIRM: mean ∈ [+0.5, +6.0%], CI lower ≥ -0.5%")
    lines.append("- **claim=ambiguous** CONFIRM: CI crosses zero (pass-through justified)")
    lines.append("- **REJECT** when sign opposite to claim, or CI excess in wrong direction (≥1.5%)")
    lines.append("- **INSUFFICIENT** when test n < 15")
    lines.append("")
    lines.append("## Splits (same date axis across all rules)")
    for label, cutoff in splits:
        lines.append(f"- **{label}**: cutoff {cutoff}")
    lines.append("")
    lines.append("---")
    lines.append("")

    summary_rows = []

    for rule in RULES:
        cell = _cell_for(df, rule.rule_id).sort_values("date").reset_index(drop=True)
        full_d = describe(cell["signed_return"].to_numpy())

        lines.append(f"## {rule.rule_id}  (claim: {rule.claim}, current weight {rule.weight})")
        lines.append("")
        lines.append(f"**Description:** {rule.description}  ")
        lines.append(f"**Prior review:** {rule.r_review_summary}  ")
        lines.append("")
        lines.append("### Full-sample (under current precedence)")
        lines.append("| Sample | n | mean | median | hit | 95% CI |")
        lines.append("|---|--:|--:|--:|--:|---|")
        lines.append(fmt_row("Full", full_d))
        lines.append("")

        print(f"\n=== {rule.rule_id} ===")
        print(f"Full: n={full_d['n']}, mean={full_d['mean_pct']:+.2f}%, "
              f"CI [{full_d['ci_lo_pct']:+.2f}%, {full_d['ci_hi_pct']:+.2f}%]")

        rule_verdicts = []
        for label, cutoff in splits:
            train_df, test_df = split_by_date(cell, cutoff)
            train_d = describe(train_df["signed_return"].to_numpy())
            test_d = describe(test_df["signed_return"].to_numpy())
            verdict = judge(test_d, rule.claim)
            rule_verdicts.append((label, verdict))

            lines.append(f"### {label}  (cutoff {cutoff})")
            lines.append("| Sample | n | mean | median | hit | 95% CI |")
            lines.append("|---|--:|--:|--:|--:|---|")
            lines.append(fmt_row("Train", train_d))
            lines.append(fmt_row("Test",  test_d))
            lines.append("")
            lines.append(f"**Verdict:** {verdict}")
            lines.append("")

            print(f"  {label}: train n={train_d['n']} mean={train_d['mean_pct']:+.2f}% | "
                  f"test n={test_d['n']} mean={test_d['mean_pct']:+.2f}% "
                  f"CI [{test_d['ci_lo_pct']:+.2f}%, {test_d['ci_hi_pct']:+.2f}%] → {verdict}")

        confirms = sum(1 for _, v in rule_verdicts if "CONFIRM" in v)
        rejects = sum(1 for _, v in rule_verdicts if "REJECT" in v)
        upgrades = sum(1 for _, v in rule_verdicts if "UPGRADE" in v)
        insuff = sum(1 for _, v in rule_verdicts if "INSUFFICIENT" in v)

        if rejects >= 1:
            rule_verdict = "REJECT (at least one split rejects)"
            action = "review weight or drop"
        elif upgrades >= 2:
            rule_verdict = f"UPGRADE-RECOMMENDED ({upgrades}/3)"
            action = "consider stronger weight in next refit"
        elif confirms >= 2 and insuff == 0:
            rule_verdict = f"CONFIRM ({confirms}/3)"
            action = f"keep weight {rule.weight}"
        elif insuff >= 2:
            rule_verdict = "INSUFFICIENT"
            action = "data thin; accumulate and re-run"
        else:
            rule_verdict = "MARGINAL"
            action = "monitor; consider weight reduction if pattern persists"

        lines.append(f"**Rule-level verdict: {rule_verdict}** → {action}")
        lines.append("")
        lines.append("---")
        lines.append("")

        summary_rows.append((rule.rule_id, rule.claim, rule.weight, full_d["n"],
                             full_d["mean_pct"], rule_verdict, action))

        print(f"  → Rule-level: {rule_verdict} → {action}")

    lines.append("## Cross-rule summary")
    lines.append("")
    lines.append("| Rule | Claim | Weight | Full n | Full mean | Verdict | Action |")
    lines.append("|---|---|--:|--:|--:|---|---|")
    for rid, claim, w, n, mean, v, action in summary_rows:
        lines.append(f"| {rid} | {claim} | {w} | {n} | {mean:+.2f}% | {v} | {action} |")
    lines.append("")

    n_rules = len(summary_rows)
    n_confirm = sum(1 for *_, v, _ in summary_rows if v.startswith("CONFIRM"))
    n_reject = sum(1 for *_, v, _ in summary_rows if v.startswith("REJECT"))
    n_upgrade = sum(1 for *_, v, _ in summary_rows if v.startswith("UPGRADE"))
    n_insuff = sum(1 for *_, v, _ in summary_rows if v.startswith("INSUFFICIENT"))
    n_marginal = sum(1 for *_, v, _ in summary_rows if v.startswith("MARGINAL"))
    lines.append(f"**Overall us_equity policy: {n_confirm}/{n_rules} CONFIRM, "
                 f"{n_reject} REJECT, {n_upgrade} UPGRADE-RECOMMENDED, "
                 f"{n_marginal} MARGINAL, {n_insuff} INSUFFICIENT.**  ")
    lines.append("")
    if n_reject == 0 and n_marginal == 0 and n_insuff <= 1:
        lines.append("R1/R2/R3 in-sample-only gap for the us_equity path is "
                     "**substantively CLOSED**.")
    elif n_reject > 0:
        lines.append(f"⚠ {n_reject} rule(s) FAIL OOS — requires policy revision.")
    else:
        lines.append(f"Partial close: {n_marginal} marginal + {n_insuff} insufficient "
                     "rule(s) remain.")
    lines.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines))
    print(f"\nReport: {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
