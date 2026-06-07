"""Output schema for the feature-extraction layer.

Reference: doc/04-feature-extraction.md §6

Per-bar snapshot of all 5 base flows + supporting metadata, ready to be
consumed by the form-detection layer.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BaseIndicators(BaseModel):
    """Raw MACD / EMA / close values, for traceability."""

    model_config = ConfigDict(extra="forbid")

    dif: float
    dea: float
    hist: float
    ema12: float
    ema24: float
    ema52: float
    close: float


class FeatureSnapshot(BaseModel):
    """All 5 base observation flows at one (level, timestamp).

    Down-stream form-detection consumes this; nothing else in the engine
    needs to look at raw indicators directly (those live in `base_indicators`
    purely for debugging/auditing).
    """

    model_config = ConfigDict(extra="forbid")

    level_id: str
    timestamp: datetime
    is_completed: bool

    # --- 4 of the 5 flows that produce scalar per-bar values ---
    dif_proximity_zero: float       # [0, 1]
    hist_amplitude_ratio: float     # [0, 1+)
    hist_dif_sign_alignment: int    # {-1, 0, +1}
    price_momentum: float           # real-valued, ~5-bar relative change

    # --- 5th flow exposed as primitive booleans (form layer composes streaks) ---
    hist_decaying_from_peak: bool
    hist_near_zero: bool
    dif_near_zero: bool

    # --- audit trail ---
    base_indicators: BaseIndicators
