"""Direction sources — force-balance + exhaustion (D-full Step 3 / β).

Two additional `DirectionSource` producers for the strategic DIR module
(see `engine.divergence.pa_direction_assessment`).  Both quantify what
the locked methodological principle calls 上下文多空力量对比 ("context
bull/bear force comparison") and 耗竭 ("exhaustion of the prevailing
side").

These functions are pure helpers — they do NOT register themselves with
`assess_direction`.  The parent orchestrator wires them into the source
list and rebalances the weights (see ``open_for_orchestrator`` notes at
the bottom of this file).

Polarity convention
-------------------
``ambush_pattern`` is the PA pattern the caller is evaluating.  We
accept the same two literals the rest of the codebase uses:

* ``"h2_bottom"`` — caller is looking at a candidate bottom (long-call
  context).  Bull-side support = bull vote; bear exhaustion at a
  bottom = bull vote (the bear who pushed price down is dying out so
  the bottom is more credible).
* ``"h2_top"`` — caller is looking at a candidate top (long-put
  context).  Bear-side support = bear vote; bull exhaustion at a top =
  bear vote (the bull who pushed price up is dying out so the top is
  more credible).

The two source functions are polarity-aware: e.g. "bull exhaustion at a
bottom" is NOT a buy signal — it would be the rally that pushed us up
into the candidate area running out of steam, which is a top setup, not
a bottom one.  Hence the matrix:

    pattern    | bull_exhaustion | bear_exhaustion
    -----------+-----------------+-----------------
    h2_bottom  | neutral         | bull
    h2_top     | bear            | neutral

Edge cases for the orchestrator
-------------------------------
1. ``force_balance_source`` needs ``lookback`` real bars including
   ``bar_idx``.  When fewer than ``lookback`` bars are available, it
   returns ``vote="neutral"`` with ``rationale="insufficient_history"``.
2. ``exhaustion_source`` needs ``lookback`` real bars.  Same fallback
   when history is too short.
3. Both functions tolerate a missing ``volume`` column gracefully
   (volume component is dropped from the composite and the rationale
   notes ``vol=na``).
4. Both functions assume daily bars.  Hourly / 15min wiring is the
   parent's responsibility (see Agent α's
   ``dir_sources_multitf.py``).
"""
from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

from engine.divergence.pa_direction_assessment import DirectionSource


# Default weight when the orchestrator does not override.  The parent
# session is expected to set its own weights when wiring these into
# ``assess_direction``; this constant is only used by direct callers
# (e.g. unit tests that want a known weight to inspect).
_DEFAULT_WEIGHT: float = 0.15

# Vote thresholds.
_FORCE_RATIO_THRESHOLD: float = 1.5
_EXHAUSTION_SCORE_THRESHOLD: float = 0.6


AmbushPattern = Literal["h2_bottom", "h2_top"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _window_slice(
    daily_bars: pd.DataFrame, bar_idx: int, lookback: int
) -> pd.DataFrame | None:
    """Return the lookback window ending at ``bar_idx`` (inclusive).

    Returns ``None`` when fewer than ``lookback`` bars are available.
    """
    if not (0 <= bar_idx < len(daily_bars)):
        return None
    start = bar_idx - lookback + 1
    if start < 0:
        return None
    return daily_bars.iloc[start : bar_idx + 1]


def _has_volume(window: pd.DataFrame) -> bool:
    """True iff ``window`` carries a usable ``volume`` column."""
    return (
        "volume" in window.columns
        and np.isfinite(window["volume"].astype(float)).any()
        and (window["volume"].astype(float) > 0).any()
    )


# ---------------------------------------------------------------------------
# Force balance
# ---------------------------------------------------------------------------


def _force_components(
    window: pd.DataFrame,
) -> tuple[float, float, dict[str, float]]:
    """Compute (bull_strength, bear_strength, diagnostics) on a window.

    Composite (each component in [0, 1] then mean-pooled per side):

    1. Close position within the bar's range — fraction of bars closing
       in the upper / lower half.
    2. Body / range ratio — average body size scaled by range.  Long
       bull bodies and long bear bodies both count, but they're split
       by direction.
    3. Volume on up / down bars — fraction of total window volume
       captured by up vs down bars.  Skipped if no volume column.
    4. Net price change — sign and magnitude of (close[-1] - close[0])
       normalised by the window's average range.

    Each side's components are averaged into a single ``strength``
    value in [0, 1].
    """
    o = window["open"].astype(float).values
    h = window["high"].astype(float).values
    l = window["low"].astype(float).values
    c = window["close"].astype(float).values

    rng = np.maximum(h - l, 1e-12)
    body = np.abs(c - o)
    is_up = c > o
    is_dn = c < o

    # 1. close-in-half
    close_pos = (c - l) / rng           # 0 = at low, 1 = at high
    upper_half = float(np.mean(close_pos > 0.5))
    lower_half = float(np.mean(close_pos < 0.5))

    # 2. body-to-range fraction split by direction
    body_frac = body / rng
    bull_body = float(np.mean(np.where(is_up, body_frac, 0.0)))
    bear_body = float(np.mean(np.where(is_dn, body_frac, 0.0)))

    # 3. volume distribution
    diagnostics: dict[str, float] = {}
    if _has_volume(window):
        vol = window["volume"].astype(float).values
        total = float(vol.sum())
        if total > 0:
            bull_vol = float(vol[is_up].sum()) / total
            bear_vol = float(vol[is_dn].sum()) / total
            diagnostics["bull_vol"] = bull_vol
            diagnostics["bear_vol"] = bear_vol
        else:
            bull_vol = bear_vol = 0.5
            diagnostics["vol"] = -1.0  # sentinel: no useful volume
    else:
        bull_vol = bear_vol = 0.5
        diagnostics["vol"] = -1.0

    # 4. net price change scaled by average range
    avg_rng = float(np.mean(rng))
    if avg_rng > 0 and len(c) >= 2:
        net = (c[-1] - c[0]) / (avg_rng * len(c))
    else:
        net = 0.0
    # Squash to [0, 1] using a logistic-like map.  Positive net favours
    # bull; negative net favours bear.  ``net`` is dimensionless and
    # typically lands in [-0.5, 0.5] for the unit-test fixtures.
    bull_net = float(min(1.0, max(0.0, 0.5 + net)))
    bear_net = float(min(1.0, max(0.0, 0.5 - net)))

    bull_strength = float(np.mean([upper_half, bull_body, bull_vol, bull_net]))
    bear_strength = float(np.mean([lower_half, bear_body, bear_vol, bear_net]))

    diagnostics.update(
        {
            "upper_half": upper_half,
            "lower_half": lower_half,
            "bull_body": bull_body,
            "bear_body": bear_body,
            "bull_net": bull_net,
            "bear_net": bear_net,
        }
    )
    return bull_strength, bear_strength, diagnostics


def force_balance_source(
    daily_bars: pd.DataFrame,
    bar_idx: int,
    lookback: int = 10,
    ambush_pattern: AmbushPattern = "h2_bottom",
    weight: float = _DEFAULT_WEIGHT,
) -> DirectionSource:
    """Direction source — context bull/bear force balance over a window.

    Computes ``bull_strength`` and ``bear_strength`` via the composite in
    :func:`_force_components`, then maps the ratio to a vote:

    * ``bull_strength / bear_strength >= 1.5`` → vote=``bull``
    * ``bear_strength / bull_strength >= 1.5`` → vote=``bear``
    * else                                     → vote=``neutral``

    The polarity is symmetric — a strong bull side is bullish whether
    the caller is hunting a bottom or hunting a top — but the rationale
    notes ``ambush_pattern`` so downstream readers can sanity-check
    alignment with the caller's polarity.
    """
    if ambush_pattern not in ("h2_bottom", "h2_top"):
        return DirectionSource(
            name="force_balance",
            vote="neutral",
            weight=weight,
            rationale=f"unknown_ambush_pattern={ambush_pattern}",
        )

    window = _window_slice(daily_bars, bar_idx, lookback)
    if window is None or len(window) < lookback:
        return DirectionSource(
            name="force_balance",
            vote="neutral",
            weight=weight,
            rationale="insufficient_history",
        )

    bull_strength, bear_strength, _ = _force_components(window)

    # Stable ratio computation — avoid div-by-zero.
    eps = 1e-9
    if bear_strength <= eps and bull_strength <= eps:
        ratio = 1.0
        vote = "neutral"
    elif bear_strength <= eps:
        # bear side is essentially zero → bull dominates outright
        ratio = float("inf")
        vote = "bull"
    elif bull_strength <= eps:
        # bull side is essentially zero → bear dominates outright
        ratio = 0.0
        vote = "bear"
    else:
        ratio = bull_strength / bear_strength
        if ratio >= _FORCE_RATIO_THRESHOLD:
            vote = "bull"
        elif (1.0 / ratio) >= _FORCE_RATIO_THRESHOLD:
            vote = "bear"
        else:
            vote = "neutral"

    rationale = (
        f"bull_strength={bull_strength:.4f}, "
        f"bear_strength={bear_strength:.4f}, "
        f"ratio={ratio:.4f}, pattern={ambush_pattern}"
    )
    return DirectionSource(
        name="force_balance",
        vote=vote,
        weight=weight,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# Exhaustion
# ---------------------------------------------------------------------------


def _exhaustion_scores(
    window: pd.DataFrame,
) -> tuple[float, float, dict[str, float]]:
    """Compute (bull_exhaustion_score, bear_exhaustion_score, diagnostics).

    Bull exhaustion (price up but force dying):
        * shrinking body sizes — slope of body sizes across the window
          is negative.
        * upper wicks growing — rejection at highs.
        * declining volume as price extends up.
        * closes drifting toward lower half of the bar.

    Bear exhaustion: symmetric mirror with lower wicks growing and
    closes drifting toward upper half.

    Both scores are clipped to [0, 1].  A score of 1.0 means every
    sub-component fired strongly; 0.0 means none did.
    """
    o = window["open"].astype(float).values
    h = window["high"].astype(float).values
    l = window["low"].astype(float).values
    c = window["close"].astype(float).values
    n = len(window)
    rng = np.maximum(h - l, 1e-12)

    body = np.abs(c - o)
    upper_wick = h - np.maximum(o, c)
    lower_wick = np.minimum(o, c) - l
    upper_wick = np.maximum(upper_wick, 0.0)
    lower_wick = np.maximum(lower_wick, 0.0)
    close_pos = (c - l) / rng

    # Determine overall direction of price over the window for the
    # "price up but force dying" condition.
    if n >= 2 and rng.mean() > 0:
        price_trend = (c[-1] - c[0]) / (rng.mean() * n)
    else:
        price_trend = 0.0

    # Linear slope helper using bar index as x.
    xs = np.arange(n, dtype=float)
    def _slope(y: np.ndarray) -> float:
        if n < 2:
            return 0.0
        x_mean = xs.mean()
        y_mean = float(np.mean(y))
        denom = float(np.sum((xs - x_mean) ** 2))
        if denom <= 0:
            return 0.0
        return float(np.sum((xs - x_mean) * (y - y_mean)) / denom)

    body_slope = _slope(body)
    upper_wick_slope = _slope(upper_wick)
    lower_wick_slope = _slope(lower_wick)
    close_pos_slope = _slope(close_pos)

    # Volume slope (optional).
    have_vol = _has_volume(window)
    if have_vol:
        vol = window["volume"].astype(float).values
        volume_slope = _slope(vol)
    else:
        volume_slope = 0.0

    # Normalise slopes into [0, 1] components.  We use simple monotone
    # maps — a slope of zero is "no signal" (0.0), a strongly negative
    # body slope is "shrinking bodies" (close to 1.0), etc.
    #
    # Calibration: with realistic daily windows the scales below should
    # saturate (component → 1.0) when the underlying signal is "clear"
    # to a human eye.  body/wick slopes are normalised by the *mean
    # body size* in the window so the score is independent of price
    # level.  close-position slope is per-bar shift in [0, 1] (a slope
    # of -0.1 means closes drifting down by 10% of range per bar).
    avg_rng = float(rng.mean())
    mean_body = max(float(np.mean(body)), avg_rng * 0.05, 1e-9)
    body_slope_scale = max(mean_body * 0.05, 1e-9)
    wick_slope_scale = max(mean_body * 0.10, 1e-9)
    close_pos_scale = 0.04
    if have_vol and n >= 2:
        mean_vol = float(np.mean(window["volume"].astype(float).values))
        vol_scale = max(mean_vol * 0.10, 1e-9)
    else:
        vol_scale = 1.0

    def _pos(x: float, scale: float) -> float:
        """Map positive-slope signals to [0, 1]."""
        if scale <= 0:
            return 0.0
        return float(min(1.0, max(0.0, x / scale)))

    def _neg(x: float, scale: float) -> float:
        """Map negative-slope signals to [0, 1]."""
        if scale <= 0:
            return 0.0
        return float(min(1.0, max(0.0, -x / scale)))

    # Price-trend gates are binary by design.  If the window's net
    # price drift is non-negative we accept "bull is up here";
    # symmetric for bear.  Magnitude-scaled gates would suppress
    # exhaustion signals on quiet drifting bars — exactly the regime
    # where exhaustion is most diagnostic.
    bull_price_gate = 1.0 if price_trend >= 0.0 else 0.0
    bear_price_gate = 1.0 if price_trend <= 0.0 else 0.0

    # --- BULL exhaustion (price up, force dying) ---
    bull_body_shrink = _neg(body_slope, body_slope_scale)
    bull_upper_wick_grow = _pos(upper_wick_slope, wick_slope_scale)
    bull_volume_decline = _neg(volume_slope, vol_scale) if have_vol else 0.0
    bull_close_slip = _neg(close_pos_slope, close_pos_scale)

    if have_vol:
        bull_components = [
            bull_body_shrink, bull_upper_wick_grow,
            bull_volume_decline, bull_close_slip,
        ]
    else:
        bull_components = [
            bull_body_shrink, bull_upper_wick_grow, bull_close_slip,
        ]
    bull_exhaustion_score = bull_price_gate * float(np.mean(bull_components))
    bull_exhaustion_score = float(min(1.0, max(0.0, bull_exhaustion_score)))

    # --- BEAR exhaustion (price down, force dying) ---
    bear_body_shrink = _neg(body_slope, body_slope_scale)
    bear_lower_wick_grow = _pos(lower_wick_slope, wick_slope_scale)
    bear_volume_decline = _neg(volume_slope, vol_scale) if have_vol else 0.0
    bear_close_lift = _pos(close_pos_slope, close_pos_scale)

    if have_vol:
        bear_components = [
            bear_body_shrink, bear_lower_wick_grow,
            bear_volume_decline, bear_close_lift,
        ]
    else:
        bear_components = [
            bear_body_shrink, bear_lower_wick_grow, bear_close_lift,
        ]
    bear_exhaustion_score = bear_price_gate * float(np.mean(bear_components))
    bear_exhaustion_score = float(min(1.0, max(0.0, bear_exhaustion_score)))

    diagnostics = {
        "price_trend": price_trend,
        "body_slope": body_slope,
        "upper_wick_slope": upper_wick_slope,
        "lower_wick_slope": lower_wick_slope,
        "close_pos_slope": close_pos_slope,
        "volume_slope": volume_slope,
        "have_vol": 1.0 if have_vol else 0.0,
        "bull_price_gate": bull_price_gate,
        "bear_price_gate": bear_price_gate,
    }
    return bull_exhaustion_score, bear_exhaustion_score, diagnostics


def exhaustion_source(
    daily_bars: pd.DataFrame,
    bar_idx: int,
    lookback: int = 5,
    ambush_pattern: AmbushPattern = "h2_bottom",
    weight: float = _DEFAULT_WEIGHT,
) -> DirectionSource:
    """Direction source — exhaustion of the prevailing side over a window.

    Returns a polarity-aware vote.  See module-level docstring for the
    {pattern, exhausting_side → vote} matrix.
    """
    if ambush_pattern not in ("h2_bottom", "h2_top"):
        return DirectionSource(
            name="exhaustion",
            vote="neutral",
            weight=weight,
            rationale=f"unknown_ambush_pattern={ambush_pattern}",
        )

    window = _window_slice(daily_bars, bar_idx, lookback)
    if window is None or len(window) < lookback:
        return DirectionSource(
            name="exhaustion",
            vote="neutral",
            weight=weight,
            rationale="insufficient_history",
        )

    bull_ex, bear_ex, _ = _exhaustion_scores(window)

    score_str = f"bull_ex={bull_ex:.4f} bear_ex={bear_ex:.4f}"

    bull_exhausting = bull_ex > _EXHAUSTION_SCORE_THRESHOLD
    bear_exhausting = bear_ex > _EXHAUSTION_SCORE_THRESHOLD

    # When both fire, defer to the dominant magnitude.  This is rare
    # because the price-trend gate makes each side mutually suppress
    # the other, but defensive handling keeps the source deterministic.
    if bull_exhausting and bear_exhausting:
        if bull_ex >= bear_ex:
            bear_exhausting = False
        else:
            bull_exhausting = False

    if not bull_exhausting and not bear_exhausting:
        return DirectionSource(
            name="exhaustion",
            vote="neutral",
            weight=weight,
            rationale=f"no_exhaustion; {score_str}; pattern={ambush_pattern}",
        )

    if bull_exhausting:
        # Bull is dying.  Bearish for h2_top setups; not actionable on
        # h2_bottom (a bull dying at a bottom is just the rally before
        # the bottom running out).
        if ambush_pattern == "h2_top":
            vote = "bear"
        else:
            vote = "neutral"
        return DirectionSource(
            name="exhaustion",
            vote=vote,
            weight=weight,
            rationale=(
                f"bull_exhausting; {score_str}; pattern={ambush_pattern}"
            ),
        )

    # bear_exhausting
    if ambush_pattern == "h2_bottom":
        vote = "bull"
    else:
        vote = "neutral"
    return DirectionSource(
        name="exhaustion",
        vote=vote,
        weight=weight,
        rationale=(
            f"bear_exhausting; {score_str}; pattern={ambush_pattern}"
        ),
    )


__all__ = [
    "force_balance_source",
    "exhaustion_source",
    "AmbushPattern",
]
