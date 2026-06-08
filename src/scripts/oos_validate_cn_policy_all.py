"""Out-of-sample validation for the entire cn_futures policy.

Extends scripts/oos_validate_cn_top_supp_fade.py to cover EVERY rule in
engine/divergence/downstream_policies._apply_cn_futures. Closes R4 §4.1
"no OOS" blanket flag for the cn_futures path.

Rules under test (precedence order as in _apply_cn_futures):
  1. CN-top-supp-fade   — top + higher_relation=supporting  (de-weight 0.80)
  2. F8-cn-no-boost     — bottom + subtype=weakness          (workhorse, 1.00)
  3. CN1-top-passthrough — top (residual after rule 1)       (pass-through 1.00)
  4. Baseline           — bottom + subtype!=weakness         (no rule, 1.00)

Each rule encodes its own data-claim and pre-registered judgment criteria
(see RULES list below). Three distinct splits to anti-cherry-pick:
  S1: 50/50 by time            (midpoint cut)
  S2: 40/60 by time            (early cut, larger test — bias toward later data)
  S3: Last 12 months as test   (live-deploy simulation)

S2 cutoff is deliberately set to 40% (not 60%) of timeline so it differs
substantially from S3's last-12-months cut — earlier versions had S2 at
60% which coincided with S3 within ~10 days, producing only 2 effectively
independent splits.

Bootstrap: 5000 resamples, numpy default_rng(42), matches R4 + supp-fade.

Note on `signed_return`:
  signed_return = +fwd_return for bottom signals
  signed_return = -fwd_return for top signals
  → POSITIVE means signal was directionally correct (profitable trade)
  → NEGATIVE means signal was wrong (contra-predictive)

So a de-weight rule's "claim" is "signed_return reliably negative", while
a workhorse/boost rule's "claim" is "signed_return reliably positive".
A pass-through residual rule's "claim" is "signed_return mean ambiguous,
CI crosses zero — no de-weight or boost is statistically justified".
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd


def _default_review_dir() -> Path:
    """Default review dir; honors DERIVED_ROOT env var, falls back to src/data/review."""
    derived = os.environ.get("DERIVED_ROOT")
    if derived:
        return Path(derived) / "paired-trading" / "src-data-review"
    return Path(__file__).resolve().parents[1] / "data" / "review"


DATA_CSV = _default_review_dir() / "cn_b_topology_signals_all.csv"
OUT_MD = Path(__file__).resolve().parents[2] / "doc" / "cn-policy-oos-2026-05-24.md"

HORIZON = 20
N_BOOTSTRAP = 5000
RNG_SEED = 42

# Pre-registered: minimum test cell size to render a judgment
MIN_TEST_N = 15

# Pre-registered: "reliable" CI cushion (how much the CI must clear zero
# in the claimed direction for STRONG / CONFIRM)
CI_NEAR_ZERO_BAND = 0.5  # 0.5pp = 0.005


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Rule:
    rule_id: str
    description: str
    cell_filter: Callable[[pd.DataFrame], pd.DataFrame]
    claim: str  # "negative" | "positive" | "ambiguous"
    weight: float
    r4_in_sample_summary: str


def _cell_supp_fade(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["direction"] == "top") & (df["higher_relation"] == "supporting")]


def _cell_f8_cn(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["direction"] == "bottom") & (df["subtype"] == "weakness")]


def _cell_cn1_residual(df: pd.DataFrame) -> pd.DataFrame:
    # Top divergence minus the supp-fade sub-bucket (residual after rule 1)
    return df[(df["direction"] == "top") & (df["higher_relation"] != "supporting")]


def _cell_baseline_bottom(df: pd.DataFrame) -> pd.DataFrame:
    # Bottom signals that DON'T match F8 (non-weakness subtype) — these
    # currently fall through to baseline weight=1.0
    return df[(df["direction"] == "bottom") & (df["subtype"] != "weakness")]


RULES: list[Rule] = [
    Rule(
        rule_id="CN-top-supp-fade",
        description="top + higher_relation=supporting (de-weight 0.80)",
        cell_filter=_cell_supp_fade,
        claim="negative",
        weight=0.80,
        r4_in_sample_summary="n=74, mean -1.59%, CI [-3.40%, +0.02%]",
    ),
    Rule(
        rule_id="F8-cn-no-boost",
        description="bottom + subtype=weakness (workhorse, pass-through 1.00)",
        cell_filter=_cell_f8_cn,
        claim="positive",
        weight=1.00,
        r4_in_sample_summary="n=56, mean +3.81%, CI [+1.76%, +6.22%] (survives Bonferroni)",
    ),
    Rule(
        rule_id="CN1-top-passthrough",
        description="top residual after supp-fade (pass-through 1.00)",
        cell_filter=_cell_cn1_residual,
        claim="ambiguous",
        weight=1.00,
        r4_in_sample_summary="pooled top: n=103, mean -1.06%, CI [-2.51%, +0.40%] (crosses zero)",
    ),
    Rule(
        rule_id="Baseline-bottom-non-weakness",
        description="bottom + subtype!=weakness (no rule fires, baseline 1.00)",
        cell_filter=_cell_baseline_bottom,
        claim="ambiguous",
        weight=1.00,
        r4_in_sample_summary=(
            "bottom+standard: n=66, mean +1.68%, CI [-0.15%, +3.78%]; "
            "bottom+hidden: n=8, mean +1.33%, CI [-3.83%, +7.13%]"
        ),
    ),
]


# ---------------------------------------------------------------------------
# Stats helpers (shared with supp-fade harness; identical seed for reproducibility)
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
    """Pre-registered judgment based on the rule's claim.

      claim="negative" (de-weight): test mean < 0 + CI upper ≤ +0.5%
      claim="positive" (boost/workhorse): test mean > 0 + CI lower ≥ -0.5%
      claim="ambiguous" (pass-through): CI crosses 0 → CONFIRM; CI clearly
        excludes 0 in either direction → REJECT (rule should be promoted
        to a de-weight or boost, not left at 1.00)
    """
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

    # claim == "ambiguous" (pass-through justified iff CI crosses zero)
    crosses_zero = (lo <= 0 <= hi)
    if crosses_zero:
        return f"**CONFIRM** (CI [{lo:+.2f}%, {hi:+.2f}%] crosses zero — pass-through justified)"
    if hi < 0:
        return f"**UPGRADE-DEWEIGHT** (CI [{lo:+.2f}%, {hi:+.2f}%] entirely negative — consider new de-weight rule)"
    if lo > 0:
        return f"**UPGRADE-BOOST** (CI [{lo:+.2f}%, {hi:+.2f}%] entirely positive — consider new boost rule)"
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

    # Compute splits globally (same date axis for all rules — fair comparison)
    date_min = df["date"].min().date()
    date_max = df["date"].max().date()
    total_days = (date_max - date_min).days
    splits = [
        ("S1 50/50 by time",     date_min + timedelta(days=total_days // 2)),
        ("S2 40/60 by time",     date_min + timedelta(days=int(total_days * 0.4))),
        ("S3 last 12mo as test", date(date_max.year - 1, date_max.month, date_max.day)),
    ]

    lines: list[str] = []
    lines.append("# cn_futures Policy — Full OOS Validation")
    lines.append("")
    lines.append(f"**Date:** 2026-05-24  ")
    lines.append(f"**Scope:** all rules in `engine/divergence/downstream_policies._apply_cn_futures`  ")
    lines.append(f"**Data:** `src/data/review/cn_b_topology_signals_all.csv` h={HORIZON}, "
                 f"{date_min} → {date_max}  ")
    lines.append(f"**Bootstrap:** {N_BOOTSTRAP} resamples, numpy default_rng({RNG_SEED})  ")
    lines.append(f"**Pre-registered min test n:** {MIN_TEST_N}  ")
    lines.append("")
    lines.append("## Pre-registered judgment criteria (per rule claim)")
    lines.append("")
    lines.append("**claim=negative** (de-weight rules, e.g. CN-top-supp-fade):")
    lines.append(f"- STRONG CONFIRM: test mean ∈ [-3.0%, -0.5%] AND CI upper ≤ +{CI_NEAR_ZERO_BAND}%")
    lines.append(f"- CONFIRM: test mean < 0 AND CI upper ≤ +{CI_NEAR_ZERO_BAND}%")
    lines.append("- REJECT: test mean > 0, OR CI upper ≥ +1.5%")
    lines.append("")
    lines.append("**claim=positive** (boost/workhorse rules, e.g. F8-cn-no-boost):")
    lines.append(f"- STRONG CONFIRM: test mean ∈ [+0.5%, +6.0%] AND CI lower ≥ -{CI_NEAR_ZERO_BAND}%")
    lines.append(f"- CONFIRM: test mean > 0 AND CI lower ≥ -{CI_NEAR_ZERO_BAND}%")
    lines.append("- REJECT: test mean < 0, OR CI lower ≤ -1.5%")
    lines.append("")
    lines.append("**claim=ambiguous** (pass-through, e.g. CN1-top-passthrough):")
    lines.append("- CONFIRM: test CI crosses zero (pass-through justified)")
    lines.append("- UPGRADE-DEWEIGHT: test CI entirely negative")
    lines.append("- UPGRADE-BOOST: test CI entirely positive")
    lines.append("")
    lines.append(f"**INSUFFICIENT** (any claim): test n < {MIN_TEST_N} → defer")
    lines.append("")
    lines.append("## Splits (same date axis across all rules)")
    for label, cutoff in splits:
        lines.append(f"- **{label}**: cutoff {cutoff}")
    lines.append("")
    lines.append("---")
    lines.append("")

    summary_rows = []

    for rule in RULES:
        cell = rule.cell_filter(df).sort_values("date").reset_index(drop=True)
        full_d = describe(cell["signed_return"].to_numpy())

        lines.append(f"## {rule.rule_id}  (claim: {rule.claim}, current weight {rule.weight})")
        lines.append("")
        lines.append(f"**Description:** {rule.description}  ")
        lines.append(f"**R4 in-sample:** {rule.r4_in_sample_summary}  ")
        lines.append("")
        lines.append(f"### Full-sample sanity check (replication of R4)")
        lines.append("| Sample | n | mean | median | hit | 95% CI |")
        lines.append("|---|--:|--:|--:|--:|---|")
        lines.append(fmt_row("Full", full_d))
        lines.append("")

        print(f"\n=== {rule.rule_id} ===")
        print(f"Full: {fmt_row('Full', full_d)}")

        rule_verdicts = []
        for label, cutoff in splits:
            train_df, test_df = split_by_date(cell, cutoff)
            train_d = describe(train_df["signed_return"].to_numpy())
            test_d = describe(test_df["signed_return"].to_numpy())
            verdict = judge(test_d, rule.claim)
            rule_verdicts.append((label, verdict, test_d))

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

        # Aggregate per rule
        confirms = sum(1 for _, v, _ in rule_verdicts if "CONFIRM" in v)
        rejects = sum(1 for _, v, _ in rule_verdicts if "REJECT" in v)
        upgrades = sum(1 for _, v, _ in rule_verdicts if "UPGRADE" in v)
        insuff = sum(1 for _, v, _ in rule_verdicts if "INSUFFICIENT" in v)

        if rejects >= 1:
            rule_verdict = "REJECT (at least one split rejects)"
            action = "drop or downgrade rule"
        elif upgrades >= 2:
            rule_verdict = f"UPGRADE-RECOMMENDED ({upgrades}/3 splits suggest)"
            action = "consider promoting from pass-through to weighted rule"
        elif confirms >= 2 and insuff == 0:
            rule_verdict = f"CONFIRM ({confirms}/3 splits)"
            action = f"keep weight {rule.weight}"
        elif insuff >= 2:
            rule_verdict = "INSUFFICIENT (defer)"
            action = "accumulate more data, re-run quarterly"
        else:
            rule_verdict = "MARGINAL"
            action = "consider downgrading to monitor pending more data"

        lines.append(f"**Rule-level verdict: {rule_verdict}** → {action}")
        lines.append("")
        lines.append("---")
        lines.append("")

        summary_rows.append((rule.rule_id, rule.claim, rule.weight, full_d["n"],
                             full_d["mean_pct"], rule_verdict, action))

        print(f"  → Rule-level: {rule_verdict} → {action}")

    # Cross-rule summary
    lines.append("## Cross-rule summary")
    lines.append("")
    lines.append("| Rule | Claim | Weight | Full n | Full mean | Verdict | Action |")
    lines.append("|---|---|--:|--:|--:|---|---|")
    for rid, claim, w, n, mean, v, action in summary_rows:
        lines.append(f"| {rid} | {claim} | {w} | {n} | {mean:+.2f}% | {v} | {action} |")
    lines.append("")

    # Aggregate verdict for the whole cn_futures policy
    n_rules = len(summary_rows)
    n_confirm = sum(1 for *_, v, _ in summary_rows if v.startswith("CONFIRM"))
    n_reject = sum(1 for *_, v, _ in summary_rows if v.startswith("REJECT"))
    n_upgrade = sum(1 for *_, v, _ in summary_rows if v.startswith("UPGRADE"))
    n_insuff = sum(1 for *_, v, _ in summary_rows if v.startswith("INSUFFICIENT"))
    lines.append(f"**Overall cn_futures policy: {n_confirm}/{n_rules} CONFIRM, "
                 f"{n_reject} REJECT, {n_upgrade} UPGRADE-RECOMMENDED, "
                 f"{n_insuff} INSUFFICIENT.**  ")
    lines.append("")
    if n_reject == 0 and n_upgrade == 0 and n_insuff <= 1:
        lines.append("R4 §4.1 'no out-of-sample validation' blanket flag is **CLOSED** "
                     "for the cn_futures path.")
    elif n_reject > 0:
        lines.append("R4 §4.1 'no out-of-sample validation' flag is **partially open**: "
                     f"{n_reject} rule(s) require revision before clearance.")
    else:
        lines.append("R4 §4.1 'no out-of-sample validation' flag is **partially closed**: "
                     f"{n_upgrade} upgrade candidate(s) and/or {n_insuff} insufficient cell(s) "
                     f"remain.")
    lines.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines))
    print(f"\nReport: {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
