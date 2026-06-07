"""Bidirectional confidence propagation.

For each form on each level:
  conf_final = conf_local × f_bottom_up × f_top_down

Where:
  f_bottom_up = 1 + w_sub · (sub level same-form confidence) · alignment_with_sub
  f_top_down  = 1 + w_up_plus  · (super supports this form)
               or
               1 - w_up_minus · (super opposes this form)

Reference: doc/08-multitimeframe-fusion.md §2, §10 (test scenarios)
           doc/10-confidence-model.md §4 (合成公式)
           doc/12-thresholds-and-params.md §6.1 (default weights)
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.fusion.level_state import LevelState
from engine.fusion.topology import LevelTopology


# Defaults per doc/12 §6.1
DEFAULT_W_SUB = 0.4         # bottom-up multiplier
DEFAULT_W_UP_PLUS = 0.3      # top-down boost when supportive
DEFAULT_W_UP_MINUS = 0.4     # top-down attenuation when opposed
DEFAULT_MIN_CONFIDENCE_FOR_SUPPORT = 0.5  # gate for "supportive" form alignment


@dataclass(frozen=True)
class PropagationConfig:
    w_sub: float = DEFAULT_W_SUB
    w_up_plus: float = DEFAULT_W_UP_PLUS
    w_up_minus: float = DEFAULT_W_UP_MINUS
    min_confidence_for_support: float = DEFAULT_MIN_CONFIDENCE_FOR_SUPPORT


# Forms classified by directional bias — used to decide if super-level trend
# is supportive or opposed for each form.
BULLISH_RELEVANT_FORMS = {"high_position_void", "hidden", "zero_inverted"}  # top-warning forms (bullish trends weakening)
BEARISH_RELEVANT_FORMS = {"high_position_void", "hidden", "zero_inverted"}  # mirror for下跌 line段
# (Both sides matter — what direction the form points depends on segment direction)

# Forms that benefit from super-level confirmation (any direction):
ANY_DIRECTION_FORMS = {"near_zero_axis", "zero_stick"}


def _supportive_from_super(form_name: str, current: LevelState, super_state: LevelState) -> float:
    """Return a [-1, +1] score for how the super-level state supports `form_name`
    on `current`.

      +1 = super state strongly supports this form
       0 = neutral
      -1 = super state opposes this form

    Heuristic: for "reversal-warning" forms (HPV, hidden, zero_inverted), the
    super level should be on the SAME side and showing fatigue — e.g., HPV on
    daily strengthens HPV on 1h. For "归零轴" forms, super being also近零 is
    supportive.
    """
    super_same_form = super_state.form_confidences.get(form_name, 0.0)
    if super_same_form > 0.5:
        return min(1.0, super_same_form)  # super has same form active → support

    # Trend-side based gating
    if form_name in {"high_position_void"}:
        # HPV warns of weakening trend in current direction
        # Supported if super still confirms direction (both bullish for top HPV)
        # Opposed if super in opposite trend
        if current.segment_direction == "up":
            if super_state.trend_side == "bullish":
                return 0.3   # weakly supportive (super on same side)
            elif super_state.trend_side == "bearish":
                return -0.4  # opposed (already in bear)
        elif current.segment_direction == "down":
            if super_state.trend_side == "bearish":
                return 0.3
            elif super_state.trend_side == "bullish":
                return -0.4
        return 0.0

    if form_name == "near_zero_axis":
        # Both being near zero is mutually reinforcing
        if super_state.form_confidences.get("near_zero_axis", 0.0) > 0.5:
            return 0.5
        return 0.0

    return 0.0


def _supportive_from_sub(form_name: str, current: LevelState, sub_state: LevelState) -> float:
    """How strongly does the sub level's same form support the current level?

    Returns [0, 1] — sub-form's confidence on the same form, capped.
    Sub-level acts as a leading indicator: when sub already shows the form,
    super-level (current) gets a boost.
    """
    return min(1.0, sub_state.form_confidences.get(form_name, 0.0))


@dataclass
class FusedLevelState:
    """Per-level fused output."""

    level_id: str
    form_confidences_local: dict[str, float]
    form_confidences_fused: dict[str, float]
    f_bottom_up: dict[str, float]
    f_top_down: dict[str, float]
    sub_level: str | None
    super_level: str | None


def propagate(
    states: dict[str, LevelState],
    topology: LevelTopology,
    *,
    config: PropagationConfig = PropagationConfig(),
) -> dict[str, FusedLevelState]:
    """Run bidirectional propagation across all provided levels.

    Args:
        states: Mapping level_id → LevelState. Need not cover all topology
                levels — only those provided participate.
        topology: Full level ordering (must contain all keys in `states`).

    Returns:
        Mapping level_id → FusedLevelState with both local and fused form
        confidences.
    """
    # Restrict topology to available levels
    available = list(states.keys())
    sub_topology = topology.restrict_to(available)

    fused = {}
    for level_id, state in states.items():
        sub_id = sub_topology.sub_of(level_id)
        super_id = sub_topology.super_of(level_id)

        sub_state = states.get(sub_id) if sub_id else None
        super_state = states.get(super_id) if super_id else None

        f_bu: dict[str, float] = {}
        f_td: dict[str, float] = {}
        fused_conf: dict[str, float] = {}

        for form_name, local_conf in state.form_confidences.items():
            # Bottom-up factor
            if sub_state is not None:
                sub_support = _supportive_from_sub(form_name, state, sub_state)
                f_bu_val = 1.0 + config.w_sub * sub_support
            else:
                f_bu_val = 1.0
            f_bu[form_name] = f_bu_val

            # Top-down factor
            if super_state is not None:
                support = _supportive_from_super(form_name, state, super_state)
                if support >= 0:
                    f_td_val = 1.0 + config.w_up_plus * support
                else:
                    f_td_val = 1.0 - config.w_up_minus * abs(support)
            else:
                f_td_val = 1.0
            f_td[form_name] = f_td_val

            raw = local_conf * f_bu_val * f_td_val
            fused_conf[form_name] = max(0.0, min(1.0, raw))

        fused[level_id] = FusedLevelState(
            level_id=level_id,
            form_confidences_local=dict(state.form_confidences),
            form_confidences_fused=fused_conf,
            f_bottom_up=f_bu,
            f_top_down=f_td,
            sub_level=sub_id,
            super_level=super_id,
        )

    return fused
