"""PA context classifier — identifies Blind Spot A and B1 contexts on daily bars.

Context A — DIF>0 pullback in uptrend:
  The existing MACD divergence detector fires no signal here (no reference heap),
  but the bull trend is intact and price is temporarily below EMA20.

Context B1 — first pullback in new cycle:
  MACD still negative but histogram recovering from trough. A first leg up (H1)
  formed; price is pulling back but has not violated the trough low.

Returns "A", "B1", or None (no active context) for a single bar index.
Caller is responsible for pre-computing MACD and EMA series (see engine/features/macd.py).
"""
from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

ContextType = Literal["A", "B1"] | None

# Guards shared by both contexts
_MIN_BARS_REQUIRED = 65   # need at least 65 bars for safe EMA60 warm-up + B1 trough lookback
_ACCEL_BODY_MULT = 2.0    # body > N× avg = acceleration bar
_ACCEL_LOOKBACK = 3       # bars to check for acceleration
_AVG_BODY_WINDOW = 20     # window for avg body computation

# Context A thresholds
_A_EMA60_TOLERANCE = 0.98    # allow up to 2% below EMA60
_A_PULLBACK_MIN = 0.03       # minimum 3% below 20-bar high
_A_PULLBACK_MAX = 0.10       # maximum 10% below 20-bar high (deeper = structural risk)
_A_HIGH_LOOKBACK = 20

# Context B1 thresholds
_B1_DIF_SLOPE_BARS = 3       # DIF must be higher than N bars ago
_B1_HIST_TROUGH_WINDOW = 30  # bars to look back for histogram trough
_B1_HIST_RECOVERY = 0.50     # histogram must recover > 50% from trough
_B1_LEG_MIN_PCT = 0.05       # H1 must be ≥ 5% above trough low
_B1_PULLBACK_MIN = 0.02      # currently at least 2% below H1


def _has_acceleration(bars: pd.DataFrame, i: int) -> bool:
    """Return True if any of the last _ACCEL_LOOKBACK bars is an acceleration bar."""
    start = max(0, i - _ACCEL_LOOKBACK + 1)
    bodies = (bars["close"].iloc[start:i+1] - bars["open"].iloc[start:i+1]).abs()
    avg_body_start = max(0, i - _AVG_BODY_WINDOW + 1)
    avg_body = (bars["close"].iloc[avg_body_start:i+1] - bars["open"].iloc[avg_body_start:i+1]).abs().mean()
    if avg_body == 0:
        return False
    return bool((bodies > _ACCEL_BODY_MULT * avg_body).any())


def _classify_A(
    bars: pd.DataFrame,
    i: int,
    macd_df: pd.DataFrame,
    ema20: pd.Series,
    ema60: pd.Series,
) -> bool:
    """Return True if bar i meets Context A conditions."""
    dif = float(macd_df["dif"].iloc[i])
    close = float(bars["close"].iloc[i])
    e20 = float(ema20.iloc[i])
    e60 = float(ema60.iloc[i])

    if dif <= 0:
        return False
    if close < e60 * _A_EMA60_TOLERANCE:
        return False
    if close >= e20:
        return False

    high_start = max(0, i - _A_HIGH_LOOKBACK + 1)
    rolling_high = float(bars["high"].iloc[high_start:i+1].max())
    if rolling_high <= 0:
        return False
    pullback = (rolling_high - close) / rolling_high
    if not (_A_PULLBACK_MIN <= pullback <= _A_PULLBACK_MAX):
        return False

    if _has_acceleration(bars, i):
        return False

    return True


def _classify_B1(
    bars: pd.DataFrame,
    i: int,
    macd_df: pd.DataFrame,
    ema20: pd.Series,
    ema60: pd.Series,
) -> bool:
    """Return True if bar i meets Context B1 conditions."""
    dif = float(macd_df["dif"].iloc[i])
    hist = macd_df["hist"]
    close = float(bars["close"].iloc[i])

    if dif >= 0:
        return False

    slope_start = i - _B1_DIF_SLOPE_BARS
    if slope_start < 0:
        return False
    if float(macd_df["dif"].iloc[slope_start]) >= dif:
        return False

    trough_window_start = max(0, i - _B1_HIST_TROUGH_WINDOW)
    hist_window = hist.iloc[trough_window_start:i+1]
    hist_trough = float(hist_window.min())
    if hist_trough >= 0:
        return False  # no negative trough found
    hist_current = float(hist.iloc[i])
    if hist_current < hist_trough * _B1_HIST_RECOVERY:
        return False  # less than 50% recovered (towards zero; hist_trough < 0)

    # Locate the bar where the histogram trough occurred (within the 30-bar window).
    # Using the MACD trough bar as the anchor ensures trough_low and H1 are
    # consistent with the MACD structure — avoids a window-mismatch bug where
    # the price minimum could come from a different bar than the MACD trough.
    trough_bar_offset = int(hist_window.values.argmin())
    trough_bar_idx = trough_window_start + trough_bar_offset
    trough_low = float(bars["low"].iloc[trough_bar_idx])

    if trough_bar_idx >= i:
        return False  # trough is current bar — no leg has formed yet
    h1 = float(bars["high"].iloc[trough_bar_idx + 1:i + 1].max())
    if h1 <= trough_low * (1 + _B1_LEG_MIN_PCT):
        return False  # no meaningful first leg formed (< 5% above trough)

    if close >= h1 * (1 - _B1_PULLBACK_MIN):
        return False  # not yet pulling back 2% from H1

    if close <= trough_low:
        return False

    if _has_acceleration(bars, i):
        return False

    return True


def classify_context(
    bars: pd.DataFrame,
    i: int,
    macd_df: pd.DataFrame,
    ema20: pd.Series,
    ema60: pd.Series,
) -> ContextType:
    """Classify bar i as context "A", "B1", or None.

    Args:
        bars:     Daily OHLCV DataFrame (reset index, positional).
        i:        Bar index to classify (must be >= _MIN_BARS_REQUIRED).
        macd_df:  Output of engine.features.macd.macd(bars["close"]).
                  Must have columns: "dif", "dea", "hist".
        ema20:    EMA-20 series aligned to bars index.
        ema60:    EMA-60 series aligned to bars index.

    Returns:
        "A" | "B1" | None
    """
    if i < _MIN_BARS_REQUIRED:
        return None

    if _classify_A(bars, i, macd_df, ema20, ema60):
        return "A"
    if _classify_B1(bars, i, macd_df, ema20, ema60):
        return "B1"
    return None
