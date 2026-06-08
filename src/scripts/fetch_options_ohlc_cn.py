"""Fetch historical daily OHLC for full CN futures option chains via akshare (Sina Finance).

Fetches the complete option chain (all strikes, calls + puts) for the nearest valid
contract month per signal. Intraday bars are not available historically from
akshare/Sina for commodity futures options — daily only.

Data sources (free, no API key required):
  - Contract chain: akshare.option_commodity_contract_table_sina(symbol, contract_month)
  - Daily bars:     akshare.option_commodity_hist_sina(symbol)

Supported products (Sina Finance coverage):
  SHFE: AU (黄金), AG (白银), CU (沪铜), RB (螺纹钢)
  DCE:  M  (豆粕), I  (铁矿石), Y (豆油)
  CZCE: SR (白糖), MA (甲醇), TA (PTA), CF (棉花)

Products without Sina options coverage (skipped):
  INE:  SC (原油)
  DCE:  P  (棕榈油), J (焦炭), JM (焦煤)
  CZCE: SA (纯碱)

Usage:
  uv run python scripts/fetch_options_ohlc_cn.py
  uv run python scripts/fetch_options_ohlc_cn.py --pool CN_METAL
  uv run python scripts/fetch_options_ohlc_cn.py --dte 30 --forward-days 30
  uv run python scripts/fetch_options_ohlc_cn.py --direction bottom top --relation opposing
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path

import akshare as ak
import pandas as pd

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
SRC_DIR    = Path(__file__).resolve().parents[1]


def _default_review_dir() -> Path:
    """Default review dir; honors DERIVED_ROOT env var, falls back to src/data/review."""
    derived = os.environ.get("DERIVED_ROOT")
    if derived:
        return Path(derived) / "paired-trading" / "src-data-review"
    return SRC_DIR / "data" / "review"


REVIEW_DIR = _default_review_dir()

SLEEP             = 0.5   # polite rate limiting between API calls
MIN_BARS_COMPLETE = 5

POOL_FILES: dict[str, str] = {
    "CN_METAL": "rr_b_cn_metal.csv",
    "CN_AGRI":  "rr_b_cn_agri.csv",
}

# symbol → (sina_product_name, prefix)
SYMBOL_CONFIG: dict[str, tuple[str, str]] = {
    # SHFE
    "kq_m_shfe_au": ("黄金期权",   "au"),
    "kq_m_shfe_ag": ("白银期权",   "ag"),
    "kq_m_shfe_cu": ("沪铜期权",   "cu"),
    "kq_m_shfe_rb": ("螺纹钢期权", "rb"),
    # DCE
    "kq_m_dce_m":   ("豆粕期权",   "m"),
    "kq_m_dce_i":   ("铁矿石期权", "i"),
    "kq_m_dce_y":   ("豆油期权",   "y"),
    # CZCE
    "kq_m_czce_sr": ("白糖期权",   "sr"),
    "kq_m_czce_ma": ("甲醇期权",   "ma"),
    "kq_m_czce_ta": ("PTA期权",    "ta"),
    "kq_m_czce_cf": ("棉花期权",   "cf"),
}


def _liquidity_flag(avg_vol: float | None) -> str:
    if avg_vol is None:
        return "unknown"
    if avg_vol >= 20:
        return "ok"
    if avg_vol >= 5:
        return "thin"
    return "illiquid"


def _next_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


# ---------------------------------------------------------------------------
# Full chain lookup via Sina Finance
# ---------------------------------------------------------------------------
def _target_month_codes(signal_date: date, dte: int, n: int = 4) -> list[str]:
    """Return n YYMM codes where approx expiry (22nd of month) >= signal_date + dte."""
    target = signal_date + timedelta(days=dte)
    codes: list[str] = []
    d = date(target.year, target.month, 1)
    for _ in range(n + 6):
        approx_expiry = date(d.year, d.month, 22)
        if approx_expiry >= target:
            codes.append(d.strftime("%y%m"))
            if len(codes) >= n:
                break
        d = _next_month(d)
    return codes


def get_full_chain(
    sina_name: str,
    prefix: str,
    signal_date: date,
    dte: int,
) -> tuple[str | None, list[dict]]:
    """Return (yymm, contracts) for the nearest valid contract month.

    contracts: list of {ticker, strike, contract_type} for all strikes (calls + puts).
    Returns (None, []) if no valid month found.
    """
    month_codes = _target_month_codes(signal_date, dte)

    for yymm in month_codes:
        contract = f"{prefix}{yymm}"
        try:
            df = ak.option_commodity_contract_table_sina(symbol=sina_name, contract=contract)
        except Exception as exc:
            print(f"      chain table error [{contract}]: {exc}", file=sys.stderr)
            time.sleep(SLEEP)
            continue
        time.sleep(SLEEP)

        if df.empty:
            continue

        call_col = next((c for c in df.columns if "看涨期权合约" in c), None)
        put_col  = next((c for c in df.columns if "看跌期权合约" in c), None)

        df = df.copy()
        df["_strike"] = pd.to_numeric(df["行权价"], errors="coerce")
        df = df.dropna(subset=["_strike"])

        contracts: list[dict] = []
        for _, row in df.iterrows():
            strike = float(row["_strike"])
            for col, ct in ((call_col, "call"), (put_col, "put")):
                if col is None:
                    continue
                val = str(row.get(col, "")).strip()
                if val and val.lower() != "nan":
                    contracts.append({
                        "ticker":        val,
                        "strike":        strike,
                        "contract_type": ct,
                        "expiry_month":  yymm,
                    })

        if contracts:
            return yymm, contracts

    return None, []


# ---------------------------------------------------------------------------
# Daily bars via Sina Finance
# ---------------------------------------------------------------------------
def _normalize_date(v: object) -> date | None:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def _fetch_daily_bars(
    sina_symbol: str,
    signal_date: date,
    forward_days: int,
) -> list[dict]:
    """Fetch daily bars for a Sina-format option ticker, filtered to forward window."""
    try:
        df = ak.option_commodity_hist_sina(symbol=sina_symbol)
    except Exception as exc:
        print(f"      hist_sina error [{sina_symbol}]: {exc}", file=sys.stderr)
        return []
    time.sleep(SLEEP)

    if df.empty:
        return []

    # SHFE returns '日期', DCE/CZCE return 'date'
    df = df.rename(columns={"日期": "date"})
    if "date" not in df.columns:
        return []

    df["date"] = df["date"].apply(_normalize_date)
    df = df.dropna(subset=["date"])

    end = signal_date + timedelta(days=forward_days)
    df  = df[(df["date"] >= signal_date) & (df["date"] <= end)].reset_index(drop=True)

    bars: list[dict] = []
    for _, row in df.iterrows():
        d  = row["date"]
        ts = int(datetime(d.year, d.month, d.day, 9, 0).timestamp())
        bars.append({
            "time":   ts,
            "open":   float(row["open"])   if pd.notna(row.get("open"))   else None,
            "high":   float(row["high"])   if pd.notna(row.get("high"))   else None,
            "low":    float(row["low"])    if pd.notna(row.get("low"))    else None,
            "close":  float(row["close"])  if pd.notna(row.get("close"))  else None,
            "volume": float(row["volume"]) if pd.notna(row.get("volume")) else None,
        })
    return bars


# ---------------------------------------------------------------------------
# Per-signal processing
# ---------------------------------------------------------------------------
def _safe(name: str) -> str:
    return name.lower().replace(".", "_").replace("-", "_")


def process_signal(
    symbol: str,
    signal_date: date,
    entry_price: float,
    sina_name: str,
    prefix: str,
    dte: int,
    forward_days: int,
    out_dir: Path,
) -> tuple[int, int]:
    """Fetch full chain for one signal. Returns (files_written, files_skipped)."""
    date_str = signal_date.isoformat()
    print(f"  [{symbol} {date_str}] entry={entry_price}")

    yymm, contracts = get_full_chain(sina_name, prefix, signal_date, dte)
    if not contracts:
        print(f"    → no chain found", file=sys.stderr)
        return 0, 0

    year   = 2000 + int(yymm[:2])
    month  = int(yymm[2:])
    approx_expiry = date(year, month, min(25, monthrange(year, month)[1]))
    print(f"    expiry≈{approx_expiry}  {len(contracts)} contracts in chain")

    sym_dir = out_dir / prefix.lower()
    sym_dir.mkdir(parents=True, exist_ok=True)

    written = skipped = 0
    for info in contracts:
        ticker = info["ticker"]
        strike = info["strike"]
        ct     = info["contract_type"]

        fname = sym_dir / f"{_safe(ticker)}_daily.json"
        if fname.exists():
            try:
                existing = json.loads(fname.read_text())
                if len(existing.get("bars", [])) >= MIN_BARS_COMPLETE:
                    skipped += 1
                    continue
            except Exception:
                pass

        bars = _fetch_daily_bars(ticker, signal_date, forward_days)
        if not bars:
            continue

        vols    = [b["volume"] for b in bars if b.get("volume") is not None]
        avg_vol = sum(vols) / len(vols) if vols else None

        payload = {
            "contract":      ticker,
            "underlying":    symbol,
            "strike":        strike,
            "contract_type": ct,
            "expiry":        approx_expiry.isoformat(),
            "liquidity": {
                "avg_daily_volume": round(avg_vol, 1) if avg_vol is not None else None,
                "liquidity_flag":   _liquidity_flag(avg_vol),
            },
            "bars": bars,
        }
        fname.write_text(json.dumps(payload))
        written += 1

    print(f"    → written={written}  skipped={skipped}  no_bars={len(contracts)-written-skipped}")
    return written, skipped


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Fetch CN futures option full chain daily OHLC via akshare (Sina Finance)"
    )
    ap.add_argument("--pool", nargs="+", default=list(POOL_FILES), metavar="POOL",
                    help=f"pools to process; choices: {list(POOL_FILES)}")
    ap.add_argument("--dte", type=int, default=30,
                    help="min days-to-expiry for contract month selection (default: 30)")
    ap.add_argument("--forward-days", type=int, default=30,
                    help="calendar days of forward OHLC to fetch (default: 30)")
    ap.add_argument("-o", "--out-dir", default="data/options/cn",
                    help="output directory (default: data/options/cn)")
    ap.add_argument("--direction", nargs="+", choices=["bottom", "top"],
                    default=None, metavar="DIR",
                    help="signal directions to process (default: all)")
    ap.add_argument("--relation", nargs="+", default=None, metavar="REL",
                    help="higher_relation filter (default: all)")
    args = ap.parse_args()

    out_dir = SRC_DIR / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    pools_to_run = [p for p in args.pool if p in POOL_FILES]
    if not pools_to_run:
        print(f"ERROR: no valid pools. choices: {list(POOL_FILES)}", file=sys.stderr)
        sys.exit(1)

    total_written = total_skipped = 0

    for pool_name in pools_to_run:
        csv_path = REVIEW_DIR / POOL_FILES[pool_name]
        if not csv_path.exists():
            print(f"WARN: {csv_path} not found, skipping {pool_name}", file=sys.stderr)
            continue

        df = pd.read_csv(csv_path)
        if args.direction:
            df = df[df["direction"].isin(args.direction)]
        if args.relation:
            df = df[df["higher_relation"].isin(args.relation)]
        signals = df.copy()
        signals["date"] = pd.to_datetime(signals["date"]).dt.date

        dir_tag = "/".join(args.direction) if args.direction else "all"
        rel_tag = "/".join(args.relation)  if args.relation  else "all"

        print(f"\n{'='*60}")
        print(f"Pool : {pool_name}  ({len(signals)} signals  dir={dir_tag} rel={rel_tag})")
        print(f"DTE  : {args.dte}  forward={args.forward_days}d")
        print(f"{'='*60}")

        for _, row in signals.iterrows():
            symbol   = row["symbol"]
            sig_date = row["date"]
            entry    = float(row["entry"])

            if symbol not in SYMBOL_CONFIG:
                print(f"  [{symbol}] no Sina options coverage, skip")
                continue

            sina_name, prefix = SYMBOL_CONFIG[symbol]

            w, s = process_signal(
                symbol=symbol,
                signal_date=sig_date,
                entry_price=entry,
                sina_name=sina_name,
                prefix=prefix,
                dte=args.dte,
                forward_days=args.forward_days,
                out_dir=out_dir,
            )
            total_written  += w
            total_skipped  += s

    n_files = sum(1 for _ in out_dir.rglob("*.json"))
    print(f"\n{'='*60}")
    print(f"Done. New files written : {total_written}")
    print(f"      Files skipped     : {total_skipped}")
    print(f"      Total in {out_dir.name}/ : {n_files}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
