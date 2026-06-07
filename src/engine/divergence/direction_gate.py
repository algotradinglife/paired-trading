"""Direction-asymmetric confidence adjustment for divergence signals.

Background: 5-year backtest across SPY/QQQ/NVDA/GLD daily (157 signals) showed
bottom divergence is well-calibrated (h=20 hit 74%, +4.09%, MFE/MAE 2.64),
while top divergence is biased upward under bull-market regimes (h=20 hit 41%,
-1.66%, MFE/MAE 0.83).

Feature breakdown of the 83 top signals identified specific failure modes:

  feature                          n    h20 hit   sret_20
  subtype=hidden                   4    0%        -9.73%   ← almost always wrong
  is_continuous_gap=True           35   31%       -2.88%   ← worst heap class
  is_continuous_gap=False          12   83%       +2.57%   ← strongest reversal class
  level=inter_segment              32   34%       -2.18%   ← bull market: segments keep going
  subtype=weakness                 24   42%       -3.05%
  conf_band=confirmed              20   60%       -0.87%   ← still weakly negative
  subtype=standard                 55   44%       -0.47%   ← baseline

This module applies multiplicative confidence adjustments. Bottom signals pass
through unchanged. Multipliers compound, then clip to [0, 1]. The "gate" lives
in continuous confidence space, consistent with the project's posterior-
inference design (no hard event flags).

The multiplier tables are PER-INSTRUMENT-CLASS:

  us_equity (default): the US-calibrated tables documented above. Penalizes
    top signals based on the observed bias in US bull-market data.

  cn_futures: PASS-THROUGH (all multipliers = 1.0). CN futures tops are
    empirically POSITIVE (+0.65% mean, 55.8% hit, n=400 in 2026-05-24
    19-symbol backtest), so the US top de-weight does not generalize.
    When more CN data is available a separate calibration may be added.

Empirical multiplier table is intentionally explicit — a future re-fit with
larger samples should overwrite these values, not the structure.
"""

from __future__ import annotations

from typing import Literal

from engine.divergence.signal import DivergenceSignal

InstrumentClass = Literal["us_equity", "cn_futures", "czce", "cn_index_futures", "cn_metal_futures"]

# ---------------------------------------------------------------------------
# us_equity multiplier tables (current US calibration)
# ---------------------------------------------------------------------------
# Multipliers derived from the 5-year US backtest. Values < 1 penalize, > 1
# boost. Compounding is intentional: a "weakness + inter_segment +
# continuous_gap" top signal stacks all three penalties.

TOP_SUBTYPE_MULT_US = {
    "hidden": 0.0,      # 4/4 lost; -9.73% — drop entirely
    "weakness": 0.7,
    "standard": 1.0,    # baseline
}

TOP_LEVEL_MULT_US = {
    "inter_segment": 0.5,         # bull-market segments keep extending; 34% hit
    "inter_cycle": 0.85,
    "intra_cycle": 1.0,            # baseline (heaps)
    "intra_cycle_hist": 1.0,       # HICD — bottom-only; top path never reaches this
    "intra_cycle_slope": 1.0,      # DIFSR — bottom-only
    "intra_cycle_dea": 1.0,        # DEAD — bottom-only
    "intra_cycle_bull_hist": 1.0,  # HICD+ — bottom-only
    "intra_cycle_bull_slope": 1.0, # DIFSR+ — bottom-only
    "intra_cycle_bull_dea": 1.0,   # DEAD+ — bottom-only
}

# Heap-level only (intra_cycle).
# Non-continuous heap reversals were the single strongest predictor (+2.57% / 83% hit).
TOP_GAP_MULT_US = {
    False: 1.2,    # boost the rare-but-strong "gapped" reversal
    True: 0.5,     # the common-but-weak "continuous" top
    None: 1.0,     # non-heap signals
}

# Back-compat aliases for any external code importing the old names.
TOP_SUBTYPE_MULT = TOP_SUBTYPE_MULT_US
TOP_LEVEL_MULT = TOP_LEVEL_MULT_US
TOP_GAP_MULT = TOP_GAP_MULT_US

# ---------------------------------------------------------------------------
# cn_futures multiplier tables (PASS-THROUGH — CN tops are empirically +)
# ---------------------------------------------------------------------------
# Per 2026-05-24 19-symbol CN futures backtest: top n=400, hit=55.8%, mean=
# +0.65%. US top de-weight does not apply. Pass-through until separate
# CN-specific calibration is justified by more data (multi-TF particularly).

TOP_SUBTYPE_MULT_CN = {"hidden": 1.0, "weakness": 1.0, "standard": 1.0}
TOP_LEVEL_MULT_CN = {
    "inter_segment": 1.0, "inter_cycle": 1.0, "intra_cycle": 1.0,
    "intra_cycle_hist": 1.0, "intra_cycle_slope": 1.0, "intra_cycle_dea": 1.0,
    "intra_cycle_bull_hist": 1.0, "intra_cycle_bull_slope": 1.0, "intra_cycle_bull_dea": 1.0,
}
TOP_GAP_MULT_CN = {False: 1.0, True: 1.0, None: 1.0}

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_TABLES_BY_CLASS = {
    "us_equity": (TOP_SUBTYPE_MULT_US, TOP_LEVEL_MULT_US, TOP_GAP_MULT_US),
    "cn_futures": (TOP_SUBTYPE_MULT_CN, TOP_LEVEL_MULT_CN, TOP_GAP_MULT_CN),
    "czce": (TOP_SUBTYPE_MULT_CN, TOP_LEVEL_MULT_CN, TOP_GAP_MULT_CN),
    "cn_index_futures": (TOP_SUBTYPE_MULT_CN, TOP_LEVEL_MULT_CN, TOP_GAP_MULT_CN),
    "cn_metal_futures": (TOP_SUBTYPE_MULT_CN, TOP_LEVEL_MULT_CN, TOP_GAP_MULT_CN),
}


def apply_direction_gate(
    sig: DivergenceSignal,
    instrument_class: InstrumentClass = "us_equity",
) -> float:
    """Return direction-adjusted confidence ∈ [0, 1]. Pure function — does not
    mutate the signal.
    """
    if sig.direction == "bottom":
        return sig.confidence

    try:
        sub_tbl, lvl_tbl, gap_tbl = _TABLES_BY_CLASS[instrument_class]
    except KeyError as e:
        raise ValueError(
            f"Unknown instrument_class: {instrument_class!r}. "
            f"Supported: {sorted(_TABLES_BY_CLASS)}"
        ) from e

    mult = (
        sub_tbl.get(sig.subtype, 1.0)
        * lvl_tbl.get(sig.level, 1.0)
        * gap_tbl.get(sig.is_continuous_gap, 1.0)
    )
    return max(0.0, min(1.0, sig.confidence * mult))


def gate_signals(
    signals: list[DivergenceSignal],
    instrument_class: InstrumentClass = "us_equity",
) -> list[DivergenceSignal]:
    """Return new signals with confidence adjusted. Drops signals whose
    adjusted confidence falls below the watching-band floor (0.30).

    For instrument_class="cn_futures", multipliers are all 1.0 → signals
    pass through with original confidence (no de-weight, no drops below
    watching except those already there).
    """
    out: list[DivergenceSignal] = []
    for sig in signals:
        adj = apply_direction_gate(sig, instrument_class=instrument_class)
        if adj < 0.30:
            continue
        if adj == sig.confidence:
            out.append(sig)
        else:
            out.append(sig.model_copy(update={"confidence": adj}))
    return out
