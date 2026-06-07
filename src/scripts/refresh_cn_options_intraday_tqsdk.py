#!/usr/bin/env python3
"""Refresh current CN option intraday bars from TqSdk into data/quant.

Current = contracts in _contracts/{SHFE,DCE,CZCE}.parquet whose expiry is in
[today, today + expiry_window].  Intervals: 5m, 15m, 1h.

This fills the gap left by AkShare/Minishare option feeds, which only provide
CN option daily bars.
"""
from __future__ import annotations

import argparse
import math
import os
import re
import sys
import time
from datetime import datetime, timezone, date
from pathlib import Path

import pandas as pd
from tqsdk import TqApi, TqAuth

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from quant_data.models import BarData, Exchange, Interval
from quant_data.storage import ParquetStorage

_INTERVAL_SECONDS = {
    Interval.MINUTE_5: 300,
    Interval.MINUTE_15: 900,
    Interval.HOUR_1: 3600,
}
_INTERVAL_LENGTH = {
    Interval.MINUTE_5: 2400,
    Interval.MINUTE_15: 900,
    Interval.HOUR_1: 400,
}
_INTERVAL_BY_VALUE = {iv.value: iv for iv in _INTERVAL_SECONDS}


def _to_tqsdk_symbol(exchange: str, symbol: str) -> str | None:
    """Convert stored CN option symbol to TqSdk instrument id."""
    m = re.match(r"^([A-Z]+)(\d{4})([CP])(\d+)$", symbol)
    if not m:
        return None
    product, yymm, cp, strike = m.groups()
    if exchange == "SHFE":
        return f"SHFE.{product.lower()}{yymm}{cp}{strike}"
    if exchange == "DCE":
        return f"DCE.{product.lower()}{yymm}-{cp}-{strike}"
    if exchange == "CZCE":
        # CZCE/TqSdk uses 3-digit contract month: 2607 -> 607, 2509 -> 509.
        return f"CZCE.{product}{yymm[1:]}{cp}{strike}"
    return None


def _fetch_bars(api: TqApi, tq_symbol: str, storage_symbol: str, exchange: Exchange, interval: Interval) -> list[BarData]:
    k = api.get_kline_serial(tq_symbol, _INTERVAL_SECONDS[interval], data_length=_INTERVAL_LENGTH[interval])
    deadline = time.time() + 5
    last_n = -1
    stable_seen = 0
    while time.time() < deadline:
        api.wait_update(deadline=time.time() + 0.8)
        n = int((k["datetime"] > 0).sum())
        if n > 0 and n == last_n:
            stable_seen += 1
            if stable_seen >= 1:
                break
        else:
            stable_seen = 0
        last_n = n

    valid = k[k["datetime"] > 0].copy()
    if valid.empty:
        return []
    bars: list[BarData] = []
    for _, row in valid.iterrows():
        try:
            ns = int(row["datetime"])
            if ns <= 0:
                continue
            o = float(row["open"])
            h = float(row["high"])
            lo = float(row["low"])
            c = float(row["close"])
            if not all(math.isfinite(x) for x in (o, h, lo, c)):
                continue
            dt = datetime.fromtimestamp(ns / 1_000_000_000, tz=timezone.utc).replace(tzinfo=None)
            bars.append(BarData(
                symbol=storage_symbol,
                exchange=exchange,
                interval=interval,
                datetime=dt,
                open_price=o,
                high_price=h,
                low_price=lo,
                close_price=c,
                volume=float(row.get("volume", 0) or 0),
                open_interest=float(row.get("close_oi", 0) or 0),
            ))
        except Exception:
            continue
    return bars


def _load_current_contracts(data_root: Path, exchanges: list[str], portfolios: set[str] | None, expiry_window: int) -> pd.DataFrame:
    today = pd.Timestamp(date.today())
    end = today + pd.Timedelta(days=expiry_window)
    frames = []
    for exch in exchanges:
        p = data_root / "_contracts" / f"{exch}.parquet"
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        df["exchange"] = exch
        df["option_expiry"] = pd.to_datetime(df["option_expiry"])
        df = df[df["option_expiry"].ge(today) & df["option_expiry"].le(end)].copy()
        if portfolios:
            allowed = {x.upper() for x in portfolios}
            df = df[df["option_portfolio"].astype(str).str.upper().isin(allowed)].copy()
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=str(_SRC / "data" / "quant"))
    ap.add_argument("--expiry-window", type=int, default=90)
    ap.add_argument("--exchanges", nargs="+", default=["SHFE", "DCE", "CZCE"])
    ap.add_argument("--portfolios", nargs="+", default=None)
    ap.add_argument("--intervals", nargs="+", default=["5m", "15m", "1h"], choices=sorted(_INTERVAL_BY_VALUE))
    ap.add_argument("--missing-only", action="store_true", default=False,
                    help="Skip contracts that already have all interval files (default: refresh all)")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--max-contracts", type=int, default=None)
    args = ap.parse_args()

    if not (os.environ.get("TQ_USERNAME") and os.environ.get("TQ_PASSWORD")):
        print("ERROR: TQ_USERNAME/TQ_PASSWORD missing", file=sys.stderr)
        return 2

    data_root = Path(args.data_root)
    contracts = _load_current_contracts(data_root, args.exchanges, set(args.portfolios) if args.portfolios else None, args.expiry_window)
    if contracts.empty:
        print("No current contracts matched.")
        return 0
    if args.max_contracts:
        contracts = contracts.head(args.max_contracts).copy()

    intervals = [_INTERVAL_BY_VALUE[x] for x in args.intervals]
    storage = ParquetStorage(data_root)
    api = TqApi(auth=TqAuth(os.environ["TQ_USERNAME"], os.environ["TQ_PASSWORD"]))
    fetched = saved = skipped = empty = errors = 0
    try:
        total_jobs = len(contracts) * len(intervals)
        job = 0
        for row in contracts.to_dict("records"):
            exch = str(row["exchange"])
            symbol = str(row["symbol"])
            tq_symbol = _to_tqsdk_symbol(exch, symbol)
            if tq_symbol is None:
                errors += len(intervals)
                continue
            exchange = Exchange(exch)
            for interval in intervals:
                job += 1
                out_path = data_root / exch / symbol / f"{interval.value}.parquet"
                if args.missing_only and out_path.exists() and not args.overwrite:
                    skipped += 1
                    continue
                print(f"[{job}/{total_jobs}] {tq_symbol} {interval.value}", flush=True)
                try:
                    bars = _fetch_bars(api, tq_symbol, symbol, exchange, interval)
                except Exception as e:
                    print(f"  ERROR {type(e).__name__}: {str(e)[:160]}", file=sys.stderr, flush=True)
                    errors += 1
                    continue
                fetched += 1
                if not bars:
                    empty += 1
                    continue
                n = storage.save_bar_data(bars)
                saved += n
                print(f"  saved {n} bars", flush=True)
    finally:
        api.close()

    print(f"Done. fetched={fetched} saved={saved} skipped={skipped} empty={empty} errors={errors}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
