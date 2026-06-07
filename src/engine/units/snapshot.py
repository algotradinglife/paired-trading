"""Unit snapshot output schema + orchestrator.

Combines heap / cycle / segment metadata into a single per-bar snapshot,
mirroring doc/06-vector-units.md §7.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict

from engine.features.streams import DEFAULT_ROLLING_WINDOW
from engine.units.cycles import (
    DEFAULT_DEPARTURE_THRESHOLD,
    DEFAULT_RETURN_CONFIRM_BARS,
    DEFAULT_RETURN_THRESHOLD,
    detect_cycles,
)
from engine.units.heaps import DEFAULT_NEAR_ZERO_HIST_RATIO, detect_heaps
from engine.units.segments import detect_segments

HeapSign = Literal[-1, 0, 1]
CycleState = Literal["at_zero", "in_cycle", "completed"]
SegmentDirection = Literal["up", "down", "none"]


class HeapInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    heap_id: int  # -1 = no heap
    heap_sign: int  # values constrained to {-1, 0, 1} but pydantic int allows any int
    peak_abs_hist: float | None
    bars_in_heap: int
    is_continuous_gap_heap: bool


class CycleInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cycle_id: int  # -1 = no cycle
    state: str  # 'at_zero' / 'in_cycle' / 'completed'
    peak_dif: float | None
    bars_in_cycle: int
    reference_heap_id: int  # -1 if no heap referenced yet


class SegmentInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    segment_id: int  # -1 = no segment (DEA == 0)
    direction: str  # 'up' / 'down' / 'none'
    peak_dif: float | None
    bars_in_segment: int


class UnitSnapshot(BaseModel):
    """All vector-unit metadata at one (level, timestamp)."""

    model_config = ConfigDict(extra="forbid")
    level_id: str
    timestamp: datetime
    is_completed: bool
    heap: HeapInfo
    cycle: CycleInfo
    segment: SegmentInfo


def compute_unit_metadata(
    dif: pd.Series,
    dea: pd.Series,
    hist: pd.Series,
    dif_proximity_zero: pd.Series,
    *,
    near_zero_hist_ratio: float = DEFAULT_NEAR_ZERO_HIST_RATIO,
    rolling_window: int = DEFAULT_ROLLING_WINDOW,
    departure_threshold: float = DEFAULT_DEPARTURE_THRESHOLD,
    return_threshold: float = DEFAULT_RETURN_THRESHOLD,
    return_confirm_bars: int = DEFAULT_RETURN_CONFIRM_BARS,
) -> pd.DataFrame:
    """Compute per-bar metadata for all three vector units.

    Returns a single DataFrame with columns from heaps, cycles, and segments
    merged (each with its own prefix to avoid collision).
    """
    heaps = detect_heaps(
        hist, rolling_window=rolling_window, near_zero_ratio=near_zero_hist_ratio
    )
    segments = detect_segments(dea, dif=dif)
    cycles = detect_cycles(
        dif,
        dif_proximity_zero=dif_proximity_zero,
        heap_metadata=heaps,
        departure_threshold=departure_threshold,
        return_threshold=return_threshold,
        return_confirm_bars=return_confirm_bars,
    )

    # Concatenate; all three DataFrames share the same index
    return pd.concat([heaps, cycles, segments], axis=1)
