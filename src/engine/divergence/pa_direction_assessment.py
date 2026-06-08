"""Strategic-layer direction synthesiser — DIR module per the Xiao design memo.

Replaces a single-source `h_rel == opposing` gate with a four-source vote:

    daily_structure | hourly_state | context | divergence

Each source returns ``bull`` / ``bear`` / ``neutral`` with equal weight 0.25.
The synthesiser maps the aggregate to:

    bull_votes  >= 0.50  →  long_call
    bear_votes  >= 0.50  →  long_put
    otherwise            →  skip

The module is intentionally annotation-only at this step — `score_today`
attaches the verdict to records but does **not** gate emission on it.
The data lands on records first so human review can compare the synthesiser's
verdict against existing PA gates before any downstream consumer relies on it.

Spec source: doc/design/xiao_modules_interface_2026-06-08.md §"Module DIR"
(adapted: this implementation uses the equal-weight 0.25 ×4 scheme called
out in open Q-1 and emits {bull, bear, neutral} votes rather than the
memo's {long_call, long_put, neutral, block} four-vote scheme — the
``block`` short-circuit is deferred to a later iteration.)

Strategic constraint (locked 2026-06-08): puts ARE in MVP.  Direction
outcome ∈ {long_call, long_put, skip}.  Weekly + exhaustion sources
deferred to Step 3.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from engine.divergence.pa_context_classifier import (
    classify_context,
    classify_context_top,
)
from engine.divergence.pa_structure import PAStructureDetector
from engine.features.macd import ema, macd as compute_macd


Vote = Literal["bull", "bear", "neutral"]
Direction = Literal["long_call", "long_put", "skip"]
AmbushPattern = Literal["h2_bottom", "h2_top"]

# Equal weights across the 8-source pool (D-full upgrade 2026-06-08).
# 4 baseline sources (daily_structure / hourly_state / context / divergence)
# + 4 new sources (weekly_trend / minute15_state / force_balance / exhaustion).
# 8 × 0.125 = 1.00; threshold 0.50 = 4-of-8 majority required.
_SOURCE_WEIGHT: float = 0.125

# Hourly DIF margin: |DIF| must exceed this multiple of 1h ATR(14)
# to count as a directional vote.  Below the threshold the source
# votes neutral (DIF "approximately zero" relative to volatility).
_HOURLY_DIF_ATR_MARGIN: float = 0.2
_HOURLY_ATR_PERIOD: int = 14

# Divergence: look back at most this many bars on daily to find the prior
# pivot low/high used for the histogram comparison.
_DIVERGENCE_LOOKBACK: int = 30
# Pivot helper: a confirmed pivot needs N bars either side.  Keep small so
# the lookback window can produce a candidate within 30 bars.
_DIVERGENCE_PIVOT_N: int = 2


@dataclass
class DirectionSource:
    """A single source's contribution to the direction verdict.

    Attributes
    ----------
    name:       one of "daily_structure" / "hourly_state" / "context" /
                "divergence" — identifies the source.
    vote:       "bull" / "bear" / "neutral" — directional inclination.
    weight:     [0, 1] — contribution to bull/bear totals.  Equal weights
                of 0.25 used uniformly today (open Q-1).
    rationale:  short human-readable string, e.g. "phase=BULL"
                or "DIF=-0.012 (margin=0.0021)".
    """
    name: str
    vote: Vote
    weight: float
    rationale: str


@dataclass
class DirectionVerdict:
    """Synthesised verdict across the four direction sources.

    Attributes
    ----------
    direction:   "long_call" / "long_put" / "skip"
    confidence:  [0, 1] — sum of the supporting weights when a side wins,
                 else max(bull_votes, bear_votes) when both sides lose
                 the 0.50 threshold (i.e. how much support the *best*
                 side had even though it failed to clear).
    sources:     four DirectionSource entries, in the order
                 [daily_structure, hourly_state, context, divergence].
    rationale:   one-line summary "src=vote, src=vote, ...".
    """
    direction: Direction
    confidence: float
    sources: list[DirectionSource] = field(default_factory=list)
    rationale: str = ""


# ---------------------------------------------------------------------------
# Source helpers
# ---------------------------------------------------------------------------


# TR position thresholds — user lock 2026-06-08 ("TR 区间底部做多，
# 顶部做空，其他位置不做"):
#   close in bottom 30% of TR + h2_bottom    → bull (entry zone)
#   close in top 30% of TR + h2_top          → bear (entry zone)
#   middle 30-70% of TR (any pattern)        → neutral (don't trade)
#   bottom 30% + h2_top  or top 30% + h2_bottom (position mismatch)
#                                            → neutral (conservative —
#     multi-TF resolution via other sources, daily_structure stays out)
_TR_BULL_ZONE_MAX: float = 0.30
_TR_BEAR_ZONE_MIN: float = 0.70


def _vote_from_daily_structure(
    daily_bars: pd.DataFrame,
    bar_idx: int,
    ambush_pattern: AmbushPattern = "h2_bottom",
) -> DirectionSource:
    """Source A — PA structural phase + TR position on daily bars.

    Direction interpretation depends on phase AND, for TR phases, the
    close's position within the range:

        BULL                              → bull  (trend backdrop)
        BEAR                              → bear  (trend backdrop)
        TR / TR_FORMING:
            pos_in_tr ≤ 0.30 + h2_bottom  → bull  ("buy support")
            pos_in_tr ≥ 0.70 + h2_top     → bear  ("sell resistance")
            otherwise (middle, or mismatch) → neutral  ("don't trade")
            tr_top or tr_bot is None        → neutral  (incomplete range)
        UNCLEAR                           → neutral  (no structure)

    Rationale carries phase + pos_in_tr (when applicable) + tr_top/tr_bot.

    Rationale for the TR/TR_FORMING logic (user-locked 2026-06-08):
    PA's H2 setups live inside TR phases — buying support at tr_bot,
    selling resistance at tr_top.  Treating every TR/TR_FORMING signal
    as "neutral" makes daily_structure miss the directional content the
    range structure provides.  Position-mismatched signals (h2_bottom
    near tr_top, or h2_top near tr_bot) stay neutral here; multi-TF
    sources (weekly_trend / hourly_state / etc.) resolve the
    ambiguity.
    """
    det = PAStructureDetector()
    struct = det.detect(daily_bars, up_to_idx=bar_idx)
    phase = struct.phase
    rationale_bits = [f"phase={phase}"]

    if phase == "BULL":
        vote: Vote = "bull"
    elif phase == "BEAR":
        vote = "bear"
    elif phase in ("TR", "TR_FORMING"):
        # Need both edges + pos_in_tr to make a position call.
        if (struct.tr_top is None or struct.tr_bot is None
                or struct.pos_in_tr is None):
            vote = "neutral"
            rationale_bits.append("incomplete_range")
        else:
            pos = float(struct.pos_in_tr)
            pos_clip = max(0.0, min(1.0, pos))
            rationale_bits.append(f"pos_in_tr={pos_clip:.2f}")
            if ambush_pattern == "h2_bottom" and pos_clip <= _TR_BULL_ZONE_MAX:
                vote = "bull"
            elif ambush_pattern == "h2_top" and pos_clip >= _TR_BEAR_ZONE_MIN:
                vote = "bear"
            else:
                # Middle of range OR position-mismatched signal —
                # conservative neutral; multi-TF sources resolve.
                vote = "neutral"
    else:  # UNCLEAR
        vote = "neutral"

    if struct.tr_top is not None and struct.tr_bot is not None:
        rationale_bits.append(f"tr=[{struct.tr_bot:.2f},{struct.tr_top:.2f}]")
    return DirectionSource(
        name="daily_structure",
        vote=vote,
        weight=_SOURCE_WEIGHT,
        rationale=", ".join(rationale_bits),
    )


def _atr(bars: pd.DataFrame, period: int) -> pd.Series:
    """Wilder ATR — used for the hourly DIF noise floor.

    Standard ATR(period) on (high, low, close).  Uses EWM with span =
    ``period`` (good enough proxy for noise floor; not used for sizing).
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


def _vote_from_hourly_state(
    hourly_bars: pd.DataFrame | None,
    signal_ts: pd.Timestamp,
    ambush_pattern: AmbushPattern = "h2_bottom",
) -> DirectionSource:
    """Source B — 1h DIF direction at the last 1h bar ≤ signal_ts.

    POLARITY-AWARE (2026-06-08): the "h=opposing" rule in PA detection
    means the hourly timeframe should be moving AGAINST the setup
    direction.  So when hunting an h2_bottom, a NEGATIVE hourly DIF is
    the confirmation we want — the source votes BULL.  When hunting an
    h2_top, a POSITIVE hourly DIF is the confirmation — vote BEAR.

    Bull / bear classification driven by ``ambush_pattern``:

      h2_bottom:
        DIF < -margin  → vote=bull (h=opposing confirms the bottom setup)
        DIF > +margin  → vote=bear (h=aligned, weakens the bottom setup)
        |DIF| ≤ margin → vote=neutral

      h2_top:
        DIF > +margin  → vote=bear (h=opposing confirms the top setup)
        DIF < -margin  → vote=bull (h=aligned, weakens the top setup)
        |DIF| ≤ margin → vote=neutral

    No hourly data → neutral with rationale "no_1h_data".
    """
    if hourly_bars is None or len(hourly_bars) == 0:
        return DirectionSource(
            name="hourly_state",
            vote="neutral",
            weight=_SOURCE_WEIGHT,
            rationale="no_1h_data",
        )
    if "timestamp" not in hourly_bars.columns or "close" not in hourly_bars.columns:
        return DirectionSource(
            name="hourly_state",
            vote="neutral",
            weight=_SOURCE_WEIGHT,
            rationale="no_1h_data",
        )

    h_ts = pd.to_datetime(hourly_bars["timestamp"]).values
    sig_np = np.datetime64(pd.Timestamp(signal_ts).to_datetime64())
    mask = h_ts <= sig_np
    if not mask.any():
        return DirectionSource(
            name="hourly_state",
            vote="neutral",
            weight=_SOURCE_WEIGHT,
            rationale="signal_before_1h_history",
        )
    h_idx = int(np.flatnonzero(mask)[-1])

    macd_df = compute_macd(hourly_bars["close"], hist_scale=1.0)
    dif_val = float(macd_df["dif"].iloc[h_idx])

    if not np.isfinite(dif_val):
        return DirectionSource(
            name="hourly_state",
            vote="neutral",
            weight=_SOURCE_WEIGHT,
            rationale="dif=nan",
        )

    atr_series = _atr(hourly_bars, _HOURLY_ATR_PERIOD)
    atr_val = float(atr_series.iloc[h_idx]) if len(atr_series) > h_idx else float("nan")
    if not np.isfinite(atr_val) or atr_val <= 0.0:
        # ATR not informative → use raw DIF sign-only as a degraded fallback.
        margin = 0.0
    else:
        margin = _HOURLY_DIF_ATR_MARGIN * atr_val

    # Classify DIF sign vs margin first; then map to bull/bear by polarity.
    if dif_val > margin and dif_val > 0:
        dif_sign: Literal["pos", "neg", "neutral"] = "pos"
    elif dif_val < -margin and dif_val < 0:
        dif_sign = "neg"
    else:
        dif_sign = "neutral"

    if ambush_pattern == "h2_bottom":
        # Hunting a bottom — hourly going AGAINST the setup (DIF<0) is the
        # h=opposing confirmation we want.  Vote bull when DIF<0.
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
        name="hourly_state",
        vote=vote,
        weight=_SOURCE_WEIGHT,
        rationale=(
            f"dif={dif_val:+.4f} margin={margin:.4f} pattern={ambush_pattern}"
        ),
    )


def _vote_from_context(
    daily_bars: pd.DataFrame,
    bar_idx: int,
    macd_df: pd.DataFrame | None,
    ambush_pattern: AmbushPattern = "h2_bottom",
) -> DirectionSource:
    """Source C — Context A / B1 (bottom) or A_top / B1_top (top).

    POLARITY-AWARE (2026-06-08): bottom and top contexts are evaluated
    independently.  Top-side (A_top / B1_top) mirrors the bull-side
    patterns: A_top = selling-into-rally in a downtrend, B1_top = first
    pullback in a new bear cycle.

      ambush_pattern == "h2_bottom":
        A or B1     → vote=bull
        None        → vote=neutral, rationale "context=None"

      ambush_pattern == "h2_top":
        A_top or B1_top → vote=bear
        None            → vote=neutral, rationale "no_top_context"
    """
    if macd_df is None:
        return DirectionSource(
            name="context",
            vote="neutral",
            weight=_SOURCE_WEIGHT,
            rationale="no_macd_df",
        )

    try:
        ema20 = ema(daily_bars["close"], 20)
        ema60 = ema(daily_bars["close"], 60)
    except Exception as exc:  # pragma: no cover — defensive
        return DirectionSource(
            name="context",
            vote="neutral",
            weight=_SOURCE_WEIGHT,
            rationale=f"context_err={exc!s}",
        )

    if ambush_pattern == "h2_top":
        try:
            ctx_top = classify_context_top(
                daily_bars, bar_idx, macd_df, ema20, ema60,
            )
        except Exception as exc:  # pragma: no cover — defensive
            return DirectionSource(
                name="context",
                vote="neutral",
                weight=_SOURCE_WEIGHT,
                rationale=f"context_err={exc!s}",
            )
        if ctx_top in ("A_top", "B1_top"):
            return DirectionSource(
                name="context",
                vote="bear",
                weight=_SOURCE_WEIGHT,
                rationale=f"context={ctx_top}",
            )
        return DirectionSource(
            name="context",
            vote="neutral",
            weight=_SOURCE_WEIGHT,
            rationale="no_top_context",
        )

    try:
        ctx = classify_context(daily_bars, bar_idx, macd_df, ema20, ema60)
    except Exception as exc:  # pragma: no cover — defensive
        return DirectionSource(
            name="context",
            vote="neutral",
            weight=_SOURCE_WEIGHT,
            rationale=f"context_err={exc!s}",
        )
    if ctx == "A" or ctx == "B1":
        return DirectionSource(
            name="context",
            vote="bull",
            weight=_SOURCE_WEIGHT,
            rationale=f"context={ctx}",
        )
    return DirectionSource(
        name="context",
        vote="neutral",
        weight=_SOURCE_WEIGHT,
        rationale="context=None",
    )


def _find_prior_pivot(
    values: pd.Series,
    bar_idx: int,
    lookback: int,
    kind: Literal["low", "high"],
    pivot_n: int = _DIVERGENCE_PIVOT_N,
) -> int | None:
    """Locate the most recent confirmed pivot (low or high) before bar_idx.

    A bar is a confirmed pivot if it is the strict min (or max) of a
    window of width 2*pivot_n+1 centred on it.  Returns the integer
    index, or None if no pivot lands within ``lookback`` bars of
    ``bar_idx``.
    """
    start = max(0, bar_idx - lookback)
    end = bar_idx - pivot_n  # need pivot_n bars to the right for confirmation
    if end <= start + pivot_n:
        return None
    arr = values.values
    best: int | None = None
    for j in range(end, start - 1, -1):
        lo = max(0, j - pivot_n)
        hi = min(len(arr), j + pivot_n + 1)
        window = arr[lo:hi]
        if not np.isfinite(window).all():
            continue
        if kind == "low":
            if arr[j] == window.min() and (window < arr[j]).sum() == 0 and (window == arr[j]).sum() == 1:
                best = j
                break
        else:
            if arr[j] == window.max() and (window > arr[j]).sum() == 0 and (window == arr[j]).sum() == 1:
                best = j
                break
    return best


def _vote_from_divergence(
    daily_bars: pd.DataFrame,
    bar_idx: int,
    macd_df: pd.DataFrame | None,
    ambush_pattern: AmbushPattern = "h2_bottom",
) -> DirectionSource:
    """Source D — Conservative PA-native divergence check on daily bars.

    Bull divergence (long_call):
        bar_idx low < prior pivot low (within last 30 bars)
        AND hist[bar_idx] > hist[prior_pivot_idx]

    Bear divergence (long_put): symmetric on high + hist.

    ``ambush_pattern`` is accepted for API symmetry but does not change
    voting: bull divergence is bullish regardless of which trade side is
    being scanned, and likewise for bear divergence.
    """
    if macd_df is None:
        return DirectionSource(
            name="divergence",
            vote="neutral",
            weight=_SOURCE_WEIGHT,
            rationale="no_macd_df",
        )
    if bar_idx < _DIVERGENCE_PIVOT_N + 1:
        return DirectionSource(
            name="divergence",
            vote="neutral",
            weight=_SOURCE_WEIGHT,
            rationale="insufficient_history",
        )
    if "hist" not in macd_df.columns:
        return DirectionSource(
            name="divergence",
            vote="neutral",
            weight=_SOURCE_WEIGHT,
            rationale="no_hist_column",
        )

    hist = macd_df["hist"]
    cur_hist = float(hist.iloc[bar_idx])
    cur_low = float(daily_bars["low"].iloc[bar_idx])
    cur_high = float(daily_bars["high"].iloc[bar_idx])

    # Bull: lower low + higher hist
    pivot_low_idx = _find_prior_pivot(
        daily_bars["low"], bar_idx, _DIVERGENCE_LOOKBACK, kind="low",
    )
    bull_hit = False
    bull_detail = "no_prior_low_pivot"
    if pivot_low_idx is not None:
        prev_low = float(daily_bars["low"].iloc[pivot_low_idx])
        prev_hist = float(hist.iloc[pivot_low_idx])
        bull_detail = (
            f"low={cur_low:.4f} vs prev_low@{pivot_low_idx}={prev_low:.4f}; "
            f"hist={cur_hist:+.4f} vs prev_hist={prev_hist:+.4f}"
        )
        if cur_low < prev_low and cur_hist > prev_hist:
            bull_hit = True

    # Bear: higher high + lower hist
    pivot_high_idx = _find_prior_pivot(
        daily_bars["high"], bar_idx, _DIVERGENCE_LOOKBACK, kind="high",
    )
    bear_hit = False
    bear_detail = "no_prior_high_pivot"
    if pivot_high_idx is not None:
        prev_high = float(daily_bars["high"].iloc[pivot_high_idx])
        prev_hist = float(hist.iloc[pivot_high_idx])
        bear_detail = (
            f"high={cur_high:.4f} vs prev_high@{pivot_high_idx}={prev_high:.4f}; "
            f"hist={cur_hist:+.4f} vs prev_hist={prev_hist:+.4f}"
        )
        if cur_high > prev_high and cur_hist < prev_hist:
            bear_hit = True

    # If both fire (rare — would require a wide-range outlier bar), let
    # bull win since the bottom side is the historically validated lane;
    # callers wanting strict-only behaviour can inspect the rationale.
    if bull_hit and bear_hit:
        return DirectionSource(
            name="divergence",
            vote="bull",
            weight=_SOURCE_WEIGHT,
            rationale=f"BOTH; {bull_detail} | {bear_detail}",
        )
    if bull_hit:
        return DirectionSource(
            name="divergence",
            vote="bull",
            weight=_SOURCE_WEIGHT,
            rationale=f"bull; {bull_detail}",
        )
    if bear_hit:
        return DirectionSource(
            name="divergence",
            vote="bear",
            weight=_SOURCE_WEIGHT,
            rationale=f"bear; {bear_detail}",
        )
    return DirectionSource(
        name="divergence",
        vote="neutral",
        weight=_SOURCE_WEIGHT,
        rationale=f"no_div; bull[{bull_detail}] bear[{bear_detail}]",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def assess_direction(
    daily_bars: pd.DataFrame,
    hourly_bars: pd.DataFrame | None,
    bar_idx: int,
    macd_df: pd.DataFrame | None = None,
    *,
    ambush_pattern: AmbushPattern = "h2_bottom",
    weekly_bars: pd.DataFrame | None = None,
    bars_15: pd.DataFrame | None = None,
) -> DirectionVerdict:
    """Aggregate the eight direction sources into a verdict.

    Source pool (each contributes weight 0.125; threshold 0.50 = 4-of-8):

      1. daily_structure   — PAStructureDetector phase
      2. hourly_state      — 1h DIF vs ATR margin
      3. context           — Context A/B1 classifier (bottom-only)
      4. divergence        — PA-native pivot+hist check
      5. weekly_trend      — W phase + W DIF (multi-TF backdrop)
      6. minute15_state    — 15m DIF vs ATR (fine-grain confirmation)
      7. force_balance     — bull/bear strength over recent window
      8. exhaustion        — exhausting-side detection

    Parameters
    ----------
    daily_bars : pd.DataFrame
        Daily OHLCV (must have at least open/high/low/close + timestamp).
    hourly_bars : pd.DataFrame or None
        Optional 1h OHLCV.  None → hourly source votes neutral.
    bar_idx : int
        Positional index into ``daily_bars`` at which to evaluate.
    macd_df : pd.DataFrame or None
        Optional daily MACD frame.  None → context + divergence neutral.
    ambush_pattern : "h2_bottom" | "h2_top"
        Polarity hint — propagated to every polarity-aware source.
    weekly_bars : pd.DataFrame or None
        Optional weekly OHLCV.  None → weekly source neutral.
    bars_15 : pd.DataFrame or None
        Optional 15-minute OHLCV.  None → 15m source neutral.

    Returns
    -------
    DirectionVerdict
        Direction ∈ {long_call, long_put, skip} with per-source rationale.
    """
    # Lazy imports to avoid circular dep at module load time
    from engine.divergence.dir_sources_multitf import (
        minute15_state_source, weekly_trend_source,
    )
    from engine.divergence.dir_sources_context import (
        exhaustion_source, force_balance_source,
    )

    _ALL_NAMES = (
        "daily_structure", "hourly_state", "context", "divergence",
        "weekly_trend", "minute15_state", "force_balance", "exhaustion",
    )

    if not (0 <= bar_idx < len(daily_bars)):
        # Degenerate — return a skip with eight neutral sources so callers
        # can serialise the record without special-casing.
        sources = [
            DirectionSource(name=name, vote="neutral",
                            weight=_SOURCE_WEIGHT, rationale="bar_idx_oob")
            for name in _ALL_NAMES
        ]
        return DirectionVerdict(
            direction="skip",
            confidence=0.0,
            sources=sources,
            rationale="bar_idx out of bounds",
        )

    # Source order is fixed — downstream consumers can index by position
    # if they choose to.
    src_structure = _vote_from_daily_structure(
        daily_bars, bar_idx, ambush_pattern=ambush_pattern,
    )

    if "timestamp" in daily_bars.columns:
        sig_ts = pd.Timestamp(daily_bars["timestamp"].iloc[bar_idx])
    else:
        sig_ts = pd.Timestamp(daily_bars.index[bar_idx])
    src_hourly = _vote_from_hourly_state(
        hourly_bars, sig_ts, ambush_pattern=ambush_pattern,
    )

    src_context = _vote_from_context(
        daily_bars, bar_idx, macd_df, ambush_pattern=ambush_pattern,
    )
    src_divergence = _vote_from_divergence(
        daily_bars, bar_idx, macd_df, ambush_pattern=ambush_pattern,
    )

    # New (D-full) sources
    src_weekly = weekly_trend_source(
        weekly_bars, sig_ts, ambush_pattern=ambush_pattern,
        weight=_SOURCE_WEIGHT,
    )
    src_15m = minute15_state_source(
        bars_15, sig_ts, ambush_pattern=ambush_pattern,
        weight=_SOURCE_WEIGHT,
    )
    src_force = force_balance_source(
        daily_bars, bar_idx, ambush_pattern=ambush_pattern,
        weight=_SOURCE_WEIGHT,
    )
    src_exhaust = exhaustion_source(
        daily_bars, bar_idx, ambush_pattern=ambush_pattern,
        weight=_SOURCE_WEIGHT,
    )

    sources = [
        src_structure, src_hourly, src_context, src_divergence,
        src_weekly, src_15m, src_force, src_exhaust,
    ]

    bull_votes = sum(s.weight for s in sources if s.vote == "bull")
    bear_votes = sum(s.weight for s in sources if s.vote == "bear")

    if bull_votes >= 0.50:
        direction: Direction = "long_call"
        confidence = bull_votes
    elif bear_votes >= 0.50:
        direction = "long_put"
        confidence = bear_votes
    else:
        direction = "skip"
        confidence = max(bull_votes, bear_votes)

    rationale = ", ".join(f"{s.name}={s.vote}" for s in sources)
    return DirectionVerdict(
        direction=direction,
        confidence=round(confidence, 4),
        sources=sources,
        rationale=rationale,
    )
