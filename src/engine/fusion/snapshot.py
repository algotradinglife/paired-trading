"""MultiTimeframeFusion output schema + end-to-end orchestrator.

Reference: doc/08-multitimeframe-fusion.md §10 (output structure)
           doc/11-output-schema.md §5
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from engine.fusion.alignment import CrossLevelSummary, summarize
from engine.fusion.level_state import LevelState, compute_level_state
from engine.fusion.propagation import (
    FusedLevelState,
    PropagationConfig,
    propagate,
)
from engine.fusion.topology import LevelTopology

DominantTrend = Literal["bullish", "bearish", "mixed"]


class LevelFusionSummary(BaseModel):
    """Per-level fusion result (compact view)."""

    model_config = ConfigDict(extra="forbid")

    level_id: str
    timestamp: datetime
    trend_side: str
    close: float
    dif: float
    dea: float
    hist: float
    ema52: float
    form_confidences_local: dict[str, float]
    form_confidences_fused: dict[str, float]
    sub_level: str | None
    super_level: str | None
    cycle_state: str
    segment_direction: str
    hidden_subtype: str
    near_zero_perfect: bool


class MultiTimeframeFusion(BaseModel):
    """Top-level output: alignment + per-level fusion + primary label."""

    model_config = ConfigDict(extra="forbid")

    system_ts: datetime
    levels: list[LevelFusionSummary]
    alignment_strength: float = Field(ge=0.0, le=1.0)
    dominant_trend: str
    primary_label: str
    primary_confidence: float = Field(ge=0.0, le=1.0)
    secondary_labels: list[tuple[str, float]]


def run_fusion(
    bars_per_level: dict[str, pd.DataFrame],
    topology: LevelTopology,
    *,
    propagation_config: PropagationConfig | None = None,
) -> tuple[
    dict[str, LevelState],
    dict[str, FusedLevelState],
    CrossLevelSummary,
]:
    """End-to-end multi-timeframe fusion.

    Args:
        bars_per_level: mapping level_id → bars DataFrame (must have at minimum
                        timestamp, open, high, low, close).
        topology: ordered topology covering the levels (or a superset).
        propagation_config: bidirectional propagation weights.

    Returns:
        (states, fused, summary)
        - states: per-level LevelState snapshots
        - fused:  per-level FusedLevelState with local + fused form confidences
        - summary: cross-level CrossLevelSummary (alignment + primary label)
    """
    if not bars_per_level:
        raise ValueError("No data provided to run_fusion")

    cfg = propagation_config or PropagationConfig()

    # 1. Compute per-level states
    states = {
        level_id: compute_level_state(level_id, bars)
        for level_id, bars in bars_per_level.items()
    }

    # 2. Propagate bidirectionally
    fused = propagate(states, topology, config=cfg)

    # 3. Cross-level summary
    summary = summarize(states, fused)

    return states, fused, summary


def to_schema(
    states: dict[str, LevelState],
    fused: dict[str, FusedLevelState],
    summary: CrossLevelSummary,
    *,
    system_ts: datetime | None = None,
) -> MultiTimeframeFusion:
    """Convert run_fusion outputs to the pydantic MultiTimeframeFusion schema."""
    if system_ts is None:
        system_ts = datetime.now()

    level_summaries = []
    # Preserve topology-like ordering: by available levels in alignment with input
    for level_id, state in states.items():
        fls = fused[level_id]
        level_summaries.append(
            LevelFusionSummary(
                level_id=level_id,
                timestamp=state.timestamp,
                trend_side=state.trend_side,
                close=state.close,
                dif=state.dif,
                dea=state.dea,
                hist=state.hist,
                ema52=state.ema52,
                form_confidences_local=fls.form_confidences_local,
                form_confidences_fused=fls.form_confidences_fused,
                sub_level=fls.sub_level,
                super_level=fls.super_level,
                cycle_state=state.cycle_state,
                segment_direction=state.segment_direction,
                hidden_subtype=state.hidden_subtype,
                near_zero_perfect=state.near_zero_perfect,
            )
        )

    return MultiTimeframeFusion(
        system_ts=system_ts,
        levels=level_summaries,
        alignment_strength=summary.alignment_strength,
        dominant_trend=summary.dominant_trend,
        primary_label=summary.primary_label,
        primary_confidence=summary.primary_confidence,
        secondary_labels=summary.secondary_labels,
    )
