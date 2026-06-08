"""Multi-timeframe direction sources for the D-full DIR upgrade.

This module hosts the WEEKLY and 15-MIN source helpers that extend the
four-source DIR synthesiser (see ``pa_direction_assessment.py``) to a
six-source synthesiser.  Each function returns a ``DirectionSource``
(with name, vote, weight, rationale) that the orchestrator merges with
the existing four sources.

Sources implemented here
------------------------

  * ``weekly_trend_source``     — W phase + W DIF sign on weekly bars
  * ``minute15_state_source``   — 15m DIF vs ATR margin on 15min bars

Both helpers are polarity-aware via the ``ambush_pattern`` argument
(``"h2_bottom"`` or ``"h2_top"``).  The semantics mirror the existing
``hourly_state`` source after the polarity fix landed:

  * 15-min state at signal time should be moving AGAINST the trade
    direction (h=opposing analogue) — DIF<0 confirms a bottom, DIF>0
    confirms a top.
  * Weekly trend should be moving WITH the trade direction (anchor),
    so a BULL weekly is bullish, BEAR weekly is bearish.

The weights here mirror the existing ``_SOURCE_WEIGHT = 0.25`` constant
in ``pa_direction_assessment.py`` so each new source can either reuse
that weight or be rebalanced by the orchestrator that merges them.  The
constant is duplicated here so this module imports nothing from the
other DIR file (no circular dep risk).

Hand-off to orchestrator
------------------------

The parent session (post-merge of agent α + agent β) is expected to:

  1. Import the two new source functions from this module.
  2. Add them to ``assess_direction``'s source list.
  3. Re-balance ``_SOURCE_WEIGHT`` across the resulting six-source pool.

This module does NOT touch ``assess_direction`` or ``score_today.py``
beyond the helper definitions — the orchestrator does the integration.
"""
from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

from engine.divergence.pa_direction_assessment import DirectionSource
from engine.divergence.pa_structure import PAStructureDetector
from engine.features.macd import macd as compute_macd


AmbushPattern = Literal["h2_bottom", "h2_top"]
Vote = Literal["bull", "bear", "neutral"]

# Equal-weight scheme inherited from the four-source DIR module.  The
# orchestrator may override this when wiring the six-source pool.
_DEFAULT_SOURCE_WEIGHT: float = 0.25

# Minimum bars required for each helper to consider the data usable.
# Weekly: 30 bars ≈ 7 months of weekly history — enough for EMA-26 +
# 5+ confirmed pivots so PAStructureDetector can classify.
_WEEKLY_MIN_BARS: int = 30
# 15min: 50 bars ≈ 12–13 trading hours — enough for ATR(14) + a few
# minutes of MACD context.
_MIN15_MIN_BARS: int = 50

# 15min DIF margin: same shape as the existing hourly margin in
# pa_direction_assessment.py — DIF must clear 0.2×ATR(14) to count as
# a directional vote.  Below that the noise dominates the read.
_MIN15_DIF_ATR_MARGIN: float = 0.2
_MIN15_ATR_PERIOD: int = 14


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _atr(bars: pd.DataFrame, period: int) -> pd.Series:
    """Wilder ATR — same shape as the hourly helper in the DIR module.

    Reproduced here so this module can be loaded without dragging the
    private ``_atr`` from ``pa_direction_assessment.py``.
    """
    high = bars["high"].astype(float)
    low = bars["low"].astype(float)
    close = bars["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=1).mean()


def _last_bar_at_or_before(bars: pd.DataFrame, signal_ts: pd.Timestamp) -> int | None:
    """Return the positional index of the last bar with timestamp ≤ signal_ts.

    Returns None if no bar qualifies, or if ``bars`` lacks a usable
    ``timestamp`` column.
    """
    if "timestamp" not in bars.columns:
        return None
    ts_arr = pd.to_datetime(bars["timestamp"]).values
    sig_np = np.datetime64(pd.Timestamp(signal_ts).to_datetime64())
    mask = ts_arr <= sig_np
    if not mask.any():
        return None
    return int(np.flatnonzero(mask)[-1])


# ---------------------------------------------------------------------------
# Source: weekly_trend
# ---------------------------------------------------------------------------


def weekly_trend_source(
    weekly_bars: pd.DataFrame | None,
    signal_ts: pd.Timestamp,
    ambush_pattern: AmbushPattern = "h2_bottom",
    *,
    weight: float = _DEFAULT_SOURCE_WEIGHT,
) -> DirectionSource:
    """W (weekly) trend source: phase + DIF sign at signal time.

    Reads the most-recent weekly bar with ``timestamp <= signal_ts``,
    computes the weekly DIF (MACD on weekly close), and runs
    :class:`PAStructureDetector` on the weekly series up to that bar.

    Vote logic (direction-anchored — weekly is the "trend backdrop"):

      * W BULL phase  + DIF > 0  → vote=bull
      * W BEAR phase  + DIF < 0  → vote=bear
      * BULL phase + DIF < 0     → vote=neutral, rationale ``"weekly transition"``
      * BEAR phase + DIF > 0     → vote=neutral, rationale ``"weekly transition"``
      * TR / TR_FORMING / UNCLEAR → vote=neutral

    Polarity (``ambush_pattern``): the vote semantics above are
    direction-anchored — they say what the weekly trend itself looks
    like.  The downstream synthesiser interprets the vote in the trade
    direction's frame, so this source returns the same vote for
    h2_bottom and h2_top.  The ``ambush_pattern`` is accepted for API
    symmetry with the polarity-aware sources.

    Rationale: ``"W: <phase>/<dif_sign>"`` (e.g. ``"W: BULL/+"``,
    ``"W: BEAR/-"``, ``"W: TR/neutral"``).

    Degraded paths:
      * ``weekly_bars`` is None or has < 30 rows → vote=neutral with
        rationale ``"weekly_unavailable"``.
      * No bar ≤ signal_ts → vote=neutral, rationale
        ``"signal_before_weekly_history"``.
    """
    if weekly_bars is None or len(weekly_bars) < _WEEKLY_MIN_BARS:
        return DirectionSource(
            name="weekly_trend",
            vote="neutral",
            weight=weight,
            rationale="weekly_unavailable",
        )

    w_idx = _last_bar_at_or_before(weekly_bars, signal_ts)
    if w_idx is None:
        return DirectionSource(
            name="weekly_trend",
            vote="neutral",
            weight=weight,
            rationale="signal_before_weekly_history",
        )

    # Weekly MACD (DIF only — DEA/hist not used in the vote).
    macd_df = compute_macd(weekly_bars["close"], hist_scale=1.0)
    dif_val = float(macd_df["dif"].iloc[w_idx])
    if not np.isfinite(dif_val):
        return DirectionSource(
            name="weekly_trend",
            vote="neutral",
            weight=weight,
            rationale="W dif=nan",
        )

    # Weekly phase from PAStructureDetector — use the same detector that
    # the daily_structure source uses, just fed weekly bars.
    det = PAStructureDetector()
    struct = det.detect(weekly_bars, up_to_idx=w_idx)
    phase = struct.phase

    if dif_val > 0:
        dif_sign = "+"
    elif dif_val < 0:
        dif_sign = "-"
    else:
        dif_sign = "0"

    rationale_base = f"W: {phase}/{dif_sign}"

    if phase == "BULL" and dif_val > 0:
        vote: Vote = "bull"
        rationale = rationale_base
    elif phase == "BEAR" and dif_val < 0:
        vote = "bear"
        rationale = rationale_base
    elif phase in ("BULL", "BEAR"):
        # Mixed signal — phase says one thing, DIF says another.
        vote = "neutral"
        rationale = f"weekly transition; {rationale_base}"
    else:
        # TR / TR_FORMING / UNCLEAR
        vote = "neutral"
        rationale = rationale_base

    return DirectionSource(
        name="weekly_trend",
        vote=vote,
        weight=weight,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# Source: minute15_state
# ---------------------------------------------------------------------------


def minute15_state_source(
    bars_15: pd.DataFrame | None,
    signal_ts: pd.Timestamp,
    ambush_pattern: AmbushPattern = "h2_bottom",
    *,
    weight: float = _DEFAULT_SOURCE_WEIGHT,
) -> DirectionSource:
    """15-minute DIF state source — sibling of ``hourly_state``.

    Same shape as the polarity-aware ``_vote_from_hourly_state`` in
    ``pa_direction_assessment.py``, but on 15-minute bars.  Used as a
    finer-grain confirmation: the 15m timeframe should be moving
    AGAINST the trade direction (h=opposing analogue applied to 15m),
    so a NEGATIVE 15m DIF confirms a bottom, POSITIVE confirms a top.

    Vote logic (with ``margin = 0.2 × ATR(15m, 14)``):

      h2_bottom:
        DIF < -margin → vote=bull (15m h=opposing on bottom setup)
        DIF > +margin → vote=bear
        |DIF| ≤ margin → vote=neutral

      h2_top:
        DIF > +margin → vote=bear (15m h=opposing on top setup)
        DIF < -margin → vote=bull
        |DIF| ≤ margin → vote=neutral

    Rationale: ``"15m DIF=<sign> vs ATR=<value>"`` (e.g.
    ``"15m DIF=+0.0023 vs ATR=0.0190 pattern=h2_bottom"``).

    Degraded paths:
      * ``bars_15`` is None or < 50 rows → vote=neutral, rationale
        ``"15m_unavailable"``.
      * No bar ≤ signal_ts → vote=neutral, rationale
        ``"signal_before_15m_history"``.
    """
    if bars_15 is None or len(bars_15) < _MIN15_MIN_BARS:
        return DirectionSource(
            name="minute15_state",
            vote="neutral",
            weight=weight,
            rationale="15m_unavailable",
        )

    m_idx = _last_bar_at_or_before(bars_15, signal_ts)
    if m_idx is None:
        return DirectionSource(
            name="minute15_state",
            vote="neutral",
            weight=weight,
            rationale="signal_before_15m_history",
        )

    macd_df = compute_macd(bars_15["close"], hist_scale=1.0)
    dif_val = float(macd_df["dif"].iloc[m_idx])

    if not np.isfinite(dif_val):
        return DirectionSource(
            name="minute15_state",
            vote="neutral",
            weight=weight,
            rationale="15m DIF=nan",
        )

    atr_series = _atr(bars_15, _MIN15_ATR_PERIOD)
    atr_val = (
        float(atr_series.iloc[m_idx]) if len(atr_series) > m_idx else float("nan")
    )
    if not np.isfinite(atr_val) or atr_val <= 0.0:
        margin = 0.0
        atr_repr = "n/a"
    else:
        margin = _MIN15_DIF_ATR_MARGIN * atr_val
        atr_repr = f"{atr_val:.4f}"

    # Classify DIF sign vs margin first; then map to bull/bear by polarity.
    if dif_val > margin and dif_val > 0:
        dif_sign: Literal["pos", "neg", "neutral"] = "pos"
    elif dif_val < -margin and dif_val < 0:
        dif_sign = "neg"
    else:
        dif_sign = "neutral"

    if ambush_pattern == "h2_bottom":
        if dif_sign == "neg":
            vote: Vote = "bull"
        elif dif_sign == "pos":
            vote = "bear"
        else:
            vote = "neutral"
    else:  # h2_top
        if dif_sign == "pos":
            vote = "bear"
        elif dif_sign == "neg":
            vote = "bull"
        else:
            vote = "neutral"

    return DirectionSource(
        name="minute15_state",
        vote=vote,
        weight=weight,
        rationale=(
            f"15m DIF={dif_val:+.4f} vs ATR={atr_repr} pattern={ambush_pattern}"
        ),
    )
