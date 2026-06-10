"""Faithful replay of score_today's ag/au options_calls emission (4 emitters:
divergence, bpull, pa_h2, context_a). Imports production detectors + scoring
helpers so the emitted contracts match what score_today would suggest. See
score_today.py:870-925 (divergence), 930-983 (bpull), 1015-1098 (pa_h2),
1238-1303 (context_a).

Signal-attribute notes (differences from naive recipe):
  - BPullSignal has NO ``direction`` field — BPull is always a bottom buy.
    Gate: BPullDetector.policy_weight(...) > 0, which requires h=opposing for
    cn_metal_futures (same as recipe intent).
  - PASignal.direction is ``"long"`` (not ``"bottom"``).
    PABottomDetector.scan() only emits bottom (long) signals; no direction
    filter needed.  Gate: PABottomDetector.policy_weight(...) > 0 + h=opposing.
  - ContextASignal has NO ``direction`` field — Context A is always a bottom
    entry.  Gate: ContextADetector.policy_weight(...) > 0.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from engine.divergence.bpull_detector import BPullDetector
from engine.divergence.context_a_detector import ContextADetector
from engine.divergence.detector import detect_all_divergences
from engine.divergence.downstream_policies import apply_policy
from engine.divergence.pa_detector import PABottomDetector
from engine.divergence.pa_structure import PAStructureDetector
from engine.features.macd import macd
from engine.features.streams import compute_feature_streams
from engine.units.snapshot import compute_unit_metadata
from scripts.score_today import (
    DIF_DETECTOR_LEVELS,
    SWEET_SPOTS,
    _compute_mm_pct,
    match_rule,
    readiness_score,
)

OPTIONS_MIN_SCORE = 3
_IC = "cn_metal_futures"


@dataclass
class EmittedSignal:
    emitter: str          # "divergence" | "bpull" | "pa_h2" | "context_a"
    sig_date: date
    entry_close: float
    calls: list[dict]     # select_otm_calls(...) output


def _select_fn(underlying: str):
    """Return the OTM-call selector for the given underlying (ag or au)."""
    if underlying == "ag":
        from engine.options.cn_ag_selector import select_otm_calls
        return select_otm_calls
    from engine.options.cn_au_selector import select_otm_calls_au
    return select_otm_calls_au


def replay_bpull(bars: pd.DataFrame, h_bars: pd.DataFrame, underlying: str,
                 sym: str) -> list[EmittedSignal]:
    """Replay BPull emitter.

    Gate (production score_today.py:943-945): BPullDetector.policy_weight(
    bsig, _IC, symbol=sym) > 0 — which implies h=opposing for cn_metal_futures,
    so bscore=4 >= OPTIONS_MIN_SCORE always. No BULL-phase filter on bpull.

    Production ref: score_today.py:940-983.
    """
    select_fn = _select_fn(underlying)
    out: list[EmittedSignal] = []
    for bsig in BPullDetector().scan(bars, h_bars):
        if BPullDetector.policy_weight(bsig, _IC, symbol=sym) == 0.0:
            continue
        # bscore = 4 when h=opposing — always >= OPTIONS_MIN_SCORE; no extra check needed
        close = float(bars["close"].iloc[bsig.bar_idx])
        out.append(EmittedSignal(
            "bpull",
            bsig.timestamp.date(),
            close,
            select_fn(close, bsig.timestamp.date()),
        ))
    return out


def replay_pa_h2(bars: pd.DataFrame, h_bars: pd.DataFrame, underlying: str,
                 sym: str) -> list[EmittedSignal]:
    """Replay PA H2 emitter.

    Production gates (score_today.py:1030-1036), all required:
      1. PABottomDetector.policy_weight(pa_sig, _IC, symbol=sym) > 0
      2. PAStructureDetector(...).detect(bars, up_to_idx=bar_idx).phase != "BULL"
         (CN_METAL BULL-phase PA H2 is consistently negative EV and is skipped)
      3. h=opposing  (bscore 4/3 both >= OPTIONS_MIN_SCORE=3)
    PASignal.direction is "long"; PABottomDetector only emits bottoms, so no
    direction filter is needed. The isolation check only affects 4-vs-3 scoring
    (both >= 3) so it does not change the emission SET — omitted intentionally.

    Production ref: score_today.py:1015-1098.
    """
    select_fn = _select_fn(underlying)
    det = PABottomDetector(min_h_legs=2, min_quality=0.3, ema_threshold=0.0)
    struct_det = PAStructureDetector()
    out: list[EmittedSignal] = []
    for pa in det.scan(bars, h_bars):
        if PABottomDetector.policy_weight(pa, _IC, symbol=sym) == 0.0:
            continue
        if struct_det.detect(bars, up_to_idx=pa.bar_idx).phase == "BULL":
            continue
        if pa.higher_tf_relation != "opposing":
            continue
        close = float(bars["close"].iloc[pa.bar_idx])
        out.append(EmittedSignal(
            "pa_h2",
            pa.timestamp.date(),
            close,
            select_fn(close, pa.timestamp.date()),
        ))
    return out


def replay_context_a(
    bars: pd.DataFrame,
    h_bars: pd.DataFrame,
    underlying: str,
    sym: str,
) -> list[EmittedSignal]:
    """Replay Context A emitter.

    Gate: ContextADetector.policy_weight(asig, _IC, symbol=sym) > 0.
    ContextASignal has no ``direction`` field — Context A is always a bottom
    (uptrend pullback) entry.  Score=3 when policy passes, >= OPTIONS_MIN_SCORE=3.

    Production ref: score_today.py:1238-1303.
    """
    select_fn = _select_fn(underlying)
    out: list[EmittedSignal] = []
    for asig in ContextADetector().scan(bars, h_bars):
        if ContextADetector.policy_weight(asig, _IC, symbol=sym) <= 0.0:
            continue
        close = float(bars["close"].iloc[asig.bar_idx])
        out.append(EmittedSignal(
            "context_a",
            asig.timestamp.date(),
            close,
            select_fn(close, asig.timestamp.date()),
        ))
    return out


def replay_divergence(bars: pd.DataFrame, h_bars: pd.DataFrame, underlying: str) -> list[EmittedSignal]:
    """Replay divergence emitter (MACD-based, uses measured-move target).

    Gate:
      1. sig.level NOT in DIF_DETECTOR_LEVELS (include_dif_detectors=False default)
      2. sig.direction == "bottom"
      3. apply_policy(sig, instrument_class=_IC).weight > 0
      4. readiness_score(matched_sweet_spots, confidence) >= OPTIONS_MIN_SCORE

    Entry close: bars["close"].iloc[sig.candidate_bar_idx].
    mm_target_pct computed via _compute_mm_pct and passed to select_otm_calls.

    Production ref: score_today.py:870-925.
    """
    select_fn = _select_fn(underlying)
    macd_df = macd(bars["close"], hist_scale=1.0)
    streams = compute_feature_streams(
        bars["close"], macd_df["dif"], macd_df["dea"], macd_df["hist"]
    )
    units = compute_unit_metadata(
        macd_df["dif"], macd_df["dea"], macd_df["hist"], streams["dif_proximity_zero"]
    )
    signals = detect_all_divergences(
        units_df=units,
        ohlc=bars,
        dif=macd_df["dif"],
        hist=macd_df["hist"],
        level_id="D",
        instrument_class=_IC,
    )
    pool_rules = [r for r in SWEET_SPOTS if r.pool_class == _IC]
    out: list[EmittedSignal] = []
    for sig in signals:
        if sig.level in DIF_DETECTOR_LEVELS:        # include_dif_detectors=False (production default)
            continue
        if sig.direction != "bottom":
            continue
        if apply_policy(sig, instrument_class=_IC).weight == 0.0:
            continue
        ctx = sig.context_features or {}
        matched = [r for r in pool_rules if match_rule(r, sig.direction, sig.subtype, ctx)]
        if readiness_score(matched, sig.confidence) < OPTIONS_MIN_SCORE:
            continue
        close = float(bars["close"].iloc[sig.candidate_bar_idx])
        mm = _compute_mm_pct(sig, bars, close)
        out.append(EmittedSignal(
            "divergence",
            sig.timestamp.date(),
            close,
            select_fn(close, sig.timestamp.date(), mm_target_pct=mm),
        ))
    return out
