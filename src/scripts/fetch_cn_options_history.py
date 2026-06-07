"""One-shot bulk historical fetch for all CN option portfolios.

Fetches every contract month from 2021-01-01 to today for supported portfolios,
downloads daily bars, and writes to ParquetStorage at data/quant/.

Sina Finance coverage (AkshareOptionsDatafeed):
  SHFE: au, ag, cu, rb, ru
  DCE:  m, i, y, c, pg
  CZCE: sr, ma, ta, cf, rm, zc, oi, pk

Tushare/Minishare coverage (MinishareOptionsDatafeed):
  DCE:  p, j, jm
  CZCE: sa

Usage:
  uv run python scripts/fetch_cn_options_history.py
  uv run python scripts/fetch_cn_options_history.py --portfolios au rb m sr p j
  uv run python scripts/fetch_cn_options_history.py --dry-run
  uv run python scripts/fetch_cn_options_history.py --portfolios m --start 2023-01-01
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from quant_data.datafeed.akshare_options import AkshareOptionsDatafeed
from quant_data.datafeed.akshare_options import _PORTFOLIO_META as _AKSHARE_META
from quant_data.datafeed.minishare_options import MinishareOptionsDatafeed
from quant_data.datafeed.minishare_options import _PORTFOLIO_META as _MINISHARE_META
from quant_data.models import Exchange, Interval
from quant_data.options_manager import OptionsManager
from quant_data.storage import ParquetStorage

_DATA_ROOT = _SRC / "data" / "quant"

_overlap = set(_AKSHARE_META) & set(_MINISHARE_META)
assert not _overlap, f"Portfolio routing ambiguous — overlap between feeds: {_overlap}"

_ALL_PORTFOLIO_EXCHANGE: dict[str, Exchange] = {
    **{k: v for k, (_, v) in _AKSHARE_META.items()},
    **{k: exchange for k, (exchange, _) in _MINISHARE_META.items()},
}

_INTERVALS = [Interval.DAILY]

_HISTORY_START = datetime(2021, 1, 1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Bulk historical CN options fetch via Sina/AkShare and Tushare/Minishare.")
    ap.add_argument(
        "--portfolios", nargs="+",
        default=sorted(_ALL_PORTFOLIO_EXCHANGE.keys()),
        help=f"Portfolios to fetch (default: all {len(_ALL_PORTFOLIO_EXCHANGE)})",
    )
    ap.add_argument("--dry-run", action="store_true", help="Discover contracts only, no bar fetch")
    ap.add_argument("--start", default="2021-01-01", help="Start date YYYY-MM-DD")
    args = ap.parse_args()

    start = datetime.fromisoformat(args.start)
    end   = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)

    storage = ParquetStorage(_DATA_ROOT)
    _akshare_feed   = AkshareOptionsDatafeed()
    _minishare_feed = MinishareOptionsDatafeed()

    total_contracts = 0
    total_bars      = 0

    for portfolio in args.portfolios:
        portfolio = portfolio.lower()
        if portfolio not in _ALL_PORTFOLIO_EXCHANGE:
            print(f"  SKIP {portfolio}: not in supported portfolio list", file=sys.stderr)
            continue

        exchange = _ALL_PORTFOLIO_EXCHANGE[portfolio]
        datafeed = _minishare_feed if portfolio in _MINISHARE_META else _akshare_feed
        manager  = OptionsManager(datafeed=datafeed, storage=storage)
        print(f"\n[{exchange.value}/{portfolio.upper()}]  {start.date()} -> {end.date()}")

        if args.dry_run:
            contracts = datafeed.query_contract_data(
                portfolio=portfolio,
                exchange=exchange,
                expiry_from=start,
                expiry_to=end,
            )
            print(f"  [dry-run] {len(contracts)} contracts discovered")
            total_contracts += len(contracts)
            continue

        per_sym = manager.backfill(
            portfolio=portfolio,
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

    if args.dry_run:
        print(f"\nDone (dry-run). {total_contracts} contracts would be discovered.")
    else:
        print(f"\nDone. {total_contracts} contracts, {total_bars} bars total.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
