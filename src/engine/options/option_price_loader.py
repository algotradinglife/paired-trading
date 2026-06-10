"""Option premium-path loader for the attribution harness.

Primary: the exact contract's real daily OHLC from data/options/cn/{ul}/.
Fallback (added in a later task): Black-76 synthetic OHLC from the underlying
futures path. Source is tagged so the baseline reports modeled%."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd


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
