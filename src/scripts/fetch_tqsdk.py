"""TqSdk K-line 抓取 — 国内期货 / 期权 多周期历史。

补 AKShare 不能给的两块：
  * 国内期货 60min / 15min 历史（AKShare sina 仅最近 6 天）
  * 国内期权合约 60min / 15min 历史 + ATM 自动发现

输出 JSON shape 与 fetch_polygon.py / fetch_akshare.py 完全一致，
engine 直接读不需任何改动。

Auth: TQ_USERNAME + TQ_PASSWORD (Shinny 快期账户) 环境变量。
免费 endpoint, 单次 get_kline_serial data_length 上限 10000。

Symbol 约定:
  KQ.m@CFFEX.IF      — 沪深300股指期货主力连续
  KQ.m@DCE.m         — 豆粕主力连续
  KQ.m@SHFE.cu       — 沪铜主力连续
  DCE.m2509          — 豆粕 2025-09 合约
  DCE.m2509-C-2900   — 豆粕 2509 看涨期权行权价 2900
  SHFE.au2606        — 沪金 2606
  CFFEX.IF2506       — IF 2025-06 合约

Usage:
  uv run python scripts/fetch_tqsdk.py KQ.m@CFFEX.IF KQ.m@DCE.m --tf daily 60min 15min
  uv run python scripts/fetch_tqsdk.py DCE.m2509-C-2900 --tf daily 60min 15min
  uv run python scripts/fetch_tqsdk.py SHFE.au2606 --tf daily --max-bars 5000
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

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

# Wait at most this many seconds per (symbol, tf) for K-line data to populate.
# K-line data usually arrives in the first wait_update; we just need to give
# the network time. Stops earlier if the valid-row count stops growing.
WAIT_DEADLINE_SEC = 30

TF_TO_SEC = {
    "1min":  60,
    "5min":  300,
    "15min": 900,
    "30min": 1800,
    "60min": 3600,
    "4hour": 14400,
    "daily": 86400,
}

TF_TO_RESOLUTION = {
    "1min":  "1",
    "5min":  "5",
    "15min": "15",
    "30min": "30",
    "60min": "60",
    "4hour": "240",
    "daily": "1D",
}


def _sanitize(symbol: str) -> str:
    """Map TqSdk symbol (containing . @ - characters) to a safe filename stem.

    Examples:
      KQ.m@DCE.m       → kq_m_dce_m
      DCE.m2509-C-2900 → dce_m2509_c_2900
      CFFEX.IF2506     → cffex_if2506
    """
    return re.sub(r"[^0-9a-zA-Z]+", "_", symbol.lower()).strip("_")


def write_snapshot(symbol: str, resolution: str, bars: list[dict]) -> Path:
    payload = {
        "symbol": symbol,
        "resolution": resolution,
        "source": "tqsdk",
        "fetched_at_data_ts": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "bars": bars,
    }
    if resolution == "1D":
        name_suffix = "daily"
    elif resolution == "1W":
        name_suffix = "weekly"
    else:
        name_suffix = resolution
    path = DATA_DIR / f"{_sanitize(symbol)}_{name_suffix}.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")))
    return path


def _df_to_bars(df: pd.DataFrame) -> list[dict]:
    """Convert TqSdk K-line DataFrame to canonical bar dicts.

    TqSdk's `datetime` column is int64 nanoseconds since epoch; empty rows
    (preallocated buffer slots that haven't received data) have datetime=0.
    """
    valid = df[df["datetime"] > 0]
    if valid.empty:
        return []
    bars: list[dict] = []
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


def fetch_kline(api: TqApi, symbol: str, dur_sec: int, max_bars: int) -> list[dict]:
    """Get_kline_serial with bounded wait for buffer to populate."""
    k = api.get_kline_serial(symbol, dur_sec, data_length=max_bars)
    deadline = time.time() + WAIT_DEADLINE_SEC
    last_n = -1
    while time.time() < deadline:
        api.wait_update(deadline=time.time() + 3)
        n = int((k["datetime"] > 0).sum())
        if n > 0 and n == last_n:
            break  # populated and stable
        last_n = n
    return _df_to_bars(k)


def fmt_range(bars: list[dict]) -> str:
    if not bars:
        return "(empty)"
    first = datetime.fromtimestamp(bars[0]["time"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    last = datetime.fromtimestamp(bars[-1]["time"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    return f"{first} → {last}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="+",
                        help="TqSdk symbols (e.g. KQ.m@DCE.m DCE.m2509-C-2900)")
    parser.add_argument("--tf", nargs="+", default=["daily"],
                        choices=sorted(TF_TO_SEC),
                        help="One or more timeframes (default: daily)")
    parser.add_argument("--max-bars", type=int, default=10000,
                        help="Per-request data_length (TqSdk per-call cap 10000)")
    args = parser.parse_args()

    user = os.environ.get("TQ_USERNAME")
    pwd = os.environ.get("TQ_PASSWORD")
    if not (user and pwd):
        print("ERROR: TQ_USERNAME + TQ_PASSWORD env vars required.", file=sys.stderr)
        return 2

    api = TqApi(auth=TqAuth(user, pwd))
    try:
        for sym in args.symbols:
            print(f"Fetching {sym}…")
            for tf in args.tf:
                dur_sec = TF_TO_SEC[tf]
                resolution = TF_TO_RESOLUTION[tf]
                try:
                    bars = fetch_kline(api, sym, dur_sec, args.max_bars)
                except Exception as e:
                    print(f"  {tf}: ERROR — {type(e).__name__}: {str(e)[:200]}",
                          file=sys.stderr)
                    continue
                if not bars:
                    print(f"  {tf}: empty")
                    continue
                p = write_snapshot(sym, resolution, bars)
                print(f"  {tf}: {len(bars)} bars  {fmt_range(bars)}  →  {p.name}")
    finally:
        api.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
