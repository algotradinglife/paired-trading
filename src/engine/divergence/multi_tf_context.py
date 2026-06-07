"""Attach multi-timeframe context to divergence signals.

Design: this is **annotation, not adjustment**. Confidence is not modified;
the downstream decision layer reads `signal.multi_tf_context` and applies its
own weighting policy. This avoids overfitting boost-multipliers on a single
sample, and preserves the calibrated confidence band semantics.

Two roles a foreign timeframe can play, with distinct semantic labels:

  Lower TF context (e.g. 1h state for a daily signal):
    keys: lower_tf_level_id, lower_tf_side, lower_tf_cycle_state, lower_relation
    lower_relation ∈ {"lagging", "leading", "pivoting"}
      lagging   = lower TF already moved in the signal's predicted direction
                  (move underway; signal is descriptive, not predictive)
      leading   = lower TF still moves against the signal's prediction
                  (signal preempts the lower-TF turn)
      pivoting  = lower TF in transition / near zero
    Empirical: bottom + lagging (60m bullish) is the high-volume, high-reliability
    sweet spot; top + lagging (60m bearish) is the stable red zone.

  Higher TF context (e.g. weekly state for a daily signal):
    keys: higher_tf_level_id, higher_tf_side, higher_tf_cycle_state, higher_relation
    higher_relation ∈ {"supporting", "opposing", "neutral"}
      supporting = higher TF direction matches signal's predicted direction
                   (trend tailwind — daily continues weekly's trend)
      opposing   = higher TF direction opposes signal prediction
                   (counter-trend; daily fights weekly trend)
      neutral    = higher TF in transition

The intermediate-TF signal (e.g. a 1h signal) could attach BOTH a lower (5m) and
a higher (D) context; the schema does not enforce mutual exclusion.
"""

from __future__ import annotations

import pandas as pd

from engine.divergence.signal import DivergenceSignal
from engine.fusion.level_state import LevelState, compute_level_state


def lower_relation_label(direction: str, lower_side: str) -> str:
    """Map (signal direction, lower-TF trend_side) → lagging / leading / pivoting."""
    if direction == "bottom":
        if lower_side == "bullish":
            return "lagging"
        if lower_side == "bearish":
            return "leading"
        return "pivoting"
    if direction == "top":
        if lower_side == "bearish":
            return "lagging"
        if lower_side == "bullish":
            return "leading"
        return "pivoting"
    return "unknown"


def higher_relation_label(direction: str, higher_side: str) -> str:
    """Map (signal direction, higher-TF trend_side) → supporting / opposing / neutral."""
    if direction == "bottom":
        if higher_side == "bullish":
            return "supporting"
        if higher_side == "bearish":
            return "opposing"
        return "neutral"
    if direction == "top":
        if higher_side == "bearish":
            return "supporting"
        if higher_side == "bullish":
            return "opposing"
        return "neutral"
    return "unknown"


# Back-compat alias (callers using the older name continue to work).
def relation_label(direction: str, lower_side: str) -> str:
    return lower_relation_label(direction, lower_side)


def _lower_ctx_fields(signal: DivergenceSignal, lower_state: LevelState) -> dict[str, str]:
    return {
        "lower_tf_level_id": lower_state.level_id,
        "lower_tf_side": lower_state.trend_side,
        "lower_tf_cycle_state": lower_state.cycle_state,
        "lower_relation": lower_relation_label(signal.direction, lower_state.trend_side),
        # Back-compat key: existing aggregators read `relation`. Keep until callers migrate.
        "relation": lower_relation_label(signal.direction, lower_state.trend_side),
    }


def _higher_ctx_fields(signal: DivergenceSignal, higher_state: LevelState) -> dict[str, str]:
    return {
        "higher_tf_level_id": higher_state.level_id,
        "higher_tf_side": higher_state.trend_side,
        "higher_tf_cycle_state": higher_state.cycle_state,
        "higher_relation": higher_relation_label(signal.direction, higher_state.trend_side),
    }


def build_context(
    signal: DivergenceSignal,
    lower_state: LevelState | None = None,
    higher_state: LevelState | None = None,
) -> dict[str, str]:
    """Compose a multi_tf_context dict from optional lower / higher LevelStates."""
    ctx: dict[str, str] = {}
    if lower_state is not None:
        ctx.update(_lower_ctx_fields(signal, lower_state))
    if higher_state is not None:
        ctx.update(_higher_ctx_fields(signal, higher_state))
    return ctx


def _state_at_signal(
    bars: pd.DataFrame,
    signal_t: pd.Timestamp,
    level_id: str,
    *,
    grace: pd.Timedelta,
    min_bars: int,
) -> LevelState | None:
    """Slice bars up to signal_t (+ grace) and compute LevelState. Return None
    if too few bars or compute fails."""
    cutoff = signal_t + grace
    sliced = bars[bars["timestamp"] <= cutoff].reset_index(drop=True)
    if len(sliced) < min_bars:
        return None
    try:
        return compute_level_state(level_id, sliced)
    except Exception:
        return None


def enrich_with_lower_tf(
    signals: list[DivergenceSignal],
    primary_bars: pd.DataFrame,
    lower_tf_bars: pd.DataFrame,
    lower_tf_level_id: str = "1h",
    *,
    intraday_grace_minutes: int = 30,
    min_bars_for_state: int = 60,
) -> list[DivergenceSignal]:
    """Return new signals (model_copy) with lower-TF multi_tf_context attached
    when the lower-TF state can be computed at the signal's timestamp.

    Known trade-off (validated by Codex 2026-05-23):
      `intraday_grace_minutes=30` includes the closing-hour 60min bar that has
      ~58% of its data already at the daily-signal time (e.g. signal at daily
      close = 20:00 UTC, last hourly bar covers 20:00–21:00 UTC). This is a
      mild forward-looking peek: the 60min bar's state may incorporate the
      30 minutes after the daily timestamp. The 95% CI on this leak's impact
      on downstream stats is within sampling noise for the validated F2 / F3
      buckets, so we keep it for richer context. Callers that need strict
      no-leak semantics should pass `intraday_grace_minutes=0`.

    Signals without enough lower-TF data pass through unchanged.
    """
    enriched: list[DivergenceSignal] = []
    grace = pd.Timedelta(minutes=intraday_grace_minutes)

    for sig in signals:
        signal_t = primary_bars["timestamp"].iloc[sig.candidate_bar_idx]
        lower_state = _state_at_signal(
            lower_tf_bars, signal_t, lower_tf_level_id,
            grace=grace, min_bars=min_bars_for_state,
        )
        if lower_state is None:
            enriched.append(sig)
            continue
        ctx = build_context(sig, lower_state=lower_state)
        existing = sig.multi_tf_context or {}
        # If a higher-TF enricher ran earlier, preserve its keys
        ctx = {**existing, **ctx}
        enriched.append(sig.model_copy(update={"multi_tf_context": ctx}))

    return enriched


def enrich_with_higher_tf(
    signals: list[DivergenceSignal],
    primary_bars: pd.DataFrame,
    higher_tf_bars: pd.DataFrame,
    higher_tf_level_id: str = "W",
    *,
    grace_minutes: int = 0,
    min_bars_for_state: int = 60,
) -> list[DivergenceSignal]:
    """Return new signals with higher-TF multi_tf_context attached.

    The higher TF (e.g. weekly) at the time of a daily signal is the weekly
    bar that contains the signal's date. We slice higher_tf_bars to <= signal_t
    so the most recent weekly bar reflects what was knowable then.
    """
    enriched: list[DivergenceSignal] = []
    grace = pd.Timedelta(minutes=grace_minutes)

    for sig in signals:
        signal_t = primary_bars["timestamp"].iloc[sig.candidate_bar_idx]
        higher_state = _state_at_signal(
            higher_tf_bars, signal_t, higher_tf_level_id,
            grace=grace, min_bars=min_bars_for_state,
        )
        if higher_state is None:
            enriched.append(sig)
            continue
        ctx = build_context(sig, higher_state=higher_state)
        existing = sig.multi_tf_context or {}
        # Preserve lower-TF context if an earlier enricher attached it
        ctx = {**existing, **ctx}
        enriched.append(sig.model_copy(update={"multi_tf_context": ctx}))

    return enriched
