"""One-shot bulk historical fetch for US ETF options via Polygon.

Fetches all contracts expiring between start and today for each ETF,
downloads daily bars, and writes to ParquetStorage at data/quant/.

Usage:
  uv run python scripts/fetch_us_options_history.py
  uv run python scripts/fetch_us_options_history.py --portfolios spy qqq gld
  uv run python scripts/fetch_us_options_history.py --dry-run
  uv run python scripts/fetch_us_options_history.py --portfolios spy --start 2025-01-01
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from quant_data.datafeed.polygon_options import PolygonOptionsDatafeed
from quant_data.models import Exchange, Interval
from quant_data.options_manager import OptionsManager
from quant_data.storage import ParquetStorage

_DATA_ROOT = _SRC / "data" / "quant"

_US_PORTFOLIOS = [
    ("spy",  Exchange.NYSE),
    ("qqq",  Exchange.NYSE),
    ("iwm",  Exchange.NYSE),
    ("dia",  Exchange.NYSE),
    ("gld",  Exchange.NYSE),
    ("gdx",  Exchange.NYSE),
    ("tlt",  Exchange.NYSE),
    ("xlf",  Exchange.NYSE),
    ("xlk",  Exchange.NYSE),
    ("nvda", Exchange.NYSE),
]

_INTERVALS = [Interval.DAILY]
_HISTORY_START = datetime(2021, 1, 1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Bulk historical US ETF options fetch via Polygon.")
    ap.add_argument(
        "--portfolios", nargs="+",
        default=[p for p, _ in _US_PORTFOLIOS],
        help="Portfolios to fetch (default: all 10)",
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--start", default="2021-01-01")
    args = ap.parse_args()

    start = datetime.fromisoformat(args.start)
    end   = datetime.now(tz=timezone.utc).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)

    portfolio_set = {p.lower() for p in args.portfolios}
    targets = [(p, ex) for p, ex in _US_PORTFOLIOS if p in portfolio_set]

    storage  = ParquetStorage(_DATA_ROOT)
    datafeed = PolygonOptionsDatafeed()
    manager  = OptionsManager(datafeed=datafeed, storage=storage)

    total_contracts = 0
    total_bars      = 0

    for portfolio, exchange in targets:
        print(f"\n[{exchange.value}/{portfolio.upper()}]  {start.date()} → {end.date()}")
        if args.dry_run:
            try:
                contracts = datafeed.query_contract_data(
                    portfolio=portfolio.upper(),
                    exchange=exchange,
                    expiry_from=start,
                    expiry_to=end,
                )
                print(f"  [dry-run] {len(contracts)} contracts discovered")
                total_contracts += len(contracts)
            except Exception as e:
                print(f"  [dry-run] ERROR: {e}", file=sys.stderr)
            continue

        try:
            per_sym = manager.backfill(
                portfolio=portfolio.upper(),
                exchange=exchange,
                intervals=_INTERVALS,
                start=start,
                end=end,
            )
            n_contracts = len(per_sym)
            n_bars      = sum(per_sym.values())
            total_contracts += n_contracts
            total_bars      += n_bars
            print(f"  {n_contracts} contracts  +{n_bars} bars")
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)

    if args.dry_run:
        print(f"\nDone (dry-run). {total_contracts} contracts would be discovered.")
    else:
        print(f"\nDone. {total_contracts} contracts, {total_bars} bars total.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
