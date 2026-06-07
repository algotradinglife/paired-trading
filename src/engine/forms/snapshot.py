"""Form snapshot output schema.

Reference: doc/11-output-schema.md §4 (LevelSnapshot.form_confidences) and
doc/05-form-detection.md §6.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

HiddenSubtype = Literal["high", "near_zero", "none"]


class FormConfidences(BaseModel):
    """All 6 form confidences for one bar.

    Each value is a continuous score in [0, 1] except `hidden_subtype` and
    `near_zero_perfect` (categorical / boolean).
    """

    model_config = ConfigDict(extra="forbid")

    high_position: float = Field(ge=0.0, le=1.0)
    high_position_void: float = Field(ge=0.0, le=1.0)

    hidden: float = Field(ge=0.0, le=1.0)
    hidden_subtype: HiddenSubtype

    zero_stick: float = Field(ge=0.0, le=1.0)
    zero_inverted: float = Field(ge=0.0, le=1.0)

    near_zero_axis: float = Field(ge=0.0, le=1.0)
    near_zero_channel_a: float = Field(ge=0.0, le=1.0)
    near_zero_channel_b: float = Field(ge=0.0, le=1.0)
    near_zero_perfect: bool


class FormSnapshot(BaseModel):
    """All form confidences at one (level, timestamp)."""

    model_config = ConfigDict(extra="forbid")

    level_id: str
    timestamp: datetime
    is_completed: bool
    confidences: FormConfidences
