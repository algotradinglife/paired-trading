"""Option premium-path loader for the attribution harness.

Primary: the exact contract's real daily OHLC from data/options/cn/{ul}/.
Fallback (added in a later task): Black-76 synthetic OHLC from the underlying
futures path. Source is tagged so the baseline reports modeled%."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from engine.options.cn_ag_selector import _bs_call_price

IV_ASSUMPTION = {"ag": 0.13, "au": 0.085}  # pinned 2026-06-10 from observed ATM IV
# medians (ag n=6 med 0.131; au n=32 med 0.085). See doc/repro/options_attribution_2026-06-10.md.
_RISK_FREE = 0.02


def load_option_daily(contract_sym: str, entry_date: date, data_dir: Path,
                      max_hold: int) -> pd.DataFrame | None:
    """Real OPTION daily-OHLC frame from entry_date forward (<= max_hold+5 rows).

    Reads {contract}_{YYYYMMDD}_daily.json (newest) or {contract}_daily.json.
    Returns None when no file/bars cover entry_date. Index reset; row 0 is the
    first bar with date >= entry_date.
    """
    sym = contract_sym.lower()
    files = sorted(data_dir.glob(f"{sym}_*_daily.json")) + sorted(data_dir.glob(f"{sym}_daily.json"))
    bars = None
    for p in files:
        doc = json.loads(p.read_text())
        if doc.get("bars"):
            bars = doc["bars"]
            break
    if not bars:
        return None
    df = pd.DataFrame(bars)
    df["date"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.date
    df = df[df["date"] >= entry_date].sort_values("date").reset_index(drop=True)
    if df.empty:
        return None
    return df.head(max_hold + 5)[["open", "high", "low", "close"]].reset_index(drop=True)


def model_option_daily(strike: float, expiry: date, entry_date: date,
                       underlying: pd.DataFrame, iv: float, max_hold: int,
                       r: float = _RISK_FREE) -> pd.DataFrame | None:
    """Black-76 synthetic OPTION daily-OHLC over the underlying path.

    Each day prices the call at the day's underlying high/low/close (so the
    exit-sim can check take/stop). T = (expiry - day)/365 in years.
    """
    ul = underlying.copy()
    ul["date"] = pd.to_datetime(ul["timestamp"], utc=True).dt.date
    ul = ul[ul["date"] >= entry_date].sort_values("date").reset_index(drop=True)
    if ul.empty:
        return None
    ul = ul.head(max_hold + 5)
    rows = []
    for _, b in ul.iterrows():
        T = max((expiry - b["date"]).days, 0) / 365.0
        rows.append({
            "open":  _bs_call_price(float(b["open"]),  strike, T, r, iv),
            "high":  _bs_call_price(float(b["high"]),  strike, T, r, iv),
            "low":   _bs_call_price(float(b["low"]),   strike, T, r, iv),
            "close": _bs_call_price(float(b["close"]), strike, T, r, iv),
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
