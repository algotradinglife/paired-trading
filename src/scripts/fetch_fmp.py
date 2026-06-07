"""Fetch daily + 60min from Financial Modeling Prep (stable API).

Both endpoints return split-adjusted prices by default — confirmed by spot-
checking NVDA's 2024-06-10 10:1 split. No manual back-adjust needed.

Requires env var FMP_API_KEY.

Usage:
  uv run python scripts/fetch_fmp.py SPY QQQ NVDA GLD --tf both --years 10 --intraday-years 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
BASE = "https://financialmodelingprep.com/stable"


def get_key() -> str:
    key = os.environ.get("FMP_API_KEY")
    if not key:
        print("ERROR: set FMP_API_KEY env var first.", file=sys.stderr)
        sys.exit(2)
    return key


def fetch_daily(symbol: str, years: int, key: str) -> list[dict]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=int(years * 366))
    r = requests.get(
        f"{BASE}/historical-price-eod/full",
        params={"symbol": symbol, "from": start.isoformat(), "to": end.isoformat(), "apikey": key},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    if not data or not isinstance(data, list):
        raise RuntimeError(f"No daily data for {symbol}: {data}")

    bars = []
    for row in data:
        d = datetime.strptime(row["date"], "%Y-%m-%d")
        dt = d.replace(hour=20, minute=0, second=0, tzinfo=timezone.utc)
        bars.append({
            "time":   int(dt.timestamp()),
            "open":   float(row["open"]),
            "high":   float(row["high"]),
            "low":    float(row["low"]),
            "close":  float(row["close"]),
            "volume": int(row.get("volume", 0)),
        })
    bars.sort(key=lambda b: b["time"])
    return bars


def fetch_intraday(symbol: str, interval: str, years: int, key: str) -> list[dict]:
    """FMP intraday returns split-adjusted bars. Timestamps are in US/Eastern.
    We store unix seconds (UTC), using a DST-aware America/New_York zone so
    spring/fall bars don't drift by an hour.
    """
    from zoneinfo import ZoneInfo

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=int(years * 366))
    r = requests.get(
        f"{BASE}/historical-chart/{interval}",
        params={"symbol": symbol, "from": start.isoformat(), "to": end.isoformat(), "apikey": key},
        timeout=180,
    )
    r.raise_for_status()
    data = r.json()
    if not data or not isinstance(data, list):
        raise RuntimeError(f"No {interval} data for {symbol}: {data}")

    et = ZoneInfo("America/New_York")
    bars = []
    for row in data:
        dt_et = datetime.strptime(row["date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=et)
        bars.append({
            "time":   int(dt_et.astimezone(timezone.utc).timestamp()),
            "open":   float(row["open"]),
            "high":   float(row["high"]),
            "low":    float(row["low"]),
            "close":  float(row["close"]),
            "volume": int(row.get("volume", 0)),
        })
    bars.sort(key=lambda b: b["time"])
    return bars


def write_snapshot(symbol: str, resolution: str, bars: list[dict]) -> Path:
    payload = {
        "symbol": symbol,
        "resolution": resolution,
        "source": "fmp",
        "fetched_at_data_ts": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "bars": bars,
    }
    name_suffix = "daily" if resolution == "1D" else resolution
    path = DATA_DIR / f"{symbol.lower()}_{name_suffix}.json"
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
    parser.add_argument("--tf", choices=("daily", "60min", "both"), default="both")
    parser.add_argument("--years", type=int, default=10)
    parser.add_argument("--intraday-years", type=int, default=5)
    args = parser.parse_args()

    key = get_key()

    for sym in args.symbols:
        if args.tf in ("daily", "both"):
            try:
                bars = fetch_daily(sym, args.years, key)
                path = write_snapshot(sym, "1D", bars)
                print(f"  {sym} daily: {len(bars)} bars  {fmt_range(bars)}  →  {path.name}")
            except Exception as e:
                print(f"  {sym} daily: ERROR — {e}", file=sys.stderr)
        if args.tf in ("60min", "both"):
            try:
                bars = fetch_intraday(sym, "1hour", args.intraday_years, key)
                path = write_snapshot(sym, "60", bars)
                print(f"  {sym} 60min: {len(bars)} bars  {fmt_range(bars)}  →  {path.name}")
            except Exception as e:
                print(f"  {sym} 60min: ERROR — {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
