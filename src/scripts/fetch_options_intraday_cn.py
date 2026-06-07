"""Fetch intraday (15min + 60min) option bars for CN commodity options via TqSdk.

Reads all existing daily JSON files under data/options/cn/, builds the TqSdk
symbol for each contract, and fetches 15min + 60min K-lines. Skips contracts
whose intraday files already exist and have ≥ MIN_BARS bars.

TqSdk symbol construction:
  SHFE/DCE:  {EXCHANGE}.{instrument}{yymm}-C-{strike}  e.g. SHFE.au2605-C-576
  CZCE:      CZCE.{INSTR}{yyy}{C/P}{strike}             e.g. CZCE.SR511C5600
             where yyy = last_digit_of_year + 2-digit_month

Auth: TQ_USERNAME + TQ_PASSWORD env vars (set via _with_creds.sh tqsdk).

Usage:
  scripts/_with_creds.sh tqsdk uv run python scripts/fetch_options_intraday_cn.py
  scripts/_with_creds.sh tqsdk uv run python scripts/fetch_options_intraday_cn.py \\
      --tfs 15min 60min --batch-size 30 --underlying au cu m
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from tqsdk import TqApi, TqAuth

SRC_DIR    = Path(__file__).resolve().parents[1]
CN_OPT_DIR = SRC_DIR / "data" / "options" / "cn"

WAIT_SEC     = 45
MIN_BARS     = 5
BATCH_SIZE   = 30

# Exchange mapping: lowercase instrument → exchange prefix
EXCHANGE_MAP: dict[str, str] = {
    # SHFE
    "au": "SHFE", "ag": "SHFE", "cu": "SHFE", "rb": "SHFE",
    "al": "SHFE", "zn": "SHFE", "ni": "SHFE", "sn": "SHFE",
    # DCE
    "m":  "DCE",  "i":  "DCE",  "pg": "DCE",  "c":  "DCE",
    "cs": "DCE",  "v":  "DCE",  "pp": "DCE",  "l":  "DCE",
    # CZCE
    "sr": "CZCE", "ma": "CZCE", "ta": "CZCE", "cf": "CZCE",
    "rm": "CZCE", "zc": "CZCE", "wr": "CZCE",
}

TF_SEC = {"15min": 900, "60min": 3600}

# Regex: e.g. "cu2605P94000" or "sr2511C5600"
CONTRACT_RE = re.compile(
    r"^([a-z]+)(\d{4})([CP])(\d+)$", re.IGNORECASE
)


def _czce_month(yymm: str) -> str:
    """Convert 4-digit yymm to CZCE 3-digit yyy.

    yymm='2511' → last-digit-of-year='5', month='11' → '511'
    """
    year2  = yymm[:2]   # e.g. '25'
    month2 = yymm[2:]   # e.g. '11'
    return year2[-1] + month2   # '5' + '11' = '511'


def contract_to_tqsdk(contract: str, underlying: str) -> str | None:
    """Return TqSdk symbol string, or None if unrecognised.

    Format by exchange:
      SHFE: SHFE.{instr}{yymm}{C/P}{strike}   e.g. SHFE.au2112C380
      DCE:  DCE.{instr}{yymm}-{C/P}-{strike}  e.g. DCE.m2209-C-3000
      CZCE: CZCE.{INSTR}{yyy}{C/P}{strike}    e.g. CZCE.SR201C5900
    """
    m = CONTRACT_RE.match(contract)
    if not m:
        return None
    instr, yymm, cp, strike = m.group(1).lower(), m.group(2), m.group(3).upper(), m.group(4)

    # Parse exchange from underlying field: 'kq_m_shfe_cu' → 'SHFE'
    parts = underlying.split("_")
    if len(parts) >= 4:
        exchange = parts[2].upper()
    else:
        exchange = EXCHANGE_MAP.get(instr, "").upper()

    if not exchange:
        return None

    if exchange == "CZCE":
        yyy = _czce_month(yymm)
        return f"CZCE.{instr.upper()}{yyy}{cp}{strike}"
    elif exchange == "SHFE":
        # SHFE options use no-hyphen format with uppercase C/P
        return f"SHFE.{instr}{yymm}{cp}{strike}"
    else:
        # DCE and others: hyphen format
        return f"{exchange}.{instr}{yymm}-{cp}-{strike}"


def _load_contracts() -> list[dict]:
    """Return list of contract metadata dicts, deduped by contract name."""
    seen: set[str] = set()
    contracts: list[dict] = []
    for f in CN_OPT_DIR.rglob("*_daily.json"):
        try:
            payload = json.loads(f.read_text())
        except Exception:
            continue
        raw = payload.get("contract", "")
        key = raw.lower()
        if key in seen:
            continue
        seen.add(key)

        tqsdk_sym = contract_to_tqsdk(key, payload.get("underlying", ""))
        if tqsdk_sym is None:
            continue

        contracts.append({
            "contract":      raw,
            "key":           key,
            "underlying":    payload.get("underlying", ""),
            "strike":        payload.get("strike"),
            "contract_type": payload.get("contract_type"),
            "expiry":        payload.get("expiry"),
            "tqsdk_sym":     tqsdk_sym,
            "out_dir":       f.parent,
        })
    return contracts


def _already_complete(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return len(json.loads(path.read_text()).get("bars", [])) >= MIN_BARS
    except Exception:
        return False


def _df_to_bars(df: pd.DataFrame) -> list[dict]:
    valid = df[df["datetime"] > 0].copy()
    if valid.empty:
        return []
    bars = []
    for _, row in valid.iterrows():
        ts_sec = int(row.datetime) // 1_000_000_000
        try:
            vol = int(row.volume) if pd.notna(row.volume) else 0
        except (ValueError, TypeError):
            vol = 0
        bars.append({
            "time":   ts_sec,
            "open":   float(row.open),
            "high":   float(row.high),
            "low":    float(row.low),
            "close":  float(row.close),
            "volume": vol,
        })
    return bars


def _liquidity_meta(bars: list[dict]) -> dict:
    if not bars:
        return {}
    vols = [b["volume"] for b in bars if b.get("volume", 0) > 0]
    if not vols:
        return {"avg_daily_volume": 0, "liquidity_flag": "no_volume"}
    avg  = sum(vols) / len(vols)
    flag = "ok" if avg >= 50 else ("thin" if avg >= 10 else "illiquid")
    return {"avg_daily_volume": round(avg, 1), "liquidity_flag": flag}


def _write(path: Path, meta: dict, bars: list[dict]) -> None:
    payload = {
        "contract":      meta["contract"],
        "underlying":    meta["underlying"],
        "strike":        meta["strike"],
        "contract_type": meta["contract_type"],
        "expiry":        meta["expiry"],
        "liquidity":     _liquidity_meta(bars),
        "bars":          bars,
    }
    path.write_text(json.dumps(payload, separators=(",", ":")))


def fetch_batch(
    api:        TqApi,
    batch:      list[dict],
    tfs:        list[str],
    written:    dict[str, int],
    skipped:    dict[str, int],
    err_count:  list[int],
) -> None:
    """Subscribe all (symbol, tf) combos in this batch, wait, then export."""
    tasks: list[tuple[dict, str, Path, pd.DataFrame]] = []

    for meta in batch:
        sym = meta["tqsdk_sym"]
        for tf in tfs:
            safe = re.sub(r"[^0-9a-z]+", "_", meta["key"]).strip("_")
            out_path = meta["out_dir"] / f"{safe}_{tf}.json"
            if _already_complete(out_path):
                skipped[tf] = skipped.get(tf, 0) + 1
                continue
            try:
                kdf = api.get_kline_serial(sym, TF_SEC[tf], data_length=10000)
                tasks.append((meta, tf, out_path, kdf))
            except Exception as exc:
                print(f"    subscribe error [{sym} {tf}]: {exc}", file=sys.stderr)
                err_count[0] += 1

    if not tasks:
        return

    # Wait until stable or deadline
    deadline = time.time() + WAIT_SEC
    last_n   = -1
    while time.time() < deadline:
        api.wait_update(deadline=time.time() + 3)
        n = sum(int((t[3]["datetime"] > 0).sum()) for t in tasks)
        if n > 0 and n == last_n:
            break
        last_n = n

    for meta, tf, out_path, kdf in tasks:
        bars = _df_to_bars(kdf)
        if not bars:
            continue
        _write(out_path, meta, bars)
        written[tf] = written.get(tf, 0) + 1
        print(f"    [{meta['tqsdk_sym']} {tf}] {len(bars)} bars → {out_path.name}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch CN option intraday bars via TqSdk."
    )
    parser.add_argument(
        "--tfs", nargs="+", choices=list(TF_SEC), default=list(TF_SEC),
        metavar="TF", help="Timeframes to fetch (default: 15min 60min)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=BATCH_SIZE,
        help=f"Contracts per TqSdk session (default: {BATCH_SIZE})",
    )
    parser.add_argument(
        "--underlying", nargs="+", default=None,
        metavar="UND",
        help="Filter to specific underlying instruments (e.g. au cu m)",
    )
    args = parser.parse_args()

    user = os.environ.get("TQ_USERNAME")
    pwd  = os.environ.get("TQ_PASSWORD")
    if not (user and pwd):
        print("ERROR: TQ_USERNAME + TQ_PASSWORD env vars required.", file=sys.stderr)
        return 2

    all_contracts = _load_contracts()
    print(f"Found {len(all_contracts)} unique contracts in {CN_OPT_DIR}")

    if args.underlying:
        und_set = set(args.underlying)
        all_contracts = [
            c for c in all_contracts
            if c["underlying"].split("_")[-1] in und_set
        ]
        print(f"Filtered to underlying={args.underlying}: {len(all_contracts)} contracts")

    written: dict[str, int] = {tf: 0 for tf in args.tfs}
    skipped: dict[str, int] = {tf: 0 for tf in args.tfs}
    err_count: list[int]    = [0]

    batches = [
        all_contracts[i : i + args.batch_size]
        for i in range(0, len(all_contracts), args.batch_size)
    ]
    print(f"Batches: {len(batches)} × ≤{args.batch_size} contracts")

    for batch_idx, batch in enumerate(batches, 1):
        syms = [c["tqsdk_sym"] for c in batch]
        print(f"\nBatch {batch_idx}/{len(batches)}  ({syms[0]} … {syms[-1]})")
        try:
            api = TqApi(auth=TqAuth(user, pwd))
        except Exception as exc:
            print(f"  TqApi connect error: {exc}", file=sys.stderr)
            err_count[0] += 1
            continue
        try:
            fetch_batch(api, batch, args.tfs, written, skipped, err_count)
        finally:
            api.close()

    print("\n" + "=" * 60)
    print("SUMMARY")
    for tf in args.tfs:
        print(f"  [{tf}]  written={written.get(tf, 0)}  skipped={skipped.get(tf, 0)}")
    print(f"  Errors: {err_count[0]}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
