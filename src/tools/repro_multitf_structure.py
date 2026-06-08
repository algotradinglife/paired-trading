"""Reproduce multitf-structure-report-2026-05-31.

Report uses h=opposing EV per instrument as a proxy for "1h readability"
across the 5 Scheme-B pools. Headline tables:
  §4  per-instrument table — HIGH / MID / LOW readability tiers
       (h=opp EV, n per symbol)
  §5.4 CN_METAL top × h=opposing: n=15, EV=-0.533R, max-stop rate 73%
  Footer notes total trades=768.

We compare:
  1. Total trade count vs report 768.
  2. Per-instrument h=opp EV and n for every symbol in the report.
  3. CN_METAL top × h=opposing aggregate (n, EV, max-stop rate).
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

# (display_name, pool, csv_symbol, report_ev, report_n, tier)
REPORT_TABLE = [
    # HIGH
    ("SR",   "CN_AGRI",   "kq_m_czce_sr",  +0.966, 10, "HIGH"),
    ("MA",   "CN_AGRI",   "kq_m_czce_ma",  +0.929,  7, "HIGH"),
    ("TA",   "CN_AGRI",   "kq_m_czce_ta",  +0.929,  7, "HIGH"),
    ("RB",   "CN_METAL",  "kq_m_shfe_rb",  +0.929,  7, "HIGH"),
    ("IC",   "CN_INDEX",  "kq_m_cffex_ic", +1.071,  7, "HIGH"),
    ("IF",   "CN_INDEX",  "kq_m_cffex_if", +0.857,  7, "HIGH"),
    ("GLD",  "US_MACRO",  "gld",           +1.286,  7, "HIGH"),
    ("TLT",  "US_MACRO",  "tlt",           +1.231,  7, "HIGH"),
    ("DIA",  "US_EQUITY", "dia",           +1.500,  9, "HIGH"),
    ("SPY",  "US_EQUITY", "spy",           +0.725, 20, "HIGH"),
    # MID
    ("SC",   "CN_METAL",  "kq_m_ine_sc",   +0.488, 12, "MID"),
    ("AU",   "CN_METAL",  "kq_m_shfe_au",  +0.673,  6, "MID"),
    ("IWM",  "US_EQUITY", "iwm",           +1.000,  5, "MID"),
    ("GDX",  "US_MACRO",  "gdx",           +0.750,  4, "MID"),
    ("I",    "CN_AGRI",   "kq_m_dce_i",    +0.350, 10, "MID"),
    ("M",    "CN_AGRI",   "kq_m_dce_m",    +0.200,  5, "MID"),
    ("NVDA", "US_EQUITY", "nvda",          +0.200,  5, "MID"),
    # LOW
    ("AG",   "CN_METAL",  "kq_m_shfe_ag",  -0.333,  9, "LOW"),
    ("CU",   "CN_METAL",  "kq_m_shfe_cu",  -1.000,  3, "LOW"),
    ("XLF",  "US_EQUITY", "xlf",           -0.050, 10, "LOW"),
    ("Y",    "CN_AGRI",   "kq_m_dce_y",     None,   0, "LOW"),  # n=0 expected
]


def load(review_dir: Path) -> pd.DataFrame:
    frames = []
    for pool, csv in POOL_TO_CSV.items():
        d = pd.read_csv(review_dir / csv)
        d["pool"] = pool
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    return df


def per_symbol_hopp(df: pd.DataFrame) -> pd.DataFrame:
    """h=opposing EV/n by symbol."""
    sub = df[df.higher_relation == "opposing"]
    rows = []
    for sym, g in sub.groupby("symbol"):
        rows.append(dict(
            symbol=sym, n=len(g),
            ev=g.realized_r.mean(),
        ))
    return pd.DataFrame(rows)


def cn_metal_top_opp(df: pd.DataFrame) -> dict:
    """CN_METAL × top × higher=opposing aggregate."""
    sub = df[
        (df.pool == "CN_METAL")
        & (df.direction == "top")
        & (df.higher_relation == "opposing")
    ]
    n = len(sub)
    ev = sub.realized_r.mean() if n else float("nan")
    # max stop = realized_r close to -1.0R (full stop) — report says 73%
    max_stop_rate = (sub.realized_r <= -0.95).mean() if n else float("nan")
    return dict(n=n, ev=ev, max_stop_rate=max_stop_rate)


def fmt_ev(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "   n/a "
    return f"{x:+.3f}R"


def verdict_ev(report, repro, n_repro):
    """Tag based on sign agreement + magnitude."""
    if report is None:
        return "n=0" if n_repro == 0 else "miss"
    if n_repro == 0:
        return "n=0 now"
    same_sign = (report >= 0) == (repro >= 0)
    if not same_sign:
        return "FLIP"
    err = abs(report - repro)
    if err < 0.2:
        return "hold"
    if err < 0.5:
        return "drift"
    return "fail"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--review-dir", type=Path, default=_default_review_dir(),
                   help="review CSV dir (env: DERIVED_ROOT → "
                        "$DERIVED_ROOT/paired-trading/src-data-review)")
    args = p.parse_args()

    df = load(args.review_dir)
    print(f"Loaded {len(df)} trades across {df.pool.nunique()} pools "
          f"({df.date.min().date()} -> {df.date.max().date()})")
    print(f"Report n=768; current n={len(df)} (x{len(df)/768:.1f})\n")

    # Pool-level overall sanity
    print("=== Pool sizes ===")
    for pool, sub in df.groupby("pool"):
        opp_n = (sub.higher_relation == "opposing").sum()
        print(f"  {pool:10s} total={len(sub):4d}  h=opp={opp_n}")
    print()

    # Per-symbol h=opposing
    by_sym = per_symbol_hopp(df).set_index("symbol")

    print("=== Per-instrument h=opposing EV vs report ===")
    print(f"{'sym':5s} {'tier':5s} {'pool':10s} {'rep_n':>6s} {'rep_EV':>8s}  "
          f"{'cur_n':>6s} {'cur_EV':>10s}  verdict")
    n_hold = 0
    n_drift = 0
    n_fail = 0
    n_flip = 0
    n_special = 0
    for name, pool, csv_sym, rep_ev, rep_n, tier in REPORT_TABLE:
        if csv_sym in by_sym.index:
            cur_n = int(by_sym.loc[csv_sym, "n"])
            cur_ev = float(by_sym.loc[csv_sym, "ev"])
        else:
            cur_n = 0
            cur_ev = float("nan")
        v = verdict_ev(rep_ev, cur_ev, cur_n)
        if v == "hold":
            n_hold += 1
        elif v == "drift":
            n_drift += 1
        elif v == "FLIP":
            n_flip += 1
        elif v == "fail":
            n_fail += 1
        else:
            n_special += 1
        rep_ev_s = fmt_ev(rep_ev)
        cur_ev_s = fmt_ev(cur_ev)
        print(f"{name:5s} {tier:5s} {pool:10s} {rep_n:>6d} {rep_ev_s:>8s}  "
              f"{cur_n:>6d} {cur_ev_s:>10s}  {v}")
    print(f"\nVerdicts: hold={n_hold}  drift={n_drift}  fail={n_fail}  "
          f"FLIP={n_flip}  special={n_special}")

    # Tier-level aggregate: do HIGH tier symbols still beat LOW tier?
    print("\n=== Tier-aggregate check ===")
    tiers = {"HIGH": [], "MID": [], "LOW": []}
    for name, pool, csv_sym, rep_ev, rep_n, tier in REPORT_TABLE:
        if csv_sym in by_sym.index:
            n = int(by_sym.loc[csv_sym, "n"])
            ev = float(by_sym.loc[csv_sym, "ev"])
            if n > 0:
                tiers[tier].append((name, n, ev))
    for tier, items in tiers.items():
        if not items:
            print(f"  {tier:5s}  empty")
            continue
        wn = sum(n for _, n, _ in items)
        wev = sum(n * ev for _, n, ev in items) / wn if wn else float("nan")
        simple_ev = np.mean([ev for _, _, ev in items])
        positives = sum(1 for _, _, ev in items if ev > 0)
        print(f"  {tier:5s}  syms={len(items):2d}  total_n={wn:4d}  "
              f"weighted_EV={wev:+.3f}R  simple_mean_EV={simple_ev:+.3f}R  "
              f"positive_syms={positives}/{len(items)}")

    # CN_METAL top × opposing
    print("\n=== CN_METAL top x h=opposing (report: n=15, EV=-0.533R, maxstop=73%) ===")
    r = cn_metal_top_opp(df)
    print(f"  n={r['n']}  EV={r['ev']:+.3f}R  max_stop_rate={r['max_stop_rate']:.0%}")

    # Sign agreement for HIGH (should all be positive) and LOW (should all <= 0)
    print("\n=== Sign-agreement summary ===")
    high_pos = sum(1 for name, _, csv_sym, _, _, t in REPORT_TABLE
                   if t == "HIGH" and csv_sym in by_sym.index
                   and by_sym.loc[csv_sym, "n"] > 0
                   and by_sym.loc[csv_sym, "ev"] > 0)
    high_total = sum(1 for *_, t in REPORT_TABLE if t == "HIGH")
    low_npos = sum(1 for name, _, csv_sym, _, _, t in REPORT_TABLE
                   if t == "LOW" and csv_sym in by_sym.index
                   and by_sym.loc[csv_sym, "n"] > 0
                   and by_sym.loc[csv_sym, "ev"] <= 0)
    low_with_data = sum(1 for name, _, csv_sym, _, _, t in REPORT_TABLE
                        if t == "LOW" and csv_sym in by_sym.index
                        and by_sym.loc[csv_sym, "n"] > 0)
    print(f"  HIGH tier remains positive: {high_pos}/{high_total}")
    print(f"  LOW tier remains non-positive: {low_npos}/{low_with_data}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
