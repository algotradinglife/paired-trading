"""Backfill / refresh ag (白银 SHFE) option daily bars via TqSdk.

Enumerates option strikes from Sina Finance (works for both expired and
active contract months), then fetches daily OHLCV bars from TqSdk.
Output: data/options/cn/ag/{contract}_daily.json

Auth:
  TqSdk — TQ_USERNAME + TQ_PASSWORD env vars (set in ~/.zshrc)
  → run via: zsh -i -c 'cd /path/to/src && uv run python scripts/backfill_ag_options_tqsdk.py ...'

Usage:
  # Historical backfill (expired contracts)
  zsh -i -c 'cd ... && uv run python scripts/backfill_ag_options_tqsdk.py --months 2505 2506 2507'
  # Near-term refresh (active contracts)
  zsh -i -c 'cd ... && uv run python scripts/backfill_ag_options_tqsdk.py --months 2607'
  # Both at once
  zsh -i -c 'cd ... && uv run python scripts/backfill_ag_options_tqsdk.py --months 2505 2506 2507 2607'
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import akshare as ak
import pandas as pd
from tqsdk import TqApi, TqAuth

SRC_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = SRC_DIR / "data" / "options" / "cn" / "ag"

WAIT_DEADLINE_SEC = 6   # contracts with data populate in <2s; deep OTM timeouts drop to 6s
MIN_BARS_TO_SKIP = 10

_SINA_NAME = "白银期权"


def _get_contracts_for_month(yymm: str) -> list[dict]:
    """Get ag option contracts for one YYMM month via Sina Finance."""
    contract_code = f"ag{yymm}"
    try:
        df = ak.option_commodity_contract_table_sina(
            symbol=_SINA_NAME, contract=contract_code
        )
    except Exception as e:
        print(f"  [WARN] Sina error for {contract_code}: {e}", file=sys.stderr)
        return []

    if df is None or df.empty:
        print(f"  [WARN] Sina returned empty for {contract_code}", file=sys.stderr)
        return []

    call_col = next((c for c in df.columns if "看涨期权合约" in c), None)
    put_col  = next((c for c in df.columns if "看跌期权合约" in c), None)
    if call_col is None and put_col is None:
        print(f"  [WARN] no call/put columns in Sina response for {contract_code}",
              file=sys.stderr)
        return []

    contracts: list[dict] = []
    for _, row in df.iterrows():
        for col, ct in ((call_col, "call"), (put_col, "put")):
            if col is None:
                continue
            ticker = str(row.get(col, "")).strip()
            if not ticker or ticker.lower() in ("nan", ""):
                continue
            # ticker looks like "ag2505C6100" — convert to TqSdk format
            # SHFE.ag2505-C-6100
            m = re.match(r"^(ag\d{4})(C|P)(\d+)$", ticker, re.IGNORECASE)
            if not m:
                continue
            inst, typ, strike = m.group(1), m.group(2).upper(), m.group(3)
            # SHFE options use no-hyphen format: SHFE.ag2607C18200
            tqsdk_sym = f"SHFE.{inst}{typ}{strike}"
            contracts.append({
                "contract":      ticker.lower(),
                "contract_type": ct,
                "tqsdk_sym":     tqsdk_sym,
            })

    return contracts


def _fetch_daily_bars(api: TqApi, tqsdk_sym: str, max_bars: int) -> list[dict]:
    """Fetch daily K-line bars for one TqSdk symbol."""
    k = api.get_kline_serial(tqsdk_sym, 86400, data_length=max_bars)
    deadline = time.time() + WAIT_DEADLINE_SEC
    last_n = -1
    while time.time() < deadline:
        api.wait_update(deadline=time.time() + 3)
        n = int((k["datetime"] > 0).sum())
        if n > 0 and n == last_n:
            break
        last_n = n

    valid = k[k["datetime"] > 0]
    if valid.empty:
        return []

    bars: list[dict] = []
    for _, row in valid.iterrows():
        ts = int(row.datetime) // 1_000_000_000
        try:
            vol = int(row.volume) if pd.notna(row.volume) else 0
        except (ValueError, TypeError):
            vol = 0
        bars.append({
            "time":   ts,
            "open":   float(row.open),
            "high":   float(row.high),
            "low":    float(row.low),
            "close":  float(row.close),
            "volume": vol,
        })
    return bars


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Backfill ag option daily bars via TqSdk → data/options/cn/ag/"
    )
    ap.add_argument(
        "--months", nargs="+", required=True,
        metavar="YYMM",
        help="Contract months in YYMM format, e.g. 2505 2506 2507 2607",
    )
    ap.add_argument(
        "--strikes", nargs="+", type=int, default=None,
        metavar="STRIKE",
        help="Only fetch these specific strike prices (optional filter)",
    )
    ap.add_argument("--max-bars", type=int, default=1000,
                    help="TqSdk data_length per request (default: 1000)")
    ap.add_argument("--overwrite", action="store_true",
                    help="Re-fetch and overwrite existing files")
    args = ap.parse_args()

    user = os.environ.get("TQ_USERNAME")
    pwd  = os.environ.get("TQ_PASSWORD")
    if not (user and pwd):
        print("ERROR: TQ_USERNAME + TQ_PASSWORD env vars required.\n"
              "Run via: zsh -i -c 'uv run python scripts/backfill_ag_options_tqsdk.py ...'",
              file=sys.stderr)
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- Step 1: Enumerate contracts via Sina Finance ---
    all_contracts: list[dict] = []
    for yymm in args.months:
        print(f"  Enumerating ag{yymm} from Sina…", flush=True)
        contracts = _get_contracts_for_month(yymm)
        print(f"    {len(contracts)} contracts")
        all_contracts.extend(contracts)
        time.sleep(0.5)  # polite rate-limit between Sina calls

    if not all_contracts:
        print("No contracts found — nothing to do.", file=sys.stderr)
        return 1

    # Optional strike filter (e.g. for targeted near-ATM refresh)
    if args.strikes:
        strike_set = set(args.strikes)
        all_contracts = [c for c in all_contracts if int(re.search(r"\d+$", c["contract"]).group()) in strike_set]
        print(f"  After --strikes filter: {len(all_contracts)} contracts")

    print(f"\n{len(all_contracts)} total contracts to process")

    # --- Step 2: Fetch TqSdk bars ---
    print(f"Connecting to TqSdk as {user}…")
    api = TqApi(auth=TqAuth(user, pwd))
    written = skipped = empty = errors = 0

    try:
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

            print(f"  [{i}/{len(all_contracts)}] {c['tqsdk_sym']}…", end="", flush=True)
            try:
                bars = _fetch_daily_bars(api, c["tqsdk_sym"], args.max_bars)
            except Exception as e:
                print(f" ERROR: {type(e).__name__}: {str(e)[:120]}")
                errors += 1
                continue

            if not bars:
                print(" (no data)")
                empty += 1
                continue

            # Parse metadata from contract symbol (e.g. "ag2505c6100")
            m_meta = re.match(r"^(ag)(\d{4})[cp](\d+)$", c["contract"], re.IGNORECASE)
            payload = {
                "contract":      c["contract"],
                "underlying":    m_meta.group(1) if m_meta else "ag",
                "expiry":        m_meta.group(2) if m_meta else None,
                "strike":        int(m_meta.group(3)) if m_meta else None,
                "contract_type": c["contract_type"],
                "bars":          bars,
            }
            out_path.write_text(json.dumps(payload, separators=(",", ":")))
            written += 1
            print(f" {len(bars)} bars → {out_path.name}")

    finally:
        api.close()

    print(f"\nDone. written={written}  skipped={skipped}  empty={empty}  errors={errors}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
