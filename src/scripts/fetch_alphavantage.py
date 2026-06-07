"""Backfill US equity OHLC from alphavantage (via qveris CLI).

Writes polygon-shape JSON snapshots to `data/raw/<sym>_<level>.json`
for backward-compatibility with the ~30 existing analysis scripts that
read that path directly. Loader-based callers (the new pipeline)
should use `data.loaders.alphavantage.load_alphavantage_*` directly
instead — this script is a transitional tool.

Polygon-shape JSON wire format (legacy):
```
{
  "symbol": "SPY",
  "resolution": "D" | "60" | "15" | ...,
  "source": "alphavantage",
  "fetched_at": <epoch>,
  "bars": [
    {"time": <epoch_seconds>, "open": ..., "high": ..., "low": ...,
     "close": ..., "volume": ...},
    ...
  ]
}
```

Pre-Stage-C scope: convert the BarFrame's period_end UTC timestamps
BACK to polygon's period_start convention (midnight-ET epoch for daily)
so the existing scripts keep working unchanged. Step 0's polygon
loader does the period_start → period_end normalization on the way in;
this script does the inverse on the way out. The BarFrame contract is
preserved internally — only the on-disk legacy file shape is polygon.

Usage:
  scripts/_with_creds.sh qveris uv run python scripts/fetch_alphavantage.py \\
      --symbol SPY --tf daily

  scripts/_with_creds.sh qveris uv run python scripts/fetch_alphavantage.py \\
      --symbol SPY --tf 5min --start-month 2021-05 --end-month 2026-05

Auth: QVERIS_API_KEY in env (loadable via scripts/_with_creds.sh qveris).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.bar_frame import BarFrame
from data.loaders.alphavantage import (
    load_alphavantage_daily,
    load_alphavantage_intraday,
)

DATA_RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

# Mapping from our internal level to polygon-style resolution code
# stored in the legacy JSON's `resolution` field.
LEVEL_TO_RESOLUTION = {
    "D": "D",
    "1min": "1",
    "5min": "5",
    "15min": "15",
    "30min": "30",
    "60min": "60",
}

# CLI `--tf` alias mapping back to the loader's internal level.
TF_TO_LEVEL = {
    "daily": "D",
    "1min": "1min",
    "5min": "5min",
    "15min": "15min",
    "30min": "30min",
    "60min": "60min",
}


def bar_frame_to_polygon_shape(
    bf: BarFrame,
    *,
    resolution: str,
) -> dict:
    """Convert a BarFrame to the legacy polygon-shape JSON dict.

    For daily bars, the polygon `time` field is the calendar-day's
    midnight US/Eastern epoch (= period_START). We reverse-engineer
    this from the BarFrame's period_END timestamp by:
      - converting the period_end UTC to US/Eastern
      - taking that date's midnight ET
      - converting back to UTC epoch

    For intraday bars, polygon stores period_START as well (the bar
    timestamped 09:35 in our period_end convention covers 09:30→09:35;
    polygon would stamp it at 09:30 ET). We subtract the bar interval
    from each timestamp.
    """
    df = bf.df
    bars: list[dict] = []
    if bf.level == "D":
        # Daily: timestamp is XNYS session_close UTC; rewind to that
        # calendar-day's midnight ET epoch.
        eastern_dates = df["timestamp"].dt.tz_convert(
            "America/New_York").dt.date
        for d, row in zip(eastern_dates, df.itertuples(index=False)):
            midnight_et = pd.Timestamp(d, tz="America/New_York")
            bars.append({
                "time": int(midnight_et.timestamp()),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": int(row.volume),
            })
    else:
        # Intraday: polygon-style `time` is period_START. With clamp
        # reverted in the loader (codex 2026-05-28 round 6), every bar's
        # BarFrame period_end is exactly `period_start + interval`, so
        # `ts - interval` is correct for ALL intraday bars including the
        # last 60min bar of an RTH session (whose actual coverage is
        # 30min but whose alphavantage-reported period is the full 60).
        interval_delta = pd.Timedelta(minutes=int(bf.level.replace("min", "")))
        for ts, row in zip(df["timestamp"], df.itertuples(index=False)):
            period_start = ts - interval_delta
            bars.append({
                "time": int(period_start.timestamp()),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": int(row.volume),
            })

    return {
        "symbol": bf.symbol,
        "resolution": resolution,
        "source": bf.provider,
        "fetched_at": int(bf.as_of.timestamp()),
        "bars": bars,
    }


def _merge_dedupe_by_time(existing: list[dict], new: list[dict]) -> list[dict]:
    """Merge `new` bars into `existing`, keeping NEW values on collision."""
    merged = {b["time"]: b for b in existing}
    for b in new:
        merged[b["time"]] = b
    return sorted(merged.values(), key=lambda b: b["time"])


def write_legacy_snapshot(bf: BarFrame, *, path: Path, resolution: str) -> None:
    """Write `bf` to `path` in polygon-shape JSON, merging with any
    existing snapshot at that path (so incremental fetches accumulate)."""
    new_payload = bar_frame_to_polygon_shape(bf, resolution=resolution)
    if path.exists():
        try:
            existing = json.loads(path.read_text())
            new_payload["bars"] = _merge_dedupe_by_time(
                existing.get("bars", []), new_payload["bars"],
            )
        except (json.JSONDecodeError, KeyError):
            # Corrupt or wrong-shape file; overwrite.
            print(f"WARN: existing {path.name} unreadable; overwriting",
                  file=sys.stderr)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(new_payload, indent=None))


def fetch_daily(symbol: str, *, out_dir: Path) -> Path:
    """Fetch daily bars and OVERWRITE the legacy snapshot.

    Codex P2 (2026-05-28 round 5): we deliberately do NOT support
    `outputsize=compact` here. Split-only adjustment factors are derived
    from the FULL set of `split coefficient` rows in the response; a
    100-bar compact response after an NVDA-style 10:1 split would emit
    the recent bars on the post-split scale while any older bars from
    a previous full backfill remain on the PRE-split scale. Merging
    those would produce a mixed-scale daily file (a silent leak class).

    Always pulling `outputsize=full` (~25y history in one 1.3-credit call)
    avoids this entire class of bug: the new payload becomes the new
    truth, no merge required. Storage cost is trivial (a few hundred KB
    per symbol).
    """
    bf = load_alphavantage_daily(symbol, outputsize="full")
    out_path = out_dir / f"{symbol.lower()}_daily.json"
    # Overwrite (NOT merge) — see docstring.
    new_payload = bar_frame_to_polygon_shape(bf, resolution="D")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(new_payload, indent=None))
    return out_path


def fetch_intraday(
    symbol: str,
    interval: str,
    *,
    out_dir: Path,
    start_month: str | None,
    end_month: str | None,
    extended_hours: bool,
) -> Path:
    """Fetch intraday bars over a month range and merge into the legacy
    snapshot path."""
    if start_month is None and end_month is None:
        # Single trailing-30-day pull.
        bf = load_alphavantage_intraday(
            symbol, interval, month=None, extended_hours=extended_hours,
        )
        out_path = out_dir / f"{symbol.lower()}_{LEVEL_TO_RESOLUTION[interval]}.json"
        write_legacy_snapshot(bf, path=out_path,
                              resolution=LEVEL_TO_RESOLUTION[interval])
        return out_path

    # Loop over months.
    if not (start_month and end_month):
        raise ValueError("must pass BOTH --start-month and --end-month, or neither")
    months = _enumerate_months(start_month, end_month)
    out_path = out_dir / f"{symbol.lower()}_{LEVEL_TO_RESOLUTION[interval]}.json"
    for i, month in enumerate(months, 1):
        print(f"  [{i}/{len(months)}] {symbol} {interval} {month} ...",
              file=sys.stderr)
        bf = load_alphavantage_intraday(
            symbol, interval, month=month, extended_hours=extended_hours,
        )
        write_legacy_snapshot(bf, path=out_path,
                              resolution=LEVEL_TO_RESOLUTION[interval])
    return out_path


def _enumerate_months(start_month: str, end_month: str) -> list[str]:
    """Yield "YYYY-MM" strings from start to end inclusive."""
    start = datetime.strptime(start_month, "%Y-%m")
    end = datetime.strptime(end_month, "%Y-%m")
    if start > end:
        raise ValueError(f"start_month {start_month} > end_month {end_month}")
    months: list[str] = []
    cur = start
    while cur <= end:
        months.append(cur.strftime("%Y-%m"))
        # advance one month
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    return months


def main() -> int:
    p = argparse.ArgumentParser(
        description="Backfill US equity OHLC from alphavantage via qveris.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--symbol", required=True, help="uppercase ticker (e.g. SPY)")
    p.add_argument("--tf", required=True,
                   choices=sorted(TF_TO_LEVEL.keys()),
                   help="timeframe (daily / 1min / 5min / 15min / 30min / 60min)")
    p.add_argument("--out-dir", type=Path, default=DATA_RAW_DIR,
                   help="output directory for legacy snapshot files")
    # intraday-only
    p.add_argument("--start-month", default=None,
                   help="(intraday only) YYYY-MM start of range; default = "
                        "trailing 30 days")
    p.add_argument("--end-month", default=None,
                   help="(intraday only) YYYY-MM end of range (inclusive)")
    p.add_argument("--extended-hours", action="store_true",
                   help="(intraday only) include pre/post-market bars")
    args = p.parse_args()

    level = TF_TO_LEVEL[args.tf]
    symbol = args.symbol.upper()

    if level == "D":
        out = fetch_daily(symbol, out_dir=args.out_dir)
    else:
        out = fetch_intraday(
            symbol, level,
            out_dir=args.out_dir,
            start_month=args.start_month,
            end_month=args.end_month,
            extended_hours=args.extended_hours,
        )
    print(f"Wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
