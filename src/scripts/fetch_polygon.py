"""Fetch OHLCV bars via a Polygon proxy.

Proxy injects the upstream apikey; we authenticate with X-Proxy-Key header.
Polygon Starter returns ~1030 results per page; we follow `next_url` and
rewrite the host to the proxy.

Env:
  POLYGON_PROXY_URL   default http://35.77.84.125:8080
  POLYGON_PROXY_KEY   required

Usage:
  uv run python scripts/fetch_polygon.py SPY QQQ NVDA GLD --tf 60min --years 5
  uv run python scripts/fetch_polygon.py SPY --tf daily --years 10
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
DEFAULT_PROXY = "http://35.77.84.125:8080"
UPSTREAM_HOST = "https://api.polygon.io"
SLEEP_BETWEEN_PAGES = 0.5
TIMEOUT = 60


def get_proxy_url() -> str:
    return os.environ.get("POLYGON_PROXY_URL", DEFAULT_PROXY)


def get_proxy_key() -> str:
    key = os.environ.get("POLYGON_PROXY_KEY")
    if not key:
        print("ERROR: set POLYGON_PROXY_KEY env var first.", file=sys.stderr)
        sys.exit(2)
    return key


def rewrite_to_proxy(url: str, proxy: str) -> str:
    """Polygon's next_url points to api.polygon.io; route it through the proxy."""
    if url.startswith(UPSTREAM_HOST):
        return proxy + url[len(UPSTREAM_HOST):]
    return url


def aggregates_url(proxy: str, ticker: str, multiplier: int, timespan: str,
                   start: str, end: str) -> str:
    return (
        f"{proxy}/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}"
        f"/{start}/{end}?adjusted=true&limit=50000&sort=asc"
    )


def fetch_paginated(url: str, headers: dict, proxy: str) -> list[dict]:
    """Follow next_url until exhausted. Returns concatenated `results` list."""
    out: list[dict] = []
    page = 0
    while url:
        page += 1
        r = requests.get(url, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        payload = r.json()
        results = payload.get("results") or []
        out.extend(results)
        nxt = payload.get("next_url")
        if not nxt:
            break
        url = rewrite_to_proxy(nxt, proxy)
        time.sleep(SLEEP_BETWEEN_PAGES)
    print(f"    ({page} pages, {len(out)} bars)")
    return out


def bars_to_json_shape(results: list[dict]) -> list[dict]:
    """Convert Polygon aggregate rows to our canonical bar shape."""
    bars = []
    for row in results:
        bars.append({
            "time":   int(row["t"] // 1000),    # ms → s
            "open":   float(row["o"]),
            "high":   float(row["h"]),
            "low":    float(row["l"]),
            "close":  float(row["c"]),
            "volume": int(row.get("v", 0)),
        })
    bars.sort(key=lambda b: b["time"])
    # de-dup by time (paginated pages can overlap at boundaries)
    seen = set()
    deduped = []
    for b in bars:
        if b["time"] in seen:
            continue
        seen.add(b["time"])
        deduped.append(b)
    return deduped


def _sanitize_filename(symbol: str) -> str:
    """Convert ticker symbols (incl. option tickers like 'O:SPY250620C00580000')
    into safe filename stems."""
    return symbol.lower().replace(":", "_")


def write_snapshot(symbol: str, resolution: str, bars: list[dict]) -> Path:
    payload = {
        "symbol": symbol,
        "resolution": resolution,
        "source": "polygon",
        "fetched_at_data_ts": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "bars": bars,
    }
    if resolution == "1D":
        name_suffix = "daily"
    elif resolution == "1W":
        name_suffix = "weekly"
    else:
        name_suffix = resolution
    path = DATA_DIR / f"{_sanitize_filename(symbol)}_{name_suffix}.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")))
    return path


def fmt_range(bars: list[dict]) -> str:
    first = datetime.fromtimestamp(bars[0]["time"], tz=timezone.utc).strftime("%Y-%m-%d")
    last = datetime.fromtimestamp(bars[-1]["time"], tz=timezone.utc).strftime("%Y-%m-%d")
    return f"{first} → {last}"


def fetch_one(symbol: str, multiplier: int, timespan: str, years: int,
              proxy: str, headers: dict,
              start_override: str | None = None,
              end_override: str | None = None) -> list[dict]:
    end_date = (
        datetime.strptime(end_override, "%Y-%m-%d").date()
        if end_override else datetime.now(timezone.utc).date()
    )
    start_date = (
        datetime.strptime(start_override, "%Y-%m-%d").date()
        if start_override else end_date - timedelta(days=int(years * 366))
    )
    url = aggregates_url(proxy, symbol, multiplier, timespan,
                         start_date.isoformat(), end_date.isoformat())
    results = fetch_paginated(url, headers, proxy)
    return bars_to_json_shape(results)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="+",
                        help="Tickers or option contract IDs (e.g. SPY, O:SPY250620C00580000)")
    parser.add_argument("--tf", choices=("60min", "daily", "weekly", "5min", "15min", "30min", "4hour"),
                        default="60min")
    parser.add_argument("--years", type=int, default=5,
                        help="Calendar years back; ignored if --start/--end given")
    parser.add_argument("--start", type=str, default=None,
                        help="YYYY-MM-DD lower bound (overrides --years)")
    parser.add_argument("--end", type=str, default=None,
                        help="YYYY-MM-DD upper bound (overrides --years)")
    args = parser.parse_args()

    proxy = get_proxy_url()
    headers = {"X-Proxy-Key": get_proxy_key()}

    tf_config = {
        # tf arg → (multiplier, timespan, resolution-string-for-snapshot)
        "5min":   (5,  "minute", "5"),
        "15min":  (15, "minute", "15"),
        "30min":  (30, "minute", "30"),
        "60min":  (1,  "hour",   "60"),
        "4hour":  (4,  "hour",   "240"),
        "daily":  (1,  "day",    "1D"),
        "weekly": (1,  "week",   "1W"),
    }
    multiplier, timespan, resolution = tf_config[args.tf]

    range_desc = (
        f"{args.start}..{args.end}" if (args.start or args.end)
        else f"{args.years}y"
    )
    for sym in args.symbols:
        print(f"Fetching {sym} {args.tf} ({range_desc})…")
        try:
            bars = fetch_one(sym, multiplier, timespan, args.years, proxy, headers,
                             start_override=args.start, end_override=args.end)
        except Exception as e:
            print(f"  {sym}: ERROR — {e}", file=sys.stderr)
            continue
        if not bars:
            print(f"  {sym}: no bars returned", file=sys.stderr)
            continue
        path = write_snapshot(sym, resolution, bars)
        print(f"  {sym}: {len(bars)} bars {fmt_range(bars)} → {path.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
