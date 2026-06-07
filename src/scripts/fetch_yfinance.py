"""Fetch daily OHLCV from yfinance and save in the same JSON shape as TV snapshots.

Usage:
  uv run python scripts/fetch_yfinance.py SPY QQQ NVDA GLD --bars 500
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


def fetch_one(symbol: str, bars: int) -> dict:
    # Pull a bit more than `bars` so we can trim from the tail; weekends/holidays
    # cause calendar-day estimates to under-fill.
    days_back = int(bars * 1.7) + 30
    df = yf.download(
        symbol,
        period=f"{days_back}d",
        interval="1d",
        auto_adjust=True,  # back-adjust for splits; otherwise MACD sees artificial gaps
        progress=False,
    )
    if df.empty:
        raise RuntimeError(f"No data returned for {symbol}")

    # yfinance returns a MultiIndex column frame when multiple tickers — flatten if needed
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = df.columns.get_level_values(0)

    df = df.tail(bars)

    bars_out = []
    for ts, row in df.iterrows():
        # ts is a pandas Timestamp; treat as US Eastern market close ≈ 21:00 UTC
        # Convert to unix seconds at 21:00 UTC of that calendar date.
        dt = ts.to_pydatetime()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # Daily bars: stamp at session-close (~20:00 UTC) like TV usage in earlier files.
        bar_ts = int(dt.replace(hour=20, minute=0, second=0).timestamp())
        bars_out.append({
            "time": bar_ts,
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"]),
        })

    return {
        "symbol": symbol,
        "resolution": "1D",
        "source": "yfinance",
        "fetched_at_data_ts": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "bars": bars_out,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="+", help="Ticker symbols (e.g. SPY QQQ)")
    parser.add_argument("--bars", type=int, default=500, help="Number of bars to keep (default 500)")
    parser.add_argument("--outdir", type=str, default=str(DATA_DIR))
    args = parser.parse_args()

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    for sym in args.symbols:
        try:
            payload = fetch_one(sym, args.bars)
        except Exception as e:
            print(f"  {sym}: ERROR — {e}", file=sys.stderr)
            continue
        path = out / f"{sym.lower()}_daily.json"
        path.write_text(json.dumps(payload, separators=(",", ":")))
        first = payload["bars"][0]["time"]
        last = payload["bars"][-1]["time"]
        first_d = datetime.fromtimestamp(first, tz=timezone.utc).strftime("%Y-%m-%d")
        last_d = datetime.fromtimestamp(last, tz=timezone.utc).strftime("%Y-%m-%d")
        print(f"  {sym}: {len(payload['bars'])} bars {first_d} → {last_d}  →  {path.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
