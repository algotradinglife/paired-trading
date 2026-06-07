"""Multi-bar swing context features for price action analysis.

Computes swing highs/lows, trend structure (HH-HL / LH-LL), directional
leg count, and market regime — all using only confirmed past information
(no lookahead) for each bar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def detect_swing_points(
    bars: pd.DataFrame,
    n: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """Return indices of confirmed swing highs and swing lows.

    Bar i is a swing high if high[i] is STRICTLY greater than all bars
    within [i-n, i-1] and [i+1, i+n].  Same logic inverted for swing lows.

    Args:
        bars: DataFrame with 'high' and 'low' columns.
        n:    Number of bars required on each side. Only bars in [n, len-1-n]
              are eligible candidates.

    Returns:
        (swing_high_idx, swing_low_idx): sorted int64 arrays of bar positions.
    """
    highs = bars["high"].values.astype(float)
    lows = bars["low"].values.astype(float)
    N = len(bars)

    sh_idx: list[int] = []
    sl_idx: list[int] = []

    for i in range(n, N - n):
        h = highs[i]
        if all(h > highs[i - k] for k in range(1, n + 1)) and \
           all(h > highs[i + k] for k in range(1, n + 1)):
            sh_idx.append(i)

        lo = lows[i]
        if all(lo < lows[i - k] for k in range(1, n + 1)) and \
           all(lo < lows[i + k] for k in range(1, n + 1)):
            sl_idx.append(i)

    return np.array(sh_idx, dtype=np.int64), np.array(sl_idx, dtype=np.int64)


def classify_trend_structure(
    bars: pd.DataFrame,
    as_of: int,
    sh_idx: np.ndarray,
    sl_idx: np.ndarray,
    n: int = 3,
) -> str:
    """Classify trend structure as of bar `as_of` using confirmed swings only.

    Uses confirmed swing points (index <= as_of - n) to avoid lookahead.
    Compares last 2 swing highs and last 2 swing lows:
      HH + HL → "uptrend"
      LH + LL → "downtrend"
      mixed   → "ranging"
    Returns "ranging" when fewer than 2 confirmed swings of either type.
    """
    confirmed_sh = sh_idx[sh_idx <= as_of - n]
    confirmed_sl = sl_idx[sl_idx <= as_of - n]

    if len(confirmed_sh) < 2 or len(confirmed_sl) < 2:
        return "ranging"

    highs = bars["high"].values.astype(float)
    lows = bars["low"].values.astype(float)

    hh = highs[confirmed_sh[-1]] > highs[confirmed_sh[-2]]
    hl = lows[confirmed_sl[-1]] > lows[confirmed_sl[-2]]

    if hh and hl:
        return "uptrend"
    if not hh and not hl:
        return "downtrend"
    return "ranging"


def count_legs_down(
    as_of: int,
    sh_idx: np.ndarray,
    sl_idx: np.ndarray,
    n: int = 3,
    from_dominant: bool = False,
    bars: pd.DataFrame | None = None,
) -> int:
    """Count confirmed downward legs ending at or before `as_of`.

    A downward leg = one swing high → swing low segment.

    Args:
        as_of: current bar index.
        sh_idx, sl_idx: detected swing indices (full array).
        n: confirmation lag; swings at index > as_of - n are excluded.
        from_dominant: if True, anchor at the HIGHEST swing high in the
            confirmed window (full-move leg count, requires `bars`).
            If False, anchor at the most recent confirmed swing high.
        bars: required when from_dominant=True.

    Returns:
        Number of confirmed swing lows after the anchor high. 0 if no anchor.
    """
    confirmed_sh = sh_idx[sh_idx <= as_of - n]
    confirmed_sl = sl_idx[sl_idx <= as_of - n]

    if len(confirmed_sh) == 0:
        return 0

    if from_dominant and bars is not None:
        highs = bars["high"].values.astype(float)
        anchor = confirmed_sh[int(np.argmax(highs[confirmed_sh]))]
    else:
        anchor = confirmed_sh[-1]

    return int(np.sum(confirmed_sl > anchor))


def market_regime_label(
    bars: pd.DataFrame,
    ema_period: int = 20,
    slope_trend_thresh: float = 0.15,
    slope_range_thresh: float = 0.04,
    overlap_range_thresh: float = 0.45,
) -> pd.Series:
    """Classify market regime per bar as 'trending', 'ranging', or 'channel'.

    trending: EMA slope steep (|slope_norm| > slope_trend_thresh)
    ranging:  EMA flat AND bars frequently cross EMA
    channel:  everything else
    """
    close = bars["close"].astype(float)
    hi = bars["high"].astype(float)
    lo = bars["low"].astype(float)

    ema = close.ewm(span=ema_period, adjust=False).mean()

    prev_c = close.shift(1)
    tr = pd.concat([hi - lo, (hi - prev_c).abs(), (lo - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=ema_period, adjust=False).mean().clip(lower=1e-9)

    ema_change = ema - ema.shift(ema_period)
    slope_norm = (ema_change / (ema_period * atr)).fillna(0.0)

    above_ema = (close > ema).astype(float)
    crosses_ema = (above_ema != above_ema.shift(1)).astype(float)
    cross_rate = crosses_ema.rolling(ema_period, min_periods=5).mean().fillna(0.0)

    result = pd.Series("channel", index=bars.index, dtype=object)
    result[slope_norm.abs() > slope_trend_thresh] = "trending"
    ranging_mask = (slope_norm.abs() <= slope_range_thresh) & (cross_rate >= overlap_range_thresh)
    result[ranging_mask] = "ranging"

    return result.rename("market_regime")


def compute_swing_context(
    bars: pd.DataFrame,
    swing_n: int = 3,
    ema_period: int = 20,
) -> pd.DataFrame:
    """Return per-bar swing context features, aligned to bars.index.

    All features use only confirmed past information at each bar (no lookahead).
    Confirmation lag = swing_n bars.

    Columns:
        trend_structure      str  "uptrend" / "downtrend" / "ranging"
        leg_count_down       int  swing lows after last confirmed swing high
        market_regime        str  "trending" / "ranging" / "channel"
        bars_since_swing_low  int  bars elapsed since last confirmed swing low
        bars_since_swing_high int  bars elapsed since last confirmed swing high
    """
    sh_all, sl_all = detect_swing_points(bars, n=swing_n)
    highs = bars["high"].values.astype(float)
    lows = bars["low"].values.astype(float)
    N = len(bars)
    MAX_DIST = N

    trend_struct = ["ranging"] * N
    leg_count = [0] * N
    bssl = [MAX_DIST] * N
    bssh = [MAX_DIST] * N

    for i in range(swing_n * 2, N):
        confirmed_sh = sh_all[sh_all <= i - swing_n]
        confirmed_sl = sl_all[sl_all <= i - swing_n]

        if len(confirmed_sh) >= 2 and len(confirmed_sl) >= 2:
            hh = highs[confirmed_sh[-1]] > highs[confirmed_sh[-2]]
            hl = lows[confirmed_sl[-1]] > lows[confirmed_sl[-2]]
            if hh and hl:
                trend_struct[i] = "uptrend"
            elif not hh and not hl:
                trend_struct[i] = "downtrend"

        if len(confirmed_sh) > 0:
            anchor = confirmed_sh[-1]
            leg_count[i] = int(np.sum(confirmed_sl > anchor))

        if len(confirmed_sl) > 0:
            bssl[i] = i - int(confirmed_sl[-1])
        if len(confirmed_sh) > 0:
            bssh[i] = i - int(confirmed_sh[-1])

    regime = market_regime_label(bars, ema_period=ema_period)

    return pd.DataFrame({
        "trend_structure":       trend_struct,
        "leg_count_down":        np.array(leg_count, dtype=np.int64),
        "market_regime":         regime.values,
        "bars_since_swing_low":  np.array(bssl, dtype=np.int64),
        "bars_since_swing_high": np.array(bssh, dtype=np.int64),
    }, index=bars.index)
