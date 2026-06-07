"""Container-level events for divergence detection.

Each completed heap / cycle / segment becomes one event with:
  - identifying ids
  - the amplitude metric (peak |hist| for heaps; peak |DIF| for cycles & segments)
  - K-line price extremes during the container's lifetime (max high, min low)
  - parent container references
  - structural flags (is_continuous_gap_heap)

These events are the inputs to the unified comparator.

Reference: doc/09-divergence-detection.md §1, doc/06-vector-units.md §7
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class HeapEvent:
    """Completed heap with all info needed for intra-cycle divergence."""

    heap_id: int
    sign: int              # +1 or -1
    cycle_id: int          # parent cycle (-1 if outside any cycle)
    segment_id: int        # parent segment (-1 if outside any segment)
    start_idx: int
    end_idx: int
    bars_in_heap: int

    peak_abs_hist: float
    peak_bar_idx: int      # bar index where peak |hist| was reached

    # K-line price extremes within the heap's life
    max_high: float        # max(high) over heap bars
    min_low: float         # min(low) over heap bars

    is_continuous_gap: bool


@dataclass(frozen=True)
class CycleEvent:
    """Completed cycle (or in-progress, with current state)."""

    cycle_id: int
    segment_id: int
    segment_direction: str  # 'up' / 'down' / 'none' — inherited from parent segment
    start_idx: int
    end_idx: int
    bars_in_cycle: int

    peak_abs_dif: float
    peak_bar_idx: int      # bar where |DIF| was max
    reference_heap_id: int  # 1号参考点 at cycle end

    max_high: float
    min_low: float

    is_completed: bool     # True if cycle had a confirmed completion


@dataclass(frozen=True)
class SegmentEvent:
    """Completed segment (or in-progress)."""

    segment_id: int
    direction: str         # 'up' or 'down'
    start_idx: int
    end_idx: int
    bars_in_segment: int

    peak_abs_dif: float
    peak_bar_idx: int

    max_high: float
    min_low: float

    is_completed: bool


# ---------------------------------------------------------------------------
# Event builders
# ---------------------------------------------------------------------------

def _reset_positional(*frames):
    """Reset index on each input so subsequent .loc[i] and .iloc[i] are interchangeable.
    Event start_idx / end_idx / peak_bar_idx are stored as 0..N-1 positions; downstream
    consumers (detector.py, backtests) use them with .iloc."""
    return tuple(f.reset_index(drop=True) for f in frames)


def build_heap_events(
    units_df: pd.DataFrame,
    ohlc: pd.DataFrame,
    hist: pd.Series,
) -> list[HeapEvent]:
    """Collapse per-bar heap metadata into HeapEvent list.

    `ohlc` must have columns: high, low.
    """
    units_df, ohlc, hist = _reset_positional(units_df, ohlc, hist)
    valid = units_df[units_df["heap_id"] >= 0]
    if valid.empty:
        return []

    events: list[HeapEvent] = []
    for heap_id, group in valid.groupby("heap_id", sort=True):
        idxs = group.index
        sign = int(group["heap_sign"].iloc[0])
        cycle_id = int(group["cycle_id"].iloc[0])
        segment_id = int(group["segment_id"].iloc[0])
        peak_abs_hist = float(group["heap_peak_so_far"].iloc[-1])
        is_gap = bool(group["is_continuous_gap_heap"].iloc[-1])

        # Bar where peak was reached (RangeIndex after reset, so label == position)
        abs_hist_local = hist.loc[idxs].abs()
        peak_bar_idx = int(abs_hist_local.idxmax())

        max_high = float(ohlc.loc[idxs, "high"].max())
        min_low = float(ohlc.loc[idxs, "low"].min())

        events.append(
            HeapEvent(
                heap_id=int(heap_id),
                sign=sign,
                cycle_id=cycle_id,
                segment_id=segment_id,
                start_idx=int(idxs[0]),
                end_idx=int(idxs[-1]),
                bars_in_heap=len(group),
                peak_abs_hist=peak_abs_hist,
                peak_bar_idx=peak_bar_idx,
                max_high=max_high,
                min_low=min_low,
                is_continuous_gap=is_gap,
            )
        )
    return events


def build_cycle_events(
    units_df: pd.DataFrame,
    ohlc: pd.DataFrame,
    dif: pd.Series,
) -> list[CycleEvent]:
    """Collapse per-bar cycle metadata into CycleEvent list."""
    units_df, ohlc, dif = _reset_positional(units_df, ohlc, dif)
    valid = units_df[units_df["cycle_id"] >= 0]
    if valid.empty:
        return []

    events: list[CycleEvent] = []
    for cycle_id, group in valid.groupby("cycle_id", sort=True):
        idxs = group.index
        segment_id = int(group["segment_id"].iloc[0])
        segment_direction = str(group["segment_direction"].iloc[0])
        peak_abs_dif = float(group["cycle_peak_dif_so_far"].iloc[-1])
        ref_heap = int(group["cycle_reference_heap_id"].iloc[-1])
        is_completed = bool((group["cycle_state"] == "completed").any())

        abs_dif_local = dif.loc[idxs].abs()
        peak_bar_idx = int(abs_dif_local.idxmax())

        max_high = float(ohlc.loc[idxs, "high"].max())
        min_low = float(ohlc.loc[idxs, "low"].min())

        events.append(
            CycleEvent(
                cycle_id=int(cycle_id),
                segment_id=segment_id,
                segment_direction=segment_direction,
                start_idx=int(idxs[0]),
                end_idx=int(idxs[-1]),
                bars_in_cycle=len(group),
                peak_abs_dif=peak_abs_dif,
                peak_bar_idx=peak_bar_idx,
                reference_heap_id=ref_heap,
                max_high=max_high,
                min_low=min_low,
                is_completed=is_completed,
            )
        )
    return events


def build_segment_events(
    units_df: pd.DataFrame,
    ohlc: pd.DataFrame,
    dif: pd.Series,
) -> list[SegmentEvent]:
    """Collapse per-bar segment metadata into SegmentEvent list."""
    units_df, ohlc, dif = _reset_positional(units_df, ohlc, dif)
    valid = units_df[units_df["segment_id"] >= 0]
    if valid.empty:
        return []

    events: list[SegmentEvent] = []
    all_ids = sorted(valid["segment_id"].unique())
    max_seg_id = int(np.max(all_ids))

    for segment_id, group in valid.groupby("segment_id", sort=True):
        idxs = group.index
        direction = str(group["segment_direction"].iloc[0])
        peak_abs_dif = float(group["segment_peak_dif_so_far"].iloc[-1])

        abs_dif_local = dif.loc[idxs].abs()
        peak_bar_idx = int(abs_dif_local.idxmax())

        max_high = float(ohlc.loc[idxs, "high"].max())
        min_low = float(ohlc.loc[idxs, "low"].min())

        # A segment is "completed" if it's not the last one in the series
        is_completed = int(segment_id) < max_seg_id

        events.append(
            SegmentEvent(
                segment_id=int(segment_id),
                direction=direction,
                start_idx=int(idxs[0]),
                end_idx=int(idxs[-1]),
                bars_in_segment=len(group),
                peak_abs_dif=peak_abs_dif,
                peak_bar_idx=peak_bar_idx,
                max_high=max_high,
                min_low=min_low,
                is_completed=is_completed,
            )
        )
    return events
