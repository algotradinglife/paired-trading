"""5 base observation flows that feed all form detection.

Reference: doc/04-feature-extraction.md §2

The 5 flows are computed per timeframe, independently. They are the only
inputs the form-detection layer reads. Keeping the flow surface narrow lets
us reason about all form definitions as combinations of 5 well-defined
quantities.

Flow design (each operates on per-bar pandas Series, returns Series of same
length, indexed identically):

  1. dif_proximity_zero       — how close DIF is to zero, normalized to [0, 1]
  2. hist_amplitude_ratio     — current |Hist| / rolling-or-segment max |Hist|
  3. hist_dif_sign_alignment  — sign(Hist) · sign(DIF) ∈ {-1, 0, +1}
  4. streak primitives        — consecutive bars a condition has held
  5. price_momentum           — rolling relative price change

`state_persistence` (the 4th conceptual flow) is form-specific (different
forms care about different states). We expose a generic `streak()` primitive
plus a few common conditions; the form layer composes form-specific streaks
from these.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Defaults per doc/12-thresholds-and-params.md §2
DEFAULT_ROLLING_WINDOW = 200
DEFAULT_PRICE_MOMENTUM_LOOKBACK = 5
DEFAULT_NEAR_ZERO_HIST_RATIO = 0.05  # |Hist| < 5% of rolling max counts as "near zero"
DEFAULT_NEAR_ZERO_DIF_PROXIMITY = 0.85  # dif_proximity_zero > 0.85 counts as "near zero"


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Element-wise division that returns NaN where denominator is zero/NaN.

    Used to avoid 0/0 = NaN propagation in early warmup bars (where rolling
    max may legitimately be zero).
    """
    denom = denominator.where(denominator > 0, np.nan)
    return numerator / denom


# ---------------------------------------------------------------------------
# Flow 1: dif_proximity_zero
# ---------------------------------------------------------------------------

def dif_proximity_zero(
    dif: pd.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
) -> pd.Series:
    """Normalized closeness of DIF to zero.

    Definition (doc/04 §2.1):
        proximity = 1 - |DIF| / R
    where R is a normalization scale (rolling max |DIF| over `window`).

    Output:
        1.0 = DIF at zero (归零轴 candidate)
        0.0 = DIF at its rolling max distance from zero

    NaN during initial warmup (when rolling max is still zero or undefined).

    NOTE: Once segment state machines are built (Layer C), R should switch to
    current-segment max |DIF| to be more faithful to Song's "单位调整周期"
    framing. The rolling-window fallback is what we use until segments exist.
    """
    abs_dif = dif.abs()
    rolling_max = abs_dif.rolling(window, min_periods=1).max()
    ratio = _safe_divide(abs_dif, rolling_max).clip(upper=1.0)
    return (1.0 - ratio).rename("dif_proximity_zero")


# ---------------------------------------------------------------------------
# Flow 2: hist_amplitude_ratio
# ---------------------------------------------------------------------------

def hist_amplitude_ratio(
    hist: pd.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
) -> pd.Series:
    """Current |Hist| relative to its rolling max.

    Definition (doc/04 §2.2):
        ratio = |Hist_t| / max |Hist| over window
    Output range [0, 1+); values near 0 indicate隐形 (hidden) candidate.

    NaN during early warmup; clipped at 1.0+ above for new highs.
    """
    abs_hist = hist.abs()
    rolling_max = abs_hist.rolling(window, min_periods=1).max()
    return _safe_divide(abs_hist, rolling_max).rename("hist_amplitude_ratio")


# ---------------------------------------------------------------------------
# Flow 3: hist_dif_sign_alignment
# ---------------------------------------------------------------------------

def hist_dif_sign_alignment(hist: pd.Series, dif: pd.Series) -> pd.Series:
    """Sign alignment between Hist and DIF.

    Definition (doc/04 §2.3):
        alignment = sign(Hist) · sign(DIF)
    Output ∈ {-1, 0, +1}
        +1: same sign (e.g. multi-方 market, Hist红 + DIF >0) → 零轴黏合 hint
        -1: opposite signs                                 → 零轴倒挂 hint
         0: at least one side is zero
    """
    # np.sign(NaN) returns NaN, and direct .astype(int) on a NaN raises
    # IntCastingNaNError. Treat NaN bars (typically early warmup region of
    # MACD/EMA series) as sign=0 so the product is also 0.
    hist_sign = np.sign(hist.fillna(0.0)).astype(int)
    dif_sign = np.sign(dif.fillna(0.0)).astype(int)
    aligned = hist_sign * dif_sign
    return pd.Series(aligned, index=hist.index, name="hist_dif_sign_alignment")


# ---------------------------------------------------------------------------
# Flow 4: streak primitives (state_persistence building blocks)
# ---------------------------------------------------------------------------

def consecutive_true_streak(condition: pd.Series) -> pd.Series:
    """Count consecutive True bars, resetting on False.

    Example: condition = [F, T, T, F, T, T, T]
             streak    = [0, 1, 2, 0, 1, 2, 3]

    This is the building block for all form-specific persistence counters.
    Form-detection layer composes form-specific conditions (e.g. "hist decaying
    + dif still far from zero" for HPV) and applies this primitive.
    """
    bool_series = condition.fillna(False).astype(bool)
    # Reset counter on each False; cumcount within each True-run
    group_id = (~bool_series).cumsum()
    streak = bool_series.groupby(group_id).cumsum()
    return streak.rename("streak")


def hist_decaying_from_peak(hist: pd.Series) -> pd.Series:
    """Boolean: is |Hist_t| less than the running peak |Hist| of the current
    same-sign run?

    Used by `high_position_void` persistence.
    """
    sign = np.sign(hist)
    # New run starts each time sign flips
    run_id = (sign != sign.shift(1)).cumsum()
    abs_hist = hist.abs()
    running_peak = abs_hist.groupby(run_id).cummax()
    is_decaying = abs_hist < running_peak
    return is_decaying.rename("hist_decaying_from_peak")


def hist_near_zero(
    hist: pd.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    threshold: float = DEFAULT_NEAR_ZERO_HIST_RATIO,
) -> pd.Series:
    """Boolean: is |Hist_t| within `threshold` × rolling max |Hist|?

    Used by `hidden` form persistence.
    """
    ratio = hist_amplitude_ratio(hist, window=window)
    return (ratio < threshold).rename("hist_near_zero")


def dif_near_zero(
    dif: pd.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    threshold: float = DEFAULT_NEAR_ZERO_DIF_PROXIMITY,
) -> pd.Series:
    """Boolean: is DIF "near zero" (proximity_zero above threshold)?

    Used by `zero_stick` form persistence.
    """
    proximity = dif_proximity_zero(dif, window=window)
    return (proximity > threshold).rename("dif_near_zero")


# ---------------------------------------------------------------------------
# Flow 5: price_momentum
# ---------------------------------------------------------------------------

def price_momentum(
    close: pd.Series,
    *,
    lookback: int = DEFAULT_PRICE_MOMENTUM_LOOKBACK,
) -> pd.Series:
    """Relative price change over the past `lookback` bars.

    Definition (doc/04 §2.5):
        momentum = (close_t - close_{t-k}) / close_{t-k}
    Positive = up move, negative = down move. Used by `hidden` form (price
    extending while Hist ≈ 0).
    """
    prev_close = close.shift(lookback)
    momentum = (close - prev_close) / prev_close
    return momentum.rename("price_momentum")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def compute_feature_streams(
    close: pd.Series,
    dif: pd.Series,
    dea: pd.Series,  # noqa: ARG001  -- not yet used; reserved for sub-streams
    hist: pd.Series,
    *,
    rolling_window: int = DEFAULT_ROLLING_WINDOW,
    price_momentum_lookback: int = DEFAULT_PRICE_MOMENTUM_LOOKBACK,
) -> pd.DataFrame:
    """Compute all base feature streams from MACD outputs.

    Returns a DataFrame indexed identically to inputs, with columns:
        dif_proximity_zero
        hist_amplitude_ratio
        hist_dif_sign_alignment
        price_momentum
        hist_decaying_from_peak     (bool, primitive)
        hist_near_zero              (bool, primitive)
        dif_near_zero               (bool, primitive)

    Form-specific persistence counters are NOT included here — the
    form-detection layer composes them from the boolean primitives via
    `consecutive_true_streak()`.
    """
    return pd.DataFrame(
        {
            "dif_proximity_zero": dif_proximity_zero(dif, window=rolling_window),
            "hist_amplitude_ratio": hist_amplitude_ratio(hist, window=rolling_window),
            "hist_dif_sign_alignment": hist_dif_sign_alignment(hist, dif),
            "price_momentum": price_momentum(close, lookback=price_momentum_lookback),
            "hist_decaying_from_peak": hist_decaying_from_peak(hist),
            "hist_near_zero": hist_near_zero(hist, window=rolling_window),
            "dif_near_zero": dif_near_zero(dif, window=rolling_window),
        }
    )
