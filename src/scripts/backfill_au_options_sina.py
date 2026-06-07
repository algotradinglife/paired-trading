"""Backfill au (黄金 SHFE) option daily bars via Sina Finance / AkShare.

Uses Sina for both contract enumeration and bar fetching — no API key required.
Output: data/options/cn/au/{contract}_daily.json

Usage:
  uv run python scripts/backfill_au_options_sina.py --months 2510 2511 2512 2601 2602 2603 2604 2605 2606 2607
  uv run python scripts/backfill_au_options_sina.py --months 2607          # near-term refresh
  uv run python scripts/backfill_au_options_sina.py --months 2607 --overwrite
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path

import akshare as ak
import pandas as pd

SRC_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = SRC_DIR / "data" / "options" / "cn" / "au"

MIN_BARS_TO_SKIP = 10
SLEEP_BETWEEN = 0.8   # polite rate-limit for Sina
_SINA_NAME = "黄金期权"
_UNDERLYING = "kq_m_shfe_au"


def _get_contracts_for_month(yymm: str) -> list[dict]:
    contract_code = f"au{yymm}"
    try:
        df = ak.option_commodity_contract_table_sina(symbol=_SINA_NAME, contract=contract_code)
    except Exception as e:
        print(f"  [WARN] Sina enumerate error for {contract_code}: {e}", file=sys.stderr)
        return []
    time.sleep(SLEEP_BETWEEN)

    if df is None or df.empty:
        print(f"  [WARN] Sina returned empty for {contract_code}", file=sys.stderr)
        return []

    call_col = next((c for c in df.columns if "看涨期权合约" in c), None)
    put_col  = next((c for c in df.columns if "看跌期权合约" in c), None)
    if call_col is None and put_col is None:
        print(f"  [WARN] no call/put columns for {contract_code}", file=sys.stderr)
        return []

    year  = 2000 + int(yymm[:2])
    month = int(yymm[2:])
    approx_expiry = date(year, month, min(25, monthrange(year, month)[1])).isoformat()

    contracts: list[dict] = []
    for _, row in df.iterrows():
        try:
            strike = float(row.get("行权价", 0) or 0)
        except (ValueError, TypeError):
            strike = 0.0
        for col, ct in ((call_col, "call"), (put_col, "put")):
            if col is None:
                continue
            ticker = str(row.get(col, "")).strip()
            if not ticker or ticker.lower() in ("nan", ""):
                continue
            contracts.append({
                "contract":      ticker.lower(),
                "ticker_sina":   ticker,   # original case for Sina API
                "underlying":    _UNDERLYING,
                "strike":        strike,
                "contract_type": ct,
                "expiry":        approx_expiry,
            })
    return contracts


def _fetch_bars(ticker_sina: str) -> list[dict]:
    """Fetch all available daily bars for a Sina au option ticker."""
    try:
        df = ak.option_commodity_hist_sina(symbol=ticker_sina)
    except Exception as e:
        print(f" WARN: hist_sina error [{ticker_sina}]: {str(e)[:80]}", file=sys.stderr)
        return []
    time.sleep(SLEEP_BETWEEN)

    if df is None or df.empty:
        return []

    bars: list[dict] = []
    for _, row in df.iterrows():
        raw_date = row.get("date")
        if raw_date is None:
            continue
        try:
            if isinstance(raw_date, str):
                d = date.fromisoformat(raw_date[:10])
            elif isinstance(raw_date, (date, datetime)):
                d = raw_date.date() if isinstance(raw_date, datetime) else raw_date
            else:
                d = date.fromisoformat(str(raw_date)[:10])
        except (ValueError, TypeError):
            continue

        ts = int(datetime(d.year, d.month, d.day, 9, 0).timestamp())

        def _f(col):
            v = row.get(col)
            return float(v) if v is not None and pd.notna(v) else None

        bars.append({
            "time":   ts,
            "open":   _f("open"),
            "high":   _f("high"),
            "low":    _f("low"),
            "close":  _f("close"),
            "volume": _f("volume"),
        })
    return bars


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Backfill au option daily bars via Sina Finance → data/options/cn/au/"
    )
    ap.add_argument("--months", nargs="+", required=True, metavar="YYMM")
    ap.add_argument("--overwrite", action="store_true",
                    help="Re-fetch and overwrite existing files")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Enumerate contracts
    all_contracts: list[dict] = []
    for yymm in args.months:
        print(f"  Enumerating au{yymm} from Sina…", flush=True)
        contracts = _get_contracts_for_month(yymm)
        print(f"    {len(contracts)} contracts")
        all_contracts.extend(contracts)

    if not all_contracts:
        print("No contracts found.", file=sys.stderr)
        return 1

    print(f"\n{len(all_contracts)} total contracts to process")

    # Step 2: Fetch bars
    written = skipped = empty = errors = 0
    for i, c in enumerate(all_contracts, 1):
        out_path = OUT_DIR / f"{c['contract']}_daily.json"

        if out_path.exists() and not args.overwrite:
            try:
                existing = json.loads(out_path.read_text())
                if len(existing.get("bars", [])) >= MIN_BARS_TO_SKIP:
                    skipped += 1
                    continue
            except Exception:
                pass

        print(f"  [{i}/{len(all_contracts)}] {c['ticker_sina']}…", end="", flush=True)
        try:
            bars = _fetch_bars(c["ticker_sina"])
        except Exception as e:
            print(f" ERROR: {type(e).__name__}: {str(e)[:80]}")
            errors += 1
            continue

        if not bars:
            print(" (no data)")
            empty += 1
            continue

        payload = {
            "contract":      c["contract"],
            "underlying":    c["underlying"],
            "strike":        c["strike"],
            "contract_type": c["contract_type"],
            "expiry":        c["expiry"],
            "liquidity":     None,
            "bars":          bars,
        }
        out_path.write_text(json.dumps(payload, separators=(",", ":")))
        written += 1
        print(f" {len(bars)} bars → {out_path.name}")

    print(f"\nDone. written={written}  skipped={skipped}  empty={empty}  errors={errors}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
