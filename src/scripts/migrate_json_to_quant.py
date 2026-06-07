"""Migrate legacy JSON snapshots → quant-data Parquet store.

Reads every {sym}_{suffix}.json file in data/raw/ (skipping kq_m_ CN futures
which have a separate fetch workflow), converts bars to BarData, and upserts
into the local quant store at data/quant/.

Usage:
  uv run python scripts/migrate_json_to_quant.py              # all US symbols
  uv run python scripts/migrate_json_to_quant.py SPY QQQ      # specific symbols
  uv run python scripts/migrate_json_to_quant.py --dry-run    # preview only
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data import bar_loader
from quant_data.models import BarData, Exchange, Interval
from quant_data.storage.parquet import ParquetStorage

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
_DEFAULT_QUANT_ROOT = Path(__file__).resolve().parents[1] / "data" / "quant"

# MIC → quant-data Exchange enum (matches store.py _EXCHANGE_MAP)
_MIC_TO_EXCHANGE: dict[str, Exchange] = {
    "XNYS": Exchange.NYSE,
    "XNAQ": Exchange.NASDAQ,
    "XSHG": Exchange.SSE,
    "XSHE": Exchange.SZSE,
    "XSHF": Exchange.SHFE,
    "XDCE": Exchange.DCE,
    "XZCE": Exchange.CZCE,
    "XCFE": Exchange.CFFEX,
    "XINE": Exchange.INE,
    "XGFE": Exchange.GFEX,
}


def _json_to_bar_data(
    path: Path,
    symbol: str,
    exchange: Exchange,
    interval: Interval,
) -> list[BarData]:
    df = bar_loader.load_bars_json(path)
    bars: list[BarData] = []
    for _, row in df.iterrows():
        ts = row["timestamp"]
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        bars.append(BarData(
            symbol=symbol,
            exchange=exchange,
            datetime=ts.to_pydatetime(),
            interval=interval,
            open_price=float(row["open"]),
            high_price=float(row["high"]),
            low_price=float(row["low"]),
            close_price=float(row["close"]),
            volume=float(row.get("volume", 0) or 0),
        ))
    return bars


def discover_files(symbols: list[str] | None = None) -> list[tuple[Path, str, Exchange, Interval]]:
    """Return (path, symbol, exchange, interval) tuples for each migratable JSON.

    Uses bar_loader.parse_snapshot_name() so both US equities (spy_daily.json)
    and CN futures (kq_m_cffex_if_daily.json → IF0/XCFE/D) are handled.
    """
    results = []
    for p in sorted(RAW_DIR.glob("*.json")):
        parsed = bar_loader.parse_snapshot_name(p.name)
        if parsed is None:
            continue
        quant_sym, mic, barstore_level = parsed
        exchange = _MIC_TO_EXCHANGE.get(mic)
        if exchange is None:
            continue
        interval_map = {
            "D":     Interval.DAILY,
            "W":     Interval.WEEKLY,
            "60min": Interval.HOUR_1,
            "4h":    Interval.HOUR_4,
            "30min": Interval.MINUTE_30,
            "15min": Interval.MINUTE_15,
            "5min":  Interval.MINUTE_5,
            "1min":  Interval.MINUTE_1,
        }
        interval = interval_map.get(barstore_level)
        if interval is None:
            continue
        if symbols and quant_sym.upper() not in {s.upper() for s in symbols}:
            continue
        results.append((p, quant_sym, exchange, interval))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate JSON snapshots to Parquet quant store.")
    parser.add_argument("symbols", nargs="*", help="Symbols to migrate (default: all)")
    parser.add_argument(
        "--quant-data-root", type=Path, default=_DEFAULT_QUANT_ROOT,
        dest="quant_data_root",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing")
    args = parser.parse_args()

    files = discover_files(args.symbols if args.symbols else None)
    if not files:
        print("No matching JSON files found.")
        return 0

    storage = ParquetStorage(args.quant_data_root)
    total_new = 0

    for path, symbol, exchange, interval in files:
        bars = _json_to_bar_data(path, symbol, exchange, interval)
        if args.dry_run:
            print(f"  [dry-run] {path.name}: {len(bars)} bars → {symbol}/{exchange.value}/{interval.value}")
            continue
        n = storage.save_bar_data(bars, upsert=True)
        print(f"  {path.name}: {len(bars)} bars → +{n} new rows saved")
        total_new += n

    if not args.dry_run:
        print(f"\nDone. Total new rows written: {total_new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
