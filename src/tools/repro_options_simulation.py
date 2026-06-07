"""Reproduce options-simulation-report-2026-05-31.

The original report ran a Black-model option-pricing simulation on top of
the CN_AGRI + CN_METAL RR backtest. That bespoke simulation script does
not survive in the repo, so a strict reproduction of the option premium
P&L isn't possible. What we *can* do:

  1. Verify signal counts from the (now-rebuilt) divergence engine vs
     the report's 287 figure — these are expected to inflate ~2-3x due
     to 6 new level variants added since 2026-05-31.
  2. Verify the underlying R-multiple EV per (direction, higher_relation)
     cell from the same RR backtest outputs.
  3. Verify the outcome distribution (tp1_tp2 / full_stop / max_hold / ...)
     for the core (bottom × opposing) cell.
  4. Verify median option-premium %F from the existing daily-payoff CSV
     restricted to the nearest-strike (ATM-proxy) row per signal.
  5. Report which symbols the existing payoff CSV does/does not cover —
     since the report claims 12-symbol coverage but our payoffs only
     contain ~5 underlyings with non-trivial sample size.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path


def _default_payoffs() -> str:
    derived = os.environ.get("DERIVED_ROOT")
    if derived:
        return str(Path(derived) / "paired-trading" / "src-data-review" / "cn_daily_payoffs.csv")
    return "data/review/cn_daily_payoffs.csv"

import numpy as np
import pandas as pd

POOL_CSVS = {
    "CN_METAL": "rr_b_cn_metal.csv",
    "CN_AGRI":  "rr_b_cn_agri.csv",
}

# Symbols the report says it covered (12 total)
REPORT_SYMBOLS = {
    "rb": "CN_METAL",  "cu": "CN_METAL",  "au": "CN_METAL",  "sc": "CN_METAL",
    "sr": "CN_AGRI",   "i":  "CN_AGRI",   "m":  "CN_AGRI",   "ta": "CN_AGRI",
    "ma": "CN_AGRI",   "p":  "CN_AGRI",   "sa": "CN_AGRI",   "cf": "CN_AGRI",
}

REPORT_PER_SYMBOL = {  # total signal counts per symbol from report
    "rb": 33, "cu": 28, "au": 30, "sc": 39,
    "sr": 25, "i": 25, "m": 22, "ta": 21,
    "ma": 19, "p": 14, "sa": 18, "cf": 13,
}
REPORT_TOTAL = 287

# Report's per-cell summary: (n, win_rate, tp1_tp2_rate, ev_opt_4tick, underlying_ev_R)
REPORT_CELLS = {
    ("bottom", "opposing"):   (41,  0.73, 0.63, 0.369, 0.892),
    ("bottom", "neutral"):    (12,  0.50, 0.50, 0.311, 0.333),
    ("bottom", "supporting"): (50,  0.40, 0.36, 0.275, 0.177),
    ("top",    "opposing"):   (33,  0.45, 0.45, 0.212, 0.288),
    ("top",    "neutral"):    (17,  0.59, 0.59, 0.304, 0.529),
    ("top",    "supporting"): (134, 0.43, 0.42, 0.139, 0.260),
}

# Report's overall outcome distribution (all 287 signals)
REPORT_OUTCOMES_TOTAL = {
    "tp1_tp2":  (131, 0.46),   # both targets hit
    "tp1_stop": (33,  0.11),
    "tp1_max":  (13,  0.05),
    "full_stop":(102, 0.36),
    "max_hold": (8,   0.03),
}

# Report's bot×opposing outcome distribution
REPORT_OUTCOMES_BXO = {
    "tp1_tp2":  (26, 0.63),
    "tp1_max":  (4,  0.10),
    "tp1_stop": (3,  0.07),
    "full_stop":(6,  0.15),
    "max_hold": (2,  0.05),
}


def _norm_sym(symbol: str) -> str:
    """kq_m_shfe_rb → rb, kq_m_ine_sc → sc, kq_m_czce_sr → sr"""
    return str(symbol).lower().split("_")[-1]


def load_pools(review_dir: Path) -> pd.DataFrame:
    frames = []
    for pool, csv in POOL_CSVS.items():
        d = pd.read_csv(review_dir / csv)
        d["pool"] = pool
        d["sym_key"] = d["symbol"].apply(_norm_sym)
        frames.append(d)
    return pd.concat(frames, ignore_index=True)


def per_symbol_counts(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sym, exp_n in REPORT_PER_SYMBOL.items():
        n_actual = int((df.sym_key == sym).sum())
        rows.append({
            "sym": sym,
            "pool": REPORT_SYMBOLS[sym],
            "report_n": exp_n,
            "actual_n": n_actual,
            "ratio": round(n_actual / exp_n, 2) if exp_n else None,
        })
    return pd.DataFrame(rows)


def per_cell_table(df: pd.DataFrame) -> pd.DataFrame:
    """For each (direction, higher_relation) cell, report n / win-rate /
    tp1_tp2-rate / underlying EV in R."""
    rows = []
    for (d, h), (rep_n, rep_win, rep_t12, rep_ev_opt, rep_ev_R) in REPORT_CELLS.items():
        sub = df[(df.direction == d) & (df.higher_relation == h)]
        n = len(sub)
        if n == 0:
            rows.append({
                "direction": d, "h_rel": h,
                "report_n": rep_n, "actual_n": 0,
                "report_winrate": rep_win, "actual_winrate": np.nan,
                "report_tp12_rate": rep_t12, "actual_tp12_rate": np.nan,
                "report_ev_R": rep_ev_R, "actual_ev_R": np.nan,
            })
            continue
        win = sub.outcome.isin(["tp1_tp2", "tp1_stop", "tp1_max"]).mean()
        t12 = (sub.outcome == "tp1_tp2").mean()
        ev_R = sub.realized_r.mean()
        rows.append({
            "direction": d, "h_rel": h,
            "report_n": rep_n, "actual_n": n,
            "report_winrate": rep_win, "actual_winrate": round(win, 3),
            "report_tp12_rate": rep_t12, "actual_tp12_rate": round(t12, 3),
            "report_ev_R": rep_ev_R, "actual_ev_R": round(ev_R, 3),
        })
    return pd.DataFrame(rows)


def outcome_distribution(df: pd.DataFrame, label: str, ref: dict) -> pd.DataFrame:
    counts = df.outcome.value_counts()
    n = len(df)
    rows = []
    for outc, (rep_n, rep_pct) in ref.items():
        actual_n = int(counts.get(outc, 0))
        actual_pct = actual_n / n if n else 0.0
        rows.append({
            "outcome": outc,
            "report_n": rep_n, "actual_n": actual_n,
            "report_pct": rep_pct, "actual_pct": round(actual_pct, 3),
        })
    return pd.DataFrame(rows)


def median_premium_pct(payoffs_path: Path) -> pd.DataFrame:
    """Compute ATM-proxy median premium %F per (direction, higher_relation)
    cell from the daily-payoffs CSV."""
    df = pd.read_csv(payoffs_path)
    mask = (
        df["direction"].notna()
        & df["entry_price"].notna()
        & (df["entry_price"] > 0)
    )
    df = df[mask].copy()
    df["premium_pct"] = df["entry_premium"] / df["entry_price"]
    df["moneyness"] = (df["strike"] - df["entry_price"]).abs() / df["entry_price"]
    # nearest-strike per signal as ATM proxy
    key = ["signal_date", "underlying", "direction", "higher_relation",
           "contract_type"]
    df["_rank"] = df.groupby(key)["moneyness"].rank(method="first")
    atm = df[df["_rank"] == 1]

    rows = []
    report_med_prem = {
        ("bottom", "opposing"):  0.0313,
        ("bottom", "neutral"):   0.0240,
        ("bottom", "supporting"):0.0180,
        ("top",    "opposing"):  0.0277,
        ("top",    "neutral"):   0.0250,
        ("top",    "supporting"):0.0219,
    }
    for (d, h), rep in report_med_prem.items():
        sub = atm[(atm.direction == d) & (atm.higher_relation == h)]
        if sub.empty:
            actual = np.nan
        else:
            actual = sub.premium_pct.median()
        rows.append({
            "direction": d, "h_rel": h,
            "n_atm": len(sub),
            "report_med_prem_pct": rep,
            "actual_med_prem_pct": round(actual, 4) if pd.notna(actual) else None,
        })
    return pd.DataFrame(rows)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--review-dir", type=Path,
                   default=Path("data/review"))
    p.add_argument("--payoffs", default=_default_payoffs(),
                   help="path to cn_daily_payoffs.csv (env: DERIVED_ROOT)")
    args = p.parse_args()

    df = load_pools(args.review_dir)
    print(f"Loaded {len(df)} signals from CN_AGRI + CN_METAL pools "
          f"(report total: {REPORT_TOTAL})")
    print(f"Ratio current/report: {len(df) / REPORT_TOTAL:.2f}x\n")

    # Filter to just the 12 report symbols
    df12 = df[df.sym_key.isin(REPORT_PER_SYMBOL)].copy()
    print(f"After filtering to the 12 report symbols: {len(df12)} signals "
          f"(report: {REPORT_TOTAL})")

    print("\n=== §1 Per-symbol signal counts (report's 12 symbols) ===")
    ps = per_symbol_counts(df12)
    print(ps.to_string(index=False))
    print(f"\n  Sum actual = {ps.actual_n.sum()}  vs report = {ps.report_n.sum()}")

    print("\n=== §2 Per-cell statistics (direction × higher_relation) ===")
    pc = per_cell_table(df12)
    for _, r in pc.iterrows():
        print(f"  {r.direction:6s}/{r.h_rel:10s}  n: rep={r.report_n:>3} act={r.actual_n:>4}  "
              f"win%: rep={r.report_winrate:.2f} act={r.actual_winrate if pd.notna(r.actual_winrate) else 'n/a'}  "
              f"tp12%: rep={r.report_tp12_rate:.2f} act={r.actual_tp12_rate if pd.notna(r.actual_tp12_rate) else 'n/a'}  "
              f"EV_R: rep={r.report_ev_R:+.3f} act="
              f"{f'{r.actual_ev_R:+.3f}' if pd.notna(r.actual_ev_R) else 'n/a'}")

    print("\n=== §3 Outcome distribution — ALL 287 signals (report) ===")
    od = outcome_distribution(df12, "ALL", REPORT_OUTCOMES_TOTAL)
    for _, r in od.iterrows():
        print(f"  {r.outcome:9s}  rep_n={r.report_n:>3} act_n={r.actual_n:>4}  "
              f"rep_pct={r.report_pct:.1%}  act_pct={r.actual_pct:.1%}")

    print("\n=== §4 Outcome distribution — bottom×opposing (report n=41) ===")
    bxo = df12[(df12.direction == "bottom") & (df12.higher_relation == "opposing")]
    print(f"  bot×opp n: report=41  actual={len(bxo)}")
    od2 = outcome_distribution(bxo, "BxO", REPORT_OUTCOMES_BXO)
    for _, r in od2.iterrows():
        print(f"  {r.outcome:9s}  rep_n={r.report_n:>3} act_n={r.actual_n:>4}  "
              f"rep_pct={r.report_pct:.1%}  act_pct={r.actual_pct:.1%}")

    print("\n=== §5 Median premium %F from daily-payoffs CSV (ATM-proxy) ===")
    print(f"  Source: {args.payoffs}")
    if Path(args.payoffs).exists():
        mp = median_premium_pct(Path(args.payoffs))
        for _, r in mp.iterrows():
            act = (f"{r.actual_med_prem_pct:.4f}"
                   if r.actual_med_prem_pct is not None else "n/a")
            print(f"  {r.direction:6s}/{r.h_rel:10s}  n_atm={r.n_atm:>3}  "
                  f"report={r.report_med_prem_pct:.4f}  actual={act}")
    else:
        print("  (payoff CSV unavailable)")

    print("\n=== §6 Coverage gap: which 12 symbols have option-payoff data? ===")
    if Path(args.payoffs).exists():
        po = pd.read_csv(args.payoffs)
        und_counts = po["underlying"].value_counts().to_dict()
        print(f"  {'sym':4s} {'in-payoffs?':>11s} {'rows':>6s}")
        for sym in REPORT_PER_SYMBOL:
            # underlyings look like 'kq_m_shfe_rb', 'kq_m_ine_sc'
            matches = [k for k in und_counts if k.endswith(f"_{sym}")]
            if matches:
                n = sum(und_counts[k] for k in matches)
                print(f"  {sym:4s}  {'YES':>11s}  {n:>6d}")
            else:
                print(f"  {sym:4s}  {'NO':>11s}       0")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
