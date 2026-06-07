"""Reproduce options-crossmarket-report-2026-05-31.

Cross-market option EV comparison for bottom × higher_relation=opposing signals
across 5 Scheme-B pools (CN_INDEX/CN_AGRI/CN_METAL/US_EQUITY/US_MACRO).

The original report priced 17-DTE ATM/OTM calls under a Black futures-option
model using HV20 as IV proxy, with a 4-tick stop on the underlying. The script
that did the Black pricing did not survive the rebuild, so we approximate by
mapping each pool×outcome to the fixed per-outcome option payoff that the
companion report (`options-simulation-report-2026-05-31.html`) explicitly
published for the bottom×opposing pool merge:

  tp1_tp2 → +67.8%   tp1_max → +25.1%
  tp1_stop → -48.9%  full_stop → -8.8% (4-tick) / -41.2% (ATR)
  max_hold → -75.6%

That table was the engine behind the cross-market EV column. The pooled EV
reproduces the companion report's +36.9% headline (4-tick) under this scheme.

We also filter out the 6 new signal levels added since 2026-05-31
(intra_cycle_dea/hist/slope/bull_*), keeping only the original
{intra_cycle, inter_segment, inter_cycle} that the report was computed on.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

POOLS = {
    "CN_INDEX":  "rr_b_cn_index.csv",
    "CN_AGRI":   "rr_b_cn_agri.csv",
    "CN_METAL":  "rr_b_cn_metal.csv",
    "US_EQUITY": "rr_b_us_equity.csv",
    "US_MACRO":  "rr_b_us_macro.csv",
}

# Original signal levels — the 6 new bull_*/dea/hist/slope variants did not
# exist when the 2026-05-31 report was generated.
ORIGINAL_LEVELS = {"intra_cycle", "inter_segment", "inter_cycle"}

# Per-outcome ATM option payoff (4-tick stop and ATR stop), taken verbatim
# from doc/options-simulation-report-2026-05-31.html § "出场路径分布"
PAYOFF_4TK = {
    "tp1_tp2":   0.678,
    "tp1_max":   0.251,
    "tp1_stop": -0.489,
    "full_stop":-0.088,
    "max_hold": -0.756,
}
PAYOFF_ATR = {
    "tp1_tp2":   0.678,
    "tp1_max":   0.251,
    "tp1_stop": -0.489,
    "full_stop":-0.412,
    "max_hold": -0.756,
}

# Per-pool counts/EV claimed by the report (cross-market table)
REPORT_NUMBERS = {
    "CN_INDEX":  dict(n=13, ev_R=0.643, ev_4tk=0.275, ev_atr=0.205, win=0.54, tp1tp2=0.54),
    "CN_AGRI":   dict(n=23, ev_R=0.814, ev_4tk=0.328, ev_atr=0.262, win=0.70, tp1tp2=0.70),
    "CN_METAL":  dict(n=18, ev_R=0.836, ev_4tk=0.421, ev_atr=0.398, win=0.78, tp1tp2=0.56),
    "US_EQUITY": dict(n=27, ev_R=0.889, ev_4tk=0.313, ev_atr=0.243, win=0.74, tp1tp2=0.74),
    "US_MACRO":  dict(n=13, ev_R=1.125, ev_4tk=0.258, ev_atr=0.258, win=0.77, tp1tp2=0.69),
    "POOLED":    dict(n=94, ev_R=None,  ev_4tk=0.325, ev_atr=0.274, win=0.71, tp1tp2=0.66),
}


def load_pool(review_dir: Path, fname: str) -> pd.DataFrame:
    df = pd.read_csv(review_dir / fname)
    df["date"] = pd.to_datetime(df["date"])
    return df


def filter_bo(df: pd.DataFrame, restrict_levels: bool) -> pd.DataFrame:
    bo = df[(df["direction"] == "bottom") & (df["higher_relation"] == "opposing")]
    if restrict_levels:
        bo = bo[bo["sig_level"].isin(ORIGINAL_LEVELS)]
    return bo


def pool_stats(bo: pd.DataFrame) -> dict:
    if bo.empty:
        return dict(n=0, ev_R=float("nan"), ev_4tk=float("nan"), ev_atr=float("nan"),
                    win=float("nan"), tp1tp2=float("nan"))
    n = len(bo)
    ev_R = bo["realized_r"].mean()
    ev_4tk = bo["outcome"].map(PAYOFF_4TK).mean()
    ev_atr = bo["outcome"].map(PAYOFF_ATR).mean()
    win = bo["outcome"].isin(["tp1_tp2", "tp1_max"]).mean()
    tp1tp2 = (bo["outcome"] == "tp1_tp2").mean()
    return dict(n=n, ev_R=ev_R, ev_4tk=ev_4tk, ev_atr=ev_atr, win=win, tp1tp2=tp1tp2)


def fmt_row(label: str, s: dict, ref: dict | None = None) -> str:
    """Render a pool row, with the reported numbers in parentheses for diff."""
    def diff(actual, expected, fmt_a, fmt_e):
        if expected is None or pd.isna(actual):
            return f"{fmt_a.format(actual)}"
        return f"{fmt_a.format(actual)} (rpt {fmt_e.format(expected)})"
    return (
        f"{label:10s}  "
        f"n={s['n']:>3d} (rpt {ref['n']:>3d})  "
        f"EV_R={diff(s['ev_R'],   ref['ev_R'],   '{:+.3f}', '{:+.3f}')}  "
        f"EV_4tk={diff(s['ev_4tk'], ref['ev_4tk'], '{:+.3f}', '{:+.3f}')}  "
        f"EV_ATR={diff(s['ev_atr'], ref['ev_atr'], '{:+.3f}', '{:+.3f}')}  "
        f"win={diff(s['win'],    ref['win'],    '{:.0%}',  '{:.0%}')}  "
        f"tp1tp2={diff(s['tp1tp2'], ref['tp1tp2'], '{:.0%}',  '{:.0%}')}"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--review-dir", default="data/review",
                    help="Directory containing rr_b_*.csv files")
    ap.add_argument("--all-levels", action="store_true",
                    help="Use all sig_levels (incl. 6 new variants); default is "
                         "to restrict to original {intra_cycle, inter_segment, "
                         "inter_cycle} to match the 2026-05-31 baseline.")
    args = ap.parse_args()

    review_dir = Path(args.review_dir)
    restrict = not args.all_levels

    print("=" * 102)
    print(f"  options-crossmarket repro  —  signal_levels="
          f"{'original-only (intra_cycle/inter_segment/inter_cycle)' if restrict else 'ALL (incl. 6 new variants)'}")
    print("=" * 102)

    pooled_frames: list[pd.DataFrame] = []
    rows: list[dict] = []
    for pool, fname in POOLS.items():
        df = load_pool(review_dir, fname)
        bo = filter_bo(df, restrict)
        s = pool_stats(bo)
        s["pool"] = pool
        rows.append(s)
        ref = REPORT_NUMBERS[pool]
        print(fmt_row(pool, s, ref))
        if not bo.empty:
            bo = bo.copy()
            bo["pool"] = pool
            pooled_frames.append(bo)

    print("-" * 102)
    pooled = pd.concat(pooled_frames, ignore_index=True) if pooled_frames else pd.DataFrame()
    if not pooled.empty:
        s = pool_stats(pooled)
        ref = REPORT_NUMBERS["POOLED"]
        print(fmt_row("POOLED",  s, ref))

    # ------------------------------------------------------------------
    # Per-pool outcome breakdown
    # ------------------------------------------------------------------
    print("\nPer-pool outcome distribution:")
    for pool, fname in POOLS.items():
        df = load_pool(review_dir, fname)
        bo = filter_bo(df, restrict)
        if bo.empty:
            continue
        oc = bo["outcome"].value_counts().sort_index().to_dict()
        print(f"  {pool:10s}  {oc}")

    # ------------------------------------------------------------------
    # OTM scaling sanity check — report claims that for OTM 2/3/4 the
    # tp1_tp2 leg gains progressively more leverage. We can't reprice the
    # Black model without HV20, so we just emit the outcome mix that drives
    # any such scan.
    # ------------------------------------------------------------------
    if not pooled.empty:
        print("\nPooled outcome mix (n={}):".format(len(pooled)))
        oc_counts = pooled["outcome"].value_counts()
        oc_pct = (oc_counts / len(pooled) * 100).round(1)
        for outcome, count in oc_counts.items():
            print(f"  {outcome:10s}  n={count:>3d}  "
                  f"{oc_pct[outcome]:>5.1f}%  "
                  f"payoff_4tk={PAYOFF_4TK.get(outcome, float('nan')):+.3f}  "
                  f"payoff_atr={PAYOFF_ATR.get(outcome, float('nan')):+.3f}")

    # ------------------------------------------------------------------
    # Headline diffs
    # ------------------------------------------------------------------
    print("\n" + "=" * 102)
    print("  Headline diff vs report")
    print("=" * 102)
    print(f"{'pool':10s} {'n_rpt':>6s} {'n_now':>6s} {'EV4tk_rpt':>10s} {'EV4tk_now':>10s} "
          f"{'diff_pp':>8s} {'win_rpt':>8s} {'win_now':>8s}")
    for row in rows:
        pool = row["pool"]
        ref = REPORT_NUMBERS[pool]
        diff_pp = (row["ev_4tk"] - ref["ev_4tk"]) * 100 if not pd.isna(row["ev_4tk"]) else float("nan")
        print(f"{pool:10s} {ref['n']:>6d} {row['n']:>6d} "
              f"{ref['ev_4tk']*100:>+9.1f}% {row['ev_4tk']*100:>+9.1f}% "
              f"{diff_pp:>+7.1f}  {ref['win']:>7.0%} {row['win']:>7.0%}")
    if not pooled.empty:
        s = pool_stats(pooled)
        ref = REPORT_NUMBERS["POOLED"]
        diff_pp = (s["ev_4tk"] - ref["ev_4tk"]) * 100
        print(f"{'POOLED':10s} {ref['n']:>6d} {s['n']:>6d} "
              f"{ref['ev_4tk']*100:>+9.1f}% {s['ev_4tk']*100:>+9.1f}% "
              f"{diff_pp:>+7.1f}  {ref['win']:>7.0%} {s['win']:>7.0%}")


if __name__ == "__main__":
    main()
