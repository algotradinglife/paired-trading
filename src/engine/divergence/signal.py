"""DivergenceSignal output schema.

Reference: doc/09-divergence-detection.md §10, doc/11-output-schema.md §6
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DivergenceLevel = Literal[
    "intra_cycle",
    "inter_cycle",
    "inter_segment",
    "intra_cycle_hist",       # HICD:  histogram recovery within one DIF < 0 cycle
    "intra_cycle_slope",      # DIFSR: DIF slope reversal within one DIF < 0 cycle
    "intra_cycle_dea",        # DEAD:  DEA slope reversal within one DIF < 0 cycle
    "intra_cycle_bull_hist",  # HICD+: histogram recovery within one DIF > 0 cycle
    "intra_cycle_bull_slope", # DIFSR+: DIF slope reversal within one DIF > 0 cycle
    "intra_cycle_bull_dea",   # DEAD+: DEA slope reversal within one DIF > 0 cycle
]
DivergenceSubtype = Literal["standard", "weakness", "hidden"]
Direction = Literal["top", "bottom"]
ContainerType = Literal["heap", "cycle", "segment", "histogram", "dif", "dea"]


class PriceSide(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference_value: float
    candidate_value: float
    is_new_extreme: bool


class AmplitudeSide(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference_value: float
    candidate_value: float
    decay_ratio: float


class DivergenceSignal(BaseModel):
    """One detected divergence event.

    Each emitted on completion of a candidate container that, compared with
    its reference, produces a non-trivial result (standard / weakness / hidden).
    Non-divergence events (candidate exceeds reference) trigger reference
    resets internally — they're not emitted as signals.
    """

    model_config = ConfigDict(extra="forbid")

    level: DivergenceLevel
    subtype: DivergenceSubtype
    direction: Direction

    level_id: str                          # e.g. "1D" — which timeframe this is on
    timestamp: datetime                     # candidate event's last bar
    candidate_bar_idx: int                  # bar index where candidate ended
    reference_bar_idx: int                  # bar index where reference's peak was

    container_type: ContainerType
    container_segment_id: int               # which segment we're in (same for both)
    reference_id: int                        # heap/cycle/segment id of reference
    candidate_id: int                        # heap/cycle/segment id of candidate

    price_side: PriceSide
    amplitude_side: AmplitudeSide

    confidence: float = Field(ge=0.0, le=1.0)

    is_continuous_gap: bool | None = None    # for intra-cycle heaps; None for higher levels

    # Optional multi-timeframe context tag, attached by `enrich_with_lower_tf`
    # (engine/divergence/multi_tf_context.py). Does NOT modify confidence —
    # downstream consumers weight as they see fit. None when no context attached.
    multi_tf_context: dict[str, str] | None = None

    # Optional candle-geometry / price-action annotations on the bar that
    # produced the price extreme (NOT necessarily the container's last bar).
    # Open-ended numeric dict; each detector emit path populates the keys it
    # knows about. Does NOT modify confidence — consumers layer their own
    # weighting. v1.3 keys:
    #   candidate_rejection_wick_ratio: float ∈ [0, 1]
    #     For top: upper wick / total bar range; for bottom: lower wick / range.
    #     Higher = stronger visible rejection.
    #   invalidation_level: float (raw price)
    #     For top: extreme bar's high. For bottom: extreme bar's low.
    #     Setup fails if price re-prints beyond this on the signal side.
    #     Direct input to tip-stop placement (consumer adds tick/% buffer).
    #   prior_swing_distance_pct: float (signed percent)
    #     For top: (candidate_extreme − reference_extreme) / reference × 100,
    #     positive when rally extended further. For bottom: sign-flipped so
    #     positive means decline extended further (direction-consistent).
    #     Direct input to measured-move target projection. Key absent when
    #     no reference price was supplied (degenerate divergence cases).
    #   candidate_volume_ratio: float (positive ratio)
    #     Extreme bar's volume / trailing-20-bar mean. Above 1.0 = above-
    #     average volume; below 1.0 = below average. Brooks: signal bars
    #     with above-average volume are higher-quality reversals. Key
    #     absent when volume column missing or lookback would underflow.
    # Future keys (Z4 in roadmap) may extend this dict; consumers should
    # ignore unknown keys.
    context_features: dict[str, float] | None = None
