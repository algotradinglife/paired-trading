"""One-shot migration: US and CN option JSON files → ParquetStorage.

Scans data/options/{underlying}/*.json (US) and data/options/cn/{underlying}/*.json (CN),
writes bars and contract metadata to data/quant/ via ParquetStorage.

Usage:
    uv run python scripts/migrate_options_to_parquet.py               # US + CN
    uv run python scripts/migrate_options_to_parquet.py --market us
    uv run python scripts/migrate_options_to_parquet.py --market cn
    uv run python scripts/migrate_options_to_parquet.py --dry-run
    uv run python scripts/migrate_options_to_parquet.py --portfolio spy qqq
    uv run python scripts/migrate_options_to_parquet.py --market cn --portfolio au rb
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from quant_data.models import BarData, ContractData, Exchange, Interval, OptionType, Product
from quant_data.storage import ParquetStorage

_DATA_ROOT    = _SRC / "data" / "quant"
_OPTIONS_ROOT = _SRC / "data" / "options"
_CN_ROOT      = _OPTIONS_ROOT / "cn"

# ── US ────────────────────────────────────────────────────────────────────────

_US_PORTFOLIOS = [
    "spy", "qqq", "gld", "gdx", "tlt", "xlf", "xlk", "nvda", "dia", "iwm",
]

_US_FILENAME_TO_INTERVAL: dict[str, Interval] = {
    "daily": Interval.DAILY,
    "60":    Interval.HOUR_1,
    "15":    Interval.MINUTE_15,
    "5":     Interval.MINUTE_5,
}

_OCC_RE = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")


def parse_occ_symbol(symbol: str) -> dict:
    """Parse an OCC option symbol into component fields.

    Returns dict with keys: portfolio, expiry, option_type, strike, option_index.
    Raises ValueError if symbol does not match OCC format.
    """
    m = _OCC_RE.match(symbol.upper())
    if not m:
        raise ValueError(f"Not an OCC symbol: {symbol!r}")
    portfolio, yymmdd, cp, strike_str = m.groups()
    expiry = datetime.strptime(yymmdd, "%y%m%d")
    option_type = "call" if cp == "C" else "put"
    strike = int(strike_str) / 1000.0
    option_index = cp + strike_str
    return {
        "portfolio":    portfolio,
        "expiry":       expiry,
        "option_type":  option_type,
        "strike":       strike,
        "option_index": option_index,
    }


def bar_dict_to_bar_data(
    bar: dict,
    symbol: str,
    exchange: Exchange,
    interval: Interval,
) -> BarData:
    """Convert a JSON bar dict (Unix timestamp) to BarData (UTC naive datetime)."""
    ts = int(bar["time"])
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
    return BarData(
        symbol=symbol,
        exchange=exchange,
        interval=interval,
        datetime=dt,
        open_price=float(bar.get("open") or 0),
        high_price=float(bar.get("high") or 0),
        low_price=float(bar.get("low") or 0),
        close_price=float(bar.get("close") or 0),
        volume=float(bar.get("volume") or 0),
    )


def migrate_json_file(
    path: Path,
    exchange: Exchange,
    interval: Interval,
) -> tuple[ContractData, list[BarData]]:
    """Parse one US JSON option file into (ContractData, list[BarData]).

    Raises ValueError if the file has no parseable OCC symbol.
    """
    payload = json.loads(path.read_text())
    raw_contract = str(payload.get("contract", ""))
    occ_sym = raw_contract[2:] if raw_contract.startswith("O:") else raw_contract
    occ_sym = occ_sym.upper()

    parsed = parse_occ_symbol(occ_sym)

    contract = ContractData(
        symbol=occ_sym,
        exchange=exchange,
        product=Product.OPTION,
        option_strike=parsed["strike"],
        option_type=OptionType.CALL if parsed["option_type"] == "call" else OptionType.PUT,
        option_expiry=parsed["expiry"],
        option_portfolio=parsed["portfolio"],
        option_index=parsed["option_index"],
        option_underlying=f"{parsed['portfolio']}.{exchange.value}",
    )

    bars = [
        bar_dict_to_bar_data(b, occ_sym, exchange, interval)
        for b in payload.get("bars", [])
    ]
    return contract, bars


def _tf_from_filename(path: Path) -> Interval | None:
    """Extract interval from US filename like o_spy250516c00515000_daily.json."""
    suffix = path.stem.rsplit("_", 1)[-1]
    return _US_FILENAME_TO_INTERVAL.get(suffix)


def migrate_portfolio(
    portfolio: str,
    storage: ParquetStorage,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Migrate all JSON files for one US underlying to ParquetStorage.

    Returns (contract_count, total_bar_count).
    """
    options_dir = _OPTIONS_ROOT / portfolio.lower()
    if not options_dir.is_dir():
        print(f"  {portfolio}: directory not found, skipping")
        return 0, 0

    contracts_by_sym: dict[str, ContractData] = {}
    all_bars: list[BarData] = []

    for f in sorted(options_dir.glob("*.json")):
        interval = _tf_from_filename(f)
        if interval is None:
            continue
        try:
            contract, bars = migrate_json_file(f, Exchange.NYSE, interval)
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            print(f"  SKIP {f.name}: {e}", file=sys.stderr)
            continue
        contracts_by_sym[contract.symbol] = contract
        all_bars.extend(bars)

    n_contracts = len(contracts_by_sym)
    n_bars = len(all_bars)
    print(f"  {portfolio:<6}  {n_contracts} contracts  {n_bars} bars")

    if not dry_run:
        if contracts_by_sym:
            storage.save_contract_data(list(contracts_by_sym.values()))
        if all_bars:
            storage.save_bar_data(all_bars)

    return n_contracts, n_bars


# ── CN ────────────────────────────────────────────────────────────────────────

_CN_PORTFOLIOS = ["ag", "au", "cu", "i", "m", "ma", "rb", "sr", "ta"]

_CN_FILENAME_TO_INTERVAL: dict[str, Interval] = {
    "daily": Interval.DAILY,
    "15min": Interval.MINUTE_15,
    "60min": Interval.HOUR_1,
}

# kq_m_{exchange_key}_ → Exchange
_KQ_M_EXCHANGE_MAP: dict[str, Exchange] = {
    "shfe":  Exchange.SHFE,
    "dce":   Exchange.DCE,
    "czce":  Exchange.CZCE,
    "ine":   Exchange.INE,
    "cffex": Exchange.CFFEX,
}

# CN option symbol: {ROOT}{YYMM}{C|P}{STRIKE}  e.g. AU2105C352, M2507C2800
_CN_OPT_RE = re.compile(r"^([A-Z]+)(\d{4})([CP])(\d+)$")


def normalize_cn_symbol(raw: str) -> str:
    """Strip exchange suffix and uppercase: 'ag2310C6000' or 'AG2310C6000.SHF' → 'AG2310C6000'."""
    return raw.split(".")[0].upper()


def parse_cn_option_symbol(symbol: str) -> dict:
    """Parse a normalized CN option symbol like AU2105C352.

    Returns dict with keys: portfolio, option_type, strike, option_index.
    Raises ValueError if symbol does not match CN option format.
    """
    sym = normalize_cn_symbol(symbol)
    m = _CN_OPT_RE.match(sym)
    if not m:
        raise ValueError(f"Not a CN option symbol: {symbol!r}")
    root, _yymm, cp, strike_str = m.groups()
    return {
        "portfolio":    root,
        "option_type":  "call" if cp == "C" else "put",
        "strike":       float(strike_str),
        "option_index": cp + strike_str,
    }


def _underlying_to_exchange(underlying: str) -> Exchange | None:
    """Map 'kq_m_shfe_au' → Exchange.SHFE."""
    parts = underlying.lower().split("_")
    if len(parts) >= 3 and parts[0] == "kq" and parts[1] == "m":
        return _KQ_M_EXCHANGE_MAP.get(parts[2])
    return None


def _underlying_to_vt_symbol(underlying: str, exchange: Exchange) -> str:
    """Map 'kq_m_shfe_au' → 'au0.SHFE'."""
    root = underlying.split("_")[-1]
    return f"{root}0.{exchange.value}"


def _tf_from_filename_cn(path: Path) -> Interval | None:
    """Extract interval from CN filename; last segment before .json.

    Handles: au2105c352_daily.json, au2105c360_20210331_daily.json,
             ag2310c6000_shf_20230919_daily.json  → all return DAILY.
    """
    suffix = path.stem.rsplit("_", 1)[-1]
    return _CN_FILENAME_TO_INTERVAL.get(suffix)


def migrate_cn_json_file(
    path: Path,
    exchange: Exchange,
    interval: Interval,
    underlying_vt: str,
) -> tuple[ContractData, list[BarData]]:
    """Parse one CN option JSON file into (ContractData, list[BarData]).

    Raises ValueError if the symbol cannot be parsed.
    """
    payload = json.loads(path.read_text())
    raw_sym = str(payload.get("contract", ""))
    norm_sym = normalize_cn_symbol(raw_sym)
    parsed = parse_cn_option_symbol(norm_sym)

    expiry_raw = payload.get("expiry")
    option_expiry: datetime | None = None
    if expiry_raw:
        try:
            option_expiry = datetime.fromisoformat(str(expiry_raw)[:10])
        except ValueError:
            pass

    contract = ContractData(
        symbol=norm_sym,
        exchange=exchange,
        product=Product.OPTION,
        option_strike=parsed["strike"],
        option_type=OptionType.CALL if parsed["option_type"] == "call" else OptionType.PUT,
        option_expiry=option_expiry,
        option_portfolio=parsed["portfolio"],
        option_index=parsed["option_index"],
        option_underlying=underlying_vt,
    )

    bars = [
        bar_dict_to_bar_data(b, norm_sym, exchange, interval)
        for b in payload.get("bars", [])
    ]
    return contract, bars


def migrate_cn_portfolio(
    portfolio: str,
    storage: ParquetStorage,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Migrate all JSON files for one CN underlying to ParquetStorage.

    Returns (contract_count, total_bar_count).
    """
    portfolio_dir = _CN_ROOT / portfolio.lower()
    if not portfolio_dir.is_dir():
        print(f"  {portfolio}: directory not found, skipping")
        return 0, 0

    # Determine exchange and vt_symbol from first readable file
    exchange: Exchange | None = None
    underlying_vt = ""
    for f in sorted(portfolio_dir.glob("*.json"))[:5]:
        try:
            payload = json.loads(f.read_text())
            und = str(payload.get("underlying", ""))
            ex = _underlying_to_exchange(und)
            if ex is not None:
                exchange = ex
                underlying_vt = _underlying_to_vt_symbol(und, ex)
                break
        except Exception:
            continue

    if exchange is None:
        print(f"  {portfolio}: cannot determine exchange, skipping", file=sys.stderr)
        return 0, 0

    contracts_by_sym: dict[str, ContractData] = {}
    all_bars: list[BarData] = []
    # Key: (symbol, exchange, interval, date-or-datetime) — for daily bars use date only
    # so variants with 15-minute timestamp offsets are treated as the same session.
    seen_bars: set[tuple[str, str, str, object]] = set()

    def _cn_file_priority(p: Path) -> tuple:
        parts = p.stem.split("_")
        # For daily files, rank by how many extra parts follow the contract root:
        #   _daily.json (canonical, 0 extras) < _YYYYMMDD_daily.json (1) < _shf_YYYYMMDD_daily.json (2)
        if parts[-1] == "daily":
            return (len(parts) - 2, p.name)
        return (0, p.name)

    for f in sorted(portfolio_dir.glob("*.json"), key=_cn_file_priority):
        interval = _tf_from_filename_cn(f)
        if interval is None:
            continue
        try:
            contract, bars = migrate_cn_json_file(f, exchange, interval, underlying_vt)
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            print(f"  SKIP {f.name}: {e}", file=sys.stderr)
            continue
        # First file for each symbol wins; _cn_file_priority ensures canonical _daily.json
        # sorts before dated (_YYYYMMDD_daily) and exchange-dated (_shf_YYYYMMDD_daily) variants.
        contracts_by_sym.setdefault(contract.symbol, contract)
        for bar in bars:
            dedup_ts = bar.datetime.date() if interval == Interval.DAILY else bar.datetime
            key = (bar.symbol, bar.exchange.value, bar.interval.value, dedup_ts)
            if key not in seen_bars:
                seen_bars.add(key)
                all_bars.append(bar)

    n_contracts = len(contracts_by_sym)
    n_bars = len(all_bars)
    print(f"  {portfolio:<4}  {n_contracts} contracts  {n_bars} bars  [{exchange.value}]")

    if not dry_run:
        if contracts_by_sym:
            storage.save_contract_data(list(contracts_by_sym.values()))
        if all_bars:
            storage.save_bar_data(all_bars)

    return n_contracts, n_bars


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Migrate US and CN option JSON files to ParquetStorage."
    )
    ap.add_argument(
        "--market", choices=["us", "cn", "all"], default="all",
        help="Market to migrate (default: all)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Parse only, do not write")
    ap.add_argument(
        "--portfolio", nargs="+", default=None,
        help="Specific portfolios to migrate (default: all for chosen market)",
    )
    args = ap.parse_args()

    storage = ParquetStorage(_DATA_ROOT)
    if args.dry_run:
        print("  [dry-run mode: no writes]")

    total_c, total_b = 0, 0

    if args.market in ("us", "all"):
        us_portfolios = (
            [p.lower() for p in args.portfolio] if args.portfolio else _US_PORTFOLIOS
        )
        print(f"\nMigrating {len(us_portfolios)} US option portfolios → {_DATA_ROOT}")
        for portfolio in us_portfolios:
            c, b = migrate_portfolio(portfolio, storage, dry_run=args.dry_run)
            total_c += c
            total_b += b

    if args.market in ("cn", "all"):
        cn_portfolios = (
            [p.lower() for p in args.portfolio] if args.portfolio else _CN_PORTFOLIOS
        )
        print(f"\nMigrating {len(cn_portfolios)} CN option portfolios → {_DATA_ROOT}")
        for portfolio in cn_portfolios:
            c, b = migrate_cn_portfolio(portfolio, storage, dry_run=args.dry_run)
            total_c += c
            total_b += b

    print(f"\nDone. {total_c} unique contracts, {total_b} total bars written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
