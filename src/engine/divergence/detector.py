"""Divergence detector orchestrator.

Iterates through completed containers (heaps within cycles for intra-cycle;
cycles within segments for inter-cycle; segments for inter-segment) and
applies the unified comparator. Emits DivergenceSignal events.

Reference: doc/09-divergence-detection.md §9 (decision flow)
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from engine.divergence.comparator import compare
from engine.divergence.direction_gate import gate_signals
from engine.divergence.events import (
    CycleEvent,
    HeapEvent,
    SegmentEvent,
    build_cycle_events,
    build_heap_events,
    build_segment_events,
)
from engine.divergence.dea_div import detect_dea_divergence
from engine.divergence.dea_div_bull import detect_dea_bull_divergence
from engine.divergence.dif_slope import detect_dif_slope_reversal
from engine.divergence.dif_slope_bull import detect_dif_bull_slope_reversal
from engine.divergence.hicd import detect_histogram_divergence
from engine.divergence.hicd_bull import detect_histogram_bull_divergence
from engine.divergence.signal import (
    AmplitudeSide,
    DivergenceSignal,
    PriceSide,
)


def _heap_direction(heap: HeapEvent) -> str:
    """A heap with positive sign generates top-divergence candidates; negative → bottom."""
    return "top" if heap.sign > 0 else "bottom"


def _segment_direction(segment: SegmentEvent) -> str:
    """Map segment.direction to comparator direction."""
    return "top" if segment.direction == "up" else "bottom"


def _ts(idx: int, df: pd.DataFrame) -> datetime:
    return df["timestamp"].iloc[idx].to_pydatetime()


VOLUME_LOOKBACK_BARS = 20


def _candidate_context_features(
    direction: str,
    container_start_idx: int,
    container_end_idx: int,
    ohlc: pd.DataFrame,
    *,
    reference_price: float | None = None,
) -> dict[str, float] | None:
    """Compute candle-geometry features on the bar that produced the price extreme.

    Z1 (2026-05-25): `candidate_rejection_wick_ratio` — proportion of the
    bar's total range occupied by the wick on the *signal-direction* side.
    For a top, the upper wick on the bar with max(high); for a bottom, the
    lower wick on the bar with min(low).

    Z2a (2026-05-25): `invalidation_level` — the raw price that, if broken
    in the signal direction, structurally invalidates the setup. For a top
    that's the extreme bar's high (price went BACK above the rejection);
    for a bottom, the extreme bar's low. Consumer adds their own tick or %
    buffer; engine doesn't assume per-instrument tick size.

    Z2b (2026-05-25): `prior_swing_distance_pct` — signed percent distance
    from the reference container's price extreme to the candidate's price
    extreme. Positive for a top divergence (rally continued upward), or
    negative if compare emitted "weakness" on a degenerate new-extreme
    case. Consumer uses this for Brooks-style measured-move projection
    (next leg ≈ this leg's magnitude) and split-take ladder sizing.

    Z3 (2026-05-25): `candidate_volume_ratio` — ratio of the extreme bar's
    volume to the trailing-{VOLUME_LOOKBACK_BARS}-bar mean (exclusive of
    the extreme bar itself). Above 1.0 = above-average volume (Brooks
    "signal bar with above-average volume" — highest-quality reversal).
    Skipped when `volume` column missing or lookback would underflow.

    NOTE: extreme bar is NOT necessarily the container's last bar. For
    multi-bar candidates (typical for heaps/cycles/segments) the price
    extreme may have occurred mid-container while the container closes
    elsewhere (codex 2026-05-25 review).

    Requires `open` and `close` columns. If absent (legacy ohlc frames
    only carrying high/low) returns None — consumer sees no features
    rather than a misleading zero.
    """
    if "open" not in ohlc.columns or "close" not in ohlc.columns:
        return None
    if container_start_idx > container_end_idx:
        # Defensive: empty / inverted range — emit no features rather than crash
        return None

    window = ohlc.iloc[container_start_idx:container_end_idx + 1]
    # NaN-safe extreme selection: numpy argmax/argmin treat NaN as max, so a
    # single missing bar in the window would mis-select. nanargmax/nanargmin
    # match the comparator's pandas behavior (NaN-skipped). All-NaN windows
    # → no features (don't fabricate a ratio from corrupt data).
    if direction == "top":
        values = window["high"].to_numpy(dtype=float)
    else:
        values = window["low"].to_numpy(dtype=float)
    if np.isnan(values).all():
        return None
    if direction == "top":
        extreme_pos = int(np.nanargmax(values))
    else:
        extreme_pos = int(np.nanargmin(values))
    extreme_bar = window.iloc[extreme_pos]
    # Check for missing values BEFORE float conversion: pandas nullable dtypes
    # (Float64, etc.) emit pd.NA, and float(pd.NA) raises TypeError. pd.isna
    # covers both numpy NaN and pd.NA.
    raw = (extreme_bar["high"], extreme_bar["low"], extreme_bar["open"], extreme_bar["close"])
    if any(pd.isna(v) for v in raw):
        return None
    high = float(raw[0])
    low = float(raw[1])
    open_ = float(raw[2])
    close = float(raw[3])
    rng = high - low

    # Z1: rejection wick
    if rng <= 0:
        wick_ratio = 0.0
    elif direction == "top":
        wick = high - max(open_, close)
        wick_ratio = max(0.0, min(1.0, wick / rng))
    else:
        wick = min(open_, close) - low
        wick_ratio = max(0.0, min(1.0, wick / rng))

    feats: dict[str, float] = {"candidate_rejection_wick_ratio": wick_ratio}

    # Z2a: invalidation_level — the raw price the setup needs to hold above
    # (for tops) or below (for bottoms). Consumer adds their own tick buffer.
    feats["invalidation_level"] = high if direction == "top" else low

    # Z2b: prior_swing_distance_pct — % distance from reference price to
    # candidate's extreme. Signed (positive = direction consistent with
    # rally/decline extension). Skipped when caller doesn't supply a
    # reference (would yield divide-by-zero on degenerate refs anyway).
    if reference_price is not None:
        ref = float(reference_price)
        if ref > 0 and not (np.isnan(ref) or ref == 0.0):
            extreme_price = high if direction == "top" else low
            # Sign convention: for top, candidate above reference = positive
            # (rally extended). For bottom, candidate below reference = positive
            # (decline extended) — flip via direction sign.
            raw_delta = (extreme_price - ref) / ref * 100.0
            feats["prior_swing_distance_pct"] = raw_delta if direction == "top" else -raw_delta

    # Z3: candidate_volume_ratio — extreme bar's volume / trailing-N-bar mean.
    # Skipped when volume column missing, when lookback would reach before
    # bar 0 (insufficient history), or when the lookback mean is 0/NaN.
    # Locate the absolute index of the extreme bar (window.iloc → reset positions).
    extreme_abs_idx = container_start_idx + extreme_pos
    if "volume" in ohlc.columns and extreme_abs_idx >= VOLUME_LOOKBACK_BARS:
        lookback_slice = ohlc["volume"].iloc[
            extreme_abs_idx - VOLUME_LOOKBACK_BARS:extreme_abs_idx
        ]
        try:
            lb_values = lookback_slice.to_numpy(dtype=float)
            cand_vol_raw = ohlc["volume"].iloc[extreme_abs_idx]
        except (TypeError, ValueError):
            lb_values = None
            cand_vol_raw = None
        if lb_values is not None and cand_vol_raw is not None and not pd.isna(cand_vol_raw):
            lb_mean = float(np.nanmean(lb_values)) if np.any(~np.isnan(lb_values)) else 0.0
            cand_vol = float(cand_vol_raw)
            if lb_mean > 0 and not np.isnan(lb_mean) and not np.isnan(cand_vol):
                feats["candidate_volume_ratio"] = cand_vol / lb_mean

    return feats


# ---------------------------------------------------------------------------
# Intra-cycle: heap vs heap within the same cycle
# ---------------------------------------------------------------------------

def detect_intra_cycle(
    heap_events: list[HeapEvent],
    level_id: str,
    df: pd.DataFrame,
) -> list[DivergenceSignal]:
    """For each cycle, walk same-sign heaps in order; emit signals when current
    candidate doesn't exceed the running reference."""
    signals: list[DivergenceSignal] = []

    # Group heaps by (cycle_id, sign)
    heaps_by_cycle_sign: dict[tuple[int, int], list[HeapEvent]] = {}
    for h in heap_events:
        if h.cycle_id < 0:
            continue
        key = (h.cycle_id, h.sign)
        heaps_by_cycle_sign.setdefault(key, []).append(h)

    for (cycle_id, sign), heaps in heaps_by_cycle_sign.items():
        heaps_sorted = sorted(heaps, key=lambda h: h.start_idx)
        if len(heaps_sorted) < 2:
            continue
        direction = "top" if sign > 0 else "bottom"

        # Reference = first heap; updated on non-divergence
        reference = heaps_sorted[0]
        for candidate in heaps_sorted[1:]:
            price_ref = reference.max_high if direction == "top" else reference.min_low
            price_cand = candidate.max_high if direction == "top" else candidate.min_low

            result = compare(
                direction=direction,
                amplitude_ref=reference.peak_abs_hist,
                amplitude_cand=candidate.peak_abs_hist,
                price_extreme_ref=price_ref,
                price_extreme_cand=price_cand,
            )

            if result.subtype == "non_divergence":
                # Candidate exceeds reference → reset
                reference = candidate
                continue
            if result.subtype in ("standard", "weakness", "hidden"):
                signals.append(
                    DivergenceSignal(
                        level="intra_cycle",
                        subtype=result.subtype,
                        direction=direction,
                        level_id=level_id,
                        timestamp=_ts(candidate.end_idx, df),
                        candidate_bar_idx=candidate.end_idx,
                        reference_bar_idx=reference.peak_bar_idx,
                        container_type="heap",
                        container_segment_id=candidate.segment_id,
                        reference_id=reference.heap_id,
                        candidate_id=candidate.heap_id,
                        price_side=PriceSide(
                            reference_value=price_ref,
                            candidate_value=price_cand,
                            is_new_extreme=result.is_new_price_extreme,
                        ),
                        amplitude_side=AmplitudeSide(
                            reference_value=reference.peak_abs_hist,
                            candidate_value=candidate.peak_abs_hist,
                            decay_ratio=result.decay_ratio,
                        ),
                        confidence=result.confidence,
                        is_continuous_gap=candidate.is_continuous_gap,
                        context_features=_candidate_context_features(
                            direction, candidate.start_idx, candidate.end_idx, df,
                            reference_price=price_ref,
                        ),
                    )
                )

    return signals


# ---------------------------------------------------------------------------
# Inter-cycle: cycle vs cycle within the same segment
# ---------------------------------------------------------------------------

def detect_inter_cycle(
    cycle_events: list[CycleEvent],
    level_id: str,
    df: pd.DataFrame,
) -> list[DivergenceSignal]:
    """Compare consecutive cycles within the same segment using segment direction.

    Only emits signals for cycle pairs where BOTH cycles are completed —
    avoids premature signals from an in-progress cycle.
    """
    signals: list[DivergenceSignal] = []

    # Group cycles by segment_id, ignoring cycles outside any segment
    cycles_by_segment: dict[int, list[CycleEvent]] = {}
    for c in cycle_events:
        if c.segment_id < 0:
            continue
        cycles_by_segment.setdefault(c.segment_id, []).append(c)

    for segment_id, cycles in cycles_by_segment.items():
        cycles_sorted = sorted(cycles, key=lambda c: c.start_idx)
        if len(cycles_sorted) < 2:
            continue

        # Direction comes from the segment, not from trial-and-error price compare:
        #   up-segment (DEA > 0)   → search for top divergence (peaks weakening)
        #   down-segment (DEA < 0) → search for bottom divergence (troughs weakening)
        # All cycles in a group share segment_id and segment_direction.
        seg_dir = cycles_sorted[0].segment_direction
        if seg_dir == "up":
            direction = "top"
        elif seg_dir == "down":
            direction = "bottom"
        else:
            # 'none' — DEA crossing or undefined; no direction to compare on
            continue

        reference = cycles_sorted[0]
        for candidate in cycles_sorted[1:]:
            # Both reference and candidate must be completed before we trust the comparison.
            # An in-progress cycle's peak/extremes are not final.
            if not (reference.is_completed and candidate.is_completed):
                continue
            price_ref = reference.max_high if direction == "top" else reference.min_low
            price_cand = candidate.max_high if direction == "top" else candidate.min_low

            result = compare(
                direction=direction,
                amplitude_ref=reference.peak_abs_dif,
                amplitude_cand=candidate.peak_abs_dif,
                price_extreme_ref=price_ref,
                price_extreme_cand=price_cand,
            )
            if result.subtype == "non_divergence":
                reference = candidate
                continue
            if result.subtype in ("standard", "weakness", "hidden"):
                signals.append(
                    DivergenceSignal(
                        level="inter_cycle",
                        subtype=result.subtype,
                        direction=direction,
                        level_id=level_id,
                        timestamp=_ts(candidate.end_idx, df),
                        candidate_bar_idx=candidate.end_idx,
                        reference_bar_idx=reference.peak_bar_idx,
                        container_type="cycle",
                        container_segment_id=segment_id,
                        reference_id=reference.cycle_id,
                        candidate_id=candidate.cycle_id,
                        price_side=PriceSide(
                            reference_value=price_ref,
                            candidate_value=price_cand,
                            is_new_extreme=result.is_new_price_extreme,
                        ),
                        amplitude_side=AmplitudeSide(
                            reference_value=reference.peak_abs_dif,
                            candidate_value=candidate.peak_abs_dif,
                            decay_ratio=result.decay_ratio,
                        ),
                        confidence=result.confidence,
                        context_features=_candidate_context_features(
                            direction, candidate.start_idx, candidate.end_idx, df,
                            reference_price=price_ref,
                        ),
                    )
                )

    return signals


# ---------------------------------------------------------------------------
# Inter-segment: segment vs segment
# ---------------------------------------------------------------------------

def detect_inter_segment(
    segment_events: list[SegmentEvent],
    level_id: str,
    df: pd.DataFrame,
) -> list[DivergenceSignal]:
    """Compare consecutive same-direction segments.

    Note: doc/09 §4 says inter-segment divergence applies after a time-level
    upgrade. We don't yet have upgrade detection; here we simply compare
    consecutive same-direction segments as a baseline.
    """
    signals: list[DivergenceSignal] = []

    # Group by direction
    by_direction: dict[str, list[SegmentEvent]] = {"up": [], "down": []}
    for s in segment_events:
        if s.direction in by_direction:
            by_direction[s.direction].append(s)

    for direction_str, segs in by_direction.items():
        if len(segs) < 2:
            continue
        segs_sorted = sorted(segs, key=lambda s: s.start_idx)
        comparator_direction = "top" if direction_str == "up" else "bottom"
        reference = segs_sorted[0]
        for candidate in segs_sorted[1:]:
            # Both segments must be completed; the most recent segment is typically
            # still in progress and shouldn't trigger inter-segment signals yet.
            if not (reference.is_completed and candidate.is_completed):
                continue
            price_ref = reference.max_high if comparator_direction == "top" else reference.min_low
            price_cand = candidate.max_high if comparator_direction == "top" else candidate.min_low

            result = compare(
                direction=comparator_direction,
                amplitude_ref=reference.peak_abs_dif,
                amplitude_cand=candidate.peak_abs_dif,
                price_extreme_ref=price_ref,
                price_extreme_cand=price_cand,
            )
            if result.subtype == "non_divergence":
                reference = candidate
                continue
            if result.subtype in ("standard", "weakness", "hidden"):
                signals.append(
                    DivergenceSignal(
                        level="inter_segment",
                        subtype=result.subtype,
                        direction=comparator_direction,
                        level_id=level_id,
                        timestamp=_ts(candidate.end_idx, df),
                        candidate_bar_idx=candidate.end_idx,
                        reference_bar_idx=reference.peak_bar_idx,
                        container_type="segment",
                        container_segment_id=candidate.segment_id,
                        reference_id=reference.segment_id,
                        candidate_id=candidate.segment_id,
                        price_side=PriceSide(
                            reference_value=price_ref,
                            candidate_value=price_cand,
                            is_new_extreme=result.is_new_price_extreme,
                        ),
                        amplitude_side=AmplitudeSide(
                            reference_value=reference.peak_abs_dif,
                            candidate_value=candidate.peak_abs_dif,
                            decay_ratio=result.decay_ratio,
                        ),
                        confidence=result.confidence,
                        context_features=_candidate_context_features(
                            comparator_direction, candidate.start_idx, candidate.end_idx, df,
                            reference_price=price_ref,
                        ),
                    )
                )

    return signals


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def detect_all_divergences(
    units_df: pd.DataFrame,
    ohlc: pd.DataFrame,
    dif: pd.Series,
    hist: pd.Series,
    *,
    level_id: str = "1D",
    instrument_class: str = "us_equity",
    gate: bool = True,
) -> list[DivergenceSignal]:
    """Build all events and run all three divergence detectors.

    `ohlc` is the bar DataFrame containing at minimum: timestamp, high, low.

    `instrument_class` controls the direction_gate calibration:
      - "us_equity" (default): apply US-tuned top de-weight multipliers
      - "cn_futures": pass-through (no top de-weight) — CN tops are
        empirically positive, US calibration over-penalizes

    `gate=False` returns the raw pre-direction-gate signals — used by the
    alert layer (engine/divergence/alert_chain.py), which needs top signals
    at raw confidence. Production callers keep the default gate=True.
    """
    # Normalize all inputs to a 0..N-1 RangeIndex so event start_idx / end_idx /
    # peak_bar_idx (returned by builders) are interchangeable with iloc positions
    # used downstream (_ts, candidate_bar_idx in DivergenceSignal, backtest scripts).
    units_df = units_df.reset_index(drop=True)
    ohlc = ohlc.reset_index(drop=True)
    dif = dif.reset_index(drop=True)
    hist = hist.reset_index(drop=True)

    heap_events = build_heap_events(units_df, ohlc, hist)
    cycle_events = build_cycle_events(units_df, ohlc, dif)
    segment_events = build_segment_events(units_df, ohlc, dif)

    signals: list[DivergenceSignal] = []
    signals += detect_intra_cycle(heap_events, level_id, ohlc)
    signals += detect_inter_cycle(cycle_events, level_id, ohlc)
    signals += detect_inter_segment(segment_events, level_id, ohlc)
    signals += detect_histogram_divergence(ohlc, dif, hist, level_id=level_id)
    signals += detect_dif_slope_reversal(ohlc, dif, hist, level_id=level_id)
    signals += detect_dea_divergence(ohlc, dif, hist, level_id=level_id)
    signals += detect_histogram_bull_divergence(ohlc, dif, hist, level_id=level_id)
    signals += detect_dif_bull_slope_reversal(ohlc, dif, hist, level_id=level_id)
    signals += detect_dea_bull_divergence(ohlc, dif, hist, level_id=level_id)

    if gate:
        signals = gate_signals(signals, instrument_class=instrument_class)
    signals.sort(key=lambda s: (s.candidate_bar_idx, s.level))
    return signals
