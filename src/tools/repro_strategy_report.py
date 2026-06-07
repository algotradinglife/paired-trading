"""Reproduce strategy-report-2026-05-30.html.

The report is a 5-pool synthesis. Most claims overlap with the already-reproduced
hopp-stability and crosspool-walkforward reports. The NEW content here is the
per-symbol breakdown tables (§4) plus a handful of single-row filter-rule stats
(§3). This script focuses on the new content:

  1. Per-pool summary  (n, win%, overall EV, h=opp n, h=opp EV)
  2. Per-symbol table  (matches each "品种" row in §4)
  3. Filter-rule stats:
       F1-top-lagging-disabled  : US_EQUITY top × lower=lagging
       CZCE1-bottom-supporting  : CN_AGRI bottom × h=supporting
       CN_METAL top × h=opposing
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


POOL_TO_CSV = {
    "CN_METAL":  "rr_b_cn_metal.csv",
    "CN_AGRI":   "rr_b_cn_agri.csv",
    "CN_INDEX":  "rr_b_cn_index.csv",
    "US_EQUITY": "rr_b_us_equity.csv",
    "US_MACRO":  "rr_b_us_macro.csv",
}

# Map raw symbol string -> short display code used in the report tables.
SYMBOL_LABEL = {
    # CN_METAL
    "kq_m_shfe_rb": "RB",
    "kq_m_shfe_cu": "CU",
    "kq_m_shfe_au": "AU",
    "kq_m_shfe_ag": "AG",
    "kq_m_ine_sc":  "SC",
    # CN_AGRI
    "kq_m_dce_j":   "J",
    "kq_m_dce_jm":  "JM",
    "kq_m_dce_i":   "I",
    "kq_m_dce_m":   "M",
    "kq_m_dce_y":   "Y",
    "kq_m_dce_p":   "P",
    "kq_m_czce_ma": "MA",
    "kq_m_czce_ta": "TA",
    "kq_m_czce_sr": "SR",
    "kq_m_czce_sa": "SA",
    "kq_m_czce_cf": "CF",
    # CN_INDEX
    "kq_m_cffex_im": "IM",
    "kq_m_cffex_if": "IF",
    "kq_m_cffex_ih": "IH",
    "kq_m_cffex_ic": "IC",
}


def load_pool(review_dir: Path, pool: str) -> pd.DataFrame:
    df = pd.read_csv(review_dir / POOL_TO_CSV[pool])
    df["pool"] = pool
    return df


def fmt_ev(x):
    if pd.isna(x):
        return "  n/a "
    return f"{x:+.3f}R"


def per_pool_summary(df: pd.DataFrame) -> dict:
    """n, win%, EV, h=opp n, h=opp EV (no direction filter — overall pool)."""
    r = df.realized_r
    out = {
        "n":   len(df),
        "win": (r > 0).mean() * 100 if len(df) else float("nan"),
        "ev":  r.mean() if len(df) else float("nan"),
    }
    opp = df[df.higher_relation == "opposing"]
    out["n_opp"] = len(opp)
    out["ev_opp"] = opp.realized_r.mean() if len(opp) else float("nan")
    # payoff ratio = mean win / |mean loss|
    wins = r[r > 0]
    losses = r[r < 0]
    if len(wins) and len(losses):
        out["payoff"] = wins.mean() / abs(losses.mean())
    else:
        out["payoff"] = float("nan")
    return out


def per_symbol_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sym, sub in df.groupby("symbol"):
        r = sub.realized_r
        opp = sub[sub.higher_relation == "opposing"]
        rows.append({
            "symbol": SYMBOL_LABEL.get(sym, sym),
            "raw":    sym,
            "n":      len(sub),
            "win":    (r > 0).mean() * 100,
            "ev":     r.mean(),
            "n_opp":  len(opp),
            "ev_opp": opp.realized_r.mean() if len(opp) else float("nan"),
        })
    return (pd.DataFrame(rows)
            .sort_values("ev", ascending=False)
            .reset_index(drop=True))


def filter_rule_stats(by_pool: dict[str, pd.DataFrame]):
    print("\n=== §3 Filter rule data points ===")

    us = by_pool["US_EQUITY"]
    sub = us[(us.direction == "top") & (us.lower_relation == "lagging")]
    print(f"F1-top-lagging-disabled  US_EQUITY top × lower=lagging:")
    print(f"  n={len(sub):3d}  EV={fmt_ev(sub.realized_r.mean())}  "
          f"full-stop%={100*(sub.realized_r == -1).mean():.1f}%   "
          f"[report: n=55 EV=-0.191R 60%]")

    agri = by_pool["CN_AGRI"]
    sub = agri[(agri.direction == "bottom") & (agri.higher_relation == "supporting")]
    print(f"\nCZCE1-bottom-supporting  CN_AGRI bottom × h=supporting:")
    print(f"  n={len(sub):3d}  EV={fmt_ev(sub.realized_r.mean())}  "
          f"full-stop%={100*(sub.realized_r == -1).mean():.1f}%   "
          f"[report: n=42 EV=-0.167R 59.5%]")

    metal = by_pool["CN_METAL"]
    sub = metal[(metal.direction == "top") & (metal.higher_relation == "opposing")]
    print(f"\nCN_METAL top × h=opposing  (monitor):")
    print(f"  n={len(sub):3d}  EV={fmt_ev(sub.realized_r.mean())}  "
          f"full-stop%={100*(sub.realized_r == -1).mean():.1f}%   "
          f"[report: n=15 EV=-0.533R 73%]")

    # CN_METAL top vs bottom overall
    top = metal[metal.direction == "top"]
    bot = metal[metal.direction == "bottom"]
    print(f"\nCN_METAL top overall:    n={len(top):3d}  EV={fmt_ev(top.realized_r.mean())}  "
          f"[report: n=73 EV=-0.052R]")
    print(f"CN_METAL bottom overall: n={len(bot):3d}  EV={fmt_ev(bot.realized_r.mean())}  "
          f"[report: EV=+0.324R]")
    bot_opp = bot[bot.higher_relation == "opposing"]
    print(f"CN_METAL bottom h=opp:   n={len(bot_opp):3d}  EV={fmt_ev(bot_opp.realized_r.mean())}  "
          f"[report: EV=+0.836R]")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--review-dir", type=Path, default=Path("data/review"))
    args = p.parse_args()

    by_pool: dict[str, pd.DataFrame] = {}
    for pool in POOL_TO_CSV:
        by_pool[pool] = load_pool(args.review_dir, pool)

    print("=== §1 Per-pool summary (overall, no direction filter) ===")
    print(f"{'Pool':10s}  {'n':>5s}  {'win%':>6s}  {'payoff':>7s}  "
          f"{'EV':>8s}  {'n_opp':>5s}  {'EV_opp':>8s}")
    report_summary = {
        "CN_INDEX":  dict(ev="+0.490R", win="52.3%", payoff="1.53", ev_opp="+0.840R"),
        "CN_AGRI":   dict(ev="+0.449R", win="53.2%", payoff="1.47", ev_opp="+0.739R"),
        "US_EQUITY": dict(ev="+0.493R", win="54.1%", payoff="1.50", ev_opp="+0.597R"),
        "US_MACRO":  dict(ev="+0.405R", win="50.0%", payoff="1.49", ev_opp="+1.146R"),
        "CN_METAL":  dict(ev="+0.159R", win="45.8%", payoff="1.37", ev_opp="+0.281R"),
    }
    for pool, df in by_pool.items():
        s = per_pool_summary(df)
        rep = report_summary[pool]
        print(f"{pool:10s}  {s['n']:5d}  {s['win']:5.1f}%  "
              f"{s['payoff']:6.2f}x  {fmt_ev(s['ev']):>8s}  "
              f"{s['n_opp']:5d}  {fmt_ev(s['ev_opp']):>8s}   "
              f"[report: EV={rep['ev']} win={rep['win']} payoff={rep['payoff']}x EV_opp={rep['ev_opp']}]")

    for pool in ["CN_INDEX", "CN_METAL", "CN_AGRI", "US_EQUITY", "US_MACRO"]:
        df = by_pool[pool]
        print(f"\n=== §4 {pool} per-symbol ===")
        tab = per_symbol_table(df)
        for _, row in tab.iterrows():
            label = row["symbol"] if row["symbol"] != row["raw"] else row["raw"].upper()
            ev_opp = fmt_ev(row["ev_opp"]) if not pd.isna(row["ev_opp"]) else "  n/a "
            print(f"  {label:6s}  n={row['n']:3d}  win={row['win']:5.1f}%  "
                  f"EV={fmt_ev(row['ev'])}   n_opp={row['n_opp']:3d}  EV_opp={ev_opp}")

    filter_rule_stats(by_pool)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
