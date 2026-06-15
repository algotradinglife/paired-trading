"""Score today's live signals against OOS-validated sweet spots.

Operational counterpart to analyze_sweet_spots_pool.py. Where the pool
analyzer FINDS sweet spots from history, this script SCORES today's
detector output against those known-good filters and produces a
trader-facing ranked card.

OOS-validated sweet spots (as of 2026-05-25, from
doc/sweet-spots-2026-05-25.md + project_initial_sweet_spots_2026_05_25
memory): only `bottom / swing_mid` for US pool survived strict 60/40
OOS validation. All other discovered patterns collapsed or lacked
sample. Production filters live in SWEET_SPOTS dict — refresh when
new OOS verdicts arrive.

Usage:
  uv run python scripts/score_today.py --pool US
  uv run python scripts/score_today.py --pool US --window-days 7
  uv run python scripts/score_today.py --symbols SPY QQQ --instrument-class us_equity

Output format:
  Latest <window_days> of signals across the pool, tagged with which
  sweet-spot region they fall in and a trade-readiness score (1-5).
  Sorted by score descending.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from data import bar_loader
from engine.divergence.bpull_detector import BPullDetector
from engine.divergence.context_a_detector import ContextADetector, ContextASignal
from engine.divergence.detector import detect_all_divergences
from engine.divergence.downstream_policies import apply_policy
from engine.divergence.pa_detector import PABottomDetector, PASignal
from engine.divergence.pa_direction_assessment import (
    DirectionVerdict,
    assess_direction,
)
from engine.divergence.pa_structure import PAStructureDetector
from engine.divergence.vflush_detector import VFlushDetector
from engine.regime.us_regime_gate import compute_regime_signal, is_risk_off
from engine.features.macd import macd
from engine.features.streams import compute_feature_streams
from engine.features.swing_context import compute_swing_context
from engine.options.cn_ag_selector import enrich_with_iv, select_otm_calls
from engine.options.cn_au_selector import enrich_with_iv_au, select_otm_calls_au
from engine.units.snapshot import compute_unit_metadata

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
_OPTIONS_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "options" / "cn" / "ag"
_AU_OPTIONS_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "options" / "cn" / "au"

_AG_SYMBOL_SUFFIX = "_ag"  # kq_m_shfe_ag — the only ag (silver) symbol in the metal pool
_AU_SYMBOL_SUFFIX = "_au"  # kq_m_shfe_au — the only au (gold) symbol in the metal pool
_OPTIONS_MIN_SCORE = 3     # Only annotate bottom signals with score >= this


def _compute_mm_pct(sig, bars: "pd.DataFrame", entry_close: float) -> float | None:
    """Measured-move target as % above entry: MM = B2 + (H1 - B1).

    H1 is the max high strictly between B1 and B2 (ref_idx excluded).
    Returns None for inter_segment signals (0% hit rate in both US and
    CN_METAL backtests), when geometry is degenerate, or when mm_pct > 10%
    (hit rate drops to 14-47% — unreliable, do not annotate).
    """
    if getattr(sig, "level", None) == "inter_segment":
        return None
    ref_idx = sig.reference_bar_idx
    cand_idx = sig.candidate_bar_idx
    # Need at least one bar between B1 and B2 to form H1
    if cand_idx <= ref_idx + 1 or entry_close <= 0:
        return None
    b1 = float(sig.price_side.reference_value)
    # Slice strictly after ref_idx so B1 bar's own high doesn't inflate H1
    h1 = float(bars["high"].iloc[ref_idx + 1:cand_idx].max())
    b2 = float(sig.price_side.candidate_value)
    mm_height = h1 - b1
    if mm_height <= 0:
        return None
    mm_pct = (b2 + mm_height) / entry_close * 100.0 - 100.0
    if mm_pct > 10.0:
        return None  # unreliable — reject rather than clamp to avoid false annotation
    return round(mm_pct, 2)


POOLS: dict[str, list[str]] = {
    "US": ["SPY", "QQQ", "IWM", "DIA", "GLD", "GDX", "XLF", "XLK", "TLT", "NVDA", "XLB", "XLE", "XLRE", "XLU"],
    "CN": ["kq_m_cffex_if", "kq_m_cffex_ih", "kq_m_cffex_ic", "kq_m_cffex_im"],
    "CN_COMMODITY": [
        "kq_m_shfe_rb", "kq_m_shfe_cu", "kq_m_shfe_au", "kq_m_shfe_ag",
        "kq_m_dce_m", "kq_m_dce_i", "kq_m_dce_j", "kq_m_dce_jm",
        "kq_m_dce_p", "kq_m_dce_y",
        "kq_m_czce_ta", "kq_m_czce_ma", "kq_m_czce_cf", "kq_m_czce_sr",
        "kq_m_ine_sc",
    ],
    # rb excluded — BPull OOS all-negative; MACD-divergence still included
    "CN_METAL": ["kq_m_shfe_cu", "kq_m_shfe_au", "kq_m_shfe_ag", "kq_m_ine_sc"],
    "CN_BOND": ["kq_m_cffex_tf", "kq_m_cffex_t", "kq_m_cffex_ts"],
}

POOL_INSTRUMENT_CLASS: dict[str, str] = {
    "US": "us_equity",
    "CN": "cn_index_futures",
    "CN_COMMODITY": "cn_futures",
    "CN_METAL": "cn_metal_futures",
    "CN_BOND": "cn_bond",  # promoted from cn_futures 2026-06-08; see pa_detector docstring
}

# PA H2 climax — STALE 2026-06-08: original K=3 STRONG PASS NOT REPRODUCIBLE.
# Full-stack 5.5y: EV -0.040R / n=64 / win 47%. 2025 alone -0.904R EV / n=9.
# Lane suspended (policy_weight=0 below).
#
# kq_m_dce_p (palm oil) EXCLUDED 2026-06-09 — n=11, EV-0.361R, full_stop rate
# 64% (worst in pool). Root cause: pivot-low stop too tight for palm oil
# intraday vol; 3 of 7 losses were 1-2 bar noise stop-outs. See
# doc/repro/agri_pos_dce_p_diagnosis_2026-06-09.md.
#
# BASELINE_REF: baselines/pa_h2_climax_cn_agri_pos.json
_CN_AGRI_POS_SYMBOLS: frozenset[str] = frozenset({
    "kq_m_dce_m",
    "kq_m_czce_ta", "kq_m_czce_ma", "kq_m_czce_sr",
})

# P0 lane × market eval 2026-06-09: pa_us_60min symbol-level suppression.
# Empirical full_stack 5.5y per-symbol shows these are net negative or
# very small samples with extreme negative EV. See
# doc/repro/lane_market_evaluation_2026-06-09.md kill list.
# 2026-06-09 P1c extension: added SPY (n=25 EV-0.04R, largest negative
# sample, structural broad-market pattern).
_PA_US_60MIN_SUPPRESS: frozenset[str] = frozenset({
    "DIA",   # n=10 EV-0.40R win=20% — broad-market reversal not the pattern
    "XLK",   # n=14 EV-0.14R win=29% — large-cap tech, low 60min vol
    "QQQ",   # n=11 EV-0.14R win=27% — same family as XLK
    "XLRE",  # n= 4 EV-0.75R win= 0% — small sample but 0 winners
    "SPY",   # n=25 EV-0.04R win=32% — broad-market (P1c 2026-06-09)
})

# P1c lane × market eval 2026-06-09: pa_us_dif_pos broad-market suppression.
# DIA and SPY consistently negative across context_a + pa_us_60min + pa_us_dif_pos
# = structural pattern (broad-market H2 reversals don't sustain to TP1).
_PA_US_DIF_POS_SUPPRESS: frozenset[str] = frozenset({
    "DIA",   # n=8  EV-0.026R win=50%
    "SPY",   # n=9  EV-0.088R win=56%
})

# All DIF-divergence-based detector levels.  paired-trading retired the
# DIF signal lane 2026-06-08 (decision: "DIF 全退役") — PA detectors own
# live signal generation.  By default score_today filters every record
# from these levels out of the scorecard; pass --include-dif-detectors
# to opt in (historical CSV regeneration or A/B comparison runs).
#
# Two groups:
#   Classical 3:        intra_cycle / inter_cycle / inter_segment
#                       — original MACD divergence detectors, baseline
#                       through 2026-05-31 reports.
#   intra_cycle_* (6):  HICD / DIFSR / DEAD ± bull variants
#                       — engine files carry DEPRECATED banner since
#                       2026-06-08; sample-explosion side-effects broke
#                       the 2026-05-31 baselines.
DIF_DETECTOR_LEVELS: frozenset[str] = frozenset({
    # Classical 3
    "intra_cycle",
    "inter_cycle",
    "inter_segment",
    # intra_cycle_* (6 deprecated variants)
    "intra_cycle_hist",
    "intra_cycle_slope",
    "intra_cycle_dea",
    "intra_cycle_bull_hist",
    "intra_cycle_bull_slope",
    "intra_cycle_bull_dea",
})


@dataclass(frozen=True)
class SweetSpotRule:
    """One OOS-validated sweet spot. score_today applies these to live signals.

    Bucket constraints carry FROZEN OOS train-period tercile edges so live
    scoring uses the same boundaries the validation used. Recomputing
    edges from a different population (e.g., full current snapshot) would
    let near-boundary live signals get a different label than the
    validated rule (codex 2026-05-25 review). When the OOS validation is
    refreshed, update the edges here AND bump validated_date / re-state
    the train/test hit numbers.

    `horizon` is the forward-return window the rule was validated on. A
    bottom/h=5 rule means "the OOS test showed 5-day forward return > 0
    in test_hit_pct of cases" — a consumer holding 20 days would get
    different outcomes. Match score reports horizon so the consumer can
    align hold period to validation window.

    `validated_pool` documents the symbol universe that produced the rule.
    Rule matching is by `pool_class` (instrument_class), so a rule
    validated on CN_COMMODITY can also fire for a CN-index signal of the
    same instrument_class — cross-pool extrapolation, real but accepted.

    Two flavours of constraint live side by side:

    1. **DIF-lane bucket constraints** (`swing_constraint`,
       `wick_constraint`, `vol_constraint`, `subtype_constraint`).  These
       read DIF-detector context features (`prior_swing_distance_pct`
       etc.) and apply only to records produced by `detect_all_divergences`.
       Per `doc/repro/score_audit_2026-06-08.md` finding S3, PA records
       never populate these — so DIF-bucket rules silently match zero PA
       signals.
    2. **PA-native constraints** (`level_constraint`, `feature_constraints`).
       Match directly on PA record fields (`level`, `pa_trend`, `pa_legs`,
       `pa_phase`, ...).  Allow sweet-spot annotation to flow on the PA
       lane (B1-2 fix 2026-06-08).

    `validation_status` carries a free-form note so consumers can tell
    OOS-validated rules apart from drafts awaiting re-validation."""
    rule_id: str
    description: str
    pool_class: str           # which instrument_class this rule applies to (us_equity / cn_futures)
    direction: str            # "top" or "bottom"
    horizon: int = 20         # forward-return window the rule was validated on
    validated_pool: str = ""  # POOL name (US / CN / CN_COMMODITY) for documentation
    subtype_constraint: str | None = None  # "standard" | "weakness" | "hidden" | None
    # Each bucket constraint is either None (no constraint) or a tuple
    # (bucket_name, (lo_edge, hi_edge)). At match time we test whether
    # the live signal's feature value falls in the named tercile under
    # those edges.  These read DIF-detector context_features only.
    swing_constraint: tuple[str, tuple[float, float]] | None = None
    wick_constraint: tuple[str, tuple[float, float]] | None = None
    vol_constraint: tuple[str, tuple[float, float]] | None = None
    # PA-native equality constraints.  level_constraint matches sig.level
    # (e.g., "pa_us_60min").  feature_constraints requires every key/value
    # pair to be present on the live record dict — useful for matching
    # PA-fields like pa_trend / pa_legs / pa_phase / pa_isolated.
    level_constraint: str | None = None
    feature_constraints: tuple[tuple[str, object], ...] | None = None
    train_hit_pct: float = 0.0
    test_hit_pct: float = 0.0
    validated_date: str = ""  # YYYY-MM-DD
    validation_status: str = ""  # free-form note; "OOS 60/40" vs "draft" etc.


# OOS-validated sweet spots — only those that survived 60/40 train/test
# split per doc/sweet-spots-2026-05-25.md.
#
# Edges below are TRAIN-PERIOD tercile bounds, extracted from
# data/review/sweet_spots_pool_us_h20_oos.csv (split=='train' rows,
# horizon-overlap purged). Refreshing OOS validation must re-extract.
#
# 2026-06-08 (B1-2 fix per score_audit_2026-06-08.md S3):
#   The original `US-bot-swing-mid-h20` rule was DIF-lane only — its
#   `prior_swing_distance_pct` predicate matched 0/95 PA records over
#   the past year because PA detectors don't populate that field.  With
#   DIF retired (`DIF_DETECTOR_LEVELS` filter), the rule was dead on
#   arrival.  Two PA-native draft rules replace it below
#   (`US-PA-60min-uptrend-hopp`, `US-PA-60min-uptrend-legs1`); they
#   trace the WF-validated winners from `pa_detector.policy_weight()`
#   docstring (uptrend + h=opp ± legs=1) but have NOT been put through
#   the 60/40 sweet-spot OOS rig that the original DIF rules were —
#   `validation_status` marks that explicitly.  The old DIF rule is
#   retained (commented below) only as documentation; it can be
#   resurrected when the DIF lane comes back, or deleted once consumers
#   stop referencing the `US-bot-swing-mid-h20` rule_id.
SWEET_SPOTS: list[SweetSpotRule] = [
    SweetSpotRule(
        rule_id="US-PA-60min-uptrend-hopp",
        description="PA H2 bottom on 60min, uptrend + h=opp (US, base lane)",
        pool_class="us_equity",
        direction="bottom",
        horizon=14,  # pa_swing max_hold ~140 60min bars ≈ 14 trading days
        validated_pool="US",
        level_constraint="pa_us_60min",
        # Match every uptrend pa_us_60min fire — already gated to h=opp
        # in score_today's pa_us_60min block (line ~964).
        feature_constraints=(("pa_trend", "uptrend"),),
        # WF backtest_pa_swing.py 60min (NOT 60/40 sweet-spot OOS):
        #   K=2: F1+0.625R(n=12) F2+0.708R(n=24)
        #   K=3: F1+0.147R F2+0.600R F3+0.636R (4/4 folds positive)
        train_hit_pct=66.7,
        test_hit_pct=66.7,  # best estimate; placeholder until sweet-spot rig re-runs
        validated_date="2026-06-08",
        validation_status="PA-native, draft — needs 60/40 OOS re-validation",
    ),
    SweetSpotRule(
        rule_id="US-PA-60min-uptrend-legs1",
        description="PA H2 bottom on 60min, uptrend + h=opp + legs_count_down=1 (US, premium lane)",
        pool_class="us_equity",
        direction="bottom",
        horizon=14,
        validated_pool="US",
        level_constraint="pa_us_60min",
        feature_constraints=(("pa_trend", "uptrend"), ("pa_legs", 1)),
        # WF backtest_pa_swing.py 60min legs=1 subset (highest-EV cell):
        #   K=2: F1+1.000R(n=5)  F2+0.750R(n=10)
        #   K=3: F1+0.500R(n=5)  F2+0.667R(n=3)  F3+0.750R(n=10)
        # All folds positive; this is the lane that earns the 0.90 weight
        # in pa_detector.policy_weight().
        train_hit_pct=75.0,
        test_hit_pct=72.0,
        validated_date="2026-06-08",
        validation_status="PA-native, draft — needs 60/40 OOS re-validation",
    ),
    # --- DIF-lane rule, retained as documentation ---------------------
    # SweetSpotRule(
    #     rule_id="US-bot-swing-mid-h20",
    #     description="bottom divergence with mid-range prior_swing_pct (US, 20-day hold)",
    #     pool_class="us_equity", direction="bottom", horizon=20,
    #     validated_pool="US",
    #     swing_constraint=("swing_mid", (-5.0181, 3.8242)),
    #     train_hit_pct=85.3, test_hit_pct=68.4, validated_date="2026-05-25",
    # )
    SweetSpotRule(
        rule_id="CN-bot-standard-h5",
        description="bottom standard-subtype divergence on CN index futures (5-day hold)",
        pool_class="cn_index_futures",
        direction="bottom",
        horizon=5,
        validated_pool="CN",
        subtype_constraint="standard",
        train_hit_pct=66.7,
        test_hit_pct=88.9,
        validated_date="2026-05-25",
    ),
    SweetSpotRule(
        rule_id="CN-COMMODITY-bot-wlow-vmid-h5",
        description="bottom low-wick mid-volume divergence on CN commodity futures (5-day hold)",
        pool_class="cn_futures",
        direction="bottom",
        horizon=5,
        validated_pool="CN_COMMODITY",
        # CN_COMMODITY h=5 train terciles:
        #   wick_ratio: [+0.2331, +0.4610]; volume_ratio: [+0.9540, +1.2629]
        wick_constraint=("wick_low", (0.2331, 0.4610)),
        vol_constraint=("vol_mid", (0.9540, 1.2629)),
        train_hit_pct=73.5,
        test_hit_pct=81.8,
        validated_date="2026-05-25",
    ),
    SweetSpotRule(
        rule_id="CN-COMMODITY-bot-wmid-vhigh-h10",
        description="bottom mid-wick high-volume divergence on CN commodity futures (10-day hold)",
        pool_class="cn_futures",
        direction="bottom",
        horizon=10,
        validated_pool="CN_COMMODITY",
        # CN_COMMODITY h=10 train terciles:
        #   wick_ratio: [+0.2328, +0.4613]; volume_ratio: [+0.9543, +1.2645]
        wick_constraint=("wick_mid", (0.2328, 0.4613)),
        vol_constraint=("vol_high", (0.9543, 1.2645)),
        train_hit_pct=78.3,
        test_hit_pct=63.0,
        validated_date="2026-05-25",
    ),
]


def in_tercile_mid(value: float | None, edges: tuple[float, float]) -> bool:
    """True iff value falls in the mid tercile (lo ≤ v < hi)."""
    if value is None:
        return False
    lo, hi = edges
    return lo <= value < hi


def in_tercile_low(value: float | None, edges: tuple[float, float]) -> bool:
    if value is None:
        return False
    return value < edges[0]


def in_tercile_high(value: float | None, edges: tuple[float, float]) -> bool:
    if value is None:
        return False
    return value >= edges[1]


_BUCKET_TESTS = {
    "swing_low": in_tercile_low, "swing_mid": in_tercile_mid, "swing_high": in_tercile_high,
    "wick_low": in_tercile_low, "wick_mid": in_tercile_mid, "wick_high": in_tercile_high,
    "vol_low": in_tercile_low, "vol_mid": in_tercile_mid, "vol_high": in_tercile_high,
}


# P2 regime gate (2026-06-09 lane × market eval):
# SPY-based risk_off detector for pa_us_60min + context_a US suppression.
# Lazy-loaded; cache lives for the lifetime of one score_today invocation.
# 2026-06-09 (post-codex #2): availability also exposed via
# get_regime_gate_status() so downstream consumers can stamp scorecard
# records with regime_gate_available=False when the gate fail-opens.
_US_REGIME_CACHE: dict = {"signal": None, "loaded": False, "unavailable_reason": None}


def _get_us_regime_signal(args) -> pd.DataFrame | None:
    """Lazy-load SPY daily and compute regime signal. Returns None if SPY
    bars are unavailable (gate becomes a no-op — no suppression).

    Logs to stderr ONCE per invocation when unavailable, so a missing SPY
    snapshot doesn't silently disable the gate (codex review 2026-06-09 #2)."""
    if _US_REGIME_CACHE["loaded"]:
        return _US_REGIME_CACHE["signal"]
    _US_REGIME_CACHE["loaded"] = True
    try:
        spy_bars = _load_bars_daily("spy", args)
    except Exception as exc:
        spy_bars = None
        _US_REGIME_CACHE["unavailable_reason"] = f"SPY load raised {type(exc).__name__}: {exc}"
    if spy_bars is None:
        if _US_REGIME_CACHE["unavailable_reason"] is None:
            _US_REGIME_CACHE["unavailable_reason"] = "SPY daily bars not found"
    elif len(spy_bars) < 200:
        _US_REGIME_CACHE["unavailable_reason"] = (
            f"SPY daily bars insufficient ({len(spy_bars)} bars, need ≥200 for SMA200)"
        )
        spy_bars = None
    if spy_bars is None:
        print(
            f"[regime_gate] FAIL-OPEN: {_US_REGIME_CACHE['unavailable_reason']}; "
            f"US H2-family suppression DISABLED for this run. "
            f"See engine/regime/us_regime_gate.py + STATUS.md.",
            file=sys.stderr,
        )
        return None
    _US_REGIME_CACHE["signal"] = compute_regime_signal(spy_bars)
    return _US_REGIME_CACHE["signal"]


def _us_lane_suppressed_by_regime(sig_date, args) -> bool:
    """Return True if US H2-family lanes should be suppressed at sig_date.
    Returns False when SPY data unavailable — bias to NOT suppressing."""
    sig = _get_us_regime_signal(args)
    if sig is None:
        return False
    return is_risk_off(sig, sig_date)


def get_regime_gate_status() -> dict:
    """Public accessor for scorecard / report consumers.

    Returns dict with:
      available: bool        — True if gate is functioning
      reason: str | None     — why unavailable (only when available=False)

    Call AFTER score_today's main loop has processed at least one US
    instrument (which triggers lazy SPY load)."""
    return {
        "available": _US_REGIME_CACHE["signal"] is not None,
        "reason": _US_REGIME_CACHE.get("unavailable_reason"),
    }


def _load_bars_daily(sym: str, args) -> pd.DataFrame | None:
    """Load daily bars for sym from BarStore or JSON fallback."""
    if getattr(args, "quant_data_root", None) is not None:
        resolved = bar_loader.infer_symbol_and_mic(sym)
        if resolved is not None:
            quant_sym, mic = resolved
            try:
                return bar_loader.load_bars_quant(quant_sym, mic, "D", args.quant_data_root)
            except Exception as e:
                print(f"quant load {sym}/daily: {e} — falling back to JSON", file=sys.stderr)
    path = args.bars_dir / f"{sym.lower()}_daily.json"
    if not path.exists():
        return None
    return bar_loader.load_bars_json(path)


def _load_bars_60(sym: str, args) -> pd.DataFrame | None:
    """Load 60min bars for sym, mirroring _load_bars_daily quant-first strategy."""
    if getattr(args, "quant_data_root", None) is not None:
        resolved = bar_loader.infer_symbol_and_mic(sym)
        if resolved is not None:
            quant_sym, mic = resolved
            try:
                return bar_loader.load_bars_quant(quant_sym, mic, "60min", args.quant_data_root)
            except Exception:
                pass  # fall through to JSON
    path = args.bars_dir / f"{sym.lower()}_60.json"
    if not path.exists():
        return None
    return bar_loader.load_bars_json(path)


def _load_bars_15(sym: str, args) -> pd.DataFrame | None:
    """Load 15min bars for sym, mirroring _load_bars_60 quant-first strategy."""
    if getattr(args, "quant_data_root", None) is not None:
        resolved = bar_loader.infer_symbol_and_mic(sym)
        if resolved is not None:
            quant_sym, mic = resolved
            try:
                return bar_loader.load_bars_quant(quant_sym, mic, "15min", args.quant_data_root)
            except Exception:
                pass
    path = args.bars_dir / f"{sym.lower()}_15.json"
    if not path.exists():
        return None
    return bar_loader.load_bars_json(path)


def _load_bars_weekly(sym: str, args) -> pd.DataFrame | None:
    """Load weekly bars for sym for the DIR weekly_trend source.

    Strategy (mirrors ``_load_bars_60`` quant-first / JSON fallback):
      1. Try BarStore Parquet at level "W".
      2. Fall back to legacy JSON snapshot at ``<sym>_weekly.json``.
      3. Last resort — resample daily bars to W via ``pd.resample('W')``.

    Returns ``None`` if no source yields a usable frame (or daily fallback
    has < 30 daily bars to resample).
    """
    if getattr(args, "quant_data_root", None) is not None:
        resolved = bar_loader.infer_symbol_and_mic(sym)
        if resolved is not None:
            quant_sym, mic = resolved
            try:
                return bar_loader.load_bars_quant(quant_sym, mic, "W", args.quant_data_root)
            except Exception:
                pass  # fall through to JSON, then to daily-resample

    json_path = args.bars_dir / f"{sym.lower()}_weekly.json"
    if json_path.exists():
        try:
            return bar_loader.load_bars_json(json_path)
        except Exception:
            pass  # fall through to daily-resample

    # Daily-resample fallback — only fires if neither Parquet nor JSON works.
    daily = _load_bars_daily(sym, args)
    if daily is None or len(daily) < 30:
        return None
    return _resample_daily_to_weekly(daily)


def _resample_daily_to_weekly(daily: pd.DataFrame) -> pd.DataFrame | None:
    """Resample a daily OHLCV frame to weekly bars (W-FRI convention).

    Returns a frame with columns ``timestamp, open, high, low, close, volume``.
    Returns None on degenerate input.
    """
    if "timestamp" not in daily.columns or len(daily) == 0:
        return None
    df = daily.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp")
    agg: dict[str, str] = {}
    for col, how in (
        ("open", "first"),
        ("high", "max"),
        ("low", "min"),
        ("close", "last"),
        ("volume", "sum"),
    ):
        if col in df.columns:
            agg[col] = how
    if not agg:
        return None
    weekly = df.resample("W").agg(agg).dropna(subset=["close"]).reset_index()
    weekly["time"] = weekly["timestamp"].values.astype("datetime64[s]").astype("int64")
    return weekly


def _attach_direction_verdict(
    rec: dict,
    daily_bars: "pd.DataFrame",
    hourly_bars: "pd.DataFrame | None",
    bar_idx: int,
    macd_df: "pd.DataFrame | None" = None,
    *,
    ambush_pattern: str = "h2_bottom",
    weekly_bars: "pd.DataFrame | None" = None,
    bars_15: "pd.DataFrame | None" = None,
    signal_tf_bars: "pd.DataFrame | None" = None,
    signal_tf_label: str | None = None,
    signal_tf_bar_idx: int | None = None,
) -> None:
    """Annotate ``rec`` with a DirectionVerdict from the DIR module.

    Adds three fields on the record:
        direction_verdict     : "long_call" | "long_put" | "skip"
        direction_confidence  : float in [0, 1]
        direction_sources     : {source_name: vote, ...}

    ANNOTATION ONLY (Step 1, 2026-06-08):
    These fields are attached for human review.  ``score_today`` does
    NOT use the verdict to gate emission, change scoring, or alter
    weights — those continue to come from the existing per-detector
    policy_weight paths.  The verdict is recorded so reviewers can
    sanity-check alignment between the synthesiser and the existing
    PA gates before any consumer starts reading the verdict.

    ``ambush_pattern`` ("h2_bottom" / "h2_top") drives the polarity-aware
    voting on the hourly / context / 15-min sources.  All four current
    emit blocks (pa_us_60min, pa_us_dif_pos, pa_h2, pa_cn_bond) emit
    bottoms, so they pass ``"h2_bottom"``.

    ``weekly_bars`` and ``bars_15`` are accepted so the caller can feed
    the multi-TF sources (weekly_trend / minute15_state) once the
    orchestrator wires them into ``assess_direction``.  Until that
    merge lands here, these are stashed on ``rec`` under the keys
    ``_dir_weekly_bars_available`` / ``_dir_15m_bars_available`` so the
    parent session's merge step can verify the wiring without changing
    this helper's call sites again.
    """
    try:
        verdict: DirectionVerdict = assess_direction(
            daily_bars, hourly_bars, bar_idx,
            macd_df=macd_df, ambush_pattern=ambush_pattern,
            weekly_bars=weekly_bars, bars_15=bars_15,
            signal_tf_bars=signal_tf_bars,
            signal_tf_label=signal_tf_label,
            signal_tf_bar_idx=signal_tf_bar_idx,
        )
    except Exception as exc:  # pragma: no cover — defensive
        rec["direction_verdict"] = "skip"
        rec["direction_confidence"] = 0.0
        rec["direction_sources"] = {}
        rec["direction_rationale"] = f"assess_err={exc!s}"
        return
    rec["direction_verdict"] = verdict.direction
    rec["direction_confidence"] = round(float(verdict.confidence), 4)
    rec["direction_sources"] = {s.name: s.vote for s in verdict.sources}
    rec["direction_rationale"] = verdict.rationale


def _position_size(r: dict) -> str:
    """Derive position-size recommendation for a scored signal.

    Levels: full / half / light / watch

    Rules (applied in order):
    1. Base from score: 4=full, 3=half, 2=light, 1=watch
    2. Phase cap (PA signals): TR/TR_FORMING → cap at half; BEAR/UNCLEAR → watch
    3. 15m confirmation: explicitly False → downgrade one level
    """
    _levels = ["full", "half", "light", "watch"]

    score = r.get("score", 1)
    if score >= 4:
        base = "full"
    elif score == 3:
        base = "half"
    elif score == 2:
        base = "light"
    else:
        base = "watch"

    # Phase cap for PA signals (pa_phase present)
    pa_phase = r.get("pa_phase")
    if pa_phase in ("TR", "TR_FORMING"):
        if base == "full":
            base = "half"
    elif pa_phase in ("BEAR", "UNCLEAR"):
        base = "watch"

    # 15min confirmation downgrade (CN_METAL PA H2 only; None = not applicable)
    pa_15m = r.get("pa_15m_confirmed")
    if pa_15m is False:
        idx = _levels.index(base)
        base = _levels[min(idx + 1, len(_levels) - 1)]

    return base


# --- Signal-bar quality gate (ADVISORY / shadow — does NOT affect position_size) ----
# Surfaced so we can gather forward/OOS evidence on the signal-bar quality finding
# (doc/signal-bar-quality-hardening-2026-06-15, reviewer t_6be91653 approved). In-sample
# pooled rb+cu+au (n=88), only the DOUBLE-STRONG conjunction (strong body AND close at
# the directional extreme) carried EV (+1.28R vs +0.40R); a SINGLE strong signal was
# NOT better than neither — so this is a BINARY flag, not a monotone full/half/light
# tier, and it is deliberately NOT wired into sizing pending out-of-sample validation.
# Thresholds are provisional (Brooks strong-bar); the study used per-corpus median splits
# (body_frac≈0.8, close_pos≈1.0) which can't be reproduced live without a cohort.
SIGNAL_BAR_BODY_FRAC_MIN = 0.5     # body >= half the range (strong/trend bar)
SIGNAL_BAR_CLOSE_EXTREME = 0.66    # close within the extreme third (oriented by direction)


def _signal_bar_quality(o: float, h: float, low: float, c: float, direction: str) -> dict:
    """Advisory candidate-bar geometry + binary double-strong flag.

    direction 'top' (short-like) → strong close near the LOW; otherwise (bottom/long-like)
    → strong close near the HIGH. Range-zero bars → flag False. ADVISORY ONLY.
    """
    rng = h - low
    if rng <= 0:
        return {"body_frac": None, "close_pos": None, "double_strong": False}
    body_frac = abs(c - o) / rng
    close_pos = (c - low) / rng
    body_strong = body_frac >= SIGNAL_BAR_BODY_FRAC_MIN
    if direction == "top":
        close_strong = close_pos <= (1.0 - SIGNAL_BAR_CLOSE_EXTREME)
    else:
        close_strong = close_pos >= SIGNAL_BAR_CLOSE_EXTREME
    return {"body_frac": round(body_frac, 3), "close_pos": round(close_pos, 3),
            "double_strong": bool(body_strong and close_strong)}


def _attach_signal_bar_quality(rec: dict, bars, bar_idx: int) -> None:
    """Attach advisory signal_bar_quality to a scored record from its candidate bar.
    Direction taken from rec['direction'] (bottom/long-like default). ADVISORY ONLY —
    never reads/writes position_size. Best-effort: on any bar access error, sets None."""
    try:
        cand = bars.iloc[bar_idx]
        rec["signal_bar_quality"] = _signal_bar_quality(
            float(cand["open"]), float(cand["high"]), float(cand["low"]),
            float(cand["close"]), rec.get("direction"))
    except (KeyError, IndexError, ValueError, TypeError):
        rec["signal_bar_quality"] = {"body_frac": None, "close_pos": None, "double_strong": False}


def match_rule(rule: SweetSpotRule, sig_dir: str, sig_subtype: str,
               ctx: dict[str, object], rec: dict[str, object] | None = None,
               sig_level: str | None = None) -> bool:
    """Apply this rule's constraints to a live signal.

    Two constraint families:

    1. DIF-lane bucket constraints (`swing_constraint`/`wick_constraint`/
       `vol_constraint` + `subtype_constraint`) read frozen OOS train-period
       tercile edges from the rule and check the live signal's
       `context_features` dict (`ctx`).  These only apply to records from
       `detect_all_divergences` — PA records carry no `ctx` content for
       these keys.

    2. PA-native constraints (`level_constraint`, `feature_constraints`)
       read the live record dict (`rec`) directly — useful for fields
       like `level`, `pa_trend`, `pa_legs`, `pa_phase`.  When `rec` is
       None (legacy DIF caller), PA-native constraints fall back to None
       lookups; any rule that *requires* a PA-native field will
       correctly fail to match.

    Args:
        rule: the candidate rule.
        sig_dir: signal direction ("top" / "bottom").
        sig_subtype: signal subtype ("standard" / "weakness" / "hidden" / PA subtype).
        ctx: DIF-detector context_features (may be empty for PA records).
        rec: the full scored-record dict (carries PA-native fields).
            None for legacy callers that don't have the dict yet.
        sig_level: signal level string ("intra_cycle" / "pa_us_60min" / ...).
            Falls back to ``rec.get("level")`` when ``rec`` is provided.
    """
    if sig_dir != rule.direction:
        return False
    if rule.subtype_constraint is not None and sig_subtype != rule.subtype_constraint:
        return False
    # DIF-lane bucket constraints (read from ctx).
    for constraint, ctx_key in [
        (rule.swing_constraint, "prior_swing_distance_pct"),
        (rule.wick_constraint, "candidate_rejection_wick_ratio"),
        (rule.vol_constraint, "candidate_volume_ratio"),
    ]:
        if constraint is None:
            continue
        bucket_name, edges = constraint
        test = _BUCKET_TESTS.get(bucket_name)
        if test is None:
            return False
        if not test(ctx.get(ctx_key), edges):
            return False
    # PA-native level constraint.
    if rule.level_constraint is not None:
        live_level = sig_level if sig_level is not None else (
            rec.get("level") if rec is not None else None
        )
        if live_level != rule.level_constraint:
            return False
    # PA-native equality constraints on record fields.
    if rule.feature_constraints is not None:
        if rec is None:
            return False
        for key, want in rule.feature_constraints:
            if rec.get(key) != want:
                return False
    return True


def _annotate_pa_sweet_spots(rec: dict, pool_rules: list[SweetSpotRule]) -> None:
    """Mutate ``rec['matched_sweet_spots']`` to list matching PA-native rules.

    Helper for the PA detector blocks (pa_us_60min, pa_us_dif_pos,
    pa_h2, pa_h2_climax, pa_cn_bond, bpull, vflush, context_a).  PA
    records carry no DIF context_features, so we feed an empty ctx and
    rely on PA-native level/feature constraints.  Rules that depend on
    DIF bucket constraints (e.g. CN_COMMODITY wick/vol rules) will
    correctly fail to match since the live record's ctx is empty.
    """
    matched: list[str] = []
    for r in pool_rules:
        if match_rule(
            r,
            sig_dir=rec.get("direction", ""),
            sig_subtype=rec.get("subtype", ""),
            ctx={},
            rec=rec,
            sig_level=rec.get("level"),
        ):
            matched.append(r.rule_id)
    rec["matched_sweet_spots"] = matched


def readiness_score(matched_rules: list[SweetSpotRule], sig_confidence: float) -> int:
    """Quick 1-5 score combining matched sweet spots + raw detector confidence."""
    base = 1
    if matched_rules:
        # +1 per OOS-validated match
        base += min(len(matched_rules), 2)
        best_test = max(r.test_hit_pct for r in matched_rules)
        if best_test >= 70:
            base += 1
    if sig_confidence >= 0.8:
        base += 1
    return min(5, base)


def main() -> int:
    p = argparse.ArgumentParser(description="Score today's signals vs OOS-validated sweet spots")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--pool", choices=sorted(POOLS), help="preset symbol pool")
    grp.add_argument("--symbols", nargs="+", help="explicit symbol list")
    p.add_argument("--instrument-class", choices=["us_equity", "cn_futures", "cn_index_futures", "czce", "cn_metal_futures", "cn_bond"],
                   default=None, dest="instrument_class")
    p.add_argument("--bars-dir", type=Path, default=DEFAULT_BARS_DIR)
    p.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
                   help="quant-data Parquet root (default: data/quant/)")
    p.add_argument("--window-days", type=int, default=7,
                   help="how many trailing calendar days of signals to surface (default 7)")
    p.add_argument("-o", "--output", type=Path, help="write JSON scorecard to this file")
    p.add_argument("--include-dif-detectors", action="store_true",
                   help="emit DIF-divergence-based detector records (classical 3 "
                        "intra_cycle/inter_cycle/inter_segment + 6 deprecated "
                        "intra_cycle_* variants); default skips them — paired-"
                        "trading retired the DIF lane 2026-06-08.  See "
                        "DIF_DETECTOR_LEVELS for the full list.")
    args = p.parse_args()

    symbols = POOLS[args.pool] if args.pool else args.symbols
    if args.instrument_class is not None:
        instrument_class = args.instrument_class
    elif args.pool:
        instrument_class = POOL_INSTRUMENT_CLASS[args.pool]
    else:
        instrument_class = "us_equity"

    pool_name = args.pool if args.pool else "custom"
    # Rule selection: instrument_class match is mandatory. Additionally, when
    # --pool is set, rules must have validated_pool matching the pool name
    # — a CN-COMMODITY-validated rule won't fire on CN index signals (codex
    # 2026-05-25). For --symbols (custom pool, validated_pool unknown) we
    # accept all matching-class rules with a warning so consumer can opt in.
    if args.pool:
        pool_rules = [r for r in SWEET_SPOTS
                       if r.pool_class == instrument_class and r.validated_pool == args.pool]
    else:
        pool_rules = [r for r in SWEET_SPOTS if r.pool_class == instrument_class]
        if pool_rules:
            print(f"NOTE: --symbols mode loads ALL {instrument_class} rules "
                  f"regardless of original validated_pool. Cross-pool extrapolation; "
                  f"verify symbol universe matches.", file=sys.stderr)

    cutoff_date = date.today() - timedelta(days=args.window_days)
    print(f"Pool: {pool_name} ({len(symbols)} symbols, class={instrument_class})")
    print(f"Window: last {args.window_days} days (signals on/after {cutoff_date})")
    print(f"Active sweet-spot rules for this class: {len(pool_rules)}")
    for r in pool_rules:
        print(f"  - {r.rule_id} (validated {r.validated_date} on {r.validated_pool}, h={r.horizon}): "
              f"{r.description}")
        print(f"      train hit {r.train_hit_pct:.1f}%, test hit {r.test_hit_pct:.1f}%")
        if r.validation_status:
            print(f"      status: {r.validation_status}")
        if r.subtype_constraint is not None:
            print(f"      subtype: {r.subtype_constraint}")
        if r.level_constraint is not None:
            print(f"      level: {r.level_constraint}")
        if r.feature_constraints is not None:
            kv = ", ".join(f"{k}={v!r}" for k, v in r.feature_constraints)
            print(f"      features: {kv}")
        for label, c in [("swing", r.swing_constraint), ("wick", r.wick_constraint),
                          ("vol", r.vol_constraint)]:
            if c is not None:
                bname, (lo, hi) = c
                # Show the actual predicate so traders see the live threshold,
                # not just the train tercile range (codex 2026-05-25):
                #   _low → value < lo;  _mid → lo ≤ value < hi;  _high → value ≥ hi
                if bname.endswith("_low"):
                    print(f"      {label}: {bname} (value < {lo:+.4f})")
                elif bname.endswith("_high"):
                    print(f"      {label}: {bname} (value ≥ {hi:+.4f})")
                else:
                    print(f"      {label}: {bname} ({lo:+.4f} ≤ value < {hi:+.4f})")
    print()

    scored: list[dict] = []
    loaded_symbols = 0
    for sym in symbols:
        bars = _load_bars_daily(sym, args)
        if bars is None:
            print(f"  {sym}: missing data, skipped", file=sys.stderr)
            continue
        loaded_symbols += 1
        h_bars = None  # loaded on demand by detector blocks below
        # DIR multi-TF feeds: cached per symbol so the four bottom emit
        # blocks (pa_us_60min, pa_us_dif_pos, pa_h2, pa_cn_bond) share
        # one Parquet hit each.  ``_w_bars`` falls back to a
        # daily→weekly resample if Parquet "W" / JSON weekly missing.
        _w_bars: pd.DataFrame | None = None
        _bars_15_cache: pd.DataFrame | None = None
        _dir_feeds_loaded: bool = False
        macd_df = macd(bars["close"], hist_scale=1.0)
        streams = compute_feature_streams(bars["close"], macd_df["dif"], macd_df["dea"], macd_df["hist"])
        units = compute_unit_metadata(macd_df["dif"], macd_df["dea"], macd_df["hist"], streams["dif_proximity_zero"])
        signals = detect_all_divergences(
            units_df=units, ohlc=bars, dif=macd_df["dif"], hist=macd_df["hist"],
            level_id="D", instrument_class=instrument_class,
        )
        for sig in signals:
            if sig.timestamp.date() < cutoff_date:
                continue
            if sig.level in DIF_DETECTOR_LEVELS and not args.include_dif_detectors:
                continue
            ctx = sig.context_features or {}
            policy = apply_policy(sig, instrument_class=instrument_class)
            if policy.weight == 0.0:
                continue
            matched = [r for r in pool_rules if match_rule(r, sig.direction, sig.subtype, ctx)]
            score = readiness_score(matched, sig.confidence)
            sig_date = sig.timestamp.date()
            entry_close = float(bars["close"].iloc[sig.candidate_bar_idx])
            rec: dict = {
                "symbol": sym,
                "date": sig_date.isoformat(),
                "direction": sig.direction,
                "level": sig.level,
                "subtype": sig.subtype,
                "confidence": round(sig.confidence, 3),
                "wick_ratio": round(ctx.get("candidate_rejection_wick_ratio"), 3) if ctx.get("candidate_rejection_wick_ratio") is not None else None,
                "swing_pct": round(ctx.get("prior_swing_distance_pct"), 2) if ctx.get("prior_swing_distance_pct") is not None else None,
                "vol_ratio": round(ctx.get("candidate_volume_ratio"), 2) if ctx.get("candidate_volume_ratio") is not None else None,
                "invalidation_level": ctx.get("invalidation_level"),
                "matched_sweet_spots": [r.rule_id for r in matched],
                "policy_rule": policy.rule_id,
                "policy_weight": policy.weight,
                "pa_isolated": None,
                "score": score,
                "underlying_price": entry_close,
                "options_calls": None,
            }
            if (
                instrument_class == "cn_metal_futures"
                and sym.endswith(_AG_SYMBOL_SUFFIX)
                and sig.direction == "bottom"
                and score >= _OPTIONS_MIN_SCORE
            ):
                mm_pct = _compute_mm_pct(sig, bars, entry_close)
                calls = select_otm_calls(entry_close, sig_date, mm_target_pct=mm_pct)
                enrich_with_iv(calls, sig_date, entry_close, _OPTIONS_DATA_DIR)
                rec["options_calls"] = calls
            elif (
                instrument_class == "cn_metal_futures"
                and sym.endswith(_AU_SYMBOL_SUFFIX)
                and sig.direction == "bottom"
                and score >= _OPTIONS_MIN_SCORE
            ):
                mm_pct = _compute_mm_pct(sig, bars, entry_close)
                calls = select_otm_calls_au(entry_close, sig_date, mm_target_pct=mm_pct)
                enrich_with_iv_au(calls, sig_date, entry_close, _AU_OPTIONS_DATA_DIR)
                rec["options_calls"] = calls
            rec["position_size"] = _position_size(rec)
            _attach_signal_bar_quality(rec, bars, sig.candidate_bar_idx)
            scored.append(rec)

        # BPull scan — cn_metal_futures only. BASELINE_REF: baselines/bpull_cn_metal_futures.json
        # (Prior stale comment cited F1=+1.000R F3=+1.008R — those were from the missed-swing
        # +EMA20 sub-experiment, not the canonical K=3 walk-forward. See BPullDetector docstring.)
        if instrument_class == "cn_metal_futures":
            h_bars = _load_bars_60(sym, args)
            bpull_det = BPullDetector()
            # Structural stop on daily — bpull is a "buy the pullback in
            # uptrend / TR" signal; PA structural_stop returns the most
            # recent HL (BULL) or TR floor (TR/TR_FORMING).  Same shape
            # as pa_h2 / context_a / pa_h2_climax.
            _bpull_struct_det = PAStructureDetector()
            for bsig in bpull_det.scan(bars, h_bars):
                if bsig.timestamp.date() < cutoff_date:
                    continue
                weight = BPullDetector.policy_weight(bsig, instrument_class, symbol=sym)
                if weight == 0.0:
                    continue
                # Score: h=opposing K=3 STRONG PASS → 4; shouldn't reach here otherwise
                bscore = 4 if bsig.higher_tf_relation == "opposing" else 2
                bsig_date = bsig.timestamp.date()
                bentry_close = float(bars["close"].iloc[bsig.bar_idx])
                _bpull_struct = _bpull_struct_det.detect(bars, up_to_idx=bsig.bar_idx)
                _b_inval = (
                    round(_bpull_struct.structural_stop, 4)
                    if _bpull_struct.structural_stop is not None
                    and _bpull_struct.structural_stop < bentry_close
                    else None
                )
                brec: dict = {
                    "symbol": sym,
                    "date": bsig_date.isoformat(),
                    "direction": "bottom",
                    "level": "bpull",
                    "subtype": "bpull",
                    "confidence": weight,  # policy_weight (0.75) — comparable to MACD confidence
                    "wick_ratio": None,
                    "swing_pct": None,
                    "vol_ratio": None,
                    "invalidation_level": _b_inval,
                    "matched_sweet_spots": [],
                    "policy_rule": "bpull-k3-cn-metal",
                    "policy_weight": weight,
                    "pa_isolated": None,
                    "score": bscore,
                    "underlying_price": bentry_close,
                    "options_calls": None,
                }
                if sym.endswith(_AG_SYMBOL_SUFFIX) and bscore >= _OPTIONS_MIN_SCORE:
                    bcalls = select_otm_calls(bentry_close, bsig_date)
                    enrich_with_iv(bcalls, bsig_date, bentry_close, _OPTIONS_DATA_DIR)
                    brec["options_calls"] = bcalls
                elif sym.endswith(_AU_SYMBOL_SUFFIX) and bscore >= _OPTIONS_MIN_SCORE:
                    bcalls = select_otm_calls_au(bentry_close, bsig_date)
                    enrich_with_iv_au(bcalls, bsig_date, bentry_close, _AU_OPTIONS_DATA_DIR)
                    brec["options_calls"] = bcalls
                _annotate_pa_sweet_spots(brec, pool_rules)
                brec["position_size"] = _position_size(brec)
                _attach_signal_bar_quality(brec, bars, bsig.bar_idx)
                scored.append(brec)

        # PA H2 scan — cn_metal_futures only, with isolation annotation + PA structure filter.
        # Isolation: no quality≥0.1 PA signal in the past 10 bars for the same symbol.
        # EV validated: isolated +0.657R vs non-isolated +0.179R (backtest_pa_standalone.py).
        # Phase filter: BULL phase excluded (K=3 OOS all-negative: F1=-1.0R F2=-1.0R F3=-0.29R).
        # TR/TR_FORMING: ATR stop kept (outperforms structural stop for CN: +0.628R vs +0.516R).
        # invalidation_level: structural stop for reference; execution uses ATR-based sizing.
        if instrument_class == "cn_metal_futures":
            if h_bars is None:
                h_bars = _load_bars_60(sym, args)

            _cn_struct_det = PAStructureDetector()

            # 15min bars for intraday confirmation (informational field pa_15m_confirmed).
            # Backtest: confirmed subset F3=+0.682R vs unconfirmed F3=+0.081R (CN_METAL TR phase).
            # Confirmation window: 5 trading days (~7 calendar days) from daily signal.
            _m15_bars = _load_bars_15(sym, args)
            _m15_sigs_opp: list[PASignal] = []
            if _m15_bars is not None and len(_m15_bars) >= 50:
                _m15_det = PABottomDetector(
                    min_h_legs=2, min_quality=0.2, ema_threshold=0.0, min_gap=3,
                )
                _m15_sigs_opp = [
                    s for s in _m15_det.scan(_m15_bars, h_bars)
                    if s.higher_tf_relation == "opposing"
                ]

            # Base scan (min_quality=0.1, min_gap=1) — reference set for isolation check
            base_pa_det = PABottomDetector(
                min_h_legs=2, min_quality=0.1, ema_threshold=0.0, min_gap=1,
            )
            all_pa_sigs: list[PASignal] = base_pa_det.scan(bars, h_bars)
            base_bar_idxs = [s.bar_idx for s in all_pa_sigs]

            # Quality≥0.3 signals — what we actually output
            pa_det = PABottomDetector(
                min_h_legs=2, min_quality=0.3, ema_threshold=0.0,
            )
            pa_sigs: list[PASignal] = pa_det.scan(bars, h_bars)

            for pa_sig in pa_sigs:
                if pa_sig.timestamp.date() < cutoff_date:
                    continue
                pa_weight = PABottomDetector.policy_weight(pa_sig, instrument_class, symbol=sym)
                if pa_weight == 0.0:
                    continue

                # PA structure filter: skip BULL phase (consistently negative EV in CN_METAL)
                _cn_struct = _cn_struct_det.detect(bars, up_to_idx=pa_sig.bar_idx)
                if _cn_struct.phase == "BULL":
                    continue

                # Isolation: no quality≥0.1 signal within past 10 bars
                recent_base = [b for b in base_bar_idxs
                               if 0 < pa_sig.bar_idx - b <= 10]
                is_isolated = len(recent_base) == 0

                # Score: isolated h=opposing → 4; non-isolated h=opposing → 3; other → 2
                if pa_sig.higher_tf_relation == "opposing":
                    pa_score = 4 if is_isolated else 3
                else:
                    pa_score = 2

                pa_date = pa_sig.timestamp.date()
                pa_close = float(bars["close"].iloc[pa_sig.bar_idx])

                # 15min intraday confirmation: first 15min h=opp signal within 5 trading days
                _confirm_deadline = pa_sig.timestamp + pd.Timedelta(days=7)
                _m15_confirm = next(
                    (s for s in _m15_sigs_opp
                     if pa_sig.timestamp < s.timestamp <= _confirm_deadline),
                    None,
                )
                pa_15m_confirmed = _m15_confirm is not None
                pa_15m_entry = (
                    round(float(_m15_bars["close"].iloc[_m15_confirm.bar_idx]), 4)
                    if _m15_confirm is not None else None
                )

                pa_rec: dict = {
                    "symbol": sym,
                    "date": pa_date.isoformat(),
                    "direction": "bottom",
                    "level": "pa_h2",
                    "subtype": "pa_h2",
                    "confidence": pa_weight,
                    "wick_ratio": None,
                    "swing_pct": None,
                    "vol_ratio": None,
                    "invalidation_level": (
                        round(_cn_struct.structural_stop, 4)
                        if _cn_struct.structural_stop else None
                    ),
                    "matched_sweet_spots": [],
                    "policy_rule": "pa-h2-cn-metal-tr-phase",
                    "policy_weight": pa_weight,
                    "pa_isolated": is_isolated,
                    "score": pa_score,
                    "underlying_price": pa_close,
                    "options_calls": None,
                    "pa_phase": _cn_struct.phase,
                    "pa_15m_confirmed": pa_15m_confirmed,
                    "pa_15m_entry": pa_15m_entry,
                }
                if sym.endswith(_AG_SYMBOL_SUFFIX) and pa_score >= _OPTIONS_MIN_SCORE:
                    pa_calls = select_otm_calls(pa_close, pa_date)
                    enrich_with_iv(pa_calls, pa_date, pa_close, _OPTIONS_DATA_DIR)
                    pa_rec["options_calls"] = pa_calls
                elif sym.endswith(_AU_SYMBOL_SUFFIX) and pa_score >= _OPTIONS_MIN_SCORE:
                    pa_calls = select_otm_calls_au(pa_close, pa_date)
                    enrich_with_iv_au(pa_calls, pa_date, pa_close, _AU_OPTIONS_DATA_DIR)
                    pa_rec["options_calls"] = pa_calls
                _annotate_pa_sweet_spots(pa_rec, pool_rules)
                # DIR multi-TF feed for the four bottom emit blocks:
                #   - bars_15 already loaded above as _m15_bars (15m sweep)
                #   - weekly bars loaded lazily, cached per symbol via _w_bars
                if not _dir_feeds_loaded:
                    _w_bars = _load_bars_weekly(sym, args)
                    _bars_15_cache = _m15_bars
                    _dir_feeds_loaded = True
                _attach_direction_verdict(
                    pa_rec, bars, h_bars, pa_sig.bar_idx,
                    macd_df=macd_df,
                    ambush_pattern="h2_bottom",
                    weekly_bars=_w_bars,
                    bars_15=_bars_15_cache,
                )
                pa_rec["position_size"] = _position_size(pa_rec)
                _attach_signal_bar_quality(pa_rec, bars, pa_sig.bar_idx)
                scored.append(pa_rec)

        # PA H2 scan — cn_bond only (CFFEX treasury futures tf/t/ts).
        # Validated 2026-06-08 (backtest_pa_cn_phasefilter --pool CN_BOND):
        #   All h=opp:   n=31 EV=+0.548R  F1=+0.219(n=16) F2=+1.500(n=6) F3=+0.500(n=9)
        #   TR phase 28/31 (90% of fires) — phase filter is essentially free here.
        #   3/3 OOS folds positive → policy_weight 0.70 (h=opp), 0.40 (neutral).
        # Differences vs cn_metal PA H2:
        #   - NO 15min confirmation gate (validated for CN_METAL only).
        #   - Skip BULL phase (mirrors cn_metal; BULL n=3, too small to fight).
        #   - Use PAStructureDetector.structural_stop (TR-dominated → tight stop).
        if instrument_class == "cn_bond":
            if h_bars is None:
                h_bars = _load_bars_60(sym, args)
            _cn_bond_struct_det = PAStructureDetector()
            _cn_bond_pa_det = PABottomDetector(
                min_h_legs=2, min_quality=0.3, ema_threshold=0.0,
            )
            for _b_sig in _cn_bond_pa_det.scan(bars, h_bars):
                if _b_sig.timestamp.date() < cutoff_date:
                    continue
                _b_weight = PABottomDetector.policy_weight(
                    _b_sig, instrument_class, symbol=sym,
                )
                if _b_weight == 0.0:
                    continue
                # PA structure filter: skip BULL phase (mirror cn_metal; only
                # 3/31 CN_BOND fires landed in BULL — not worth fighting over).
                _b_struct = _cn_bond_struct_det.detect(bars, up_to_idx=_b_sig.bar_idx)
                if _b_struct.phase == "BULL":
                    continue
                _b_date = _b_sig.timestamp.date()
                _b_close = float(bars["close"].iloc[_b_sig.bar_idx])
                _b_rec: dict = {
                    "symbol": sym,
                    "date": _b_date.isoformat(),
                    "direction": "bottom",
                    "level": "pa_cn_bond",
                    "subtype": "pa_h2",
                    "confidence": _b_weight,
                    "wick_ratio": None,
                    "swing_pct": None,
                    "vol_ratio": None,
                    "invalidation_level": (
                        round(_b_struct.structural_stop, 4)
                        if _b_struct.structural_stop else None
                    ),
                    "matched_sweet_spots": [],
                    "policy_rule": "pa-cn-bond-h-opp",
                    "policy_weight": _b_weight,
                    "pa_isolated": None,
                    "score": 3,  # TR phase dominant per validation; matches cn_metal TR pattern
                    "underlying_price": _b_close,
                    "options_calls": None,
                    "pa_phase": _b_struct.phase,
                }
                _annotate_pa_sweet_spots(_b_rec, pool_rules)
                if not _dir_feeds_loaded:
                    _w_bars = _load_bars_weekly(sym, args)
                    _bars_15_cache = _load_bars_15(sym, args)
                    _dir_feeds_loaded = True
                _attach_direction_verdict(
                    _b_rec, bars, h_bars, _b_sig.bar_idx,
                    macd_df=macd_df,
                    ambush_pattern="h2_bottom",
                    weekly_bars=_w_bars,
                    bars_15=_bars_15_cache,
                )
                _b_rec["position_size"] = _position_size(_b_rec)
                _attach_signal_bar_quality(_b_rec, bars, _b_sig.bar_idx)
                scored.append(_b_rec)

        # VFlush scan — cn_metal_futures only. BASELINE_REF: baselines/vflush_cn_metal_cu_sc.json
        # 2026-06-09 DRIFT verdict reverted: was a false alarm caused by
        # backtest_vflush.py's truncated JSON loader; full_stack confirms cu+sc n=42
        # over 5.5y, consistent with docstring n=50. Weight back to 0.65.
        # V-shape vertical flush bottoms: deep below EMA + current-bar selling climax,
        # NO h_leg requirement. ag+au excluded (OOS negative).
        if instrument_class == "cn_metal_futures":
            if h_bars is None:
                h_bars = _load_bars_60(sym, args)
            vflush_det = VFlushDetector()
            # Structural stop — v-flush ANCHOR is the signal bar's own low,
            # NOT the prior PA structural support (vflush by definition
            # breaks the prior support; the climax low IS the new pivot
            # low and the natural inflection).  Per user-locked 2026-06-08
            # "止损线架在支撑线或者压力线附近": for vflush the support
            # line is the climax low itself.
            for vsig in vflush_det.scan(bars, h_bars):
                if vsig.timestamp.date() < cutoff_date:
                    continue
                vweight = VFlushDetector.policy_weight(vsig, instrument_class, symbol=sym)
                if vweight == 0.0:
                    continue
                vscore = 3 if vsig.higher_tf_relation == "opposing" else 2
                vsig_date = vsig.timestamp.date()
                vclose = float(bars["close"].iloc[vsig.bar_idx])
                _vflush_low = float(bars["low"].iloc[vsig.bar_idx])
                _v_inval = round(_vflush_low * 0.99, 4) if _vflush_low < vclose else None
                vrec: dict = {
                    "symbol": sym,
                    "date": vsig_date.isoformat(),
                    "direction": "bottom",
                    "level": "vflush",
                    "subtype": "vflush",
                    "confidence": vweight,
                    "wick_ratio": None,
                    "swing_pct": None,
                    "vol_ratio": None,
                    "invalidation_level": _v_inval,
                    "matched_sweet_spots": [],
                    "policy_rule": "vflush-k3-cn-metal",
                    "policy_weight": vweight,
                    "pa_isolated": None,
                    "score": vscore,
                    "underlying_price": vclose,
                    "options_calls": None,
                }
                # ag+au excluded by policy_weight gate above; only cu/sc reach here
                _annotate_pa_sweet_spots(vrec, pool_rules)
                vrec["position_size"] = _position_size(vrec)
                _attach_signal_bar_quality(vrec, bars, vsig.bar_idx)
                scored.append(vrec)

        # Context A scan — US (us_equity) + CN_METAL (cn_metal_futures).
        # CONDITIONAL PASS K=3: h=opposing only; policy_weight=0.60.
        # US: OOS F1=+0.106R / F2=+0.179R / F3=+0.574R (3/3 positive).
        # CN_METAL: F1=+0.342R / F2=−0.192R / F3=+0.619R (F2 2024 regime known).
        # 2026-06-09 P2 regime gate: US side suppressed during risk_off
        # (SPY < SMA200 OR 20d vol > 25%). 2022 H2 family kept only 4 of
        # 71 trades after gate, dropping -21.4R drag from the lane.
        if instrument_class in ("us_equity", "cn_metal_futures"):
            if h_bars is None:
                h_bars = _load_bars_60(sym, args)
            ctx_a_det = ContextADetector()
            # Structural stop on daily — same convention as pa_h2 / pa_cn_bond.
            _ctxa_struct_det = PAStructureDetector()
            for asig in ctx_a_det.scan(bars, h_bars):
                if asig.timestamp.date() < cutoff_date:
                    continue
                aweight = ContextADetector.policy_weight(asig, instrument_class, symbol=sym)
                if aweight == 0.0:
                    continue
                # P2 regime gate (US only)
                if instrument_class == "us_equity" and _us_lane_suppressed_by_regime(asig.timestamp, args):
                    continue
                ascore = 3  # Conditional PASS
                asig_date = asig.timestamp.date()
                aclose = float(bars["close"].iloc[asig.bar_idx])
                _ctxa_struct = _ctxa_struct_det.detect(bars, up_to_idx=asig.bar_idx)
                _a_inval = (
                    round(_ctxa_struct.structural_stop, 4)
                    if _ctxa_struct.structural_stop is not None
                    and _ctxa_struct.structural_stop < aclose
                    else None
                )
                arec: dict = {
                    "symbol": sym,
                    "date": asig_date.isoformat(),
                    "direction": "bottom",
                    "level": "context_a",
                    "subtype": "context_a",
                    "confidence": aweight,
                    "wick_ratio": None,
                    "swing_pct": None,
                    "vol_ratio": None,
                    "invalidation_level": _a_inval,
                    "matched_sweet_spots": [],
                    "policy_rule": "context-a-k3-conditional",
                    "policy_weight": aweight,
                    "pa_isolated": None,
                    "score": ascore,
                    "underlying_price": aclose,
                    "options_calls": None,
                }
                if (
                    instrument_class == "cn_metal_futures"
                    and sym.endswith(_AG_SYMBOL_SUFFIX)
                    and ascore >= _OPTIONS_MIN_SCORE
                ):
                    acalls = select_otm_calls(aclose, asig_date)
                    enrich_with_iv(acalls, asig_date, aclose, _OPTIONS_DATA_DIR)
                    arec["options_calls"] = acalls
                elif (
                    instrument_class == "cn_metal_futures"
                    and sym.endswith(_AU_SYMBOL_SUFFIX)
                    and ascore >= _OPTIONS_MIN_SCORE
                ):
                    acalls = select_otm_calls_au(aclose, asig_date)
                    enrich_with_iv_au(acalls, asig_date, aclose, _AU_OPTIONS_DATA_DIR)
                    arec["options_calls"] = acalls
                _annotate_pa_sweet_spots(arec, pool_rules)
                if not _dir_feeds_loaded:
                    _w_bars = _load_bars_weekly(sym, args)
                    _bars_15_cache = _load_bars_15(sym, args)
                    _dir_feeds_loaded = True
                _attach_direction_verdict(
                    arec, bars, h_bars, asig.bar_idx,
                    macd_df=macd_df,
                    ambush_pattern="h2_bottom",
                    weekly_bars=_w_bars,
                    bars_15=_bars_15_cache,
                )
                arec["position_size"] = _position_size(arec)
                _attach_signal_bar_quality(arec, bars, asig.bar_idx)
                scored.append(arec)

        # US PA — DIF>0 h=opposing + structural stop.
        # Framework: PA structure first → stop from TR floor / recent HL; DIF<0 disabled.
        # K=3 validated: DIF>0 h=opp struct F3=+0.507R; TR phase struct F3=+0.141R.
        # Phase allocation: BULL=full weight, TR/TR_FORMING=half weight, BEAR/UNCLEAR=skip.
        # US long-duration treasury ETFs structurally break PA H2 (4/4 folds
        # negative across hike/yield-peak/cut regimes — see
        # doc/repro/pa_tlt_diagnostic_2026-06-08.md).  Match the
        # PABottomDetector.policy_weight() suppression set.
        if instrument_class == "us_equity" and sym.lower() not in PABottomDetector.US_LONG_BOND_SUPPRESS:
            # P1c lane × market eval 2026-06-09: pa_us_dif_pos broad-market suppression.
            # DIA n=8 EV-0.026, SPY n=9 EV-0.088 — same broad-market pattern as
            # context_a US and pa_us_60min. Sample is borderline but principle is
            # structural: broad-market reversals are slow-moving, don't fit H2 timing.
            if sym.upper() in _PA_US_DIF_POS_SUPPRESS:
                continue
            if h_bars is None:
                h_bars = _load_bars_60(sym, args)
            _pa_struct_det = PAStructureDetector()
            _pa_us_det = PABottomDetector(
                min_h_legs=2, min_quality=0.3, ema_threshold=0.0, min_gap=10,
            )
            _pa_us_sigs: list[PASignal] = _pa_us_det.scan(bars, h_bars)
            for _us_sig in _pa_us_sigs:
                if _us_sig.timestamp.date() < cutoff_date:
                    continue
                # DIF>0 required — DIF<0 disabled in all phases per PA framework
                _us_dif = float(macd_df["dif"].iloc[_us_sig.bar_idx])
                if _us_dif <= 0:
                    continue
                # h=opposing required (60m DIF<0 confirms daily bottom)
                if _us_sig.higher_tf_relation != "opposing":
                    continue
                # PA structure at signal bar
                _us_struct = _pa_struct_det.detect(bars, up_to_idx=_us_sig.bar_idx)
                if _us_struct.phase in ("BEAR", "UNCLEAR"):
                    continue
                if _us_struct.structural_stop is None:
                    continue
                _us_close = float(bars["close"].iloc[_us_sig.bar_idx])
                if _us_struct.structural_stop >= _us_close:
                    continue
                # Phase-based weight: BULL=0.65, TR/TR_FORMING=0.30
                # B1-1 (2026-06-08): dropped the `at_tr_bottom` gate and lowered
                # the TR weight from 0.40 → 0.30 per audit memo
                # `doc/repro/score_audit_2026-06-08.md` §S2.  The gate (pos_in_tr<0.25
                # of recent 8-pivot range) was killing 100% of TR signals (15/15
                # in scripts/_b1_1_inspect_at_tr_bottom.py 365-day run, min pos_in_tr=
                # 0.426).  H2 bottoms close back into the range by construction, so
                # close-position-in-TR is structurally incompatible with the H2
                # signal shape — the gate is dead, not selective.  Dropping the
                # gate lifts annual fires 5 → ~20 (4x).  TR weight cut to 0.30
                # when the un-gated TR-phase subset was still unvalidated.
                # K=3 (2026-06-10, doc/repro/pa_us_dif_pos_tr_k3_2026-06-10.md):
                # the subset is entirely TR_FORMING (n=36, EV+0.069R) — positive
                # but marginal, fails the 3/3-OOS bar, so 0.30 is held as a
                # validated-marginal weight (no raise, no suppress). BULL rides
                # 0.65 from pa_baseline_2026-06-08.md.
                _us_phase_w = 0.65 if _us_struct.phase == "BULL" else 0.30
                _us_score = 3 if _us_struct.phase == "BULL" else 2
                _us_date  = _us_sig.timestamp.date()
                _us_stop  = round(_us_struct.structural_stop, 4)
                _us_stop_pct = round(
                    (_us_close - _us_struct.structural_stop) / _us_close * 100, 1
                )
                _us_rec: dict = {
                    "symbol": sym,
                    "date": _us_date.isoformat(),
                    "direction": "bottom",
                    "level": "pa_us_dif_pos",
                    "subtype": f"pa_us_{_us_struct.phase.lower()}",
                    "confidence": _us_phase_w,
                    "wick_ratio": None,
                    "swing_pct": None,
                    "vol_ratio": None,
                    "invalidation_level": _us_stop,
                    "matched_sweet_spots": [],
                    "policy_rule": "pa-us-dif-pos-structural-stop",
                    "policy_weight": _us_phase_w,
                    "pa_isolated": None,
                    "score": _us_score,
                    "underlying_price": _us_close,
                    "options_calls": None,
                    # Extra PA context for downstream inspection
                    "pa_phase": _us_struct.phase,
                    "pa_tr_top": round(_us_struct.tr_top, 2) if _us_struct.tr_top else None,
                    "pa_tr_bot": round(_us_struct.tr_bot, 2) if _us_struct.tr_bot else None,
                    "pa_stop_pct": _us_stop_pct,
                }
                _annotate_pa_sweet_spots(_us_rec, pool_rules)
                if not _dir_feeds_loaded:
                    _w_bars = _load_bars_weekly(sym, args)
                    _bars_15_cache = _load_bars_15(sym, args)
                    _dir_feeds_loaded = True
                _attach_direction_verdict(
                    _us_rec, bars, h_bars, _us_sig.bar_idx,
                    macd_df=macd_df,
                    ambush_pattern="h2_bottom",
                    weekly_bars=_w_bars,
                    bars_15=_bars_15_cache,
                )
                _us_rec["position_size"] = _position_size(_us_rec)
                _attach_signal_bar_quality(_us_rec, bars, _us_sig.bar_idx)
                scored.append(_us_rec)

        # PA H2 scan — us_equity 60min "fast lane".  Sibling of the daily
        # us_equity block above; emits independent records (different
        # timestamps, hold period, stop sizing).
        #
        # Backtest validation (pa_swing --dataset us_60min, 5y 2021-2026):
        #   uptrend + h=opp:              n=56  EV=+0.384R  F1+0.625 F2+0.708
        #   uptrend + h=opp + legs=1:     n=21  EV=+0.595R  hit 62%
        # Per-symbol standouts: nvda +1.200R(n=5), gdx +1.000R(n=5),
        # spy +0.929R(n=7) — nvda flips from -0.20R daily → +1.20R 60min.
        #
        # Operational profile: 60min entry, daily HTF for h=opp gate,
        # max_hold ~140 60min bars (~3.5 trading days), atr_period=50.
        # Distinct from the daily lane: don't run BULL phase filter or
        # structural stop here — pa_swing didn't validate those.
        if instrument_class == "us_equity" and sym.lower() not in PABottomDetector.US_LONG_BOND_SUPPRESS:
            _bars_60 = _load_bars_60(sym, args)
            if _bars_60 is not None and len(_bars_60) >= 100:
                _h_daily = bars  # daily bars already loaded above as `bars`
                _swing_ctx = compute_swing_context(_bars_60, swing_n=3)
                _pa60_det = PABottomDetector(
                    min_h_legs=2,
                    min_quality=0.3,    # production threshold (pa_swing used 0.1 in backtest)
                    ema_threshold=0.0,
                    min_gap=35,         # ~1.5 trading day spacing on 60min
                    h_lookback=20,
                )
                _pa60_sigs: list[PASignal] = _pa60_det.scan(
                    _bars_60, h_bars=_h_daily, swing_context=_swing_ctx,
                )
                for _s60 in _pa60_sigs:
                    if _s60.timestamp.date() < cutoff_date:
                        continue
                    if _s60.higher_tf_relation != "opposing":
                        continue
                    _trend = str(_s60.features.get("trend_structure", ""))
                    if _trend != "uptrend":
                        continue
                    # P0 symbol-level suppression (2026-06-09 lane × market eval):
                    # DIA n=10 EV-0.40, XLK n=14 EV-0.14, QQQ n=11 EV-0.14,
                    # XLRE n=4 EV-0.75. See doc/repro/lane_market_evaluation_2026-06-09.md.
                    if sym.upper() in _PA_US_60MIN_SUPPRESS:
                        continue
                    # P2 regime gate (2026-06-09): suppress during risk_off
                    if _us_lane_suppressed_by_regime(_s60.timestamp, args):
                        continue
                    _w60 = PABottomDetector.policy_weight(_s60, instrument_class, symbol=sym)
                    if _w60 == 0.0:
                        continue
                    _legs60 = int(_s60.features.get("leg_count_down", 0))
                    _close60 = float(_bars_60["close"].iloc[_s60.bar_idx])
                    # Structural stop (calibrated 2026-06-08 on 30 live
                    # 365d samples — see doc/repro/score_audit_2026-06-08.md
                    # §M1 / §N5).
                    #
                    # Definition: lowest low in the 11-bar window
                    # `[idx-10 .. idx]` (signal bar inclusive) minus a
                    # 0.5% buffer.  Including the signal bar in the
                    # window guarantees `stop < entry_close` — for many
                    # H2 records the signal bar IS the lowest of the
                    # prior pullback, so a prior-only window puts the
                    # floor above entry close (observed in 2/30 samples).
                    #
                    # Not used as a gate — pa_swing backtest did not
                    # validate stop-based filtering on this lane.  This
                    # populates `invalidation_level` / `pa_stop_pct` so
                    # downstream consumers can size or annotate risk.
                    #
                    # Why not reuse PAStructureDetector.structural_stop:
                    # on 60min bars pivot-based stops are unreliable
                    # across split/dividend events (pre-event pivots
                    # produce levels above the post-event price — e.g.
                    # XLK 2025-12-05 in the 365d sample).  swing_low(10)
                    # is split-robust because it is anchored to recent
                    # bars only.  Calibrated distribution on the 30
                    # samples: mean 1.26%, median 1.22%, stdev 0.53%,
                    # range 0.69%–3.29% — clean unimodal tail.
                    _lo_window = _bars_60["low"].iloc[
                        max(0, _s60.bar_idx - 10) : _s60.bar_idx + 1
                    ]
                    _floor60 = float(_lo_window.min())
                    _stop60 = _floor60 * 0.995
                    _stop60_pct = (_close60 - _stop60) / _close60 * 100
                    _rec60: dict = {
                        "symbol": sym,
                        "date": _s60.timestamp.date().isoformat(),
                        "direction": "bottom",
                        "level": "pa_us_60min",
                        "subtype": f"pa_us_60min_uptrend{'_legs1' if _legs60 == 1 else ''}",
                        "confidence": _w60,
                        "wick_ratio": None,
                        "swing_pct": None,
                        "vol_ratio": None,
                        "invalidation_level": round(_stop60, 4),
                        "matched_sweet_spots": [],
                        "policy_rule": "pa-us-60min-uptrend-hopp",
                        "policy_weight": _w60,
                        "pa_isolated": None,
                        # score=4 when legs=1 bonus fires (weight=0.90), else 3
                        "score": 4 if _legs60 == 1 else 3,
                        "underlying_price": _close60,
                        "options_calls": None,
                        # Extra context so downstream can sort/group on TF
                        "pa_timeframe": "60min",
                        "pa_trend": _trend,
                        "pa_legs": _legs60,
                        "pa_60m_timestamp": _s60.timestamp.isoformat(),
                        "pa_stop_pct": round(_stop60_pct, 2),
                    }
                    _annotate_pa_sweet_spots(_rec60, pool_rules)
                    # Map the 60min signal bar to the corresponding daily
                    # bar index so the DIR module can read structure /
                    # context / divergence on the daily lens, then pass
                    # the 60min series as the hourly_bars argument.
                    _daily_ts = pd.to_datetime(bars["timestamp"]).values
                    _sig_np = pd.Timestamp(_s60.timestamp).to_datetime64()
                    _mask = _daily_ts <= _sig_np
                    if _mask.any():
                        _daily_idx = int(_mask.sum()) - 1
                    else:
                        _daily_idx = 0
                    if not _dir_feeds_loaded:
                        _w_bars = _load_bars_weekly(sym, args)
                        _bars_15_cache = _load_bars_15(sym, args)
                        _dir_feeds_loaded = True
                    # POC: pa_us_60min is the first lane to use the 10-source
                    # DIR path (signal_tf_structure on 60min bars +
                    # resonance vs daily structure).  Per the user-locked
                    # 2026-06-08 architecture: each PA lane judges
                    # structure on its OWN TF; daily is a parallel
                    # backdrop providing the resonance flag.  Other PA
                    # emit blocks keep the 8-source path until this POC
                    # is validated.
                    _attach_direction_verdict(
                        _rec60, bars, _bars_60, _daily_idx,
                        macd_df=macd_df,
                        ambush_pattern="h2_bottom",
                        weekly_bars=_w_bars,
                        bars_15=_bars_15_cache,
                        signal_tf_bars=_bars_60,
                        signal_tf_label="60min",
                        signal_tf_bar_idx=int(_s60.bar_idx),
                    )
                    _rec60["position_size"] = _position_size(_rec60)
                    # 60min lane: signal bar geometry from the 60min series, not daily
                    _attach_signal_bar_quality(_rec60, _bars_60, int(_s60.bar_idx))
                    scored.append(_rec60)

        # CN_AGRI_POS PA H2 climax scan — m/p/ta/ma/sr only.
        # STALE 2026-06-08: prior K=3 STRONG PASS (F1+0.640/F2+0.516/F3+0.571, n=22)
        # NOT REPRODUCIBLE; full-stack 5.5y replay shows EV -0.040R / n=64, win 47%
        # with 2025 collapse (-0.904R EV / n=9 dominates). Weight dropped 0.65→0.0;
        # lane retained for annotation/data collection only (gated below).
        # See doc/repro/pa_h2_climax_anomaly_2026-06-08.md
        # BASELINE_REF: baselines/pa_h2_climax_cn_agri_pos.json
        if instrument_class == "cn_futures" and sym in _CN_AGRI_POS_SYMBOLS:
            if h_bars is None:
                h_bars = _load_bars_60(sym, args)
            _agri_det = PABottomDetector(
                min_h_legs=2, min_quality=0.3, ema_threshold=0.0,
                min_gap=10,
                require_climax=True, climax_threshold=0.4,
            )
            # Structural stop on daily — pa_h2_climax fires on CN agri
            # daily PA H2, same shape as cn_metal pa_h2 lane.
            _agri_struct_det = PAStructureDetector()
            for _agri_sig in _agri_det.scan(bars, h_bars):
                if _agri_sig.timestamp.date() < cutoff_date:
                    continue
                if _agri_sig.higher_tf_relation != "opposing":
                    continue
                _agri_date  = _agri_sig.timestamp.date()
                _agri_close = float(bars["close"].iloc[_agri_sig.bar_idx])
                _agri_struct = _agri_struct_det.detect(bars, up_to_idx=_agri_sig.bar_idx)
                _agri_inval = (
                    round(_agri_struct.structural_stop, 4)
                    if _agri_struct.structural_stop is not None
                    and _agri_struct.structural_stop < _agri_close
                    else None
                )
                _agri_rec: dict = {
                    "symbol": sym,
                    "date": _agri_date.isoformat(),
                    "direction": "bottom",
                    "level": "pa_h2_climax",
                    "subtype": "pa_agri_climax",
                    "confidence": 0.0,
                    "wick_ratio": None,
                    "swing_pct": None,
                    "vol_ratio": None,
                    "invalidation_level": _agri_inval,
                    "matched_sweet_spots": [],
                    "policy_rule": "pa-h2-agri-climax-hopp-WATCH",
                    "policy_weight": 0.0,
                    "pa_isolated": None,
                    "score": 3,
                    "underlying_price": _agri_close,
                    "options_calls": None,
                }
                _annotate_pa_sweet_spots(_agri_rec, pool_rules)
                _agri_rec["position_size"] = _position_size(_agri_rec)
                _attach_signal_bar_quality(_agri_rec, bars, _agri_sig.bar_idx)
                scored.append(_agri_rec)

    if loaded_symbols == 0:
        src = args.quant_data_root or args.bars_dir
        hint = "fetch_quant.py" if args.quant_data_root else "fetch_polygon / fetch_akshare / fetch_tqsdk"
        print(f"ERROR: 0/{len(symbols)} symbols loadable from {src}. Run {hint}.",
              file=sys.stderr)
        return 2
    if not scored:
        print(f"No signals in last {args.window_days} days "
              f"({loaded_symbols}/{len(symbols)} symbols loaded).")
        return 0
    scored.sort(key=lambda r: (-r["score"], -r["confidence"]))

    print(f"{'sym':<8} {'date':<11} {'dir':<7} {'lvl':<14} {'conf':<5} "
          f"{'wick':<5} {'swng':<6} {'vol':<5} {'invd':<10} {'sweet':<22} {'policy':<28} {'iso':<4} {'15m':<4} {'sc':<2} {'pos':<5}")
    print("-" * 149)
    for r in scored:
        sweet = ",".join(r["matched_sweet_spots"]) or "—"
        wick = f"{r['wick_ratio']:.2f}" if r['wick_ratio'] is not None else "—"
        swng = f"{r['swing_pct']:+.1f}" if r['swing_pct'] is not None else "—"
        vol = f"{r['vol_ratio']:.2f}" if r['vol_ratio'] is not None else "—"
        invd = f"{r['invalidation_level']:.2f}" if r['invalidation_level'] is not None else "—"
        pa_iso = r.get("pa_isolated")
        iso_str = "iso" if pa_iso is True else ("—" if pa_iso is False else "")
        m15c = r.get("pa_15m_confirmed")
        m15_str = "✓" if m15c is True else ("…" if m15c is False else "")
        pos_str = r.get("position_size", "")
        print(f"{r['symbol']:<8} {r['date']:<11} {r['direction']:<7} {r['level']:<14} "
              f"{r['confidence']:.2f}  {wick:<5} {swng:<6} {vol:<5} {invd:<10} "
              f"{sweet:<22} {r['policy_rule'] or '(baseline)':<28} {iso_str:<4} {m15_str:<4} {r['score']} {pos_str:<5}")

    # Options suggestions for ag/au bottom signals (score >= OPTIONS_MIN_SCORE)
    option_signals = [
        r for r in scored
        if r.get("options_calls")
        and r["direction"] == "bottom"
        and r["score"] >= _OPTIONS_MIN_SCORE
    ]
    if option_signals:
        print()
        print(f"Options suggestions (ag/au bottom signals, score>={_OPTIONS_MIN_SCORE}):")
        for r in option_signals:
            calls = r["options_calls"]
            underlying = r.get("underlying_price", float("nan"))
            metal = "au" if r["symbol"].endswith(_AU_SYMBOL_SUFFIX) else "ag"
            # MM target annotation (same for all strikes in this signal)
            mm_pct = calls[0].get("mm_target_pct") if calls else None
            mm_tag = f"  MM_target=+{mm_pct:.1f}%" if mm_pct is not None else ""
            print(f"  {metal} [{r['date']}] underlying={underlying:.2f}{mm_tag}:")
            for c in calls:
                price_str = f"{c['option_price']:.0f}" if c.get("option_price") is not None else "n/a"
                iv_str = f"{c['iv']:.1f}%" if c.get("iv") is not None else "n/a"
                src = c.get("price_source")
                src_tag = f" [{src}]" if src is not None else ""
                mm_marker = "  ← MM" if c.get("is_mm_strike") else ""
                print(f"    {c['contract_sym']}  OTM={c['otm_pct']:.1f}%  DTE={c['days_to_expiry']}"
                      f"  price={price_str}  IV={iv_str}{src_tag}{mm_marker}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({
            "pool": pool_name,
            "instrument_class": instrument_class,
            "window_days": args.window_days,
            "active_rules": [r.rule_id for r in pool_rules],
            "scored": scored,
        }, indent=2))
        print(f"\nJSON scorecard → {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
