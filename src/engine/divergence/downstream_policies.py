"""Downstream weighting policies for divergence signals.

Design boundary: the engine layer detects + tags signals. This module proposes
a *reference policy* for converting an engine output into a final actionable
weight. Downstream consumers (trading systems) may override or replace.

Policies are calibrated per `instrument_class`:

  us_equity (default):
    Calibrated on 5y × 10-symbol × 3-TF US equity backtest
    (Codex Rounds 1-3, 2026-05-23). Rules F1-F8 + B1.

  cn_futures:
    Last revised: Codex R5 (2026-05-26) on 10y deep-data v2 sample.
    Earlier Codex R4 (2026-05-24) was on a 2.4y window (n=233 signals)
    whose magnitudes were sample-window inflated; R5 replaced R4 estimates
    using qveris-backfilled 14y CN intraday data (n=1008 signals at h=20).
    Key R5 findings:
      * **R4's CN-top-supp-fade rule was REMOVED in R5.** The R4 basis
        for de-weighting top+higher=supporting (n=74, mean -1.59%, CI
        [-3.40%, +0.02%] — marginal even in R4) collapsed on deep-data
        v2 to n=324, mean -0.10%, CI [-0.99%, +0.82%]. Fully crosses zero.
        All top configurations now route to CN1-top-passthrough at 1.00.
      * F8 (bottom+weakness) still positive significant but R4 magnitude
        was inflated: v2 n=306, mean +1.19%, CI [+0.26%, +2.14%], hit
        57.5% (R4 was +3.81% on n=56). Weight stays 1.00 — no boost
        without dedicated walk-forward validation.
      * Pooled top sign-flipped: R4 -1.06% (2.4y) → R5 +0.34% (10y).
      * Walk-forward K=3 on v2 deep data still yields 0 cells stable
        across both test folds — filter tuning has hit a structural
        ceiling. Future alpha must come from new detector types (see
        doc/exhaustion-detector-spec-2026-05-26.md).
      * Symbol-level filter (coal complex j0/jm0 negative-EV cluster) is a
        CONSUMER concern, surfaced via strategy_hints. Should be
        re-validated on v2.

Output schema (PolicyDecision):
    weight: float ∈ [0, ~1.3]   # 0 = drop, 1 = pass-through, >1 = boost
    rule_id: str | None         # which rule fired (None = baseline)
    monitor_required: bool      # True when statistical caveat suggests
                                # ongoing re-validation
    reason: str                 # human-readable explanation
    strategy_hints: dict | None # advisory tags for specific consumer strategies

Note on direction_gate (engine/divergence/direction_gate.py):
  direction_gate is applied at signal *detection* time and is currently
  calibrated for US equity (top de-weight). When generating signals on CN
  futures data, downstream consumers should either:
    (a) skip gate_signals() at detection time, or
    (b) inverse-compensate at policy time (cn_futures policy does NOT do
        this automatically — known limitation; flagged in cn rule docstrings)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from engine.divergence.signal import DivergenceSignal

InstrumentClass = Literal["us_equity", "cn_futures", "czce", "cn_index_futures", "cn_metal_futures"]

# Confidence band thresholds — duplicated from alignment.py to keep this module
# self-contained for downstream consumers
LABEL_CANDIDATE_THRESHOLD = 0.65
LABEL_CONFIRMED_THRESHOLD = 0.80

# CN futures: symbols with negative EV historically (Codex 2026-05-24).
# Surfaced via strategy_hints; consumer applies the filter at universe selection.
CN_BLACKLIST_SYMBOLS = frozenset({"j0", "jm0"})


@dataclass(frozen=True)
class PolicyDecision:
    weight: float
    rule_id: str | None
    monitor_required: bool
    reason: str
    strategy_hints: dict[str, str] | None = None


def conf_band(c: float) -> Literal["confirmed", "candidate", "forming", "watching", "dormant"]:
    if c >= LABEL_CONFIRMED_THRESHOLD:
        return "confirmed"
    if c >= LABEL_CANDIDATE_THRESHOLD:
        return "candidate"
    if c >= 0.50:
        return "forming"
    if c >= 0.30:
        return "watching"
    return "dormant"


def apply_policy(
    sig: DivergenceSignal,
    instrument_class: InstrumentClass = "us_equity",
) -> PolicyDecision:
    """Return a PolicyDecision for one signal, calibrated to instrument_class.

    Args:
        sig: divergence signal (post direction_gate, post multi_tf_context enrichment)
        instrument_class: "us_equity" (default) or "cn_futures"
    """
    # CN2: disable weak bottom sublevels for CN commodity pools only.
    # NOT applied to cn_index_futures (governed by CNI1) or czce.
    # WF K=2 (2026-06-02, h=opposing, CN_COMMODITY+CN_METAL):
    #   intra_cycle_dea:   n=225, EV=-0.014R, F1=-0.175R, F2=-0.092R
    #   intra_cycle_slope: n=211, EV=-0.010R, F1=+0.005R, F2=-0.064R
    #   Combined removal:  n=436, F1=-0.073R, F2=-0.080R (both folds negative)
    #   After gate: portfolio EV +0.144R→+0.219R, both OOS folds improve.
    _CN2_WEAK_LEVELS = {"intra_cycle_dea", "intra_cycle_slope"}
    _cn2_higher_rel = (sig.multi_tf_context or {}).get("higher_relation")
    if (instrument_class in {"cn_futures", "cn_metal_futures"}
            and sig.direction == "bottom"
            and sig.level in _CN2_WEAK_LEVELS
            and _cn2_higher_rel == "opposing"):
        return PolicyDecision(
            weight=0.0,
            rule_id="CN2-bottom-weak-sublevel-disabled",
            monitor_required=False,
            reason=(
                f"CN bottom/{sig.level} h=opposing: disabled via CN2 gate (2026-06-02). "
                "intra_cycle_dea/slope fire on DEA/slope divergence within "
                "bearish heap but are consistently negative EV in OOS (h=opposing). "
                "WF K=2: intra_cycle_dea F1=-0.175R F2=-0.092R, "
                "intra_cycle_slope F1=+0.005R F2=-0.064R. "
                "Combined n=436, F1=-0.073R, F2=-0.080R. "
                "Supporting/neutral buckets pass through to base policy."
            ),
        )

    if instrument_class == "us_equity":
        return _apply_us_equity(sig)
    if instrument_class == "cn_futures":
        return _apply_cn_futures(sig)
    if instrument_class == "czce":
        return _apply_czce(sig)
    if instrument_class == "cn_index_futures":
        return _apply_cn_index_futures(sig)
    if instrument_class == "cn_metal_futures":
        return _apply_cn_metal_futures(sig)
    raise ValueError(
        f"Unknown instrument_class: {instrument_class!r}. "
        f"Supported: us_equity, cn_futures, czce, cn_index_futures"
    )


# ---------------------------------------------------------------------------
# US Equity calibration (Codex Rounds 1-3)
# ---------------------------------------------------------------------------

def _apply_us_equity(sig: DivergenceSignal) -> PolicyDecision:
    """US equity policy. Precedence (most specific first):

      1. F2  — bottom + leading + opposing      (Codex R1 validated)
      2. F3  — candidate × opposing             (Codex R1 validated, monitor)
      3. F4  — top + leading + opposing         (options-asymmetric, more specific than B1)
      4. B1  — top + higher=opposing            (Codex R3: 27% stop-hit, real entry alpha)
      5. F1  — top + lagging                    (Codex R1 edge; soft de-weight)
      6. F8  — bottom + weakness baseline       (Codex R2 validated)
      7. Baseline
    """
    ctx = sig.multi_tf_context or {}
    direction = sig.direction
    lower_rel = ctx.get("lower_relation") or ctx.get("relation")  # back-compat
    higher_rel = ctx.get("higher_relation")
    band = conf_band(sig.confidence)

    # --- F2: bottom + leading + opposing -----------------------------------
    if direction == "bottom" and lower_rel == "leading" and higher_rel == "opposing":
        return PolicyDecision(
            weight=1.20,
            rule_id="F2-strong-bottom",
            monitor_required=False,
            reason=(
                "bottom divergence with lower-TF still in counter-trend + "
                "higher-TF still in counter-trend — validated multi-TF reversal "
                "pattern (Codex 2026-05-23)"
            ),
        )

    # --- F3: candidate × opposing weekly trend ----------------------------
    if band == "candidate" and higher_rel == "opposing":
        return PolicyDecision(
            weight=1.15,
            rule_id="F3-candidate-counter-trend",
            monitor_required=True,
            reason=(
                "candidate-band signal opposing the higher-TF trend — "
                "historically perfect (14/14) in 5y sample; statistically "
                "strong but the perfect record itself flags overfitting risk "
                "and requires continued validation"
            ),
        )

    # --- F4: top + leading + opposing  (more specific than B1) ------------
    if direction == "top" and lower_rel == "leading" and higher_rel == "opposing":
        return PolicyDecision(
            weight=1.0,
            rule_id="F4-options-asymmetric",
            monitor_required=False,
            reason=(
                "top divergence with lower-TF and higher-TF still trending up "
                "— non-tradeable for linear stock strategies (one outlier "
                "destroys mean) but the 24/25 ≈ 96% small-win pattern is "
                "asymmetric-friendly under defined-risk options structures."
            ),
            strategy_hints={
                "options_asymmetric": (
                    "high-frequency small underlying wins amplified by long "
                    "PUT gamma; strict stop on PUT premium caps the rare "
                    "trend-continuation tail loss."
                ),
            },
        )

    # --- B1: top + higher=opposing (residual after F4) ---------------------
    # Codex Round 3 / tight-stop sensitivity verdict: stop-hit rate is 27%
    # under SL -3% vs F1's 72% — multi-TF filter is screening out the worst
    # entries, not just capping losers. h=10 realized EV +41.6% at SL -10%;
    # h=20 +33.8%. Real entry-quality alpha; the strongest top-side bucket.
    if direction == "top" and higher_rel == "opposing":
        return PolicyDecision(
            weight=1.30,
            rule_id="B1-top-higher-opposing",
            monitor_required=True,
            reason=(
                "top divergence with higher-TF still trending up (not also "
                "matching F4). Multi-TF filter shows 27% stop-hit rate vs F1's "
                "72% — entry-quality alpha. Realized EV +33.8% at h=20 under "
                "SL -10% (tight-stop sensitivity, Codex 2026-05-24). Sample "
                "n=11 with option data; monitor."
            ),
            strategy_hints={
                "exit_policy": (
                    "let-run with -10% SL on PUT premium; tight TP not "
                    "recommended (winners average +70% premium)."
                ),
                "calibration_note": (
                    "weight derived from B-topology (D+15m+1h) data; A-topology "
                    "(D+1h+W) population may behave differently."
                ),
            },
        )

    # --- F1: top + lagging — disabled (2026-05-30) -----------------------
    # RR backtest (n=55, stop=ATR×0.75): EV=-0.191R, full_stop=60%.
    # B1 already handles the only viable subset (top+lagging+h=opposing).
    # Remaining top+lagging (h=supporting/neutral) has no positive EV.
    if direction == "top" and lower_rel == "lagging":
        return PolicyDecision(
            weight=0.0,
            rule_id="F1-top-lagging-disabled",
            monitor_required=False,
            reason=(
                "top divergence after lower-TF has already turned bearish, "
                "without higher-TF opposing (caught by B1). "
                "RR backtest 2026-05-30: n=55, EV=-0.191R, full_stop=60% — "
                "no positive EV regardless of stop width. Disabled."
            ),
        )

    # --- F8: bottom + subtype=weakness — universal bottom-weakness baseline -
    if direction == "bottom" and sig.subtype == "weakness":
        return PolicyDecision(
            weight=1.10,
            rule_id="F8-bottom-weakness-baseline",
            monitor_required=False,
            reason=(
                "weakness-subtype bottom divergence — the largest-sample "
                "consistently-positive workhorse signal (Codex Round 2 "
                "validated, n=123). Tight-stop sensitivity (R3) confirms "
                "+73.5% EV at SL -3%. Independent of multi-TF context."
            ),
        )

    # --- Baseline ----------------------------------------------------------
    return PolicyDecision(
        weight=1.0,
        rule_id=None,
        monitor_required=False,
        reason="no calibrated rule applied; baseline confidence",
    )


# ---------------------------------------------------------------------------
# CN Futures calibration (Codex 2026-05-24, 19 symbols, single-TF only)
# ---------------------------------------------------------------------------

def _apply_cn_futures(sig: DivergenceSignal) -> PolicyDecision:
    """CN futures policy. Calibrated via Codex R4 (2026-05-24) + Codex R5
    revision (2026-05-26) after qveris deep-data backfill (4.3x sample).

    R5 findings (deep-data replacement estimates at h=20):
      * F8 (bottom+weakness): n=306, mean +1.19%, CI [+0.26%, +2.14%],
        hit 57.5%. Still positive significant but ~3x weaker than R4's
        +3.81% claim — R4 magnitude was a 2.4y-window artifact. Weight
        stays 1.00 pass-through; no boost without separate WF validation.
      * top+higher=supporting (was the R4 CN-top-supp-fade rule basis):
        n=324, mean -0.10%, CI [-0.99%, +0.82%]. CI fully crosses zero.
        R5 verdict (D1): REMOVE the rule, revert to pass-through 1.00.
        The original -1.59% was already CI-marginal in R4 and is now
        statistically gone. Regime-conditional version may be tested
        later (D4 research item — pre-specified regime gate, must pass
        walk-forward before re-introduction).
      * Pooled top: v1 -1.06% → v2 +0.34% (sign-flipped — pooled de-weight
        was never defensible).
      * Coal complex (j0, jm0) hint still surfaced.

    Precedence (most specific first):
      1. F8-cn-no-boost   — bottom + weakness                  (workhorse, pass-through)
      2. CN1-top-passthrough — top (any direction)             (pass-through, no de-weight)
      3. Baseline
    """
    direction = sig.direction
    subtype = sig.subtype

    # --- F8-cn-no-boost: bottom + weakness — pass-through on CN ----------
    # R5 (2026-05-26, n=306): mean +1.19%, CI [+0.26%, +2.14%], hit 57.5%.
    # Significant positive (CI excludes zero) but R4's +3.81% was a 2.4y
    # window artifact. Hold at 1.00 pass-through; do NOT add boost without
    # separate walk-forward validation.
    if direction == "bottom" and subtype == "weakness":
        return PolicyDecision(
            weight=1.00,
            rule_id="F8-cn-no-boost",
            monitor_required=True,
            reason=(
                "weakness-subtype bottom on CN futures — most robust CN "
                "finding (Codex R5 2026-05-26: n=306, mean +1.19%, "
                "CI [+0.26%, +2.14%], hit 57.5%). R4's +3.81% was inflated "
                "by 2.4y sample window. Pass-through weight; no boost "
                "without dedicated walk-forward validation."
            ),
            strategy_hints=_cn_consumer_hints(sig),
        )

    # --- CN1-top-passthrough: ALL top divergences — pass-through ---------
    # R5 verdict (2026-05-26) removed the CN-top-supp-fade rule that
    # previously de-weighted top+higher=supporting to 0.80. Deep-data v2
    # (n=324) collapsed its basis from R4's mean -1.59% to -0.10% with
    # CI [-0.99%, +0.82%] fully crossing zero. Pooled top mean also
    # sign-flipped from -1.06% to +0.34%. No CN top configuration has
    # statistical basis for de-weighting on current evidence.
    if direction == "top":
        return PolicyDecision(
            weight=1.00,
            rule_id="CN1-top-passthrough",
            monitor_required=True,
            reason=(
                "top divergence on CN futures — no sub-bucket has a "
                "statistically defensible de-weight on deep-data v2 "
                "(Codex R5 2026-05-26). Pooled top n=506, mean +0.34%, "
                "CI [-0.32%, +1.02%]; top+higher=supporting n=324, "
                "mean -0.10%, CI [-0.99%, +0.82%]. Both CIs cross zero. "
                "R4's CN-top-supp-fade rule (weight 0.80 for the "
                "supporting sub-bucket) was REMOVED in R5 — its basis "
                "was a 2.4y sample window artifact."
            ),
            strategy_hints={
                "direction_gate_calibration_mismatch": (
                    "direction_gate is US-calibrated. cn_futures table is "
                    "pass-through, but consumers building outside the "
                    "engine should be aware of the mismatch."
                ),
                **(_cn_consumer_hints(sig) or {}),
            },
        )

    # --- Baseline ---------------------------------------------------------
    return PolicyDecision(
        weight=1.00,
        rule_id=None,
        monitor_required=False,
        reason=(
            "no calibrated CN futures rule applied; baseline confidence"
        ),
        strategy_hints=_cn_consumer_hints(sig),
    )


# ---------------------------------------------------------------------------
# CZCE calibration (extends cn_futures; 2026-05-30)
# ---------------------------------------------------------------------------

def _apply_czce(sig: DivergenceSignal) -> PolicyDecision:
    """CZCE commodity policy: cn_futures base + bottom/h=supporting disabled.

    RR backtest 2026-05-30 (ATR×0.75, n=125):
      bottom/h=supporting: n=42, EV=-0.167R, full_stop=59.5% — uniquely negative
      vs CFFEX (+0.458R) and CN_COMMODITY (positive) for the same cell.
    """
    ctx = sig.multi_tf_context or {}
    direction = sig.direction
    higher_rel = ctx.get("higher_relation")

    # --- CZCE1: bottom + h=supporting — disabled ----------------------------
    if direction == "bottom" and higher_rel == "supporting":
        return PolicyDecision(
            weight=0.0,
            rule_id="CZCE1-bottom-supporting-disabled",
            monitor_required=False,
            reason=(
                "CZCE bottom divergence with higher-TF supporting: "
                "RR backtest 2026-05-30 n=42, EV=-0.167R, full_stop=59.5%. "
                "CZCE-specific finding — CFFEX and CN_COMMODITY show positive "
                "EV for the same cell. Disabled."
            ),
        )

    return _apply_cn_futures(sig)


# ---------------------------------------------------------------------------
# CN Index Futures calibration (CFFEX IF/IH/IC/IM — 2026-06-01)
# ---------------------------------------------------------------------------

# DIF<0 sub-signal levels that are systematically negative in stock index futures.
# Per 2026-06-01 IS analysis (6-pool WF dataset, h=opposing, bottom signals):
#   intra_cycle_hist   n=113  EV=-0.299R
#   intra_cycle_dea    n= 31  EV=-0.195R   (DEAD, DIF<0)
#   intra_cycle_slope  n= 26  EV=-0.385R   (DIFSR, DIF<0)
# Heap (intra_cycle, n=14, EV=+0.564R) and inter_segment (n=46, EV=+0.433R)
# remain positive — only the DIF<0 sub-signal oscillator patterns fail.
_CN_INDEX_DISABLED_LEVELS = frozenset({
    "intra_cycle_hist",
    "intra_cycle_dea",
    "intra_cycle_slope",
})


def _apply_cn_index_futures(sig: DivergenceSignal) -> PolicyDecision:
    """CN stock index futures policy (CFFEX IF/IH/IC/IM).

    CNI1: bottom + h=opposing DIF<0 sub-signals are disabled.
    Calibrated on 2026-06-01 IS analysis of h=opposing bottoms only.
    Heap (intra_cycle) and inter_segment remain valid.

    All other signals fall back to cn_futures base policy.
    """
    ctx = sig.multi_tf_context or {}
    higher_rel = ctx.get("higher_relation")
    if (sig.direction == "bottom"
            and higher_rel == "opposing"
            and sig.level in _CN_INDEX_DISABLED_LEVELS):
        return PolicyDecision(
            weight=0.0,
            rule_id="CNI1-dif-neg-sublevel-disabled",
            monitor_required=False,
            reason=(
                f"DIF<0 sub-signal ({sig.level}) disabled for CN stock index futures "
                "(2026-06-01 IS, bottom × h=opposing): "
                "HICD n=113 EV=-0.299R, DEAD n=31 EV=-0.195R, DIFSR n=26 EV=-0.385R. "
                "Heap (intra_cycle +0.564R) and inter_segment (+0.433R) remain active."
            ),
        )

    return _apply_cn_futures(sig)


# ---------------------------------------------------------------------------
# CN Metal Futures calibration (SHFE/INE metals + energy — 2026-06-01)
# ---------------------------------------------------------------------------

def _apply_cn_metal_futures(sig: DivergenceSignal) -> PolicyDecision:
    """CN metal/energy futures policy (SHFE au/ag/cu/rb + INE sc).

    CNM1: top × inter_segment is disabled.
    2026-06-01 IS: n=49 EV=-0.182R, hit=31%.
    WF K=3: fold1=-0.297R (n=16), fold2=-0.225R (n=16) — both folds negative.
    Mechanism: inter_segment top divergence in commodity markets reliably fires
    at pullback points within larger uptrends rather than at true reversals.
    Heap (intra_cycle) top signals remain strongly positive — not gated.

    All other signals fall back to cn_futures base policy.
    """
    if sig.direction == "top" and sig.level == "inter_segment":
        return PolicyDecision(
            weight=0.0,
            rule_id="CNM1-top-inter-segment-disabled",
            monitor_required=False,
            reason=(
                "CN metal futures top/inter_segment: "
                "2026-06-01 IS n=49 EV=-0.182R hit=31%; "
                "WF K=3 fold1=-0.297R, fold2=-0.225R (both negative). "
                "Inter-segment top divergence fires at pullback points in uptrends, "
                "not at true reversals. Heap tops (+0.617R) remain active."
            ),
        )

    return _apply_cn_futures(sig)


def _cn_consumer_hints(sig: DivergenceSignal) -> dict[str, str] | None:
    """Common consumer hints for CN futures signals — universe selection guidance."""
    hint = {
        "instrument_filter_recommendation": (
            "exclude coal complex (j0, jm0) — sole negative-EV cluster "
            "in 19-symbol CN futures backtest (2026-05-24)"
        ),
        "preferred_universe": (
            "index futures (IF/IH/IC/IM) outperformed commodities by wide "
            "margin (bottoms +1.95%/63.7% vs commodity bottoms ~+1.0%)"
        ),
    }
    return hint


def weighted_signals(
    signals: list[DivergenceSignal],
    instrument_class: InstrumentClass = "us_equity",
) -> list[tuple[DivergenceSignal, PolicyDecision]]:
    """Convenience helper: apply the policy to every signal in a list."""
    return [(sig, apply_policy(sig, instrument_class=instrument_class)) for sig in signals]


# ---------------------------------------------------------------------------
# Provenance — these rules MUST be re-fit if any of the following changes:
# ---------------------------------------------------------------------------
#   us_equity:
#     - Data source: Polygon (current) → other (results may drift slightly)
#     - Adjustment basis: split-only (current) → split+dividend
#     - Symbol universe: 10-symbol US ETF/equity mix
#     - Timespan: 2021-05-24 → 2026-05-22 (5y, includes 2022 bear market)
#     - direction_gate multipliers (engine/divergence/direction_gate.py)
#     - Confidence band thresholds (LABEL_CANDIDATE/CONFIRMED above)
#
#   cn_futures:
#     - Data source: AKShare (sina) daily + TqSdk (Shinny) 60min/15min
#     - Symbol universe: 19 CN futures (4 index + 15 commodity)
#     - Timespan: daily 2005-2026; B-topology 2023-11 to 2026-04 (2.4y)
#     - B-topology: D + 1h + 15m multi-TF context enabled
#     - Validated by Codex R1-R4 (last: 2026-05-24)
#
# When refitting, also revisit:
#   - doc/cn-b-topology-backtest-2026-05-24.md
#   - doc/cn-option-payoff-backtest-2026-05-24.md
#   - doc/r4-review-2026-05-24.md
