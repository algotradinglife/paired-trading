"""Context A — 1H Entry Timing Study.

Studies whether entering at the first 1H bar where MACD histogram turns
positive (within a daily Context A window) gives better timing than entering
at the daily Context A close.

Context A = daily DIF>0, established uptrend (EMA20 >= 1.05×EMA60),
price 3-10% below 20-bar daily high, below EMA20.

Usage:
  uv run python scripts/backtest_context_a_1h.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from engine.divergence.pa_context_classifier import classify_context
from engine.features.macd import macd, ema

# ---------------------------------------------------------------------------
# Symbol pools
# ---------------------------------------------------------------------------

POOLS: dict[str, list[str]] = {
    "US": ["spy", "qqq", "nvda", "gdx"],
    "CN_METAL": ["kq_m_shfe_ag", "kq_m_shfe_au", "kq_m_shfe_cu"],
}

BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_bars(sym: str, suffix: str = "_daily") -> pd.DataFrame | None:
    candidates = list(BARS_DIR.glob(f"**/{sym}{suffix}.json"))
    if not candidates:
        return None
    payload = json.loads(candidates[0].read_text())
    raw = payload.get("bars", payload)
    df = pd.DataFrame(raw)
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Context A window detection
# ---------------------------------------------------------------------------


def find_context_a_windows(bars: pd.DataFrame) -> list[int]:
    """Return indices of the FIRST bar in each continuous Context A run."""
    macd_df = macd(bars["close"])
    e20 = ema(bars["close"], 20)
    e60 = ema(bars["close"], 60)

    contexts = []
    for i in range(len(bars)):
        ctx = classify_context(bars, i, macd_df, e20, e60)
        contexts.append(ctx)

    # Deduplicate: keep only the first bar of each continuous A run
    window_starts: list[int] = []
    prev = None
    for i, ctx in enumerate(contexts):
        if ctx == "A" and prev != "A":
            window_starts.append(i)
        prev = ctx
    return window_starts


# ---------------------------------------------------------------------------
# 1H MACD hist turn-positive detection
# ---------------------------------------------------------------------------


def find_1h_entry(
    h_bars: pd.DataFrame,
    h_macd_hist: pd.Series,
    window_start_ts: pd.Timestamp,
    window_end_ts: pd.Timestamp,
) -> int | None:
    """Find first 1H bar (strict hist zero-crossing positive) within window.

    Looks for first j where hist[j] > 0 AND hist[j-1] <= 0, after
    window_start_ts.

    Returns the positional index into h_bars, or None.
    """
    mask = (h_bars["timestamp"] >= window_start_ts) & (h_bars["timestamp"] <= window_end_ts)
    window_indices = h_bars.index[mask].tolist()

    for pos in window_indices:
        if pos == 0:
            continue  # can't check previous bar
        hist_cur = float(h_macd_hist.iloc[pos])
        hist_prev = float(h_macd_hist.iloc[pos - 1])
        if hist_cur > 0 and hist_prev <= 0:
            return pos
    return None


# ---------------------------------------------------------------------------
# Forward return helpers
# ---------------------------------------------------------------------------


def fwd_max_return_daily(bars: pd.DataFrame, entry_idx: int, n_bars: int) -> float | None:
    """Max high in next n_bars daily bars, expressed as % above close at entry_idx."""
    entry_price = float(bars["close"].iloc[entry_idx])
    end_idx = min(entry_idx + n_bars + 1, len(bars))
    highs = bars["high"].iloc[entry_idx + 1 : end_idx]
    if highs.empty:
        return None
    max_high = float(highs.max())
    return (max_high - entry_price) / entry_price * 100.0


def fwd_max_return_1h(
    h_bars: pd.DataFrame,
    h1_entry_pos: int,
    n_bars: int,
) -> float | None:
    """Max high in next n_bars 1H bars, expressed as % above 1H entry bar close."""
    entry_price = float(h_bars["close"].iloc[h1_entry_pos])
    end_pos = min(h1_entry_pos + n_bars + 1, len(h_bars))
    highs = h_bars["high"].iloc[h1_entry_pos + 1 : end_pos]
    if highs.empty:
        return None
    max_high = float(highs.max())
    return (max_high - entry_price) / entry_price * 100.0


def stop_low_before_entry(h_bars: pd.DataFrame, h1_entry_pos: int, lookback: int = 5) -> float:
    """Min low of last `lookback` 1H bars before the entry bar."""
    start = max(0, h1_entry_pos - lookback)
    lows = h_bars["low"].iloc[start:h1_entry_pos]
    if lows.empty:
        return float(h_bars["low"].iloc[h1_entry_pos])
    return float(lows.min())


# ---------------------------------------------------------------------------
# Per-symbol study
# ---------------------------------------------------------------------------


def _h1_anchor_price(h_bars: pd.DataFrame, daily_ts: pd.Timestamp) -> float | None:
    """Find the last 1H bar close on the same calendar day as daily_ts.

    Searches a 24-hour window starting from daily_ts (which is typically the
    day open timestamp, e.g. 04:00 UTC for US or 00:00/01:00 UTC for CN).
    Returns the last 1H bar close on that day as the baseline anchor.

    Using the 1H close as the baseline keeps both baseline_entry and h1_entry_price
    on the same price scale, avoiding distortion from split-adjusted mismatches
    between daily and 60min data sources (e.g. NVDA pre-2024 60min vs adjusted daily).
    """
    # Search the entire calendar day: from daily_ts to daily_ts + 24h
    anchor_start = daily_ts
    anchor_end = daily_ts + pd.Timedelta(hours=24)
    mask = (h_bars["timestamp"] >= anchor_start) & (h_bars["timestamp"] < anchor_end)
    candidates = h_bars[mask]
    if candidates.empty:
        return None
    return float(candidates["close"].iloc[-1])


def study_symbol(sym: str) -> list[dict] | None:
    """Run the 1H entry timing study for one symbol.

    Returns a list of event records, or None if data is missing.

    Entry improvement is computed entirely in 1H price space to avoid
    cross-dataset price-scale mismatches (split-adjusted daily vs raw 60min).
    """
    d_bars = load_bars(sym, "_daily")
    h_bars = load_bars(sym, "_60")
    if d_bars is None or h_bars is None:
        return None

    # Compute 1H MACD on FULL series (avoids warm-up window issues)
    h1_macd = macd(h_bars["close"])
    h1_hist = h1_macd["hist"].reset_index(drop=True)
    h_bars = h_bars.reset_index(drop=True)

    window_starts = find_context_a_windows(d_bars)

    records: list[dict] = []
    for d_idx in window_starts:
        # Skip if too close to end of daily series (need 40 bars of fwd returns)
        if d_idx + 41 > len(d_bars):
            continue

        daily_ts = d_bars["timestamp"].iloc[d_idx]

        # 1H anchor: use the last 1H close on the same trading day as the daily bar.
        # This keeps baseline and entry prices on the same (60min data) price scale.
        h1_anchor = _h1_anchor_price(h_bars, daily_ts)
        if h1_anchor is None:
            # 60min data doesn't cover this date — skip (e.g. early history)
            continue

        # 1H search window: slightly before daily open of D to catch same-day signals,
        # up to 10 days forward
        window_start_ts = daily_ts - pd.Timedelta(hours=4)
        window_end_ts = daily_ts + pd.Timedelta(days=10)

        h1_entry_pos = find_1h_entry(h_bars, h1_hist, window_start_ts, window_end_ts)

        if h1_entry_pos is None:
            records.append({
                "symbol": sym,
                "d_idx": d_idx,
                "daily_ts": daily_ts,
                "no_1h_signal": True,
                "entry_improvement_pct": np.nan,
                "stop_low": np.nan,
                "h1_entry_price": np.nan,
                "h1_entry_ts": pd.NaT,
                "daily_maxret_10d": fwd_max_return_daily(d_bars, d_idx, 10),
                "daily_maxret_20d": fwd_max_return_daily(d_bars, d_idx, 20),
                "daily_maxret_40d": fwd_max_return_daily(d_bars, d_idx, 40),
                "h1_maxret_20h": np.nan,
                "h1_maxret_40h": np.nan,
                "h1_maxret_80h": np.nan,
            })
            continue

        h1_entry_price = float(h_bars["close"].iloc[h1_entry_pos])
        h1_entry_ts = h_bars["timestamp"].iloc[h1_entry_pos]
        # Improvement expressed in 1H price scale: positive = 1H enters lower
        entry_improvement_pct = (h1_anchor - h1_entry_price) / h1_anchor * 100.0
        sl = stop_low_before_entry(h_bars, h1_entry_pos, lookback=5)

        records.append({
            "symbol": sym,
            "d_idx": d_idx,
            "daily_ts": daily_ts,
            "no_1h_signal": False,
            "entry_improvement_pct": entry_improvement_pct,
            "stop_low": sl,
            "h1_entry_price": h1_entry_price,
            "h1_entry_ts": h1_entry_ts,
            "daily_maxret_10d": fwd_max_return_daily(d_bars, d_idx, 10),
            "daily_maxret_20d": fwd_max_return_daily(d_bars, d_idx, 20),
            "daily_maxret_40d": fwd_max_return_daily(d_bars, d_idx, 40),
            "h1_maxret_20h": fwd_max_return_1h(h_bars, h1_entry_pos, 20),
            "h1_maxret_40h": fwd_max_return_1h(h_bars, h1_entry_pos, 40),
            "h1_maxret_80h": fwd_max_return_1h(h_bars, h1_entry_pos, 80),
        })

    return records


# ---------------------------------------------------------------------------
# Report printing
# ---------------------------------------------------------------------------


def print_pool_report(pool_name: str, syms_with_data: list[str], all_records: list[dict]) -> None:
    df = pd.DataFrame(all_records)
    total_windows = len(df)
    found = df[~df["no_1h_signal"]]
    no_sig = df[df["no_1h_signal"]]
    n_found = len(found)
    n_no_sig = len(no_sig)
    pct_found = n_found / total_windows * 100 if total_windows > 0 else 0.0

    print(f"\nPool: {pool_name}  (symbols with 60min data: {', '.join(syms_with_data)})")
    print(f"  Context A windows: {total_windows:3d}  |  "
          f"1H signal found: {n_found} ({pct_found:.0f}%)  |  "
          f"no signal: {n_no_sig}")

    if found.empty:
        print("  (no 1H signals — cannot compute improvement stats)")
        return

    imp = found["entry_improvement_pct"]
    print(f"\n  Entry improvement (1H entry vs daily close):")
    print(f"    mean: {imp.mean():+.1f}%  median: {imp.median():+.1f}%  "
          f"p25: {imp.quantile(0.25):.1f}%  p75: {imp.quantile(0.75):.1f}%")
    print(f"    (positive = 1H enters lower = better timing)")

    # Daily forward returns (using all windows regardless of 1H signal)
    dr10 = df["daily_maxret_10d"].dropna()
    dr20 = df["daily_maxret_20d"].dropna()
    dr40 = df["daily_maxret_40d"].dropna()
    print(f"\n  Forward max return from DAILY close entry:")
    print(f"    MaxRet@10d: {dr10.mean():+.1f}%   "
          f"MaxRet@20d: {dr20.mean():+.1f}%   "
          f"MaxRet@40d: {dr40.mean():+.1f}%")

    # 1H forward returns (only where 1H signal found)
    hr20 = found["h1_maxret_20h"].dropna()
    hr40 = found["h1_maxret_40h"].dropna()
    hr80 = found["h1_maxret_80h"].dropna()
    print(f"\n  Forward max return from 1H histogram-positive entry:")
    print(f"    MaxRet@20h: {hr20.mean():+.1f}%   "
          f"MaxRet@40h: {hr40.mean():+.1f}%   "
          f"MaxRet@80h: {hr80.mean():+.1f}%")

    # Per-symbol breakdown
    print(f"\n  Per-symbol:")
    for sym in syms_with_data:
        sym_df = df[df["symbol"] == sym]
        if sym_df.empty:
            continue
        sym_found = sym_df[~sym_df["no_1h_signal"]]
        n_a = len(sym_df)
        n_f = len(sym_found)
        if n_f > 0:
            avg_imp = sym_found["entry_improvement_pct"].mean()
            imp_str = f"entry_improv={avg_imp:+.1f}%"
        else:
            imp_str = "entry_improv=N/A"
        print(f"    {sym:<28s}  A_windows={n_a:3d}  1h_found={n_f:3d}  {imp_str}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("Context A — 1H Entry Timing Study")
    print("===================================")

    for pool_name, symbols in POOLS.items():
        all_records: list[dict] = []
        syms_with_data: list[str] = []

        for sym in symbols:
            records = study_symbol(sym)
            if records is None:
                continue
            if records:
                syms_with_data.append(sym)
            all_records.extend(records)

        if not all_records:
            print(f"\nPool: {pool_name}  — no data found")
            continue

        print_pool_report(pool_name, syms_with_data, all_records)

    print()


if __name__ == "__main__":
    main()
