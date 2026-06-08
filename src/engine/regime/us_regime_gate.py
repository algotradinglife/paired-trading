"""US regime gate — SPY-based risk_off detector.

Used by score_today to suppress US H2-family lanes (pa_us_60min, context_a US)
during bear/high-vol regimes. Backtest-calibrated 2026-06-09 on full_stack
5.5y replay (954 trades): without gate, 2022 H2-family was -21.4R drag; with
gate, 2022 H2-family kept only 4 trades (out of 71) at +0.50R.

Gate condition (risk_off = True):
  SPY close < SPY 200-day SMA
  OR 20-day realized vol (annualized) > 25%

The realized-vol threshold of 0.25 (25% annualized) is a proxy for VIX > 25;
the two are 1:1 monotonic in practice. SPY 200dma below catches sustained
bear markets; realized-vol catches sharp single-week panics that 200dma
misses (e.g. Aug 2024 carry unwind).

Validation on full_stack 5.5y per year:
  2021: risk_off 0.0% of days   — bull
  2022: risk_off 86.5%           — sustained bear (correct flagging)
  2023: risk_off 10.4%           — early-year recovery
  2024: risk_off 0.0%            — bull
  2025: risk_off 16.8%           — mixed (mid-year drawdowns)
  2026 YTD: risk_off 13.0%       — current

BASELINE_REF: baselines/us_regime_gate.json (TODO — write after live deployment)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Calibrated thresholds — do NOT change without re-running counterfactual.
_SMA_PERIOD = 200
_VOL_PERIOD = 20
_VOL_THRESHOLD = 0.25  # 25% annualized realized vol


def compute_regime_signal(spy_bars: pd.DataFrame) -> pd.DataFrame:
    """Annotate SPY daily bars with regime columns.

    Args:
        spy_bars: DataFrame with 'timestamp' (UTC) and 'close' columns,
                  sorted ascending. Must have at least _SMA_PERIOD bars.

    Returns:
        Copy of input with added columns:
          sma200      — 200-day rolling close mean (NaN for first 200 bars)
          ret         — daily pct change
          vol20_ann   — 20-day realized vol annualized (sqrt(252))
          below_sma200 — bool
          high_vol    — bool (vol20_ann > 0.25)
          risk_off    — below_sma200 | high_vol
    """
    df = spy_bars[["timestamp", "close"]].copy()
    df["sma200"] = df["close"].rolling(_SMA_PERIOD).mean()
    df["ret"] = df["close"].pct_change()
    df["vol20_ann"] = df["ret"].rolling(_VOL_PERIOD).std() * np.sqrt(252)
    df["below_sma200"] = df["close"] < df["sma200"]
    df["high_vol"] = df["vol20_ann"] > _VOL_THRESHOLD
    df["risk_off"] = df["below_sma200"] | df["high_vol"]
    return df


def is_risk_off(spy_bars_with_signal: pd.DataFrame, as_of_date) -> bool:
    """Return risk_off state at the bar matching as_of_date or the most
    recent preceding bar.

    Args:
        spy_bars_with_signal: output of compute_regime_signal()
        as_of_date: pd.Timestamp or date

    Returns:
        False if no SPY bar available at/before as_of_date.
        True only if confirmed risk_off; bias to False on missing data
        (don't suppress trades when we can't measure).
    """
    target = pd.Timestamp(as_of_date)
    # Align tz with the signal column to avoid tz-naive vs tz-aware comparison.
    bars_tz = spy_bars_with_signal["timestamp"].dt.tz
    if bars_tz is not None and target.tz is None:
        target = target.tz_localize(bars_tz)
    elif bars_tz is None and target.tz is not None:
        target = target.tz_convert(None)
    mask = spy_bars_with_signal["timestamp"] <= target
    if not mask.any():
        return False
    last_row = spy_bars_with_signal.loc[mask].iloc[-1]
    val = last_row.get("risk_off")
    if pd.isna(val):
        return False
    return bool(val)
