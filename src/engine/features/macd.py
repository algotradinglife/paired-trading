"""Standard MACD calculation.

Implements the classic Appel/Aspray MACD with EMA-based DIF, DEA, and Histogram.
Plus auxiliary EMA24 / EMA52 chart-overlay lines used in the K-line momentum
theory (Song Jianyi) for归零轴 (near-zero-axis) position coordinates.

Reference: doc/04-feature-extraction.md §1
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Standard parameters per doc/12-thresholds-and-params.md §1
DEFAULT_FAST = 12
DEFAULT_SLOW = 26
DEFAULT_SIGNAL = 9

# Histogram scaling factor.
#
# Aspray's original 1986 spec used 2 (so that Hist amplitude reads like a
# rebased difference). However TradingView, MetaTrader and most modern charting
# platforms render Hist = DIF - DEA without the x2 scaling. We default to 1.0
# to keep engine output directly comparable to platform visualizations.
HIST_SCALE = 1.0


def ema(series: pd.Series, period: int, *, adjust: bool = False) -> pd.Series:
    """Exponential moving average using the standard recursion.

    alpha = 2 / (N + 1).

    By default uses adjust=False which is the recursive form most platforms use:
        EMA[t] = alpha * x[t] + (1 - alpha) * EMA[t-1]
        EMA[0] = x[0]

    This matches TradingView's `ta.ema()` behavior.
    """
    if period <= 0:
        raise ValueError(f"period must be positive, got {period}")
    if series.empty:
        return series.copy()
    return series.ewm(span=period, adjust=adjust, min_periods=1).mean()


def macd(
    close: pd.Series,
    *,
    fast: int = DEFAULT_FAST,
    slow: int = DEFAULT_SLOW,
    signal: int = DEFAULT_SIGNAL,
    hist_scale: float = HIST_SCALE,
) -> pd.DataFrame:
    """Compute MACD triple (DIF, DEA, Histogram) from close prices.

    Parameters
    ----------
    close : pd.Series
        Closing prices, indexed by timestamp.
    fast, slow, signal : int
        Standard MACD periods (12, 26, 9 by default).
    hist_scale : float
        Histogram scaling factor (2.0 by default per Aspray).

    Returns
    -------
    pd.DataFrame with columns: ema_fast, ema_slow, dif, dea, hist
    Indexed identically to ``close``.
    """
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    dif = ema_fast - ema_slow
    dea = ema(dif, signal)
    hist = hist_scale * (dif - dea)
    return pd.DataFrame(
        {
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "dif": dif,
            "dea": dea,
            "hist": hist,
        }
    )


def overlay_emas(
    close: pd.Series,
    *,
    short: int = 12,
    mid: int = 24,
    long: int = 52,
) -> pd.DataFrame:
    """Chart-overlay EMAs used by Song's near-zero-axis position coordinates.

    EMA52 ≈ price location when current-level DIF returns to zero.
    EMA24 ≈ price location when sub-level DIF returns to zero.

    Reference: doc/04-feature-extraction.md §1.2
    """
    return pd.DataFrame(
        {
            f"ema{short}": ema(close, short),
            f"ema{mid}": ema(close, mid),
            f"ema{long}": ema(close, long),
        }
    )
