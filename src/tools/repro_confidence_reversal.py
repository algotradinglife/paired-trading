"""Reproduce confidence-reversal-report-2026-05-31.

Across 5 Scheme-B pools, split each pool's trades by confidence_band
(low/mid/high), check:
  §1   — sample sizes per pool and per band (~equal thirds expected)
  §2   — pooled EV per band (report: low+0.43 / mid+0.36 / high+0.42R)
  §3   — monotonicity per pool×direction (10 combinations)
  §4   — direction breakdown (top mid weakness)
  §6   — does h=opposing cover confidence? (bot×opp split by band)
  §7   — temporal stability (early vs late period)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

POOL_TO_CSV = {
    "CN_METAL":  "rr_b_cn_metal.csv",
    "CN_AGRI":   "rr_b_cn_agri.csv",
    "CN_INDEX":  "rr_b_cn_index.csv",
    "US_EQUITY": "rr_b_us_equity.csv",
    "US_MACRO":  "rr_b_us_macro.csv",
}

BAND_ORDER = ["low", "mid", "high"]


def load(review_dir: Path) -> pd.DataFrame:
    frames = []
    for pool, csv in POOL_TO_CSV.items():
        d = pd.read_csv(review_dir / csv)
        d["pool"] = pool
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    return df


def ci95(arr: np.ndarray) -> tuple[float, float]:
    if len(arr) < 2:
        return (float("nan"), float("nan"))
    m = arr.mean()
    se = arr.std(ddof=1) / np.sqrt(len(arr))
    return (m - 1.96 * se, m + 1.96 * se)


def per_band_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for band in BAND_ORDER:
        sub = df[df.confidence_band == band]
        lo, hi = ci95(sub.realized_r.values)
        rows.append(dict(band=band, n=len(sub),
                         ev=sub.realized_r.mean(),
                         ci_lo=lo, ci_hi=hi))
    return pd.DataFrame(rows)


def pool_band_sizes(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for pool, sub in df.groupby("pool"):
        c = sub.confidence_band.value_counts()
        rows.append(dict(pool=pool, total=len(sub),
                         n_low=int(c.get("low", 0)),
                         n_mid=int(c.get("mid", 0)),
                         n_high=int(c.get("high", 0)),
                         ev_pool=sub.realized_r.mean()))
    return pd.DataFrame(rows).sort_values("pool").reset_index(drop=True)


def monotonicity_check(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for pool, sub in df.groupby("pool"):
        for direction in ["bottom", "top"]:
            d = sub[sub.direction == direction]
            evs = {b: d[d.confidence_band == b].realized_r.mean() for b in BAND_ORDER}
            ns  = {b: (d.confidence_band == b).sum() for b in BAND_ORDER}
            monotonic = (evs["low"] < evs["mid"] < evs["high"])
            if pd.isna(evs["mid"]):
                pattern = "n/a"
            elif evs["mid"] < min(evs["low"], evs["high"]):
                pattern = "mid LOWEST (U)"
            elif evs["mid"] > max(evs["low"], evs["high"]):
                pattern = "mid HIGHEST (∩)"
            elif evs["low"] < evs["mid"] < evs["high"]:
                pattern = "monotonic ↑"
            elif evs["low"] > evs["mid"] > evs["high"]:
                pattern = "monotonic ↓"
            else:
                pattern = "mixed"
            rows.append(dict(
                pool=pool, direction=direction,
                n_low=ns["low"], n_mid=ns["mid"], n_high=ns["high"],
                ev_low=evs["low"], ev_mid=evs["mid"], ev_high=evs["high"],
                pattern=pattern, monotonic_up=monotonic,
            ))
    return pd.DataFrame(rows)


def opposing_filter_band(df: pd.DataFrame) -> pd.DataFrame:
    bot_opp = df[(df.direction == "bottom") & (df.higher_relation == "opposing")]
    rows = []
    for band in BAND_ORDER:
        sub = bot_opp[bot_opp.confidence_band == band]
        lo, hi = ci95(sub.realized_r.values)
        rows.append(dict(band=band, n=len(sub),
                         ev=sub.realized_r.mean(), ci_lo=lo, ci_hi=hi))
    return pd.DataFrame(rows)


def temporal_split(df: pd.DataFrame, cutoff: str = "2023-11-01") -> pd.DataFrame:
    cutoff_ts = pd.Timestamp(cutoff, tz="UTC")
    if df["date"].dt.tz is None:
        cutoff_ts = pd.Timestamp(cutoff)
    rows = []
    for label, mask in [("early", df.date < cutoff_ts), ("late", df.date >= cutoff_ts)]:
        sub = df[mask]
        row = dict(period=label, n=len(sub))
        for band in BAND_ORDER:
            b = sub[sub.confidence_band == band]
            row[f"ev_{band}"] = b.realized_r.mean()
            row[f"n_{band}"]  = len(b)
        rows.append(row)
    return pd.DataFrame(rows)


def fmt(x, w=8):
    if pd.isna(x):
        return f"{'n/a':>{w}s}"
    return f"{x:+{w}.3f}R"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--review-dir", type=Path, default=Path("data/review"))
    args = p.parse_args()

    df = load(args.review_dir)
    print(f"Loaded {len(df)} trades across {df.pool.nunique()} pools "
          f"({df.date.min().date()} → {df.date.max().date()})")
    print(f"Report n=768; current n={len(df)} (×{len(df)/768:.1f})\n")

    print("=== §1 Pool / Band sample sizes ===")
    pbs = pool_band_sizes(df)
    pbs_print = pbs.copy()
    pbs_print["ev_pool"] = pbs_print["ev_pool"].apply(lambda x: f"{x:+.3f}R")
    print(pbs_print.to_string(index=False))

    print("\n=== §2 Pooled EV by band ===")
    print("  Report: low=+0.431R / mid=+0.359R / high=+0.417R  (CIs heavily overlap)")
    band_t = per_band_table(df)
    for _, r in band_t.iterrows():
        print(f"  {r.band:5s}  n={int(r.n):4d}  EV={r.ev:+.3f}R  CI95=[{r.ci_lo:+.3f}, {r.ci_hi:+.3f}]")

    print("\n=== §3 Monotonicity check (low<mid<high) — Report: 0/10 ===")
    mc = monotonicity_check(df)
    print(f"{'pool':10s} {'dir':6s} {'n_low':>5s} {'n_mid':>5s} {'n_high':>6s}  "
          f"{'ev_low':>10s} {'ev_mid':>10s} {'ev_high':>10s}  {'pattern':20s}  mono?")
    for _, r in mc.iterrows():
        print(f"{r.pool:10s} {r.direction:6s} {r.n_low:>5d} {r.n_mid:>5d} {r.n_high:>6d}  "
              f"{fmt(r.ev_low, 8)} {fmt(r.ev_mid, 8)} {fmt(r.ev_high, 8)}  "
              f"{r.pattern:20s}  {'YES' if r.monotonic_up else 'no'}")
    n_mono = int(mc.monotonic_up.sum())
    print(f"\nTotal monotonic ↑ (low<mid<high): {n_mono}/{len(mc)}")

    print("\n=== §4 Direction × Band (pooled across pools) ===")
    print("Report bot: low+0.526 / mid+0.521 / high+0.445R  (CIs overlap, mid not weak)")
    print("Report top: low+0.360 / mid+0.157 / high+0.376R  (mid weak)")
    for direction in ["bottom", "top"]:
        d = df[df.direction == direction]
        print(f"  {direction.upper()}:")
        for band in BAND_ORDER:
            b = d[d.confidence_band == band]
            lo, hi = ci95(b.realized_r.values)
            print(f"    {band:5s} n={len(b):4d}  EV={b.realized_r.mean():+.3f}R  CI95=[{lo:+.3f}, {hi:+.3f}]")

    print("\n=== §6 h=opposing covers confidence? (bottom × opposing × band) ===")
    print("Report bot×opp: low+0.900 / mid+0.952 / high+0.699R  (CIs overlap, conf adds nothing)")
    of = opposing_filter_band(df)
    for _, r in of.iterrows():
        print(f"  bot×opp×{r.band:5s} n={int(r.n):4d}  EV={r.ev:+.3f}R  CI95=[{r.ci_lo:+.3f}, {r.ci_hi:+.3f}]")

    print("\n=== §7 Temporal stability (cutoff 2023-11) ===")
    print("Report: early mid+0.400 strong; late mid+0.314 weakest (mode flip)")
    ts = temporal_split(df)
    for _, r in ts.iterrows():
        print(f"  {r.period:5s}  n={int(r.n):4d}  "
              f"low(n={int(r.n_low)})={r.ev_low:+.3f}R  "
              f"mid(n={int(r.n_mid)})={r.ev_mid:+.3f}R  "
              f"high(n={int(r.n_high)})={r.ev_high:+.3f}R")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
