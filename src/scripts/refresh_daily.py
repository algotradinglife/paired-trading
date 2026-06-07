"""Daily data refresh for paired-trading quant store.

Fetches the latest bars for all symbols used by the trading system:
  - US equities (weekly + daily + 1h + 15m): yfinance (no API key needed)
  - CN futures (daily + 1h + 15m): AkShare

Usage:
  uv run python scripts/refresh_daily.py
  uv run python scripts/refresh_daily.py --start 2026-01-01
  uv run python scripts/refresh_daily.py --us-only
  uv run python scripts/refresh_daily.py --cn-only
  uv run python scripts/refresh_daily.py --tf daily        # skip intraday
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from quant_data.datafeed import AkshareDatafeed, YFinanceDatafeed, PolygonOptionsDatafeed
from quant_data.datafeed.akshare_options import AkshareOptionsDatafeed, _PORTFOLIO_META
from quant_data.models import Exchange, Interval
from quant_data.storage import ParquetStorage
from quant_data import DataManager, OptionsManager

from data.bar_loader import _kq_m_to_quant  # noqa: E402

# ── Data root ────────────────────────────────────────────────────────────────
_DATA_ROOT = _SRC / "data" / "quant"

# ── US equities ───────────────────────────────────────────────────────────────
_US_SYMBOLS: list[tuple[str, Exchange]] = [
    ("SPY",  Exchange.NYSE),
    ("QQQ",  Exchange.NYSE),
    ("GLD",  Exchange.NYSE),
    ("GDX",  Exchange.NYSE),
    ("TLT",  Exchange.NYSE),
    ("XLF",  Exchange.NYSE),
    ("XLK",  Exchange.NYSE),
    ("NVDA", Exchange.NYSE),
    ("DIA",  Exchange.NYSE),
    ("IWM",  Exchange.NYSE),
    ("XLB",  Exchange.NYSE),
    ("XLE",  Exchange.NYSE),
    ("XLRE", Exchange.NYSE),
    ("XLU",  Exchange.NYSE),
]

# ── CN futures (kq_m_ → quant_symbol/exchange) ───────────────────────────────
_CN_KQ_SYMBOLS: list[str] = [
    # CFFEX — equity index + treasury futures
    "kq_m_cffex_if", "kq_m_cffex_ih", "kq_m_cffex_ic", "kq_m_cffex_im",
    "kq_m_cffex_t", "kq_m_cffex_tf", "kq_m_cffex_ts",
    # SHFE — metals + rebar
    "kq_m_shfe_rb", "kq_m_shfe_ag", "kq_m_shfe_au", "kq_m_shfe_cu",
    # CZCE — agricultural + chemicals
    "kq_m_czce_ma", "kq_m_czce_sa", "kq_m_czce_sr",
    "kq_m_czce_ta", "kq_m_czce_cf",
    # DCE — agricultural + coking
    "kq_m_dce_i", "kq_m_dce_j", "kq_m_dce_jm",
    "kq_m_dce_m", "kq_m_dce_p", "kq_m_dce_y",
    # INE — crude oil
    "kq_m_ine_sc",
]

# MIC → Exchange enum
_MIC_TO_EXCHANGE: dict[str, Exchange] = {
    "XCFE": Exchange.CFFEX,
    "XSHF": Exchange.SHFE,
    "XDCE": Exchange.DCE,
    "XZCE": Exchange.CZCE,
    "XINE": Exchange.INE,
    "XGFE": Exchange.GFEX,
}

# US intervals: weekly enables topology A (D+1h+W) in backtest_fusion_d1h15m
_US_INTERVALS_ALL = [Interval.WEEKLY, Interval.DAILY, Interval.HOUR_1, Interval.MINUTE_15]
_US_INTERVALS_DAILY = [Interval.WEEKLY, Interval.DAILY]

# CN futures intraday intervals
_CN_INTRADAY_INTERVALS = [Interval.MINUTE_15, Interval.HOUR_1]

# US options intervals
_US_OPTION_INTERVALS = [Interval.DAILY, Interval.HOUR_1, Interval.MINUTE_15, Interval.MINUTE_5]


def _date_range(start_str: str | None, lookback_days: int = 7) -> tuple[datetime, datetime]:
    end = datetime.now(timezone.utc)
    start = (
        datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if start_str
        else end - timedelta(days=lookback_days)
    )
    return start, end


def _refresh_us(start: datetime, end: datetime, intervals: list[Interval]) -> int:
    """Refresh US equity bars via yfinance. Returns new bar count."""
    storage = ParquetStorage(_DATA_ROOT)
    manager = DataManager(datafeed=YFinanceDatafeed(), storage=storage)
    total = 0
    print(f"\n[US equities]  {start.date()} → {end.date()}")
    for symbol, exchange in _US_SYMBOLS:
        for interval in intervals:
            try:
                n = manager.update(symbol, exchange, interval, start, end)
                print(f"  {symbol:<6} {interval.value:<8}  +{n} bars")
                total += n
            except Exception as e:
                print(f"  {symbol:<6} {interval.value:<8}  ERROR: {e}", file=sys.stderr)
    return total


def _refresh_cn(start: datetime, end: datetime, intervals: list[Interval]) -> int:
    """Refresh CN futures bars via AkShare. Returns new bar count."""
    storage = ParquetStorage(_DATA_ROOT)
    manager = DataManager(datafeed=AkshareDatafeed(), storage=storage)
    total = 0
    print(f"\n[CN futures]  {start.date()} → {end.date()}")
    for kq_sym in _CN_KQ_SYMBOLS:
        result = _kq_m_to_quant(kq_sym)
        if result is None:
            print(f"  {kq_sym}: cannot translate", file=sys.stderr)
            continue
        quant_sym, mic = result
        exchange = _MIC_TO_EXCHANGE.get(mic)
        if exchange is None:
            print(f"  {kq_sym}: unknown MIC {mic!r}", file=sys.stderr)
            continue
        for interval in intervals:
            try:
                n = manager.update(quant_sym, exchange, interval, start, end)
                print(f"  {quant_sym:<6} {interval.value:<8}  +{n} bars")
                total += n
            except Exception as e:
                print(f"  {quant_sym:<6} {interval.value:<8}  ERROR: {e}", file=sys.stderr)
    return total


_CN_OPTION_PORTFOLIOS: list[tuple[str, Exchange]] = [
    (p, meta[1]) for p, meta in _PORTFOLIO_META.items()
]

_CN_OPTION_INTERVALS = [Interval.DAILY]


def _refresh_us_options(lookback_days: int = 30, expiry_window_days: int = 90) -> dict[str, int]:
    """Refresh US options via PolygonOptionsDatafeed. Returns {symbol: total_new_bars}."""
    storage = ParquetStorage(_DATA_ROOT)
    datafeed = PolygonOptionsDatafeed()
    manager = OptionsManager(datafeed=datafeed, storage=storage)
    results: dict[str, int] = {}
    print(f"\n[US options]  lookback={lookback_days}d  expiry_window={expiry_window_days}d")
    for symbol, exchange in _US_SYMBOLS:
        try:
            counts = manager.update_all(
                portfolio=symbol,
                exchange=exchange,
                intervals=_US_OPTION_INTERVALS,
                lookback_days=lookback_days,
                expiry_window_days=expiry_window_days,
            )
            total = sum(counts.values())
            results[symbol] = total
            print(f"  {symbol:<6}  {len(counts)} contracts  +{total} bars")
        except Exception as e:
            print(f"  {symbol:<6}  ERROR: {e}", file=sys.stderr)
    return results


def _refresh_cn_options(lookback_days: int = 30, expiry_window_days: int = 90) -> dict[str, int]:
    """Refresh CN options via AkshareOptionsDatafeed. Returns {portfolio: total_new_bars}."""
    storage  = ParquetStorage(_DATA_ROOT)
    datafeed = AkshareOptionsDatafeed()
    manager  = OptionsManager(datafeed=datafeed, storage=storage)
    results: dict[str, int] = {}
    print(f"\n[CN options]  lookback={lookback_days}d  expiry_window={expiry_window_days}d")
    for portfolio, exchange in _CN_OPTION_PORTFOLIOS:
        try:
            counts = manager.update_all(
                portfolio=portfolio,
                exchange=exchange,
                intervals=_CN_OPTION_INTERVALS,
                lookback_days=lookback_days,
                expiry_window_days=expiry_window_days,
            )
            total = sum(counts.values())
            results[portfolio] = total
            print(f"  {portfolio.upper():<6}  {len(counts)} contracts  +{total} bars")
        except Exception as e:
            print(f"  {portfolio.upper():<6}  ERROR: {e}", file=sys.stderr)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily data refresh for paired-trading.")
    parser.add_argument(
        "--start", type=str, default=None,
        help="YYYY-MM-DD start date (default: 7 days ago)",
    )
    parser.add_argument(
        "--us-only", action="store_true", help="Refresh US equities only",
    )
    parser.add_argument(
        "--cn-only", action="store_true", help="Refresh CN futures only",
    )
    parser.add_argument(
        "--tf", choices=["daily", "all"], default="all",
        help="Timeframes: 'daily' refreshes only daily bars, 'all' includes 15m+1h (default: all)",
    )
    parser.add_argument(
        "--options-only", action="store_true", help="Refresh US options only",
    )
    parser.add_argument(
        "--cn-options-only", action="store_true", help="Refresh CN options only",
    )
    parser.add_argument(
        "--lookback", type=int, default=30,
        help="Options lookback window in days (default: 30)",
    )
    parser.add_argument(
        "--expiry-window", type=int, default=90,
        help="Options expiry discovery window in days (default: 90)",
    )
    args = parser.parse_args()

    start, end = _date_range(args.start)
    print(f"refresh_daily  start={start.date()}  end={end.date()}  tf={args.tf}")

    if args.tf == "daily":
        us_intervals = _US_INTERVALS_DAILY
        cn_intervals = [Interval.DAILY]
    else:
        us_intervals = _US_INTERVALS_ALL
        cn_intervals = [Interval.DAILY] + _CN_INTRADAY_INTERVALS

    total_new = 0

    run_us_equities = not args.options_only and not args.cn_options_only and not args.cn_only
    run_cn_futures  = not args.options_only and not args.cn_options_only and not args.us_only
    run_us_options  = not args.us_only and not args.cn_only and not args.cn_options_only
    run_cn_options  = not args.us_only and not args.cn_only and not args.options_only

    if run_us_equities:
        total_new += _refresh_us(start, end, us_intervals)
    if run_cn_futures:
        total_new += _refresh_cn(start, end, cn_intervals)
    if run_us_options:
        counts = _refresh_us_options(
            lookback_days=args.lookback,
            expiry_window_days=args.expiry_window,
        )
        total_new += sum(counts.values())
    if run_cn_options:
        counts = _refresh_cn_options(
            lookback_days=args.lookback,
            expiry_window_days=args.expiry_window,
        )
        total_new += sum(counts.values())

    print(f"\nDone. Total new bars: {total_new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
