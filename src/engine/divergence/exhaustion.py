"""Trend-exhaustion candidate detector.

Targets the 30-35% blind-spot bucket revealed by `src/scripts/missed_swing_state.py`
diagnostic (CSV outputs in `<review_dir>/missed_swing_state_*.csv`, where
`review_dir` is resolved via the DERIVED_ROOT env var or falls back to
`src/data/review/`): swings
where all 3 TFs were aligned same-direction trending — no MACD divergence
can fire because there's no opposing-momentum container to compare against.
Spec: `doc/exhaustion-detector-spec-2026-05-26.md`.

Triggers (T1–T5):
  T1 — segment maturity: `bars_in_segment ≥ min_bars_in_segment` in the
       current MACD segment. Bars-in-segment replaces the spec's
       "n_completed_cycles ≥ 3" gate after the 2026-05-27 calibration
       run showed daily MACD segments rarely complete more than 1–2
       cycles before flipping (SPY: 30 segments, 0 reach 3 completions).
       Bars-based is the spec's documented fallback. `n_completed_cycles`
       is still populated on the emitted event for downstream filtering.
       Per-TF recommended thresholds: D=20, 1h=50, 15m=200.
  T2 — multi-TF alignment: higher-TF trend_side AND lower-TF trend_side both
       match the primary segment direction (strict mode requires both to be
       computable; if a foreign-TF state can't be derived the candidate is
       skipped under strict_alignment=True)
  T3 — K-line reversal signature on the candidate bar:
       top (up-segment exhaustion):    upper_wick_ratio ≥ min_wick_ratio
                                       AND close in lower half of range
       bottom (down-segment exhaustion): lower_wick_ratio ≥ min_wick_ratio
                                       AND close in upper half of range
  T4 — at segment extreme: bar's relevant high/low ties the segment-so-far
       extreme (i.e. this is a new or matching high/low for the segment)
  T5 (optional) — volume climax: bar volume ≥ `volume_climax_threshold` ×
       trailing-`VOLUME_LOOKBACK_BARS`-bar mean. Off by default; enable via
       require_volume_climax=True.

An ExhaustionEvent is direction-opposite to the segment: up-segments emit
"top" candidates (predicting a downside reversal); down-segments emit
"bottom".

Confidence is computed in-detector (vs DivergenceSignal where it's set by
comparator). Downstream consumers read `confidence` directly; there is no
PolicyDecision wrapper at v1.4 — that can be added once OOS validation
gives instrument-class-specific weights.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from engine.fusion.level_state import LevelState, compute_level_state

VOLUME_LOOKBACK_BARS = 20  # matches engine/divergence/detector.py


Direction = Literal["top", "bottom"]
BodyHalf = Literal["upper", "lower", "middle"]


class ExhaustionEvent(BaseModel):
    """One trend-exhaustion reversal candidate.

    Lifecycle: emitted on a bar where an in-progress MACD segment has run
    long enough (T1), multi-TF context is aligned same-direction trending
    (T2), the bar both sits at the segment extreme (T4) and shows a
    Brooks-style reversal candle (T3). A subsequent bar exceeding this bar's
    extreme means the candidate did not turn the trend (false positive in
    retrospect).

    Field guarantees (envelope schema 1.4):
      - level_id, timestamp: emitting TF identification (UTC)
      - candidate_bar_idx: position in the primary_bars frame the detector
        was given (zero-based, post reset_index)
      - direction: predicted reversal direction (opposite of segment)
      - segment_id, segment_direction, bars_in_segment: segment context
      - n_completed_cycles: count of cycles fully closed within this segment
        BEFORE/INCLUDING this bar
      - wick_ratio: rejection-side wick / bar range, clipped [0, 1]
      - body_half: where the close sits within the bar range
      - volume_ratio: bar volume / trailing-{VOLUME_LOOKBACK_BARS}-bar mean,
        excluding the bar itself. None when volume column missing OR lookback
        would underflow.
      - multi_tf_alignment: {level_id → "with_segment" | "against" | "neutral"}.
        Always contains the primary level (always "with_segment" by trigger
        construction). Foreign-TF entries appear only when their bars were
        passed in and state could be computed.
      - confidence: model-confidence score in [0, 1]; see _confidence() body.
      - context_features: forward-compat extension dict (Z-roadmap analogues
        of DivergenceSignal.context_features). None at v1.4.
    """

    model_config = ConfigDict(extra="forbid")

    level_id: str
    timestamp: datetime
    candidate_bar_idx: int = Field(ge=0)
    direction: Direction
    segment_id: int
    segment_direction: str
    # T1 gate field; informational for downstream consumers wanting to
    # filter at custom maturity thresholds.
    bars_in_segment: int = Field(ge=0)
    # Diagnostic counter retained even though T1 no longer gates on it
    # (calibration: daily segments often complete only 1–2 cycles).
    n_completed_cycles: int = Field(ge=0)
    wick_ratio: float = Field(ge=0.0, le=1.0)
    body_half: BodyHalf
    volume_ratio: float | None
    multi_tf_alignment: dict[str, str]
    confidence: float = Field(ge=0.0, le=1.0)
    context_features: dict[str, float | str] | None = None


def _state_at(
    bars: pd.DataFrame,
    ts: pd.Timestamp,
    level_id: str,
    *,
    grace: pd.Timedelta,
    min_bars: int,
) -> LevelState | None:
    """Slice foreign-TF bars up to ts (+ grace) and compute LevelState.
    Return None when slice is too short or compute fails.

    Mirrors `engine/divergence/multi_tf_context._state_at_signal` but kept
    local to avoid coupling on an underscore-prefixed helper.
    """
    cutoff = ts + grace
    sliced = bars[bars["timestamp"] <= cutoff].reset_index(drop=True)
    if len(sliced) < min_bars:
        return None
    try:
        return compute_level_state(level_id, sliced)
    except Exception:
        return None


def _trend_side_label(trend_side: str, segment_direction: str) -> str:
    """Compare a foreign-TF trend_side string to the primary segment direction.

    Returns 'with_segment' (aligned trending same way), 'against' (opposite),
    or 'neutral' (foreign TF in transition / no clear side).
    """
    if segment_direction == "up":
        if trend_side == "bullish":
            return "with_segment"
        if trend_side == "bearish":
            return "against"
        return "neutral"
    if segment_direction == "down":
        if trend_side == "bearish":
            return "with_segment"
        if trend_side == "bullish":
            return "against"
        return "neutral"
    return "neutral"


def _is_reversal_bar(
    direction: Direction,
    high: float,
    low: float,
    open_px: float,
    close: float,
    min_wick_ratio: float,
) -> tuple[bool, float, BodyHalf]:
    """Return (passes_T3, signal_side_wick_ratio, body_half)."""
    rng = high - low
    if rng <= 0:
        return False, 0.0, "middle"
    mid = (high + low) / 2.0
    body_top = max(open_px, close)
    body_bottom = min(open_px, close)
    if direction == "top":
        wick = high - body_top
        wick_ratio = wick / rng
        passes = wick_ratio >= min_wick_ratio and close < mid
        half: BodyHalf = (
            "lower" if close < mid else ("upper" if close > mid else "middle")
        )
        return passes, max(0.0, min(1.0, wick_ratio)), half
    # bottom
    wick = body_bottom - low
    wick_ratio = wick / rng
    passes = wick_ratio >= min_wick_ratio and close > mid
    half = "upper" if close > mid else ("lower" if close < mid else "middle")
    return passes, max(0.0, min(1.0, wick_ratio)), half


def _confidence(
    bars_in_segment: int,
    min_bars_in_segment: int,
    wick_ratio: float,
    min_wick_ratio: float,
    multi_tf_alignment_strength: float,
    volume_ratio: float | None,
) -> float:
    """Per doc/exhaustion-detector-spec-2026-05-26.md §confidence (with the
    2026-05-27 calibration update: T1 maturity scales on bars_in_segment
    rather than n_completed_cycles, since daily segments rarely accrue
    enough completions to reach the original cap).

    base 0.5
      + 0.10 × min(bars_in_segment / min_bars_in_segment, 5) / 5
      + 0.20 × (wick_ratio − min_wick_ratio) / (1 − min_wick_ratio)
      + 0.10 × multi_tf_alignment_strength
      + 0.10 × min(max(volume_ratio − 1.0, 0), 1.0)   (only when volume known)
    clipped to [0, 1].
    """
    c = 0.5
    if min_bars_in_segment > 0:
        c += 0.10 * min(bars_in_segment / min_bars_in_segment, 5.0) / 5.0
    denom = 1.0 - min_wick_ratio
    if denom > 0:
        c += 0.20 * max(0.0, (wick_ratio - min_wick_ratio)) / denom
    c += 0.10 * multi_tf_alignment_strength
    if volume_ratio is not None:
        c += 0.10 * min(max(volume_ratio - 1.0, 0.0), 1.0)
    return max(0.0, min(1.0, c))


def detect_exhaustion_events(
    primary_bars: pd.DataFrame,
    units_df: pd.DataFrame,
    *,
    level_id: str = "D",
    higher_bars: pd.DataFrame | None = None,
    higher_level_id: str | None = None,
    lower_bars: pd.DataFrame | None = None,
    lower_level_id: str | None = None,
    min_bars_in_segment: int = 20,
    min_wick_ratio: float = 0.4,
    require_volume_climax: bool = False,
    volume_climax_threshold: float = 1.5,
    strict_alignment: bool = True,
    intraday_grace_minutes: int = 0,
    min_bars_for_state: int = 60,
) -> list[ExhaustionEvent]:
    """Scan `primary_bars` for trend-exhaustion candidates.

    Args:
        primary_bars: DataFrame with columns timestamp/open/high/low/close
                      (volume optional). Aligns row-by-row with units_df.
        units_df: output of `engine.units.snapshot.compute_unit_metadata`
                  (segment_id / segment_direction / segment_bars_so_far /
                  cycle_id / cycle_state).
        level_id: primary-TF identifier (e.g. "D"). Stamped on every event.
        higher_bars / higher_level_id: optional super-TF context for T2.
        lower_bars / lower_level_id: optional sub-TF context for T2.
        min_bars_in_segment: T1 maturity gate. Default 20 (daily). Use
            ~50 for hourly and ~200 for 15-minute. Replaces the spec's
            `n_completed_cycles ≥ 3` rule after the 2026-05-27 calibration
            run on 10 US ETFs × 5y showed daily segments almost never
            reach 3 completed cycles before flipping.
        min_wick_ratio: T3 wick-ratio threshold. Default 0.4 (matches
            `score_today.SweetSpotRule` wick threshold; see Z1 calibration).
        require_volume_climax: when True, T5 becomes a hard gate.
        volume_climax_threshold: T5 multiplier vs trailing mean.
        strict_alignment: when True (default), foreign-TF state being
            uncomputable or non-aligned skips the candidate. When False, the
            detector still fires and `multi_tf_alignment_strength` ∈ [0, 1]
            reflects partial alignment.
        intraday_grace_minutes: timestamp slack for lower-TF state lookup;
            0 by default (mirrors the multi-tf timing-leak feedback in
            user memory `feedback-multi-tf-sweet-spot-timing-pitfall`).
        min_bars_for_state: minimum foreign-TF history before a state lookup
            is trusted.

    Returns:
        list[ExhaustionEvent] sorted by candidate_bar_idx ascending.

    Notes:
        - When `primary_bars` is missing any of open/high/low/close the
          function returns an empty list rather than raising (mirrors
          `_candidate_context_features` in detector.py).
        - The detector emits one event per qualifying bar. The same segment
          can yield multiple ExhaustionEvents at different bars (each new
          extreme + reversal-bar combination). Callers wanting "last-only"
          should filter post hoc.
    """
    if "timestamp" not in primary_bars.columns:
        raise ValueError("primary_bars must contain a 'timestamp' column")
    required_ohlc = {"open", "high", "low", "close"}
    if not required_ohlc.issubset(primary_bars.columns):
        return []
    if len(primary_bars) != len(units_df):
        raise ValueError(
            f"primary_bars (len={len(primary_bars)}) and units_df "
            f"(len={len(units_df)}) must align row-by-row"
        )
    if min_bars_in_segment < 0:
        raise ValueError("min_bars_in_segment must be >= 0")
    if not 0.0 <= min_wick_ratio < 1.0:
        raise ValueError("min_wick_ratio must be in [0.0, 1.0)")

    primary = primary_bars.reset_index(drop=True)
    units = units_df.reset_index(drop=True)

    have_volume = "volume" in primary.columns
    volume_arr = primary["volume"].to_numpy() if have_volume else None
    n = len(primary)

    events: list[ExhaustionEvent] = []

    cur_seg_id: int | None = None
    cur_seg_high = float("-inf")
    cur_seg_low = float("inf")
    cur_seg_completed_cycles: set[int] = set()
    # Cycles can span DEA segment boundaries; the row where one becomes
    # "completed" may belong to a different segment than where it started.
    # T1 should only count cycles whose lifecycle is fully contained in the
    # current segment — track origin segment per cycle id to gate completions.
    cycle_origin_segment: dict[int, int] = {}

    for i in range(n):
        urow = units.iloc[i]
        seg_id = int(urow["segment_id"])
        seg_dir = str(urow["segment_direction"])
        cycle_id = int(urow["cycle_id"])
        cycle_state = str(urow["cycle_state"])
        seg_bars = int(urow["segment_bars_so_far"]) if seg_id >= 0 else 0

        if seg_id != cur_seg_id:
            cur_seg_id = seg_id
            cur_seg_high = float("-inf")
            cur_seg_low = float("inf")
            cur_seg_completed_cycles = set()

        if seg_id < 0:
            # Still record cycle origins so that if a cycle straddles a no-segment
            # gap, its first sighting still anchors to the right segment_id.
            if cycle_id >= 0 and cycle_id not in cycle_origin_segment:
                cycle_origin_segment[cycle_id] = seg_id
            continue  # bars outside any segment can't exhaust

        bar = primary.iloc[i]
        bar_high = float(bar["high"])
        bar_low = float(bar["low"])
        cur_seg_high = max(cur_seg_high, bar_high)
        cur_seg_low = min(cur_seg_low, bar_low)

        if cycle_id >= 0:
            if cycle_id not in cycle_origin_segment:
                cycle_origin_segment[cycle_id] = seg_id
            # Count completion only when the cycle originated in this segment.
            if (
                cycle_state == "completed"
                and cycle_origin_segment[cycle_id] == seg_id
            ):
                cur_seg_completed_cycles.add(cycle_id)

        # ---- T1 maturity (bars-based; cycles retained as diagnostic) ----
        if seg_bars < min_bars_in_segment:
            continue
        n_completed = len(cur_seg_completed_cycles)

        # Direction of the predicted reversal
        if seg_dir == "up":
            direction: Direction = "top"
        elif seg_dir == "down":
            direction = "bottom"
        else:
            continue

        # ---- T4 at segment extreme ----
        if direction == "top":
            if bar_high < cur_seg_high - 1e-12:
                continue
        else:
            if bar_low > cur_seg_low + 1e-12:
                continue

        # ---- T3 reversal candle ----
        passes_t3, wick_ratio, body_half = _is_reversal_bar(
            direction=direction,
            high=bar_high,
            low=bar_low,
            open_px=float(bar["open"]),
            close=float(bar["close"]),
            min_wick_ratio=min_wick_ratio,
        )
        if not passes_t3:
            continue

        # ---- T2 multi-TF alignment ----
        ts = bar["timestamp"]
        alignment: dict[str, str] = {level_id: "with_segment"}
        n_aligned = 1
        n_evaluated = 1
        candidate_skipped = False

        if higher_bars is not None and higher_level_id is not None:
            h_state = _state_at(
                higher_bars, ts, higher_level_id,
                grace=pd.Timedelta(0), min_bars=min_bars_for_state,
            )
            if h_state is None:
                if strict_alignment:
                    candidate_skipped = True
                else:
                    # Loose mode: a requested foreign TF that can't be evaluated
                    # is recorded as "neutral" and counted in the denominator
                    # so the candidate doesn't get full credit by omission.
                    alignment[higher_level_id] = "neutral"
                    n_evaluated += 1
            else:
                lbl = _trend_side_label(h_state.trend_side, seg_dir)
                alignment[higher_level_id] = lbl
                n_evaluated += 1
                if lbl == "with_segment":
                    n_aligned += 1
                elif strict_alignment:
                    candidate_skipped = True
        if candidate_skipped:
            continue

        if lower_bars is not None and lower_level_id is not None:
            l_state = _state_at(
                lower_bars, ts, lower_level_id,
                grace=pd.Timedelta(minutes=intraday_grace_minutes),
                min_bars=min_bars_for_state,
            )
            if l_state is None:
                if strict_alignment:
                    candidate_skipped = True
                else:
                    alignment[lower_level_id] = "neutral"
                    n_evaluated += 1
            else:
                lbl = _trend_side_label(l_state.trend_side, seg_dir)
                alignment[lower_level_id] = lbl
                n_evaluated += 1
                if lbl == "with_segment":
                    n_aligned += 1
                elif strict_alignment:
                    candidate_skipped = True
        if candidate_skipped:
            continue

        alignment_strength = n_aligned / n_evaluated if n_evaluated > 0 else 0.0

        # ---- T5 volume confirmation (optional) ----
        # NaN-safe: a missing candidate or trailing-window volume keeps
        # volume_ratio at None so require_volume_climax=True correctly fails,
        # and the confidence bonus skips the bar instead of injecting NaN.
        volume_ratio: float | None = None
        if have_volume and i >= VOLUME_LOOKBACK_BARS:
            cand_vol = float(volume_arr[i])
            trailing = volume_arr[i - VOLUME_LOOKBACK_BARS:i]
            if (
                trailing.size > 0
                and np.isfinite(cand_vol)
                and np.isfinite(trailing).all()
            ):
                mean = float(trailing.mean())
                if mean > 0:
                    volume_ratio = cand_vol / mean
        if require_volume_climax:
            if volume_ratio is None or volume_ratio < volume_climax_threshold:
                continue

        conf = _confidence(
            bars_in_segment=seg_bars,
            min_bars_in_segment=min_bars_in_segment,
            wick_ratio=wick_ratio,
            min_wick_ratio=min_wick_ratio,
            multi_tf_alignment_strength=alignment_strength,
            volume_ratio=volume_ratio,
        )

        ts_dt: datetime
        if isinstance(ts, pd.Timestamp):
            ts_dt = ts.to_pydatetime()
        elif isinstance(ts, datetime):
            ts_dt = ts
        else:
            ts_dt = pd.Timestamp(ts).to_pydatetime()

        events.append(ExhaustionEvent(
            level_id=level_id,
            timestamp=ts_dt,
            candidate_bar_idx=i,
            direction=direction,
            segment_id=int(seg_id),
            segment_direction=seg_dir,
            bars_in_segment=seg_bars,
            n_completed_cycles=n_completed,
            wick_ratio=wick_ratio,
            body_half=body_half,
            volume_ratio=volume_ratio,
            multi_tf_alignment=alignment,
            confidence=conf,
        ))

    return events
