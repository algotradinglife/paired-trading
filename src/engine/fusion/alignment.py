"""Cross-level alignment + primary-label synthesis.

Reference: doc/08-multitimeframe-fusion.md §9 (alignment strength)
           doc/11-output-schema.md §5.1 (primary label values)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from engine.fusion.level_state import LevelState
from engine.fusion.propagation import FusedLevelState

DominantTrend = Literal["bullish", "bearish", "mixed"]


@dataclass(frozen=True)
class CrossLevelSummary:
    alignment_strength: float       # [0, 1] — fraction of levels agreeing with dominant
    dominant_trend: DominantTrend
    primary_label: str               # main conclusion across all levels
    primary_confidence: float
    secondary_labels: list[tuple[str, float]]


# Trigger thresholds for primary labels (cf. doc/11 §5.1 + doc/10 §2 stages)
LABEL_CANDIDATE_THRESHOLD = 0.65
LABEL_CONFIRMED_THRESHOLD = 0.80

# How recent a divergence must be (relative to the level's last bar) to count
# as a primary candidate. Calibrated to roughly one "active cycle" per level —
# daily MACD cycles run ~10-30 bars, 60min ~30-100 bars.
RECENCY_WINDOW = {
    "1m": timedelta(hours=12),
    "5m": timedelta(days=3),
    "15m": timedelta(days=7),
    "30m": timedelta(days=14),
    "1h": timedelta(days=21),
    "4h": timedelta(days=45),
    "D":  timedelta(days=45),
    "W":  timedelta(days=180),
    "M":  timedelta(days=540),
}
DEFAULT_RECENCY = timedelta(days=30)


def compute_alignment_strength(states: dict[str, LevelState]) -> tuple[float, DominantTrend]:
    """Returns (alignment_strength, dominant_trend).

    Alignment = max fraction of levels with the same trend_side.
    Tie / no clear majority → "mixed".
    """
    if not states:
        return 0.0, "mixed"

    sides = [s.trend_side for s in states.values()]
    n = len(sides)
    if n == 0:
        return 0.0, "mixed"

    counts = {
        "bullish": sides.count("bullish"),
        "bearish": sides.count("bearish"),
        "transition": sides.count("transition"),
    }

    bullish_frac = counts["bullish"] / n
    bearish_frac = counts["bearish"] / n

    if bullish_frac > bearish_frac and bullish_frac >= 0.5:
        return bullish_frac, "bullish"
    if bearish_frac > bullish_frac and bearish_frac >= 0.5:
        return bearish_frac, "bearish"
    # No clear majority — use the higher of the two as alignment, mixed direction
    return max(bullish_frac, bearish_frac), "mixed"


def select_primary_label(
    fused: dict[str, FusedLevelState],
    states: dict[str, LevelState],
    *,
    candidate_threshold: float = LABEL_CANDIDATE_THRESHOLD,
) -> tuple[str, float, list[tuple[str, float]]]:
    """Pick the highest-priority primary label across all levels.

    Priority (per doc/10 §7):
      inter_segment_divergence > level_upgrade > zero_cross_confirmed >
      bottom_phase > inter_cycle_divergence > goldmine_form > intra_cycle_divergence >
      form嫌疑 (HPV, hidden, zero_inverted, near_zero_axis)

    For v1 we focus on form-嫌疑 labels and recent divergence; advanced
    detectors (level upgrade, bottom phase) live in doc/08 §4-§8 and will be
    added in future增量.
    """
    # Build a list of (label, confidence, level) candidates above threshold.
    candidates: list[tuple[str, float, str]] = []

    # 1) Divergence signals from any level — most-recent above threshold,
    # filtered to a per-level recency window so we don't surface stale (multi-
    # year-old) signals as the current primary label.
    for level_id, state in states.items():
        sig = state.most_recent_divergence
        if sig is None:
            continue
        if sig.confidence < candidate_threshold:
            continue
        max_age = RECENCY_WINDOW.get(level_id, DEFAULT_RECENCY)
        # Both timestamps are tz-aware (UTC) by construction
        if state.timestamp - sig.timestamp > max_age:
            continue
        label = f"{sig.level}_{sig.subtype}_{sig.direction}@{level_id}"
        candidates.append((label, sig.confidence, level_id))

    # 2) Active forms (fused) above threshold
    for level_id, fls in fused.items():
        for form_name, conf in fls.form_confidences_fused.items():
            if conf >= candidate_threshold:
                label = f"{form_name}@{level_id}"
                candidates.append((label, conf, level_id))

    # Sort by confidence descending
    candidates.sort(key=lambda c: -c[1])

    if not candidates:
        return "stable", 0.0, []

    primary_label, primary_conf, _ = candidates[0]
    secondary = [(label, conf) for label, conf, _ in candidates[1:6]]   # next 5
    return primary_label, primary_conf, secondary


def summarize(
    states: dict[str, LevelState],
    fused: dict[str, FusedLevelState],
) -> CrossLevelSummary:
    alignment, dominant = compute_alignment_strength(states)
    label, conf, secondary = select_primary_label(fused, states)
    return CrossLevelSummary(
        alignment_strength=alignment,
        dominant_trend=dominant,
        primary_label=label,
        primary_confidence=conf,
        secondary_labels=secondary,
    )
