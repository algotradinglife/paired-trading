"""Attribution backtest for score_today's ag/au options_calls emission.
Replays the live emission, prices each Rank-1 OTM call (real data + Black-76
fallback), simulates the validated DD-line exit, aggregates IS/OOS folds.
Spec: docs/superpowers/specs/2026-06-10-options-attribution-design.md"""
from __future__ import annotations

IS_CUTOFF_YEAR = 2023  # IS <= 2023, OOS >= 2024


def fold_of(year: int) -> str:
    return "is" if year <= IS_CUTOFF_YEAR else "oos"


def verdict_for(is_ev: float, oos_ev: float) -> str:
    """EV_mult > 1.0 = profit. PROMOTE iff both folds profitable; REGIME_ONLY
    iff only OOS; REJECT iff neither."""
    if is_ev > 1.0 and oos_ev > 1.0:
        return "PROMOTE"
    if oos_ev > 1.0:
        return "REGIME_ONLY"
    return "REJECT"
