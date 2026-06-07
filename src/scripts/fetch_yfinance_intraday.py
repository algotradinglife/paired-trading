"""Fetch 60min OHLCV via yfinance using chunked requests.

yfinance hourly cap: ~730 days total history; single call usually <60 days.

Usage:
  uv run python scripts/fetch_yfinance_intraday.py SPY QQQ NVDA GLD --days 720

Notes:
  - Uses auto_adjust=True (split+dividend adjusted). Inconsistent with FMP
    daily (split-only) but MACD divergence patterns are unaffected.
  - Walks BACKWARD from now in 25-day windows; even if a chunk returns empty
    (e.g. weekends, holiday-only ranges, edge of 730-day cap), the loop still
    advances. Stops after 3 consecutive empty chunks.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Silence yfinance's noisy stderr logging for failed downloads — we handle
# empties ourselves.
os.environ.setdefault("YF_QUIET", "1")
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore")

import yfinance as yf

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

CHUNK_DAYS = 25
SLEEP_SECONDS = 0.4
MAX_CONSECUTIVE_EMPTY = 3
SAFETY_DAYS = 5     # back off from yfinance 730-day cap


def fetch_chunked(symbol: str, total_days: int) -> list[dict]:
    end = datetime.now(timezone.utc)
    earliest = end - timedelta(days=total_days - SAFETY_DAYS)
    seen: dict[int, dict] = {}

    cur_end = end
    consecutive_empty = 0
    chunk_count = 0

    while cur_end > earliest:
        cur_start = max(cur_end - timedelta(days=CHUNK_DAYS), earliest)
        chunk_count += 1
        try:
            df = yf.download(
                symbol,
                start=cur_start.strftime("%Y-%m-%d"),
                end=cur_end.strftime("%Y-%m-%d"),
                interval="60m",
                auto_adjust=True,
                progress=False,
                threads=False,
            )
        except Exception:
            df = None

        is_empty = df is None or df.empty
        if is_empty:
            consecutive_empty += 1
            if consecutive_empty >= MAX_CONSECUTIVE_EMPTY:
                # hit the historical cap; stop
                break
        else:
            consecutive_empty = 0
            if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
                df.columns = df.columns.get_level_values(0)
            for ts, row in df.iterrows():
                dt = ts.to_pydatetime()
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                t = int(dt.timestamp())
                if t in seen:
                    continue
                vol = row["Volume"]
                seen[t] = {
                    "time":   t,
                    "open":   float(row["Open"]),
                    "high":   float(row["High"]),
                    "low":    float(row["Low"]),
                    "close":  float(row["Close"]),
                    "volume": int(vol) if vol == vol else 0,    # NaN guard
                }

        # ALWAYS advance backwards, regardless of success/failure
        cur_end = cur_start
        time.sleep(SLEEP_SECONDS)

    bars = sorted(seen.values(), key=lambda b: b["time"])
    print(f"  ({chunk_count} chunks, {len(bars)} unique bars)")
    return bars


def write_snapshot(symbol: str, bars: list[dict]) -> Path:
    payload = {
        "symbol": symbol,
        "resolution": "60",
        "source": "yfinance",
        "fetched_at_data_ts": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "bars": bars,
    }
    path = DATA_DIR / f"{symbol.lower()}_60.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")))
    return path


def fmt_range(bars: list[dict]) -> str:
    first = datetime.fromtimestamp(bars[0]["time"], tz=timezone.utc).strftime("%Y-%m-%d")
    last = datetime.fromtimestamp(bars[-1]["time"], tz=timezone.utc).strftime("%Y-%m-%d")
    return f"{first} → {last}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--days", type=int, default=720)
    args = parser.parse_args()

    for sym in args.symbols:
        print(f"Fetching {sym} 60min…")
        try:
            bars = fetch_chunked(sym, args.days)
        except Exception as e:
            print(f"  {sym}: ERROR — {e}", file=sys.stderr)
            continue
        if not bars:
            print(f"  {sym}: no bars returned", file=sys.stderr)
            continue
        path = write_snapshot(sym, bars)
        print(f"  {sym}: {len(bars)} bars {fmt_range(bars)} → {path.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
