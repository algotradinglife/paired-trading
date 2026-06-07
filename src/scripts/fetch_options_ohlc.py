"""Fetch OHLC candle data for full option chains on US ETFs via Polygon proxy.

For each signal, fetches the complete option chain (all strikes, calls + puts)
for the nearest monthly expiry with target DTE. Bars are available at daily,
60min (1h), 15min, and 5min timeframes.

Note: Polygon Starter plan provides ~2 years of history. Signals older than
      ~2 years will be skipped (expired contracts not returned by reference API).

Auth:
  POLYGON_PROXY_KEY env var (set via _with_creds.sh polygon)

Usage:
  uv run python scripts/fetch_options_ohlc.py
  uv run python scripts/fetch_options_ohlc.py --pool US_EQUITY US_MACRO
  uv run python scripts/fetch_options_ohlc.py --dte 21 --forward-days 20
  uv run python scripts/fetch_options_ohlc.py --tfs daily 60 15 5
  uv run python scripts/fetch_options_ohlc.py --direction bottom --relation opposing
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
SRC_DIR    = Path(__file__).resolve().parents[1]
REVIEW_DIR = SRC_DIR / "data" / "review"

PROXY   = os.environ.get("POLYGON_PROXY_URL", "http://35.77.84.125:8080")
SLEEP   = 0.3
TIMEOUT = 60

POOL_FILES: dict[str, str] = {
    "US_EQUITY": "rr_b_us_equity.csv",
    "US_MACRO":  "rr_b_us_macro.csv",
}

POOL_SYMBOLS: dict[str, str] = {
    "spy":  "SPY",
    "qqq":  "QQQ",
    "iwm":  "IWM",
    "dia":  "DIA",
    "nvda": "NVDA",
    "xlf":  "XLF",
    "xlk":  "XLK",
    "gdx":  "GDX",
    "gld":  "GLD",
    "tlt":  "TLT",
}

TF_CONFIG: dict[str, tuple[int, str]] = {
    "daily": (1,  "day"),
    "60":    (60, "minute"),
    "15":    (15, "minute"),
    "5":     (5,  "minute"),
}

MIN_BARS_COMPLETE = 5

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
HEADERS: dict[str, str] = {}


def _get_proxy_key() -> str:
    k = os.environ.get("POLYGON_PROXY_KEY")
    if not k:
        print("ERROR: POLYGON_PROXY_KEY env var is required.", file=sys.stderr)
        sys.exit(2)
    return k


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------
def _get_json(url: str) -> dict:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    time.sleep(SLEEP)
    return r.json()


# ---------------------------------------------------------------------------
# Expiry finder
# ---------------------------------------------------------------------------
def _nearest_actual_expiry(
    underlying: str,
    signal_date: date,
    target_dte: int,
) -> date | None:
    """Return nearest expiry date >= signal_date + target_dte from Polygon reference API.

    Returns None if signal is outside the ~2-year Polygon Starter plan window.
    """
    target = signal_date + timedelta(days=target_dte)
    cutoff = date.today() - timedelta(days=730)
    if target < cutoff:
        return None
    url = (
        f"{PROXY}/v3/reference/options/contracts"
        f"?underlying_ticker={underlying}"
        f"&contract_type=call"
        f"&expiration_date.gte={target.isoformat()}"
        f"&sort=expiration_date&order=asc&limit=1"
    )
    try:
        data = _get_json(url)
    except Exception:
        return None
    results = data.get("results") or []
    if not results:
        return None
    return date.fromisoformat(results[0]["expiration_date"])


# ---------------------------------------------------------------------------
# Full chain lookup
# ---------------------------------------------------------------------------
def get_chain_contracts(
    underlying: str,
    signal_date: date,
    dte: int,
) -> tuple[date | None, list[dict]]:
    """Return (expiry_date, contracts) for the nearest valid expiry.

    contracts: list of {ticker, strike, contract_type} for all strikes (calls + puts).
    Returns (None, []) when outside the 2-year window or no data found.
    """
    target_exp = _nearest_actual_expiry(underlying, signal_date, dte)
    if target_exp is None:
        print(
            f"    [{underlying} {signal_date}] outside Polygon 2yr window — skip",
            file=sys.stderr,
        )
        return None, []

    contracts: list[dict] = []
    for ct in ("call", "put"):
        url = (
            f"{PROXY}/v3/reference/options/contracts"
            f"?underlying_ticker={underlying}"
            f"&contract_type={ct}"
            f"&expiration_date={target_exp.isoformat()}"
            f"&limit=1000"
        )
        try:
            data = _get_json(url)
        except Exception as exc:
            print(f"    chain-list error {underlying} {ct}: {exc}", file=sys.stderr)
            continue
        for r in (data.get("results") or []):
            contracts.append({
                "ticker":        str(r["ticker"]),
                "strike":        float(r["strike_price"]),
                "contract_type": ct,
            })

    if not contracts:
        print(
            f"    [{underlying} {signal_date}] no contracts returned for expiry {target_exp}",
            file=sys.stderr,
        )
    return target_exp, contracts


# ---------------------------------------------------------------------------
# OHLC fetch
# ---------------------------------------------------------------------------
def _bars_from_results(results: list[dict]) -> list[dict]:
    bars = []
    for row in results:
        bars.append({
            "time":   int(row["t"]) // 1000,
            "open":   float(row["o"]),
            "high":   float(row["h"]),
            "low":    float(row["l"]),
            "close":  float(row["c"]),
            "volume": int(row.get("v", 0)),
        })
    bars.sort(key=lambda b: b["time"])
    seen: set[int] = set()
    deduped: list[dict] = []
    for b in bars:
        if b["time"] not in seen:
            seen.add(b["time"])
            deduped.append(b)
    return deduped


def fetch_ohlc(
    contract_ticker: str,
    tf_label: str,
    start: date,
    end: date,
) -> list[dict]:
    multiplier, timespan = TF_CONFIG[tf_label]
    url = (
        f"{PROXY}/v2/aggs/ticker/{contract_ticker}/range"
        f"/{multiplier}/{timespan}"
        f"/{start.isoformat()}/{end.isoformat()}"
        f"?adjusted=true&limit=5000&sort=asc"
    )
    try:
        data = _get_json(url)
    except Exception as exc:
        print(f"    OHLC fetch error ({contract_ticker} {tf_label}): {exc}", file=sys.stderr)
        return []
    return _bars_from_results(data.get("results") or [])


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def _output_path(output_dir: Path, symbol: str, contract_ticker: str, tf_label: str) -> Path:
    sym_dir = output_dir / symbol.lower()
    sym_dir.mkdir(parents=True, exist_ok=True)
    safe_ticker = contract_ticker.lower().replace(":", "_")
    return sym_dir / f"{safe_ticker}_{tf_label}.json"


def _already_complete(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text())
        return len(payload.get("bars", [])) >= MIN_BARS_COMPLETE
    except Exception:
        return False


def _liquidity_meta(bars: list[dict]) -> dict:
    if not bars:
        return {}
    vols = [b["volume"] for b in bars if b.get("volume", 0) > 0]
    if not vols:
        return {"avg_daily_volume": 0, "liquidity_flag": "no_volume"}
    avg  = sum(vols) / len(vols)
    flag = "ok" if avg >= 50 else ("thin" if avg >= 10 else "illiquid")
    return {"avg_daily_volume": round(avg, 1), "liquidity_flag": flag}


def _write_output(
    path: Path,
    contract_ticker: str,
    underlying: str,
    strike: float,
    contract_type: str,
    bars: list[dict],
    daily_bars: list[dict] | None = None,
) -> None:
    liq_source = daily_bars if daily_bars is not None else bars
    payload = {
        "contract":      contract_ticker,
        "underlying":    underlying.lower(),
        "strike":        strike,
        "contract_type": contract_type,
        "liquidity":     _liquidity_meta(liq_source),
        "bars":          bars,
    }
    path.write_text(json.dumps(payload, separators=(",", ":")))


# ---------------------------------------------------------------------------
# Signal loading
# ---------------------------------------------------------------------------
def load_signals(
    pool: str,
    directions: list[str] | None = None,
    relations: list[str] | None = None,
) -> pd.DataFrame:
    fname = POOL_FILES[pool]
    path  = REVIEW_DIR / fname
    if not path.exists():
        print(f"  WARNING: signal file not found: {path}", file=sys.stderr)
        return pd.DataFrame()

    df = pd.read_csv(path)
    if directions:
        df = df[df["direction"].isin(directions)]
    if relations:
        df = df[df["higher_relation"].isin(relations)]
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------
def process_signals(
    pools: list[str],
    dte: int,
    forward_days: int,
    tfs: list[str],
    output_dir: Path,
    directions: list[str] | None = None,
    relations: list[str] | None = None,
) -> None:
    total_signals = 0
    total_contracts = 0
    files_written: dict[str, int] = {tf: 0 for tf in tfs}
    files_skipped: dict[str, int] = {tf: 0 for tf in tfs}
    illiquid_count = 0

    for pool in pools:
        print(f"\n=== Pool: {pool} ===")
        signals_df = load_signals(pool, directions=directions, relations=relations)
        if signals_df.empty:
            print(f"  No signals (direction={directions} relation={relations}).")
            continue

        dir_tag = "/".join(directions) if directions else "all"
        rel_tag = "/".join(relations)  if relations  else "all"
        print(f"  {len(signals_df)} signals (direction={dir_tag} relation={rel_tag})")
        total_signals += len(signals_df)

        for _, row in signals_df.iterrows():
            sym_lower  = str(row["symbol"]).lower()
            underlying = POOL_SYMBOLS.get(sym_lower)
            if underlying is None:
                print(f"  [{sym_lower}] unknown symbol — skipping")
                continue

            signal_date: date  = row["date"]
            entry_price: float = float(row["entry"])

            print(f"  [{sym_lower} {signal_date}] entry={entry_price:.2f}")

            target_exp, contracts = get_chain_contracts(underlying, signal_date, dte)
            if not contracts:
                continue

            print(f"    expiry={target_exp}  {len(contracts)} contracts in chain")
            total_contracts += len(contracts)

            fetch_start = signal_date
            fetch_end   = signal_date + timedelta(days=forward_days)

            sig_written = sig_skipped = 0
            for info in contracts:
                contract_ticker = info["ticker"]
                strike          = info["strike"]
                ct              = info["contract_type"]

                # Fetch daily first for liquidity assessment
                daily_bars: list[dict] = []
                if "daily" in tfs:
                    out_path = _output_path(output_dir, underlying, contract_ticker, "daily")
                    if _already_complete(out_path):
                        sig_skipped += 1
                        files_skipped["daily"] += 1
                        try:
                            daily_bars = json.loads(out_path.read_text()).get("bars", [])
                        except Exception:
                            pass
                    else:
                        daily_bars = fetch_ohlc(contract_ticker, "daily", fetch_start, fetch_end)
                        if daily_bars:
                            liq  = _liquidity_meta(daily_bars)
                            flag = liq.get("liquidity_flag", "?")
                            if flag in ("thin", "illiquid"):
                                illiquid_count += 1
                            _write_output(out_path, contract_ticker, underlying,
                                          strike, ct, daily_bars, daily_bars)
                            sig_written += 1
                            files_written["daily"] += 1

                for tf in tfs:
                    if tf == "daily":
                        continue
                    out_path = _output_path(output_dir, underlying, contract_ticker, tf)
                    if _already_complete(out_path):
                        sig_skipped += 1
                        files_skipped[tf] += 1
                        continue
                    bars = fetch_ohlc(contract_ticker, tf, fetch_start, fetch_end)
                    if not bars:
                        continue
                    _write_output(out_path, contract_ticker, underlying,
                                  strike, ct, bars, daily_bars or None)
                    sig_written += 1
                    files_written[tf] += 1

            print(f"    → written={sig_written}  skipped={sig_skipped}")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print(f"  Signals processed : {total_signals}")
    print(f"  Contracts fetched : {total_contracts}")
    print(f"  Illiquid/thin     : {illiquid_count}")
    for tf in tfs:
        print(f"  Files [{tf:>5}]  written={files_written[tf]}  skipped={files_skipped[tf]}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch full option chain OHLC for US signals via Polygon proxy."
    )
    parser.add_argument(
        "--pool",
        nargs="+",
        choices=list(POOL_FILES),
        default=list(POOL_FILES),
        metavar="POOL",
        help=f"Signal pools to process (default: all). Choices: {list(POOL_FILES)}",
    )
    parser.add_argument(
        "--dte",
        type=int,
        default=21,
        help="Target days-to-expiry for contract month selection (default: 21)",
    )
    parser.add_argument(
        "--forward-days",
        type=int,
        default=20,
        help="Calendar days after signal_date to fetch OHLC (default: 20)",
    )
    parser.add_argument(
        "--tfs",
        nargs="+",
        choices=list(TF_CONFIG),
        default=["daily", "60", "15"],
        metavar="TF",
        help=f"Timeframes (default: daily 60 15). Choices: {list(TF_CONFIG)}",
    )
    parser.add_argument(
        "--direction",
        nargs="+",
        choices=["bottom", "top"],
        default=None,
        metavar="DIR",
        help="Signal directions to process (default: all)",
    )
    parser.add_argument(
        "--relation",
        nargs="+",
        default=None,
        metavar="REL",
        help="higher_relation filter (default: all)",
    )
    parser.add_argument(
        "-o", "--output",
        default="data/options",
        help="Output directory relative to src/ (default: data/options)",
    )
    args = parser.parse_args()

    HEADERS["X-Proxy-Key"] = _get_proxy_key()

    output_dir = SRC_DIR / args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Pools       : {args.pool}")
    print(f"Direction   : {args.direction or 'all'}")
    print(f"Relation    : {args.relation or 'all'}")
    print(f"Target DTE  : {args.dte}")
    print(f"Forward days: {args.forward_days}")
    print(f"Timeframes  : {args.tfs}")
    print(f"Output dir  : {output_dir}")

    process_signals(
        pools=args.pool,
        dte=args.dte,
        forward_days=args.forward_days,
        tfs=args.tfs,
        output_dir=output_dir,
        directions=args.direction,
        relations=args.relation,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
