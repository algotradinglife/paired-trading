"""Over-extension + second-entry de-weight factor for bottom-reversal signals.

Productionizes two validated, OOS-checked findings (epic 过度延伸 gate, 2026-06-13):

- **A — over-extension penalty** (range_vs_avg): a signal bar much larger than its
  recent average range is a worse long-reversal entry. Validated on bottom×opposing
  (gap +0.52R, P=1.0, OOS +0.16) and bottom×neutral; **bottom-side only** — on tops
  it does not hold / reverses, so this de-weight is restricted to bottom direction.
- **B — second-entry preference** (test ordinal): the first test of a swing low beats
  retests (first vs 2nd+ gap +0.39R, nested-OOS significant). De-weight retests.

The two are complementary/orthogonal (combined EV +0.665 vs ~+0.07 baseline; each adds
~+0.29R on top of the other). Continuous weighting (this module) keeps ~half the signal
count vs a hard AND-filter (weighted-EV +0.275 at eff_n 157 vs +0.665 at n=35) — see
doc/deweight-curve-2026-06-13.md / doc/combined-gate-design-2026-06-13.md.

Returned factor is a **multiplier on the existing policy weight** (1.0 = no change),
applied by consumers (score_today) where daily bars are available to compute the two
features. Restricted to bottom × (opposing|neutral); returns 1.0 for all other lanes
so non-validated signals are untouched.

Constants are the P2.5 calibration; tunable but changing them shifts emitted weights
(run validate_baselines --full to quantify drift).
"""
from __future__ import annotations

import math

# --- A: over-extension weight w_a(range_vs_avg) ----------------------------
WA_CUT = 1.0        # rva ≤ 1.0 → full weight (EV flips sign at ~1.0, P2.5 sweep)
WA_SCALE = 1.0      # linear decay per ATR-relative unit above the cut
W_MIN = 0.2         # floor (never fully zero — keep the observation, just down-weight)

# --- B: second-entry weight w_b(ordinal) -----------------------------------
WB_FIRST = 1.0      # ordinal == 1 (first test) → full weight
WB_RETEST = 0.3     # ordinal >= 2 (retest) → de-weight (P1b: 2nd+ EV ≈ −0.03 vs +0.36)

# Lanes the de-weight applies to (bottom-side only; top side not validated/reverses).
_APPLICABLE_HREL = frozenset({"opposing", "neutral"})


def w_a(range_vs_avg: float) -> float:
    """Over-extension weight: 1.0 for rva ≤ WA_CUT, linearly down to W_MIN above."""
    if range_vs_avg is None or not math.isfinite(range_vs_avg):
        return W_MIN
    return min(1.0, max(W_MIN, (WA_CUT - range_vs_avg) / WA_SCALE + 1.0))


def w_b(ordinal: int | None) -> float:
    """Second-entry weight: full for first test, de-weighted for retests."""
    if ordinal is None:
        return WB_RETEST
    return WB_FIRST if int(ordinal) == 1 else WB_RETEST


def deweight_factor(
    direction: str,
    higher_relation: str | None,
    range_vs_avg: float | None,
    ordinal: int | None,
) -> float:
    """Multiplier on policy weight for bottom × (opposing|neutral) signals.

    Returns 1.0 (no change) for any other lane so non-validated signals are
    untouched. Otherwise w_a(range_vs_avg) × w_b(ordinal).
    """
    if direction != "bottom" or higher_relation not in _APPLICABLE_HREL:
        return 1.0
    return w_a(range_vs_avg) * w_b(ordinal)
