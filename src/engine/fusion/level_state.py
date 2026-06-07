"""LevelState — per-timeframe latest-bar snapshot for fusion.

Each timeframe runs the full pipeline (features → forms → units → divergence)
independently. LevelState collects the latest-bar essentials from that pipeline
into a compact object that the fusion layer can consume.

Reference: doc/08-multitimeframe-fusion.md §2 (propagation inputs)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import pandas as pd

from engine.divergence.detector import detect_all_divergences
from engine.divergence.signal import DivergenceSignal
from engine.features.macd import macd, overlay_emas
from engine.features.streams import compute_feature_streams
from engine.forms.detectors import compute_form_confidences
from engine.units.snapshot import compute_unit_metadata

TrendSide = Literal["bullish", "bearish", "transition"]


@dataclass(frozen=True)
class LevelState:
    """Latest-bar snapshot for one timeframe."""

    level_id: str
    timestamp: datetime
    is_completed: bool

    # Form confidences (subset of doc/05 §6)
    form_confidences: dict[str, float] = field(default_factory=dict)
    hidden_subtype: str = "none"
    near_zero_perfect: bool = False

    # Trend classification
    trend_side: TrendSide = "transition"

    # Latest unit attribution
    heap_id: int = -1
    heap_sign: int = 0
    cycle_id: int = -1
    cycle_state: str = "at_zero"
    cycle_reference_heap_id: int = -1
    segment_id: int = -1
    segment_direction: str = "none"

    # Most-recent divergence signal on this level (highest-confidence, any age)
    most_recent_divergence: DivergenceSignal | None = None
    strongest_divergence: DivergenceSignal | None = None

    # Raw indicator values (for traceability)
    close: float = 0.0
    dif: float = 0.0
    dea: float = 0.0
    hist: float = 0.0
    ema52: float = 0.0


def _classify_trend(dif: float, dea: float) -> TrendSide:
    """Trend side per doc/04: multi-方 when both above zero; vice versa."""
    if dif > 0 and dea > 0:
        return "bullish"
    if dif < 0 and dea < 0:
        return "bearish"
    return "transition"


def compute_level_state(
    level_id: str,
    bars: pd.DataFrame,
    *,
    is_completed: bool = True,
) -> LevelState:
    """Run the full single-timeframe pipeline and emit a LevelState snapshot
    for the LAST bar of `bars`.

    `bars` requires columns: timestamp, open, high, low, close, volume.
    """
    if bars.empty:
        raise ValueError(f"No bars provided for level {level_id}")

    close = bars["close"]
    macd_df = macd(close, hist_scale=1.0)
    ema_df = overlay_emas(close)
    streams = compute_feature_streams(close, macd_df["dif"], macd_df["dea"], macd_df["hist"])
    forms = compute_form_confidences(streams, close, ema_df["ema52"])
    units = compute_unit_metadata(
        macd_df["dif"], macd_df["dea"], macd_df["hist"], streams["dif_proximity_zero"]
    )

    signals = detect_all_divergences(
        units_df=units,
        ohlc=bars,
        dif=macd_df["dif"],
        hist=macd_df["hist"],
        level_id=level_id,
    )

    # Last bar
    last = bars.iloc[-1]
    last_macd = macd_df.iloc[-1]
    last_ema = ema_df.iloc[-1]
    last_forms = forms.iloc[-1]
    last_units = units.iloc[-1]

    most_recent = signals[-1] if signals else None
    strongest = max(signals, key=lambda s: s.confidence) if signals else None

    return LevelState(
        level_id=level_id,
        timestamp=last["timestamp"].to_pydatetime(),
        is_completed=is_completed,
        form_confidences={
            "high_position": float(last_forms["high_position"]),
            "high_position_void": float(last_forms["high_position_void"]),
            "hidden": float(last_forms["hidden"]),
            "zero_stick": float(last_forms["zero_stick"]),
            "zero_inverted": float(last_forms["zero_inverted"]),
            "near_zero_axis": float(last_forms["near_zero_axis"]),
        },
        hidden_subtype=str(last_forms["hidden_subtype"]),
        near_zero_perfect=bool(last_forms["near_zero_perfect"]),
        trend_side=_classify_trend(float(last_macd["dif"]), float(last_macd["dea"])),
        heap_id=int(last_units["heap_id"]),
        heap_sign=int(last_units["heap_sign"]),
        cycle_id=int(last_units["cycle_id"]),
        cycle_state=str(last_units["cycle_state"]),
        cycle_reference_heap_id=int(last_units["cycle_reference_heap_id"]),
        segment_id=int(last_units["segment_id"]),
        segment_direction=str(last_units["segment_direction"]),
        most_recent_divergence=most_recent,
        strongest_divergence=strongest,
        close=float(last["close"]),
        dif=float(last_macd["dif"]),
        dea=float(last_macd["dea"]),
        hist=float(last_macd["hist"]),
        ema52=float(last_ema["ema52"]),
    )
