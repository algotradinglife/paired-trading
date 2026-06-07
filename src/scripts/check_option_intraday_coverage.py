#!/usr/bin/env python3
"""Check current option intraday coverage in data/quant.

Current = option contracts with expiry in [today, today + expiry_window_days].
Intervals checked: 5m, 15m, 1h (60m).
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default="data/quant")
    ap.add_argument("--expiry-window", type=int, default=90)
    ap.add_argument("--details", action="store_true")
    args = ap.parse_args()

    base = Path(args.data_root)
    contracts_dir = base / "_contracts"
    today = pd.Timestamp(date.today())
    window_end = today + pd.Timedelta(days=args.expiry_window)
    intervals = ["5m", "15m", "1h"]
    rows: list[dict] = []

    for cf in sorted(contracts_dir.glob("*.parquet")):
        df = pd.read_parquet(cf)
        df["option_expiry"] = pd.to_datetime(df["option_expiry"])
        cur = df[df["option_expiry"].ge(today) & df["option_expiry"].le(window_end)].copy()
        for portfolio, g in sorted(cur.groupby("option_portfolio")):
            exch = cf.stem
            syms = set(g["symbol"])
            r: dict = {"exchange": exch, "portfolio": portfolio, "total": len(syms)}
            complete = 0
            for sym in syms:
                if all((base / exch / sym / f"{iv}.parquet").exists() for iv in intervals):
                    complete += 1
            r["all3_files"] = complete
            for iv in intervals:
                exist = 0
                gapless = 0
                min_end = None
                max_end = None
                for sym in syms:
                    if (base / exch / sym / f"{iv}.parquet").exists():
                        exist += 1
                    mp = base / exch / sym / f"{iv}.meta.json"
                    if not mp.exists():
                        continue
                    try:
                        m = json.loads(mp.read_text())
                    except Exception:
                        continue
                    e = m.get("end")
                    if e:
                        min_end = e if min_end is None or e < min_end else min_end
                        max_end = e if max_end is None or e > max_end else max_end
                    if not m.get("gaps"):
                        gapless += 1
                r[f"{iv}_exist"] = exist
                r[f"{iv}_gapless"] = gapless
                r[f"{iv}_end_min"] = min_end[:10] if min_end else "-"
                r[f"{iv}_end_max"] = max_end[:10] if max_end else "-"
            rows.append(r)

    out = pd.DataFrame(rows)
    print(f"DATE_LOCAL {today.date()} WINDOW_END {window_end.date()}")
    print("AGG_BY_EXCHANGE")
    if out.empty or "exchange" not in out.columns:
        print("  (no contracts matched)")
        return 0
    agg: list[dict] = []
    for exch, g in out.groupby("exchange"):
        a = {
            "exchange": exch,
            "portfolios": len(g),
            "contracts": int(g.total.sum()),
            "all3_files": int(g.all3_files.sum()),
        }
        for iv in intervals:
            a[f"{iv}_exist"] = int(g[f"{iv}_exist"].sum())
        agg.append(a)
    print(pd.DataFrame(agg).to_string(index=False))

    if args.details:
        print("\nBY_PORTFOLIO: exchange portfolio total all3 5m 15m 1h")
        for row in out.to_dict("records"):
            print(
                f"{str(row['exchange']):5} {str(row['portfolio']):5} "
                f"{int(row['total']):5} {int(row['all3_files']):5} "
                f"{int(row['5m_exist']):5} {int(row['15m_exist']):5} {int(row['1h_exist']):5}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
