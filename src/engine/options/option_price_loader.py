"""Option premium-path loader for the attribution harness.

Primary: the exact contract's real daily OHLC from data/options/cn/{ul}/.
Fallback (added in a later task): Black-76 synthetic OHLC from the underlying
futures path. Source is tagged so the baseline reports modeled%."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from engine.options.black76 import black76_price

IV_ASSUMPTION = {"ag": 0.13, "au": 0.085}  # pinned 2026-06-10 from observed ATM IV
# medians (ag n=6 med 0.131; au n=32 med 0.085). See doc/repro/options_attribution_2026-06-10.md.
_RISK_FREE = 0.02


def load_option_daily(contract_sym: str, entry_date: date, data_dir: Path,
                      max_hold: int, *,
                      quant_root: Path | None = None) -> pd.DataFrame | None:
    """Real OPTION daily-OHLC frame from entry_date forward (<= max_hold+5 rows).

    Reads both the quant-cli OptionStore parquet (``quant_root`` defaults
    to the data/quant symlink) and the legacy JSON files
    ({contract}_{YYYYMMDD}_daily.json newest first, then
    {contract}_daily.json) and returns whichever covers MORE sessions —
    a mid-backfill parquet stub must not shadow a complete JSON path
    (and vice versa). Returns None when no source covers entry_date.
    Index reset; row 0 is the first bar with date >= entry_date.
    """
    sym = contract_sym.lower()

    from data.bar_loader import DEFAULT_QUANT_ROOT
    from data.option_store import get_store
    store = get_store(quant_root if quant_root is not None else DEFAULT_QUANT_ROOT)
    pq_frame: pd.DataFrame | None = None
    pq = store.load_contract_daily(sym)
    if pq is not None:
        pq = pq[pq["date"] >= entry_date].reset_index(drop=True)
        if not pq.empty:
            pq_frame = pq.head(max_hold + 5)[
                ["open", "high", "low", "close"]
            ].reset_index(drop=True)

    # Newest dated snapshot first (most complete history), then the rolling file.
    # Try each until one actually covers entry_date — don't stop at the first
    # file with bars, or a stale snapshot spuriously forces the model fallback.
    json_frame: pd.DataFrame | None = None
    files = (sorted(data_dir.glob(f"{sym}_*_daily.json"), reverse=True)
             + sorted(data_dir.glob(f"{sym}_daily.json")))
    for p in files:
        doc = json.loads(p.read_text())
        bars = doc.get("bars")
        if not bars:
            continue
        df = pd.DataFrame(bars)
        df["date"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.date
        df = df[df["date"] >= entry_date].sort_values("date").reset_index(drop=True)
        if not df.empty:
            json_frame = df.head(max_hold + 5)[
                ["open", "high", "low", "close"]
            ].reset_index(drop=True)
            break

    candidates = [f for f in (pq_frame, json_frame) if f is not None]
    if not candidates:
        return None
    return max(candidates, key=len)


def model_option_daily(strike: float, expiry: date, entry_date: date,
                       underlying: pd.DataFrame, iv: float, max_hold: int,
                       r: float = _RISK_FREE) -> pd.DataFrame | None:
    """Black-76 synthetic OPTION daily-OHLC over the underlying path.

    Each day prices the call at the day's underlying high/low/close (so the
    exit-sim can check take/stop). T = (expiry - day)/365 in years. The path is
    truncated at expiry — past expiry the option no longer trades, so simulating
    further would mark intrinsic value on post-expiry underlying moves.
    """
    ul = underlying.copy()
    ul["date"] = pd.to_datetime(ul["timestamp"], utc=True).dt.date
    ul = ul[(ul["date"] >= entry_date) & (ul["date"] <= expiry)]
    ul = ul.sort_values("date").reset_index(drop=True)
    if ul.empty:
        return None
    ul = ul.head(max_hold + 5)
    rows = []
    for _, b in ul.iterrows():
        T = max((expiry - b["date"]).days, 0) / 365.0
        rows.append({
            "open":  black76_price(float(b["open"]),  strike, T, r, iv, "C"),
            "high":  black76_price(float(b["high"]),  strike, T, r, iv, "C"),
            "low":   black76_price(float(b["low"]),   strike, T, r, iv, "C"),
            "close": black76_price(float(b["close"]), strike, T, r, iv, "C"),
        })
    return pd.DataFrame(rows)


def premium_path(contract_sym: str, *, strike: float, expiry: date,
                 entry_date: date, data_dir: Path, underlying: pd.DataFrame,
                 iv: float, max_hold: int, min_cover: int = 5):
    """Return (option_daily_ohlc, source). Market if the real contract has
    >= min_cover rows from entry_date, else Black-76 model."""
    real = load_option_daily(contract_sym, entry_date, data_dir, max_hold)
    if real is not None and len(real) >= min_cover:
        return real, "market"
    model = model_option_daily(strike, expiry, entry_date, underlying, iv, max_hold)
    return model, "model"
