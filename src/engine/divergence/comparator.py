"""Unified comparator: reference vs candidate container event.

Same code works for all three divergence levels because the inputs share a
common shape (amplitude + price-extreme + identity). The level dimension
(heap / cycle / segment) is just a label on the event objects.

Reference: doc/09-divergence-detection.md §1 (statement of universality)
           doc/09-divergence-detection.md §4 (comparison logic)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

Direction = Literal["top", "bottom"]
DivergenceSubtype = Literal[
    "standard",       # price broke prior extreme + amplitude decayed
    "weakness",       # price did NOT break + amplitude decayed (动能不足)
    "hidden",         # amplitude ≈ 0 (隐形)
    "non_divergence",  # candidate exceeds reference — should reset reference, no signal
    "none",            # nothing notable
]


@dataclass(frozen=True)
class ComparisonResult:
    """Single comparison outcome (reference vs candidate)."""

    subtype: DivergenceSubtype
    direction: Direction

    is_new_price_extreme: bool
    amplitude_ref: float
    amplitude_cand: float
    decay_ratio: float            # (ref - cand) / ref; positive when decaying
    is_hidden: bool                # amplitude very small relative to reference

    # Soft scoring components (each in [0, 1])
    score_price_break: float
    score_amplitude_decay: float
    score_hidden: float
    confidence: float              # final composite score [0, 1]


# ---------------------------------------------------------------------------
# Comparator
# ---------------------------------------------------------------------------

# Default thresholds (cf. doc/12)
DEFAULT_HIDDEN_AMPLITUDE_THRESHOLD = 0.05  # cand / ref < this → hidden subtype


def _classify_subtype(
    *,
    is_new_extreme: bool,
    is_hidden: bool,
    is_decay: bool,
    cand_exceeds_ref: bool,
) -> DivergenceSubtype:
    """Pick a subtype label based on flags."""
    if cand_exceeds_ref:
        return "non_divergence"
    if is_hidden:
        return "hidden"
    if is_decay and is_new_extreme:
        return "standard"
    if is_decay and not is_new_extreme:
        return "weakness"
    return "none"


def compare(
    *,
    direction: Direction,
    amplitude_ref: float,
    amplitude_cand: float,
    price_extreme_ref: float,    # max_high for top / min_low for bottom
    price_extreme_cand: float,
    hidden_amplitude_threshold: float = DEFAULT_HIDDEN_AMPLITUDE_THRESHOLD,
) -> ComparisonResult:
    """Compare a candidate container event to its reference.

    Inputs are direction-coherent:
      direction='top'    → price_extreme_* = max_high
      direction='bottom' → price_extreme_* = min_low
      amplitude_*        = peak |hist| (heap) or peak |DIF| (cycle / segment)

    Returns a ComparisonResult with subtype + soft confidence score.
    """
    # NaN guard: if any input is non-finite (e.g. price extreme NaN from a degenerate
    # bar, or an amplitude that didn't accumulate), we can't compare. Return "none"
    # rather than silently passing through (a NaN > NaN compare is False, which
    # combined with is_decay=True would otherwise mislabel as "weakness").
    if (
        not math.isfinite(amplitude_ref)
        or not math.isfinite(amplitude_cand)
        or not math.isfinite(price_extreme_ref)
        or not math.isfinite(price_extreme_cand)
    ):
        return ComparisonResult(
            subtype="none",
            direction=direction,
            is_new_price_extreme=False,
            amplitude_ref=amplitude_ref if math.isfinite(amplitude_ref) else 0.0,
            amplitude_cand=amplitude_cand if math.isfinite(amplitude_cand) else 0.0,
            decay_ratio=0.0,
            is_hidden=False,
            score_price_break=0.0,
            score_amplitude_decay=0.0,
            score_hidden=0.0,
            confidence=0.0,
        )

    if amplitude_ref <= 0:
        # Degenerate reference — can't compute decay ratio sensibly
        return ComparisonResult(
            subtype="none",
            direction=direction,
            is_new_price_extreme=False,
            amplitude_ref=amplitude_ref,
            amplitude_cand=amplitude_cand,
            decay_ratio=0.0,
            is_hidden=False,
            score_price_break=0.0,
            score_amplitude_decay=0.0,
            score_hidden=0.0,
            confidence=0.0,
        )

    cand_exceeds_ref = amplitude_cand > amplitude_ref
    decay_ratio = (amplitude_ref - amplitude_cand) / amplitude_ref  # positive when decay
    decay_ratio = max(0.0, decay_ratio)  # clamp to [0, ∞)
    is_decay = amplitude_cand < amplitude_ref
    is_hidden = (amplitude_cand / amplitude_ref) < hidden_amplitude_threshold

    if direction == "top":
        is_new_extreme = price_extreme_cand > price_extreme_ref
    else:
        is_new_extreme = price_extreme_cand < price_extreme_ref

    subtype = _classify_subtype(
        is_new_extreme=is_new_extreme,
        is_hidden=is_hidden,
        is_decay=is_decay,
        cand_exceeds_ref=cand_exceeds_ref,
    )

    # Soft scoring (each in [0, 1])
    # - Price break: stronger when price extends further past reference
    if direction == "top":
        if price_extreme_ref > 0:
            score_price_break = max(
                0.0,
                (price_extreme_cand - price_extreme_ref) / price_extreme_ref,
            )
        else:
            score_price_break = 0.0
    else:
        if price_extreme_ref > 0:
            score_price_break = max(
                0.0,
                (price_extreme_ref - price_extreme_cand) / price_extreme_ref,
            )
        else:
            score_price_break = 0.0
    score_price_break = min(1.0, score_price_break * 20)  # normalize a typical ~5% break to ~1.0

    # - Amplitude decay magnitude
    score_amplitude_decay = min(1.0, decay_ratio)

    # - Hidden: extra credit for amplitude near zero
    score_hidden = max(
        0.0,
        1.0 - (amplitude_cand / amplitude_ref) / hidden_amplitude_threshold,
    ) if amplitude_ref > 0 else 0.0
    score_hidden = min(1.0, score_hidden)

    # Composite confidence by subtype
    confidence = 0.0
    if subtype == "standard":
        # Want: price broke + amplitude decayed
        confidence = 0.5 * score_price_break + 0.5 * score_amplitude_decay
    elif subtype == "weakness":
        # Want: amplitude decayed, no price break
        confidence = score_amplitude_decay
    elif subtype == "hidden":
        # Want: amplitude near zero; bonus if price broke
        confidence = 0.7 * score_hidden + 0.3 * score_price_break
    elif subtype in ("non_divergence", "none"):
        confidence = 0.0

    confidence = max(0.0, min(1.0, confidence))

    return ComparisonResult(
        subtype=subtype,
        direction=direction,
        is_new_price_extreme=is_new_extreme,
        amplitude_ref=amplitude_ref,
        amplitude_cand=amplitude_cand,
        decay_ratio=decay_ratio,
        is_hidden=is_hidden,
        score_price_break=score_price_break,
        score_amplitude_decay=score_amplitude_decay,
        score_hidden=score_hidden,
        confidence=confidence,
    )
