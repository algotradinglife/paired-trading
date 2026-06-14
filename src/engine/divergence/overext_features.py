"""Bar-geometry features for the bottom-side over-extension / second-entry de-weight.

Mirrors the *exact* validated definitions used in the epic 过度延伸 gate研究
(2026-06-13) so production weights match the backtested numbers:

- ``range_vs_avg``  — scripts/analyze_signalbar_quality.signal_bar_features
  (signal bar range / mean range over the prior LEN_WIN bars, strictly no-lookahead).
- ``test_ordinal``  — scripts/analyze_second_entry.classify_test_ordinal
  (anchored at the signal bar's own low; counts prior confirmed same-level swing
  lows with an intervening ATR-relative bounce; no-lookahead).
- ATR / swing detection use the same span-EWM ATR (period 14) and
  engine.features.swing_context.detect_swing_points (n=3) as the research pipeline.

The validated analysis scripts keep their own copies (changing them would invalidate
prior reviewer sign-off); this module is the production-side mirror. The two are
covered by tests/test_overext_features.py asserting numeric agreement.

Entry point for consumers: ``signal_deweight_factor`` — fail-open (returns 1.0) for
non-applicable lanes and for signals too early in history to assess. Compute the
per-symbol context (ATR + swing lows) once with ``prepare_context`` and pass it in.
"""
from __future__ import annotations

from typing import NamedTuple

import numpy as np
import pandas as pd

from engine.features.swing_context import detect_swing_points

from .overext_deweight import deweight_factor

# Constants — pinned to the validated research pipeline.
ATR_PERIOD = 14       # span-EWM ATR (scripts/backtest_rr_pool.compute_atr)
LEN_WIN = 20          # range_vs_avg baseline: mean of prior 20 bars (no-lookahead)
SWING_N = 3           # detect_swing_points confirmation bars per side
TOL_ATR = 1.0         # same-level tolerance: |prior low - ref low| <= 1.0×ATR
BOUNCE_ATR = 1.5      # required intervening rally between two lows (true two-leg)
LOOKBACK_BARS = 60    # how far before the signal to look for an earlier same-level low


class DeweightContext(NamedTuple):
    atr: pd.Series
    swing_low_idx: np.ndarray


def _atr(bars: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    """Span-EWM ATR — identical to scripts/backtest_rr_pool.compute_atr."""
    high, low, close = bars["high"], bars["low"], bars["close"]
    prev_c = close.shift(1)
    tr = pd.concat([high - low,
                    (high - prev_c).abs(),
                    (low - prev_c).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def prepare_context(bars: pd.DataFrame) -> DeweightContext:
    """Per-symbol ATR + confirmed swing lows; compute once, reuse per signal."""
    _, sl_idx = detect_swing_points(bars, n=SWING_N)
    return DeweightContext(atr=_atr(bars), swing_low_idx=sl_idx)


def range_vs_avg(bars: pd.DataFrame, idx: int, len_win: int = LEN_WIN) -> float | None:
    """Signal bar range / mean range of the prior ``len_win`` bars (no-lookahead).

    Returns None when too early (idx < len_win) or the signal bar is degenerate.
    """
    if idx < len_win:
        return None
    high = float(bars["high"].iloc[idx])
    low = float(bars["low"].iloc[idx])
    rng = high - low
    if not np.isfinite(rng) or rng <= 0:
        return None
    highs = bars["high"].values
    lows = bars["low"].values
    prior = highs[idx - len_win:idx] - lows[idx - len_win:idx]
    avg = float(np.mean(prior)) if prior.size else float("nan")
    if not np.isfinite(avg) or avg <= 0:
        return None
    result = rng / avg
    # Non-finite (e.g. nan from missing OHLC) → caller must fail open, not penalize.
    return result if np.isfinite(result) else None


def test_ordinal(
    bars: pd.DataFrame,
    signal_idx: int,
    ctx: DeweightContext,
    *,
    swing_n: int = SWING_N,
    tol_atr: float = TOL_ATR,
    bounce_atr: float = BOUNCE_ATR,
    lookback: int = LOOKBACK_BARS,
) -> int | None:
    """Test ordinal of the signal bar (1 = first test, >=2 = retest). No-lookahead.

    Anchored at the signal bar's own low; counts prior *confirmed* same-level swing
    lows (within tol_atr×ATR) that have a >= bounce_atr×ATR rally strictly between
    them and the signal bar. Returns None when ATR is unavailable (very early bars).
    Mirrors scripts/analyze_second_entry.classify_test_ordinal.
    """
    atr = float(ctx.atr.iloc[signal_idx])
    if not np.isfinite(atr) or atr <= 0:
        return None
    ref_low = float(bars["low"].iloc[signal_idx])
    highs = bars["high"].values
    sl_idx = ctx.swing_low_idx
    window_start = signal_idx - lookback
    priors = sl_idx[(sl_idx + swing_n <= signal_idx)
                    & (sl_idx < signal_idx) & (sl_idx >= window_start)]
    n_same = 0
    for p in priors:
        p = int(p)
        plow = float(bars["low"].iloc[p])
        if abs(plow - ref_low) > tol_atr * atr:
            continue
        between = highs[p + 1:signal_idx]
        if between.size == 0:
            continue
        seg_high = float(np.max(between))
        if seg_high - max(plow, ref_low) >= bounce_atr * atr:
            n_same += 1
    return 1 + n_same


def signal_deweight_factor(
    bars: pd.DataFrame,
    signal_idx: int,
    direction: str,
    higher_relation: str | None,
    ctx: DeweightContext,
) -> float:
    """Production de-weight multiplier for one signal. Fail-open (1.0) when the lane
    is not applicable or the signal is too early to assess either feature.

    Applies only to bottom × (opposing|neutral); see overext_deweight for the math.
    """
    # Cheap lane check first — non-applicable lanes never touch bar geometry.
    if direction != "bottom" or higher_relation not in ("opposing", "neutral"):
        return 1.0
    rva = range_vs_avg(bars, signal_idx)
    if rva is None or not np.isfinite(rva):
        return 1.0  # too early / degenerate / missing-data bar — do not penalize
    ordn = test_ordinal(bars, signal_idx, ctx)
    if ordn is None:
        ordn = 1     # ATR unavailable — no ordinal penalty
    return deweight_factor(direction, higher_relation, rva, ordn)
