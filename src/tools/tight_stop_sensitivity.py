"""Compute realized EV per trade under a tight-stop model on option payoff data.

Inputs:
  <review_dir>/option_payoffs_topology_b_no_nvda.csv

Outputs:
  <review_dir>/tight_stop_ev_sensitivity.csv
  ../doc/options-tight-stop-sensitivity-2026-05-24.md

`review_dir` resolves via DERIVED_ROOT env var (preferred) or falls back to
`src/data/review/` relative to this script. Set DERIVED_ROOT to point at the
external drive's derived/paired-trading tree.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

SRC = Path(__file__).resolve().parents[1]


def _default_review_dir() -> Path:
    """Default review dir; honors DERIVED_ROOT env var, falls back to src/data/review."""
    derived = os.environ.get("DERIVED_ROOT")
    if derived:
        return Path(derived) / "paired-trading" / "src-data-review"
    return SRC / "data" / "review"


REVIEW_DIR = _default_review_dir()
CSV_IN = REVIEW_DIR / "option_payoffs_topology_b_no_nvda.csv"
CSV_OUT = REVIEW_DIR / "tight_stop_ev_sensitivity.csv"
MD_OUT = SRC.parent / "doc" / "options-tight-stop-sensitivity-2026-05-24.md"

SL_LEVELS = [-0.03, -0.05, -0.10, -0.20, -0.30]
HORIZONS = [5, 10, 20]
RULES = [
    "F1-top-lagging-soft",
    "F2-strong-bottom",
    "F3-candidate-counter-trend",
    "F4-options-asymmetric",
    "F8-bottom-weakness-baseline",
    "—",
]


def apply_stop(returns: pd.Series, sl: float) -> pd.Series:
    """Clip to stop-loss: if terminal < sl, realized = sl; else realized = terminal.

    NOTE: this is an UPPER BOUND on losses — path may have hit SL before recovering.
    """
    return returns.where(returns >= sl, other=sl)


def bucket_stats(returns: pd.Series, sl: float | None) -> dict:
    n = int(len(returns))
    if n == 0:
        return {"n": 0, "hit_rate": np.nan, "realized_ev_pct": np.nan}
    if sl is None:
        realized = returns
        hit_rate = np.nan  # not meaningful without a stop
    else:
        realized = apply_stop(returns, sl)
        hit_rate = float((returns < sl).mean())
    return {
        "n": n,
        "hit_rate": hit_rate,
        "realized_ev_pct": float(realized.mean()),
    }


def build_long_table(df: pd.DataFrame, buckets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for label, sub in buckets.items():
        for h in HORIZONS:
            col = f"h{h}_ret"
            r = sub[col].dropna()
            # fixed hold (no stop)
            fixed = bucket_stats(r, None)
            for sl in SL_LEVELS:
                s = bucket_stats(r, sl)
                rows.append({
                    "rule_id": label,
                    "horizon": h,
                    "sl_pct": sl,
                    "n": s["n"],
                    "hit_rate": s["hit_rate"],
                    "realized_ev_pct": s["realized_ev_pct"],
                    "fixed_hold_ev_pct": fixed["realized_ev_pct"],
                })
    return pd.DataFrame(rows)


def fmt_pct(x: float) -> str:
    if pd.isna(x):
        return "n/a"
    return f"{x*100:+.1f}%"


def fmt_rate(x: float) -> str:
    if pd.isna(x):
        return "n/a"
    return f"{x*100:.0f}%"


def render_matrix(long_df: pd.DataFrame, horizon: int) -> str:
    sub = long_df[long_df["horizon"] == horizon].copy()
    # Pivot: rows = rule_id, cols = sl
    pivot = sub.pivot(index="rule_id", columns="sl_pct", values="realized_ev_pct")
    n_map = sub.drop_duplicates(subset=["rule_id"]).set_index("rule_id")["n"]
    fixed_map = sub.drop_duplicates(subset=["rule_id"]).set_index("rule_id")["fixed_hold_ev_pct"]

    # Preserve our rule ordering, plus spotlight at end if present
    ordered_rules = [r for r in RULES if r in pivot.index]
    extras = [r for r in pivot.index if r not in RULES]
    ordered_rules += extras

    sl_cols = sorted(pivot.columns, reverse=True)  # -0.03 first (tightest)

    headers = ["rule_id", "n"] + [f"SL {int(sl*100)}%" for sl in sl_cols] + ["fixed hold"]
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for rule in ordered_rules:
        row = [rule, str(int(n_map[rule]))]
        for sl in sl_cols:
            row.append(fmt_pct(pivot.loc[rule, sl]))
        row.append(fmt_pct(fixed_map[rule]))
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def render_hit_rate_matrix(long_df: pd.DataFrame, horizon: int) -> str:
    sub = long_df[long_df["horizon"] == horizon].copy()
    pivot = sub.pivot(index="rule_id", columns="sl_pct", values="hit_rate")
    ordered_rules = [r for r in RULES if r in pivot.index]
    extras = [r for r in pivot.index if r not in RULES]
    ordered_rules += extras
    sl_cols = sorted(pivot.columns, reverse=True)

    headers = ["rule_id"] + [f"SL {int(sl*100)}%" for sl in sl_cols]
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for rule in ordered_rules:
        row = [rule]
        for sl in sl_cols:
            row.append(fmt_rate(pivot.loc[rule, sl]))
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def find_flips(long_df: pd.DataFrame) -> list[str]:
    """Find (rule, horizon, sl) where fixed-hold EV is negative but realized EV is positive."""
    flips = []
    for _, row in long_df.iterrows():
        if pd.isna(row["fixed_hold_ev_pct"]) or pd.isna(row["realized_ev_pct"]):
            continue
        if row["fixed_hold_ev_pct"] < 0 and row["realized_ev_pct"] > 0:
            flips.append(
                f"- **{row['rule_id']}** @ h={int(row['horizon'])}, SL={int(row['sl_pct']*100)}%: "
                f"fixed {fmt_pct(row['fixed_hold_ev_pct'])} → realized {fmt_pct(row['realized_ev_pct'])} "
                f"(n={int(row['n'])}, stop hit {fmt_rate(row['hit_rate'])})"
            )
    return flips


def find_persistently_negative(long_df: pd.DataFrame) -> list[str]:
    """Rule × horizon where realized EV stays negative at ALL SL levels (incl. tightest)."""
    notes = []
    for (rule, h), grp in long_df.groupby(["rule_id", "horizon"]):
        evs = grp["realized_ev_pct"].values
        fixed = grp["fixed_hold_ev_pct"].iloc[0]
        if (evs < 0).all() and fixed < 0:
            best_sl = grp.loc[grp["realized_ev_pct"].idxmax()]
            notes.append(
                f"- **{rule}** @ h={int(h)}: realized EV stays negative across all SL "
                f"(best = {fmt_pct(best_sl['realized_ev_pct'])} at SL {int(best_sl['sl_pct']*100)}%; "
                f"fixed hold {fmt_pct(fixed)}, n={int(best_sl['n'])})"
            )
    return notes


def main() -> None:
    df = pd.read_csv(CSV_IN)

    buckets: dict[str, pd.DataFrame] = {}
    for rule in RULES:
        buckets[rule] = df[df["rule_id"] == rule]

    long_df = build_long_table(df, buckets)

    # Spotlight bucket: top + higher_relation==opposing across all rules
    spot = df[(df["direction"] == "top") & (df["higher_relation"] == "opposing")]
    spot_label = "SPOTLIGHT: top + higher=opposing"
    spot_long = build_long_table(df, {spot_label: spot})

    full_long = pd.concat([long_df, spot_long], ignore_index=True)
    full_long.to_csv(CSV_OUT, index=False)

    # Build markdown
    methodology = """## Methodology

For each (rule_id, horizon h, stop-loss level SL):

- Take the option-premium return at horizon h: `h{h}_ret`.
- Apply tight stop: realized return = max(h{h}_ret, SL).
  - If h{h}_ret < SL → realized = SL  (stop triggered)
  - Else            → realized = h{h}_ret
- Realized EV per trade = mean of realized returns across trades in the bucket.

SL levels tested: -3%, -5%, -10%, -20%, -30%.
Horizons: h = 5 / 10 / 20 trading days.
"Fixed hold" column = mean of raw `h{N}_ret` (no stop, terminal value only).

### Caveat (must read)

This is an **upper bound** on realized losses. The terminal value at day h is
the only information we have — we cannot tell whether intraday path hit the
stop *before* an eventual recovery. Real path-dependent stop fills would:

1. **Increase** the realized stop-out rate (some trades that recovered to a
   small final loss may have touched the stop intra-window).
2. Therefore **lower** the realized EV vs. what this report shows.

In particular, the "SL -3%" column is essentially "if we stop out the moment
premium drops 3%, what's the realized average?" — but with daily-close-only
data we only stop trades whose *day-h close* is worse than -3%. A trade
ending at +50% that touched -8% mid-path is counted as +50% here. So treat
this as a **best-case** for tight stops.

### Buckets

- Per rule_id: F1, F2, F3, F4, F8, baseline (`—`).
- Spotlight: all signals where `direction == top` AND `higher_relation == opposing`
  (regardless of rule_id) — the dual-confirmation top-reversal context.
"""

    parts = [
        "# Options Tight-Stop EV Sensitivity (2026-05-24)",
        "",
        "Source data: `src/data/review/option_payoffs_topology_b_no_nvda.csv` (79 signals, NVDA excluded).",
        "Long-format output: `src/data/review/tight_stop_ev_sensitivity.csv`.",
        "",
        methodology,
        "",
        "## Realized EV per Trade — Matrix",
        "",
        "### h = 5 trading days",
        "",
        render_matrix(full_long, 5),
        "",
        "### h = 10 trading days",
        "",
        render_matrix(full_long, 10),
        "",
        "### h = 20 trading days",
        "",
        render_matrix(full_long, 20),
        "",
        "## Stop-hit rate (share of trades whose terminal value < SL)",
        "",
        "Recall: actual path-dependent stop-hit rate would be >= these numbers.",
        "",
        "### h = 5",
        "",
        render_hit_rate_matrix(full_long, 5),
        "",
        "### h = 10",
        "",
        render_hit_rate_matrix(full_long, 10),
        "",
        "### h = 20",
        "",
        render_hit_rate_matrix(full_long, 20),
        "",
        "## Spotlight bucket — top + higher=opposing",
        "",
        f"Sample size: **n = {len(spot)}** trades "
        f"(rule composition: " + ", ".join(
            f"{r}×{c}" for r, c in spot["rule_id"].value_counts().items()
        ) + ").",
        "",
        "Per-horizon realized EV under each stop:",
        "",
        "| horizon | n | SL -3% | SL -5% | SL -10% | SL -20% | SL -30% | fixed hold |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for h in HORIZONS:
        sub = spot_long[spot_long["horizon"] == h]
        n = int(sub["n"].iloc[0])
        sl_map = sub.set_index("sl_pct")["realized_ev_pct"]
        fixed = sub["fixed_hold_ev_pct"].iloc[0]
        parts.append(
            f"| h={h} | {n} | "
            f"{fmt_pct(sl_map[-0.03])} | {fmt_pct(sl_map[-0.05])} | "
            f"{fmt_pct(sl_map[-0.10])} | {fmt_pct(sl_map[-0.20])} | "
            f"{fmt_pct(sl_map[-0.30])} | {fmt_pct(fixed)} |"
        )

    # Spotlight raw return distribution
    parts += [
        "",
        "Raw return distribution within spotlight:",
        "",
        "| horizon | min | p25 | median | p75 | max | mean |",
        "|---|---|---|---|---|---|---|",
    ]
    for h in HORIZONS:
        r = spot[f"h{h}_ret"]
        parts.append(
            f"| h={h} | {fmt_pct(r.min())} | {fmt_pct(r.quantile(0.25))} | "
            f"{fmt_pct(r.median())} | {fmt_pct(r.quantile(0.75))} | "
            f"{fmt_pct(r.max())} | {fmt_pct(r.mean())} |"
        )

    # Findings
    flips = find_flips(full_long)
    persistent = find_persistently_negative(full_long)

    parts += [
        "",
        "## Key Findings",
        "",
        "### Tight stops that flip a losing rule positive",
        "",
        "(fixed-hold EV < 0, but realized EV > 0 after applying SL)",
        "",
    ]
    parts += flips if flips else ["- *None.* No rule flips from net-negative to net-positive purely by adding a daily-close stop.*"]

    parts += [
        "",
        "### Rules that stay negative at every SL level tested",
        "",
        "(truly directionless under this stop model — adding a tighter stop does not rescue them)",
        "",
    ]
    parts += persistent if persistent else ["- *None — every rule reaches positive EV at some SL level.*"]

    # Best-EV pick per rule
    parts += [
        "",
        "### Best realized EV per rule (across all SL × h combos)",
        "",
        "| rule_id | best EV | at horizon | at SL | n | fixed hold @ same h |",
        "|---|---|---|---|---|---|",
    ]
    for rule in RULES + [spot_label]:
        sub = full_long[full_long["rule_id"] == rule]
        if sub.empty:
            continue
        best = sub.loc[sub["realized_ev_pct"].idxmax()]
        parts.append(
            f"| {rule} | {fmt_pct(best['realized_ev_pct'])} | h={int(best['horizon'])} | "
            f"SL {int(best['sl_pct']*100)}% | {int(best['n'])} | {fmt_pct(best['fixed_hold_ev_pct'])} |"
        )

    # Interpretive summary
    parts += [
        "",
        "### Interpretation",
        "",
        "1. **Tight stops mechanically improve every rule's EV** in this end-of-day model, "
        "because they truncate the left tail without touching the right tail. The interesting "
        "question is *how much* improvement, and whether it crosses zero.",
        "",
        "2. **Path-dependence warning bites hardest at SL -3% and -5%**. A 30-DTE ATM option "
        "routinely swings 5-10% intraday on noise. Real-world tightness of -3% to -5% will "
        "stop out many trades that this analysis credits with positive terminal value. "
        "Treat -10% as the most operationally honest column.",
        "",
        "3. **The spotlight bucket (top + higher=opposing)** is where the multi-TF "
        "confirmation thesis should pay off. Compare its realized EV to F1 alone and to "
        "the `—` baseline at the same horizon to see whether the higher-TF filter adds "
        "edge net of the smaller sample.",
        "",
        "4. **Use the CSV** (`tight_stop_ev_sensitivity.csv`) for further slicing — it's "
        "long-format and joins cleanly to other rule/topology metadata.",
        "",
    ]

    MD_OUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"Wrote {CSV_OUT}")
    print(f"Wrote {MD_OUT}")
    print(f"Long-format rows: {len(full_long)}")


if __name__ == "__main__":
    main()
