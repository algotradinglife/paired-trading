"""Stock-signal → option-payoff backtest.

For each gated divergence signal on the underlying stock:
  - bottom signal → buy ~30-DTE ATM CALL
  - top signal    → buy ~30-DTE ATM PUT
Compute the option premium return at h=5/10/20 trading days. Aggregate by
rule_id to test whether stock-validated rules (F1-F8) preserve their relative
ordering — and especially their magnitudes — when payoff is asymmetric.

This is the proper framework for the question "do F1-F8 transfer to options":
keep signals on the stock (where rules are calibrated), measure on the option
(where payoff lives).

API estimate (proxy): ~2 calls per signal (contracts list + aggregates).
SPY-only: ~86 calls. All 10 symbols: ~530 calls.

Output:
  data/review/option_payoffs_{symbol}.csv  — per-signal option results
  printout — aggregation by rule_id × horizon

Usage:
  POLYGON_PROXY_KEY=... uv run python scripts/option_payoff_backtest.py SPY
  POLYGON_PROXY_KEY=... uv run python scripts/option_payoff_backtest.py --all
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import requests

from engine.divergence.detector import detect_all_divergences
from engine.divergence.downstream_policies import apply_policy
from engine.features.macd import macd
from engine.features.streams import compute_feature_streams
from engine.divergence.multi_tf_context import (
    enrich_with_higher_tf,
    enrich_with_lower_tf,
)
from engine.units.snapshot import compute_unit_metadata

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "review"

PROXY = os.environ.get("POLYGON_PROXY_URL", "http://35.77.84.125:8080")
SLEEP = 0.3
TIMEOUT = 60
FORWARD_HORIZONS = [5, 10, 20]
TARGET_DTE = 45          # aim for 45-day expiry so h=20 trading days fit
DTE_WINDOW_DAYS = 15     # accept contracts ±15 calendar days from target
HORIZON_LOOKAHEAD_DAYS = 45  # window to pull option premium (covers h=20)

SYMBOLS_DEFAULT = ["SPY", "QQQ", "NVDA", "GLD", "DIA", "IWM", "TLT", "XLK", "XLF", "GDX"]


def get_proxy_key() -> str:
    k = os.environ.get("POLYGON_PROXY_KEY")
    if not k:
        print("ERROR: POLYGON_PROXY_KEY env var required.", file=sys.stderr)
        sys.exit(2)
    return k


HEADERS: dict[str, str] = {}


def _get_json(url: str) -> dict:
    """GET with proxy header, returning JSON. Pauses between calls."""
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    time.sleep(SLEEP)
    return r.json()


def load_underlying_bars(symbol: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol.lower()}_daily.json"
    payload = json.loads(path.read_text())
    df = pd.DataFrame(payload["bars"])
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df["date"] = df["timestamp"].dt.date
    return df.sort_values("timestamp").reset_index(drop=True)


def detect_signals_with_context(symbol: str, topology: str = "A") -> list:
    """Full pipeline: detect + enrich + apply policy.

    topology="A" (production): D + lower=1h + higher=W
    topology="B" (experimental): D + lower=15m + higher=1h
    """
    daily = load_underlying_bars(symbol)

    macd_df = macd(daily["close"], hist_scale=1.0)
    streams = compute_feature_streams(daily["close"], macd_df["dif"], macd_df["dea"], macd_df["hist"])
    units = compute_unit_metadata(macd_df["dif"], macd_df["dea"], macd_df["hist"],
                                  streams["dif_proximity_zero"])
    signals = detect_all_divergences(units_df=units, ohlc=daily, dif=macd_df["dif"],
                                     hist=macd_df["hist"], level_id="D")

    if topology == "A":
        higher_file, higher_level = f"{symbol.lower()}_weekly.json", "W"
        lower_file,  lower_level  = f"{symbol.lower()}_60.json",     "1h"
    elif topology == "B":
        higher_file, higher_level = f"{symbol.lower()}_60.json",     "1h"
        lower_file,  lower_level  = f"{symbol.lower()}_15.json",     "15m"
    else:
        raise ValueError(f"unknown topology: {topology}")

    higher_path = DATA_DIR / higher_file
    lower_path  = DATA_DIR / lower_file

    if higher_path.exists():
        bars = pd.DataFrame(json.loads(higher_path.read_text())["bars"])
        bars["timestamp"] = pd.to_datetime(bars["time"], unit="s", utc=True)
        signals = enrich_with_higher_tf(signals, daily, bars, higher_tf_level_id=higher_level)

    if lower_path.exists():
        bars = pd.DataFrame(json.loads(lower_path.read_text())["bars"])
        bars["timestamp"] = pd.to_datetime(bars["time"], unit="s", utc=True)
        signals = enrich_with_lower_tf(signals, daily, bars, lower_tf_level_id=lower_level)

    rows = []
    for sig in signals:
        idx = sig.candidate_bar_idx
        if idx + max(FORWARD_HORIZONS) >= len(daily):
            continue
        if sig.confidence < 0.3:
            continue
        entry_close = float(daily["close"].iloc[idx])
        decision = apply_policy(sig)
        rows.append((sig, decision, idx, entry_close, daily))
    return rows


def _third_friday(year: int, month: int) -> date:
    """3rd Friday of given month (standard US monthly options expiry)."""
    first = date(year, month, 1)
    days_until_friday = (4 - first.weekday()) % 7  # weekday 4 = Friday
    return first + timedelta(days=days_until_friday + 14)


def _target_monthly_expiry(signal_date: date, target_dte: int = TARGET_DTE) -> date | None:
    """Find the 3rd-Friday monthly expiry closest to signal_date + target_dte.

    Returns date or None if no suitable expiry within ±20 days of target.
    """
    target = signal_date + timedelta(days=target_dte)
    best = None
    best_gap = 10**9
    for off in range(0, 4):
        m = target.month + off
        y = target.year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        tf = _third_friday(y, m)
        days_away = abs((tf - target).days)
        if days_away < best_gap:
            best_gap = days_away
            best = tf
    if best is None or best_gap > 20:
        return None
    return best


def find_atm_contract(
    underlying: str, signal_date: date, signal_dir: str, underlying_price: float,
) -> str | None:
    """Find ~30-DTE ATM monthly-expiry option contract on signal_date.

    Restricts to standard 3rd-Friday monthly expiries (have full historical
    aggregate data on Polygon Starter; weekly/zero-DTE contracts have very
    limited history).

    Returns ticker like 'O:SPY250620C00580000', or None if no match.
    """
    target_exp = _target_monthly_expiry(signal_date)
    if target_exp is None:
        return None
    contract_type = "call" if signal_dir == "bottom" else "put"
    url = (
        f"{PROXY}/v3/reference/options/contracts"
        f"?underlying_ticker={underlying}"
        f"&contract_type={contract_type}"
        f"&expired=true"
        f"&expiration_date={target_exp.isoformat()}"
        f"&limit=1000"
    )
    try:
        data = _get_json(url)
    except Exception as e:
        print(f"    contract-list error: {e}", file=sys.stderr)
        return None
    results = data.get("results") or []
    if not results:
        return None
    best = min(results, key=lambda r: abs(r["strike_price"] - underlying_price))
    return best["ticker"]


def fetch_premium_series(ticker: str, start: date, end: date) -> pd.DataFrame:
    """Daily aggregates for one option contract from start to end."""
    url = (
        f"{PROXY}/v2/aggs/ticker/{ticker}/range/1/day/"
        f"{start.isoformat()}/{end.isoformat()}"
        f"?adjusted=true&limit=500&sort=asc"
    )
    try:
        data = _get_json(url)
    except Exception as e:
        print(f"    premium fetch error: {e}", file=sys.stderr)
        return pd.DataFrame()
    results = data.get("results") or []
    if not results:
        return pd.DataFrame()
    df = pd.DataFrame(results)
    df["date"] = pd.to_datetime(df["t"], unit="ms", utc=True).dt.date
    df = df.rename(columns={"c": "close"})
    return df[["date", "close"]]


def compute_payoff(signal_date: date, premium_df: pd.DataFrame) -> dict | None:
    """Return {h: return_pct} or None if data insufficient."""
    if premium_df.empty:
        return None
    # Trading-day forward returns. Find signal_date row (or nearest after).
    candidates = premium_df[premium_df["date"] >= signal_date].reset_index(drop=True)
    if len(candidates) < max(FORWARD_HORIZONS) + 1:
        return None
    entry_premium = float(candidates["close"].iloc[0])
    if entry_premium <= 0.01:
        return None
    out = {"entry_premium": entry_premium}
    for h in FORWARD_HORIZONS:
        target = float(candidates["close"].iloc[h])
        out[f"h{h}_ret"] = (target - entry_premium) / entry_premium
    return out


def process_symbol(symbol: str, topology: str = "A") -> pd.DataFrame:
    print(f"=== {symbol} (topology {topology}) ===")
    detection_rows = detect_signals_with_context(symbol, topology=topology)
    print(f"  {len(detection_rows)} signals with forward window")

    records = []
    for i, (sig, decision, entry_idx, entry_close, daily) in enumerate(detection_rows, 1):
        signal_date = daily["date"].iloc[entry_idx]
        contract = find_atm_contract(symbol, signal_date, sig.direction, entry_close)
        if contract is None:
            print(f"  [{i:3d}/{len(detection_rows)}] {signal_date}  {sig.direction:6s}  NO CONTRACT")
            continue
        end_date = signal_date + timedelta(days=HORIZON_LOOKAHEAD_DAYS + 10)
        premium = fetch_premium_series(contract, signal_date, end_date)
        payoff = compute_payoff(signal_date, premium)
        if payoff is None:
            print(f"  [{i:3d}/{len(detection_rows)}] {signal_date}  {sig.direction:6s}  insufficient option data ({contract})")
            continue
        ctx = sig.multi_tf_context or {}
        rec = {
            "symbol": symbol,
            "topology": topology,
            "date": signal_date.isoformat(),
            "direction": sig.direction,
            "subtype": sig.subtype,
            "level": sig.level,
            "confidence": sig.confidence,
            "rule_id": decision.rule_id or "—",
            "rule_weight": decision.weight,
            "lower_relation": ctx.get("lower_relation", "n/a"),
            "lower_tf_level": ctx.get("lower_tf_level_id", "n/a"),
            "higher_relation": ctx.get("higher_relation", "n/a"),
            "higher_tf_level": ctx.get("higher_tf_level_id", "n/a"),
            "contract": contract,
            "entry_close": entry_close,
            "entry_premium": payoff["entry_premium"],
            **{f"h{h}_ret": payoff[f"h{h}_ret"] for h in FORWARD_HORIZONS},
        }
        records.append(rec)
        if i % 5 == 0 or i == len(detection_rows):
            print(f"  [{i:3d}/{len(detection_rows)}] {signal_date}  {sig.direction:6s}  {contract}  h20={payoff['h20_ret']*100:+.1f}%")

    df = pd.DataFrame(records)
    if df.empty:
        return df
    suffix = f"_{topology.lower()}" if topology != "A" else ""
    out_path = OUT_DIR / f"option_payoffs_{symbol.lower()}{suffix}.csv"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"  saved {len(df)} rows → {out_path}\n")
    return df


def aggregate_report(df: pd.DataFrame):
    if df.empty:
        print("No records to aggregate.")
        return
    print("\n=== Aggregate by rule_id (option-payoff h=20) ===")
    for h in FORWARD_HORIZONS:
        col = f"h{h}_ret"
        print(f"\n  -- h={h} --")
        agg = df.groupby("rule_id").agg(
            n=("symbol", "size"),
            hit_rate=(col, lambda s: float((s > 0).mean())),
            mean_ret=(col, "mean"),
            median_ret=(col, "median"),
            p25=(col, lambda s: float(s.quantile(0.25))),
            p75=(col, lambda s: float(s.quantile(0.75))),
        ).round(4)
        agg["hit_rate"] = (agg["hit_rate"] * 100).round(1).astype(str) + "%"
        for c in ("mean_ret", "median_ret", "p25", "p75"):
            agg[c] = (agg[c] * 100).round(1).astype(str) + "%"
        print(agg.to_string())

    print("\n=== By direction × rule_id (h=20) ===")
    g = df.groupby(["direction", "rule_id"]).agg(
        n=("symbol", "size"),
        hit_rate=("h20_ret", lambda s: float((s > 0).mean())),
        mean_ret=("h20_ret", "mean"),
    ).round(4)
    g["hit_rate"] = (g["hit_rate"] * 100).round(1).astype(str) + "%"
    g["mean_ret"] = (g["mean_ret"] * 100).round(1).astype(str) + "%"
    print(g.to_string())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="*", help="Underlying tickers (default: SPY)")
    parser.add_argument("--all", action="store_true", help=f"Process all default symbols: {SYMBOLS_DEFAULT}")
    parser.add_argument("--topology", choices=("A", "B"), default="A",
                        help="A = production (D+1h+W), B = experimental (D+15m+1h)")
    parser.add_argument("--exclude", action="append", default=[],
                        help="Symbols to skip (repeatable, e.g. --exclude NVDA)")
    parser.add_argument("--output-suffix", default=None,
                        help="Suffix for combined CSV (default: derived from topology + excludes)")
    args = parser.parse_args()

    HEADERS["X-Proxy-Key"] = get_proxy_key()

    symbols = SYMBOLS_DEFAULT if args.all else (args.symbols or ["SPY"])
    excludes = {s.upper() for s in args.exclude}
    symbols = [s for s in symbols if s.upper() not in excludes]
    if excludes:
        print(f"Excluding: {sorted(excludes)}")
    print(f"Symbols ({len(symbols)}): {symbols}")
    print(f"Topology: {args.topology}\n")

    all_dfs = []
    for sym in symbols:
        df = process_symbol(sym, topology=args.topology)
        if not df.empty:
            all_dfs.append(df)

    if not all_dfs:
        print("No data collected.")
        return 0

    combined = pd.concat(all_dfs, ignore_index=True)
    if args.output_suffix is not None:
        suffix = args.output_suffix
    else:
        suffix_parts = [f"topology_{args.topology.lower()}"]
        if excludes:
            suffix_parts.append("no_" + "_".join(sorted(s.lower() for s in excludes)))
        suffix = "_".join(suffix_parts)
    combined_path = OUT_DIR / f"option_payoffs_{suffix}.csv"
    combined.to_csv(combined_path, index=False)
    print(f"\nCombined CSV → {combined_path}  ({len(combined)} rows)")
    aggregate_report(combined)
    return 0


if __name__ == "__main__":
    sys.exit(main())
