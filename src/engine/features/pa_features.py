"""Price action feature extraction — Brooks-derived features for daily OHLCV bars.

Computes bar-level PA features that can be used as context_features in
DivergenceSignal or as standalone signal conditions for the PA capitulation
bottom detector.

All features are computable from OHLCV only (no external data required).
Designed for DAILY bars; parameters are tuned for daily CN/US futures.

Key features:
  bar_quality     — bull reversal bar strength (0-1); high = large body,
                    close near top, significant lower wick
  h_leg_count     — number of recovery attempts (H1/H2 equivalent) in
                    the recent lookback window; 2 = classic H2
  consec_bear     — consecutive bear bars immediately before current
  climax_score    — how extreme the current bar is vs recent range (0-1);
                    a large bear bar near bottom of recent range = selling climax
  compression     — body shrinking over last 3 bars (True/False); common
                    before expansion reversals
  ema_distance    — close minus EMA20, normalised by ATR; negative = below EMA
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Individual feature functions (all return pd.Series aligned to bars.index)
# ---------------------------------------------------------------------------

def bar_quality_bull(bars: pd.DataFrame) -> pd.Series:
    """Bull reversal bar quality score (0-1).

    Strong bull bar: large body, close in upper portion, significant lower wick.
    Formula: body_ratio * close_position_in_range
    """
    hi = bars["high"]; lo = bars["low"]
    op = bars["open"]; cl = bars["close"]
    total = (hi - lo).clip(lower=1e-9)
    body = (cl - op).abs()
    body_ratio = body / total
    close_pos = (cl - lo) / total   # 0=closed at low, 1=closed at high
    return (body_ratio * close_pos).rename("bar_quality_bull")


def bar_quality_bear(bars: pd.DataFrame) -> pd.Series:
    """Bear reversal bar quality score (0-1). Mirror of bull quality."""
    hi = bars["high"]; lo = bars["low"]
    op = bars["open"]; cl = bars["close"]
    total = (hi - lo).clip(lower=1e-9)
    body = (cl - op).abs()
    body_ratio = body / total
    close_pos_bear = (hi - cl) / total  # 0=closed at high, 1=closed at low
    return (body_ratio * close_pos_bear).rename("bar_quality_bear")


def consecutive_bear_bars(bars: pd.DataFrame) -> pd.Series:
    """Count of consecutive bear bars immediately before current bar.

    A bear bar: close < open.
    Resets to 0 on any bull bar.
    """
    is_bear = (bars["close"] < bars["open"]).astype(int)
    result = []
    count = 0
    for v in is_bear:
        result.append(count)  # bears before this bar
        count = count + 1 if v else 0
    return pd.Series(result, index=bars.index, name="consec_bear_before")


def h_leg_count(bars: pd.DataFrame, lookback: int = 8) -> pd.Series:
    """Number of prior recovery attempts (H1/H2 logic) in lookback window.

    A 'recovery attempt' (H1-style event) at bar j is defined as:
      close[j] > high[j-1]  (bar closes above previous bar's high)

    Counts such events in the window (t-lookback, t-1) at each bar t.
    Value 0 = no prior attempt (first try), 1 = H1 fired before, 2 = H2 situation.
    """
    closes = bars["close"].values
    highs = bars["high"].values
    n = len(bars)
    result = np.zeros(n, dtype=int)
    for i in range(1, n):
        start = max(1, i - lookback)
        count = 0
        for j in range(start, i):
            if closes[j] > highs[j - 1]:
                count += 1
        result[i] = count
    return pd.Series(result, index=bars.index, name="h_leg_count")


def selling_climax_score(bars: pd.DataFrame, window: int = 20) -> pd.Series:
    """Selling climax score (0-1) — how extreme the current bear move is.

    High score: current bar has large body, closed near its low, and the
    body is large relative to recent bars (potential exhaustion candle).

    Formula: bear_body_ratio * body_vs_recent_max * close_at_bottom
    """
    hi = bars["high"]; lo = bars["low"]
    op = bars["open"]; cl = bars["close"]
    total = (hi - lo).clip(lower=1e-9)
    body = (cl - op).abs()
    body_ratio = body / total
    close_pos_bear = (hi - cl) / total  # 1 = closed at low

    # Body relative to recent max body
    body_rolling_max = body.rolling(window, min_periods=3).max().clip(lower=1e-9)
    body_vs_max = body / body_rolling_max

    raw = body_ratio * close_pos_bear * body_vs_max
    return raw.clip(upper=1.0).rename("selling_climax_score")


def body_compression(bars: pd.DataFrame, n: int = 3) -> pd.Series:
    """True if body size has been shrinking over the last n bars.

    Compression = bodies monotonically decreasing over window.
    Typically precedes a directional expansion (potential reversal signal).
    """
    hi = bars["high"]; lo = bars["low"]
    op = bars["open"]; cl = bars["close"]
    body = (cl - op).abs()
    result = [False] * len(bars)
    for i in range(n, len(bars)):
        window_bodies = body.iloc[i - n: i].values
        if all(window_bodies[j] > window_bodies[j + 1] for j in range(len(window_bodies) - 1)):
            result[i] = True
    return pd.Series(result, index=bars.index, name="body_compression")


def ema_distance_norm(bars: pd.DataFrame, period: int = 20, atr_period: int = 14) -> pd.Series:
    """(close - EMA) / ATR — normalised EMA distance.

    Negative = price below EMA (bearish), magnitude shows how far.
    Used to identify tests of EMA and distance from EMA.
    """
    ema = bars["close"].ewm(span=period, adjust=False).mean()
    hi = bars["high"]; lo = bars["low"]
    prev_c = bars["close"].shift(1)
    tr = pd.concat([hi - lo, (hi - prev_c).abs(), (lo - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=atr_period, adjust=False).mean().clip(lower=1e-9)
    return ((bars["close"] - ema) / atr).rename("ema_distance_norm")


# ---------------------------------------------------------------------------
# Composite: compute all PA features at once
# ---------------------------------------------------------------------------

def compute_pa_features(bars: pd.DataFrame, h_lookback: int = 8) -> pd.DataFrame:
    """Return a DataFrame of all PA features aligned to bars.index.

    Columns:
      bar_quality_bull     float [0-1]  bull reversal quality
      bar_quality_bear     float [0-1]  bear reversal quality
      consec_bear_before   int          consecutive bear bars before current
      h_leg_count          int          # recovery attempts in lookback window
      selling_climax_score float [0-1]  selling climax magnitude
      body_compression     bool         bodies shrinking over 3 bars
      ema_distance_norm    float        (close - EMA20) / ATR
    """
    return pd.concat([
        bar_quality_bull(bars),
        bar_quality_bear(bars),
        consecutive_bear_bars(bars),
        h_leg_count(bars, lookback=h_lookback),
        selling_climax_score(bars),
        body_compression(bars),
        ema_distance_norm(bars),
    ], axis=1)
