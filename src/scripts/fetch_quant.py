"""Fetch OHLCV bars via quant-data (Polygon/yfinance for US, Minishare for CN, AkShare for CN futures).

Stores data using quant-data's ParquetStorage so that BarStore.load_barframe()
can read it back as BarFrame objects.

This script does NOT replace fetch_polygon.py — both coexist.
fetch_polygon.py writes raw JSON snapshots; this script writes Parquet
via quant-data's DataManager.

Env (US symbols):
  POLYGON_API_KEY      direct Polygon API key, OR
  POLYGON_PROXY_URL    proxy URL (default http://35.77.84.125:8080)
  POLYGON_PROXY_KEY    proxy auth key

Env (CN symbols):
  MINISHARE_API_KEY    Minishare API key (loaded from macOS keychain if unset)

Usage:
  python scripts/fetch_quant.py SPY QQQ NVDA --tf 60min --years 5
  python scripts/fetch_quant.py RB2501.SHFE --tf daily --exchange XSHF
  python scripts/fetch_quant.py SPY --tf daily --start 2020-01-01 --end 2024-12-31

  # CN futures main continuous contracts (kq_m_ convention, AkShare auto-selected):
  python scripts/fetch_quant.py kq_m_cffex_if kq_m_cffex_ih kq_m_shfe_rb --tf daily
  # Or using AkShare symbol format directly with --feed akshare:
  python scripts/fetch_quant.py IF0 IH0 --feed akshare --exchange XCFE --tf daily
  python scripts/fetch_quant.py rb0 cu0 --feed akshare --exchange XSHF --tf daily

Exchange inference from symbol suffix:
  Plain ticker (no dot)        → XNYS (default)
  TICKER.SH or TICKER.SSE      → XSHG
  TICKER.SZ or TICKER.SZSE     → XSHE
  TICKER.SHFE or CONTRACT.SHFE → XSHF
  TICKER.DCE                   → XDCE
  TICKER.CZCE                  → XZCE
  TICKER.CFFEX                 → XCFE
  TICKER.INE                   → XINE
  TICKER.GFEX                  → XGFE
  TICKER.NYSE                  → XNYS
  TICKER.NASDAQ or .NQ         → XNAQ
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Project src/ must be on sys.path so relative imports work.
# When invoked as `python scripts/fetch_quant.py` from src/, the cwd is
# expected to be src/ or it's run via `uv run python scripts/...` which
# sets sys.path from pyproject.toml.  Add src/ defensively.
_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from data.bar_loader import _kq_m_to_quant  # noqa: E402 — after path fixup
from data.store import BarStore  # noqa: E402


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

# Root directory for quant-data Parquet files
_DEFAULT_DATA_ROOT = _SRC / "data" / "quant"

# Suffix → MIC exchange string
_SUFFIX_TO_EXCHANGE: dict[str, str] = {
    "SH":    "XSHG",
    "SSE":   "XSHG",
    "SZ":    "XSHE",
    "SZSE":  "XSHE",
    "SHFE":  "XSHF",
    "DCE":   "XDCE",
    "CZCE":  "XZCE",
    "CFFEX": "XCFE",
    "INE":   "XINE",
    "GFEX":  "XGFE",
    "NYSE":  "XNYS",
    "NASDAQ":"XNAQ",
    "NQ":    "XNAQ",
}

# MIC → quant-data Exchange enum (for AkShare path that bypasses BarStore)
_MIC_TO_EXCHANGE: dict[str, str] = {
    "XCFE": "CFFEX",
    "XSHF": "SHFE",
    "XDCE": "DCE",
    "XZCE": "CZCE",
    "XINE": "INE",
    "XGFE": "GFEX",
    "XSHG": "SSE",
    "XSHE": "SZSE",
    "XNYS": "NYSE",
    "XNAQ": "NASDAQ",
}

# fetch_polygon.py --tf string → BarStore level string
_TF_TO_LEVEL: dict[str, str] = {
    "daily":  "D",
    "weekly": "W",
    "60min":  "60min",
    "4hour":  "4h",
    "30min":  "30min",
    "15min":  "15min",
    "5min":   "5min",
    "1min":   "1min",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_exchange(symbol: str) -> str:
    """Infer MIC exchange string from symbol suffix."""
    if "." in symbol:
        suffix = symbol.rsplit(".", 1)[-1].upper()
        if suffix in _SUFFIX_TO_EXCHANGE:
            return _SUFFIX_TO_EXCHANGE[suffix]
    return "XNYS"


def _clean_symbol(symbol: str) -> str:
    """Return the base symbol code without exchange suffix.

    quant-data (Minishare) expects symbols with the original dot-notation
    for CN (e.g. "159915.SZ"), while Polygon expects bare tickers (e.g.
    "SPY").  We keep the symbol as-is and let the datafeed handle it.
    """
    return symbol


def _date_range(
    years: int,
    start_str: str | None,
    end_str: str | None,
) -> tuple[datetime, datetime]:
    """Return (start_dt, end_dt) as UTC-aware datetimes."""
    end_dt = (
        datetime.strptime(end_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if end_str
        else datetime.now(timezone.utc)
    )
    start_dt = (
        datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if start_str
        else end_dt - timedelta(days=int(years * 366))
    )
    return start_dt, end_dt


def _fmt_range(start: datetime, end: datetime) -> str:
    return f"{start.date()} → {end.date()}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch OHLCV bars via quant-data and store as Parquet. "
            "US symbols use Polygon; CN spot symbols use Minishare; "
            "CN futures continuous contracts use AkShare (kq_m_ symbols "
            "are auto-detected and route to AkShare)."
        )
    )
    parser.add_argument(
        "symbols",
        nargs="+",
        help=(
            "Tickers, contract codes, or kq_m_ continuous contract names. "
            "kq_m_ symbols (e.g. kq_m_cffex_if) are auto-translated and "
            "fetched via AkShare. "
            "Suffix determines exchange (e.g. RB2501.SHFE → XSHF). "
            "Plain tickers default to XNYS unless --exchange is given."
        ),
    )
    parser.add_argument(
        "--tf",
        choices=list(_TF_TO_LEVEL.keys()),
        default="daily",
        help="Timeframe (default: daily)",
    )
    parser.add_argument(
        "--feed",
        choices=["auto", "minishare", "polygon", "akshare", "yfinance"],
        default="auto",
        help=(
            "Datafeed override. 'auto' selects based on exchange: "
            "XNYS/XNAQ→polygon, CN→minishare, kq_m_→akshare. "
            "'yfinance' uses yfinance for US equities (no API key needed). "
            "(default: auto)"
        ),
    )
    parser.add_argument(
        "--exchange",
        default=None,
        help=(
            "Override exchange MIC for all symbols "
            "(e.g. XNYS, XNAQ, XSHG, XSHE, XSHF, XDCE, XZCE, XCFE, XINE, XGFE). "
            "Default: inferred from symbol suffix."
        ),
    )
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="Calendar years back from today (ignored if --start/--end given)",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="YYYY-MM-DD lower bound (overrides --years)",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="YYYY-MM-DD upper bound (defaults to today)",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=_DEFAULT_DATA_ROOT,
        help=f"Parquet data root (default: {_DEFAULT_DATA_ROOT})",
    )
    args = parser.parse_args()

    level = _TF_TO_LEVEL[args.tf]
    start_dt, end_dt = _date_range(args.years, args.start, args.end)
    store = BarStore(args.data_root)

    range_desc = (
        f"{args.start}..{args.end}" if (args.start or args.end)
        else f"{args.years}y"
    )

    print(
        f"fetch_quant  tf={args.tf} ({level})  range={range_desc}  "
        f"data_root={args.data_root}"
    )

    errors = 0
    for sym in args.symbols:
        # Auto-detect kq_m_ continuous contracts → AkShare
        use_akshare = (
            args.feed == "akshare"
            or (args.feed == "auto" and sym.lower().startswith("kq_m_"))
        )

        if use_akshare:
            errors += _fetch_with_akshare(
                sym, args.exchange, level, start_dt, end_dt, args.data_root
            )
        else:
            exchange = args.exchange or _infer_exchange(sym)
            print(f"  {sym}  exchange={exchange}  …", end="", flush=True)
            # Build explicit datafeed when --feed is not 'auto'
            explicit_datafeed = None
            if args.feed == "polygon":
                from quant_data.datafeed import PolygonDatafeed
                explicit_datafeed = PolygonDatafeed()
            elif args.feed == "minishare":
                from quant_data.datafeed import MinishareDatafeed
                explicit_datafeed = MinishareDatafeed()
            elif args.feed == "yfinance":
                from quant_data.datafeed import YFinanceDatafeed
                explicit_datafeed = YFinanceDatafeed()
            try:
                n = store.update(
                    symbol=sym,
                    exchange=exchange,
                    level=level,
                    start=start_dt,
                    end=end_dt,
                    datafeed=explicit_datafeed,
                )
                print(f"  +{n} new bars  {_fmt_range(start_dt, end_dt)}")
            except KeyError as e:
                print(f"\n  {sym}: UNSUPPORTED — {e}", file=sys.stderr)
                errors += 1
            except Exception as e:
                print(f"\n  {sym}: ERROR — {e}", file=sys.stderr)
                errors += 1

    return 1 if errors else 0


def _fetch_with_akshare(
    sym: str,
    exchange_override: str | None,
    level: str,
    start_dt: datetime,
    end_dt: datetime,
    data_root: Path,
) -> int:
    """Fetch one symbol using AkshareDatafeed. Returns 1 on error, 0 on success."""
    from quant_data import DataManager
    from quant_data.datafeed import AkshareDatafeed
    from quant_data.models import Exchange as QExchange, Interval as QInterval
    from quant_data.storage import ParquetStorage

    # Translate kq_m_ symbol → (quant_sym, mic)
    if sym.lower().startswith("kq_m_"):
        result = _kq_m_to_quant(sym)
        if result is None:
            print(f"\n  {sym}: cannot translate kq_m_ symbol", file=sys.stderr)
            return 1
        quant_sym, mic = result
    else:
        mic = exchange_override or _infer_exchange(sym)
        quant_sym = sym

    exchange_str = _MIC_TO_EXCHANGE.get(mic)
    if exchange_str is None:
        print(f"\n  {sym}: unrecognized MIC {mic!r}", file=sys.stderr)
        return 1

    try:
        q_exchange = QExchange(exchange_str)
        interval = {
            "D":     QInterval.DAILY,
            "W":     QInterval.WEEKLY,
            "60min": QInterval.HOUR_1,
            "4h":    QInterval.HOUR_4,
            "30min": QInterval.MINUTE_30,
            "15min": QInterval.MINUTE_15,
            "5min":  QInterval.MINUTE_5,
            "1min":  QInterval.MINUTE_1,
        }[level]
    except (ValueError, KeyError) as e:
        print(f"\n  {sym}: mapping error — {e}", file=sys.stderr)
        return 1

    print(f"  {sym} → {quant_sym}/{mic} [akshare]  …", end="", flush=True)
    try:
        manager = DataManager(
            datafeed=AkshareDatafeed(),
            storage=ParquetStorage(data_root),
        )
        n = manager.update(quant_sym, q_exchange, interval, start_dt, end_dt)
        print(f"  +{n} new bars")
        return 0
    except Exception as e:
        print(f"\n  {sym}: ERROR — {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
