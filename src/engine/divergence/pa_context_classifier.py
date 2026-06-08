"""PA context classifier — identifies Blind Spot A and B1 contexts on daily bars.

Bottom side (classify_context):

  Context A — DIF>0 pullback in uptrend:
    The existing MACD divergence detector fires no signal here (no reference heap),
    but the bull trend is intact and price is temporarily below EMA20.

  Context B1 — first pullback in new cycle:
    MACD still negative but histogram recovering from trough. A first leg up (H1)
    formed; price is pulling back but has not violated the trough low.

Top side (classify_context_top, added 2026-06-08):

  Context A_top — DIF<0 rally in downtrend:
    Symmetric mirror of A.  Bear trend intact, price temporarily above EMA20
    on a counter-trend bounce — selling-into-rally opportunity.

  Context B1_top — first pullback in new bear cycle:
    Symmetric mirror of B1.  MACD still positive but histogram declining from
    peak.  A first leg down (L1) formed; price has bounced but stays below the
    peak high — first rally in a fresh bear cycle.

Returns "A", "B1", or None for ``classify_context``; "A_top", "B1_top", or None
for ``classify_context_top``.  Caller is responsible for pre-computing MACD and
EMA series (see engine/features/macd.py).
"""
from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

ContextType = Literal["A", "B1"] | None
ContextTopType = Literal["A_top", "B1_top"] | None

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


# ---------------------------------------------------------------------------
# Top-side (bear) mirrors — added 2026-06-08 to close the h2_top context gap
# in pa_direction_assessment.  Thresholds mirror the bull side; see helper
# docstrings for the asymmetry notes (EMA60 acting as resistance instead of
# support, etc.).
# ---------------------------------------------------------------------------


def _classify_A_top(
    bars: pd.DataFrame,
    i: int,
    macd_df: pd.DataFrame,
    ema20: pd.Series,
    ema60: pd.Series,
) -> bool:
    """Return True if bar i meets Context A_top conditions.

    Symmetric mirror of :func:`_classify_A`:

      * DIF < 0          (bear cycle, mirror of DIF>0)
      * close <= EMA60 * (2 - _A_EMA60_TOLERANCE)   — EMA60 now acts as
        resistance; allow up to 2% above (mirror of the 2% below tolerance)
      * close > EMA20   (counter-trend bounce above the 20-day MA)
      * 3% <= rally_from_low <= 10%   (mirror of the pullback band)
      * no acceleration bar in the last 3 bars
    """
    dif = float(macd_df["dif"].iloc[i])
    close = float(bars["close"].iloc[i])
    e20 = float(ema20.iloc[i])
    e60 = float(ema60.iloc[i])

    if dif >= 0:
        return False
    # EMA60 acts as resistance: reject if close is more than 2% above EMA60.
    # Mirror of the bull side's "reject if more than 2% below EMA60".
    if close > e60 * (2.0 - _A_EMA60_TOLERANCE):
        return False
    if close <= e20:
        return False

    low_start = max(0, i - _A_HIGH_LOOKBACK + 1)
    rolling_low = float(bars["low"].iloc[low_start:i+1].min())
    if rolling_low <= 0:
        return False
    rally = (close - rolling_low) / rolling_low
    if not (_A_PULLBACK_MIN <= rally <= _A_PULLBACK_MAX):
        return False

    if _has_acceleration(bars, i):
        return False

    return True


def _classify_B1_top(
    bars: pd.DataFrame,
    i: int,
    macd_df: pd.DataFrame,
    ema20: pd.Series,
    ema60: pd.Series,
) -> bool:
    """Return True if bar i meets Context B1_top conditions.

    Symmetric mirror of :func:`_classify_B1`:

      * DIF > 0           (bullish cycle, exhausting — mirror of DIF<0)
      * DIF slope down    (current DIF < DIF[-N], mirror of "DIF higher
        than N bars ago")
      * histogram peak > 0 within the last 30 bars
      * histogram has declined > 50% from peak (toward zero)
      * leg L1 formed at least 5% below the peak high
      * close has bounced at least 2% above L1 (not yet retesting L1)
      * close stays below peak_high (the bounce hasn't broken back above
        the prior peak)
      * no acceleration bar in the last 3 bars
    """
    dif = float(macd_df["dif"].iloc[i])
    hist = macd_df["hist"]
    close = float(bars["close"].iloc[i])

    if dif <= 0:
        return False

    slope_start = i - _B1_DIF_SLOPE_BARS
    if slope_start < 0:
        return False
    if float(macd_df["dif"].iloc[slope_start]) <= dif:
        return False  # DIF is not falling

    peak_window_start = max(0, i - _B1_HIST_TROUGH_WINDOW)
    hist_window = hist.iloc[peak_window_start:i+1]
    hist_peak = float(hist_window.max())
    if hist_peak <= 0:
        return False  # no positive peak found
    hist_current = float(hist.iloc[i])
    # Mirror of "recovered > 50% toward zero from a negative trough":
    # decayed > 50% toward zero from a positive peak.  Reject if the
    # histogram is still more than 50% of its peak value.
    if hist_current > hist_peak * _B1_HIST_RECOVERY:
        return False

    # Locate the bar where the histogram peak occurred.  Using the MACD
    # peak as the anchor keeps peak_high and L1 consistent with the MACD
    # structure (same logic as B1 — avoids window-mismatch where the
    # price max comes from a different bar than the MACD peak).
    peak_bar_offset = int(hist_window.values.argmax())
    peak_bar_idx = peak_window_start + peak_bar_offset
    peak_high = float(bars["high"].iloc[peak_bar_idx])
    if peak_high <= 0:
        return False

    if peak_bar_idx >= i:
        return False  # peak is current bar — no leg has formed yet
    l1 = float(bars["low"].iloc[peak_bar_idx + 1:i + 1].min())
    if l1 >= peak_high * (1 - _B1_LEG_MIN_PCT):
        return False  # no meaningful first leg down (< 5% below peak)

    # Mirror of "close < H1 * (1 - 0.02)": close > L1 * (1 + 0.02).
    if close <= l1 * (1 + _B1_PULLBACK_MIN):
        return False  # not yet bouncing 2% above L1

    if close >= peak_high:
        return False  # bounce broke back above peak — no longer first-pullback

    if _has_acceleration(bars, i):
        return False

    return True


def classify_context_top(
    bars: pd.DataFrame,
    i: int,
    macd_df: pd.DataFrame,
    ema20: pd.Series,
    ema60: pd.Series,
) -> ContextTopType:
    """Classify bar i as context "A_top", "B1_top", or None.

    Top-side mirror of :func:`classify_context`.  Same MACD/EMA inputs;
    pattern thresholds mirror the bull side (see helper docstrings for
    the EMA60-as-resistance / EMA60-as-support asymmetry note).

    Args:
        bars:     Daily OHLCV DataFrame (reset index, positional).
        i:        Bar index to classify (must be >= _MIN_BARS_REQUIRED).
        macd_df:  Output of engine.features.macd.macd(bars["close"]).
                  Must have columns: "dif", "dea", "hist".
        ema20:    EMA-20 series aligned to bars index.
        ema60:    EMA-60 series aligned to bars index.

    Returns:
        "A_top" | "B1_top" | None
    """
    if i < _MIN_BARS_REQUIRED:
        return None

    if _classify_A_top(bars, i, macd_df, ema20, ema60):
        return "A_top"
    if _classify_B1_top(bars, i, macd_df, ema20, ema60):
        return "B1_top"
    return None
