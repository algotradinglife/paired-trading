"""VFlush (Vertical Flush) bottom detector — exhaustion-based standalone pattern.

Detects V-shape vertical flush bottoms from daily OHLCV bars WITHOUT
requiring MACD divergence state or Brooks H2 structure (h_leg_count >= 2).

These are rapid capitulation drops: price falls sharply, selling exhausts,
reverses without building a classic recovery-attempt structure.

Core pattern — VFlush Bottom:
  1. ema_distance_norm < -0.02      — price >= 2% (in ATR units) below EMA20
  2. selling_climax_score >= 0.3    — CURRENT BAR exhaustion signal (primary gate)
     NOTE: lookback-only climax without current-bar signal is disabled by default
           because backtest showed lookback_only EV=-0.018R vs current_bar +0.281R
  3. h_leg_count <= 1               — NOT an H2 (no classic recovery structure)
  4. min_gap = 10                   — gap enforcement (same as PA H2)
  5. higher_tf_relation annotated from 60min DIF (same as PA H2)

Rationale:
  PA H2 detector (pa_detector.py) requires h_leg_count >= 2 and
  bar_quality_bull >= 0.3. Recall-gap analysis found 75% of missed CN_METAL
  bottoms have h_leg_count < 2 and bar_quality_bull < 0.1 — they are V-shape
  flushes, not gradual H2 formations.

Confidence formula:
  climax * 0.6 + min(|ema_dist| / 0.05, 1.0) * 0.4

Walk-forward status (2026-06-03, backtest_vflush.py, CN_METAL):
  Current-bar-only gate | h=opposing — cu+sc only (ag+au excluded):
    IS=+0.598R(n=22)  F1=+0.722R(n=12)  F2=+0.436R(n=9)  F3=+0.533R(n=7)
    All 4 folds positive — K=3 STRONG PASS
  Full pool (all 4 symbols, for reference):
    IS=+0.255R(n=32)  F1=+0.684R(n=18)  F2=+0.101R(n=14)  F3=+0.341R(n=13)
    ag=-0.015R(n=19), au=-0.357R(n=8) drag F2 to marginal
  policy_weight: cn_metal_futures cu+sc + h=opposing → 0.65; ag+au → 0.0
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from engine.features.macd import macd as compute_macd
from engine.features.pa_features import compute_pa_features

# Re-export helpers from pa_detector to avoid duplication
from engine.divergence.pa_detector import _compute_htf_dif, _htf_relation_at

# Symbols with negative OOS history — excluded from VFlush policy (like BPull excludes rb).
# ag and au both show negative mean OOS across K=3 folds; cu+sc are the validated drivers.
_VFLUSH_EXCLUDED_CN_METAL: frozenset[str] = frozenset({"kq_m_shfe_ag", "kq_m_shfe_au"})


# ---------------------------------------------------------------------------
# Signal dataclass
# ---------------------------------------------------------------------------

@dataclass
class VFlushSignal:
    """A V-shape vertical flush bottom signal (exhaustion-based).

    Attributes:
        pattern: always "vflush_bottom"
        bar_idx: integer position in the source bars DataFrame
        timestamp: UTC timestamp of the signal bar
        confidence: [0, 1] composite score from climax + ema_distance
        features: raw PA feature values at signal bar
        higher_tf_relation: DIF direction on the higher TF
            ("opposing"   = HTF DIF < 0 → bearish HTF validates a bottom)
            ("supporting" = HTF DIF > 0 → counter-trend context)
            ("neutral"    = DIF ≈ 0)
            None          = no HTF data
    """
    pattern: str
    bar_idx: int
    timestamp: pd.Timestamp
    confidence: float
    features: dict[str, object]
    higher_tf_relation: str | None = None


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class VFlushDetector:
    """Vertical-flush standalone bottom detector from daily OHLCV bars.

    Fires when:
      1. ema_distance_norm < ema_threshold (price deeply below EMA — flush)
      2. selling_climax_score >= min_climax  (current bar exhaustion)
         OR  max(climax in prior climax_lookback bars) >= lookback_climax_thr
      3. h_leg_count <= max_h_legs           (NOT an H2 structure)
      4. At least min_gap bars since the previous signal

    Args:
        max_h_legs: maximum h_leg_count allowed (1 = no recovery structure)
        min_ema_pct: ema_distance_norm must be below this (negative = below EMA)
        min_climax: minimum selling_climax_score on the signal bar
        climax_lookback: bars to look back for recent climax (prior bars only)
        lookback_climax_thr: minimum climax score in the lookback window
        min_gap: minimum bars between consecutive signals
    """

    def __init__(
        self,
        max_h_legs: int = 1,
        min_ema_pct: float = -0.02,
        min_climax: float = 0.3,
        climax_lookback: int = 3,
        lookback_climax_thr: float = 99.0,
        min_gap: int = 10,
    ) -> None:
        """
        Args:
            max_h_legs: maximum h_leg_count allowed (default 1 = no H2 structure)
            min_ema_pct: ema_distance_norm must be below this (< 0 = below EMA)
            min_climax: minimum selling_climax_score on the CURRENT bar (primary gate)
            climax_lookback: bars to look back for recent climax (prior bars only)
            lookback_climax_thr: minimum climax score in the lookback window.
                Default 99.0 effectively disables the lookback path — backtest
                showed lookback-only EV=-0.018R vs current-bar EV=+0.281R.
                Set to e.g. 0.4 to re-enable lookback as a secondary gate.
            min_gap: minimum bars between consecutive signals
        """
        self.max_h_legs = max_h_legs
        self.min_ema_pct = min_ema_pct
        self.min_climax = min_climax
        self.climax_lookback = climax_lookback
        self.lookback_climax_thr = lookback_climax_thr
        self.min_gap = min_gap

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(
        self,
        bars: pd.DataFrame,
        h_bars: pd.DataFrame | None = None,
    ) -> list[VFlushSignal]:
        """Scan daily bars for VFlush bottom patterns.

        Args:
            bars: daily OHLCV with 'timestamp', 'open', 'high', 'low',
                  'close', 'volume' columns
            h_bars: optional higher-TF (60min) bars for HTF relation annotation.
                    Must have 'timestamp' and 'close' columns.

        Returns:
            List of VFlushSignal, sorted by bar_idx.
        """
        pa = compute_pa_features(bars, h_lookback=8)
        h_dif, h_ts = _compute_htf_dif(h_bars) if h_bars is not None else (None, None)

        signals: list[VFlushSignal] = []
        last_sig_idx = -999

        for i in range(30, len(bars)):
            if i - last_sig_idx < self.min_gap:
                continue

            row = pa.iloc[i]

            # Gate 1: h_leg_count must be <= max_h_legs (not an H2)
            if int(row["h_leg_count"]) > self.max_h_legs:
                continue

            # Gate 2: price must be below EMA by at least min_ema_pct
            ema_dist = float(row["ema_distance_norm"])
            if ema_dist >= self.min_ema_pct:
                continue

            # Gate 3: exhaustion — current bar OR recent lookback
            climax = float(row["selling_climax_score"])
            current_fire = climax >= self.min_climax

            lookback_fire = False
            if not current_fire and i > 0:
                lb_start = max(0, i - self.climax_lookback)
                recent_max = float(pa["selling_climax_score"].iloc[lb_start:i].max())
                lookback_fire = recent_max >= self.lookback_climax_thr

            if not (current_fire or lookback_fire):
                continue

            # Store lookback climax max (prior bars) for reporting
            lb_start = max(0, i - self.climax_lookback)
            recent_climax_max = float(
                pa["selling_climax_score"].iloc[lb_start:i].max()
            ) if i > 0 else 0.0

            confidence = _compute_confidence(climax, ema_dist)
            ts = bars["timestamp"].iloc[i]
            h_rel = _htf_relation_at(ts, h_ts, h_dif) if h_dif is not None else None

            signals.append(VFlushSignal(
                pattern="vflush_bottom",
                bar_idx=i,
                timestamp=ts,
                confidence=round(confidence, 4),
                features={
                    "h_leg_count": int(row["h_leg_count"]),
                    "bar_quality_bull": round(float(row["bar_quality_bull"]), 4),
                    "selling_climax_score": round(climax, 4),
                    "recent_climax_max": round(recent_climax_max, 4),
                    "ema_distance_norm": round(ema_dist, 4),
                    "body_compression": bool(row["body_compression"]),
                    "consec_bear_before": int(row["consec_bear_before"]),
                    "current_fire": bool(current_fire),
                    "lookback_fire": bool(lookback_fire),
                },
                higher_tf_relation=h_rel,
            ))
            last_sig_idx = i

        return signals

    # ------------------------------------------------------------------
    # Policy weights (placeholder — updated after WF backtest)
    # ------------------------------------------------------------------

    @staticmethod
    def policy_weight(
        sig: VFlushSignal,
        instrument_class: str = "cn_metal_futures",
        symbol: str | None = None,
    ) -> float:
        """Policy weight for a VFlush bottom signal.

        Calibrated from WF backtest (2026-06-03, backtest_vflush.py):

          cn_metal_futures — cu+sc only | h=opposing (K=3):
            IS=+0.598R(n=22)  F1=+0.722R(n=12)  F2=+0.436R(n=9)  F3=+0.533R(n=7)
            All 4 folds positive — K=3 STRONG PASS → weight 0.65
          ag+au excluded (OOS negative; see _VFLUSH_EXCLUDED_CN_METAL):
            ag: IS=-0.375R  F1=+0.554R  F2=-0.375R  F3=+0.667R (inconsistent)
            au: IS=-1.000R  F1=+0.718R  F2=-1.000R  F3=-0.432R (negative EV)

          Other instrument classes: not validated → 0.0

        Args:
            sig: VFlushSignal to score.
            instrument_class: instrument class string (e.g. "cn_metal_futures").
            symbol: optional symbol name (e.g. "kq_m_shfe_cu"). When provided,
                symbols in _VFLUSH_EXCLUDED_CN_METAL return 0.0.
        """
        rel = sig.higher_tf_relation

        if instrument_class == "cn_metal_futures":
            if symbol is not None and symbol.lower() in _VFLUSH_EXCLUDED_CN_METAL:
                return 0.0
            if rel == "opposing":
                return 0.65
            return 0.0  # non-opposing not validated in K=3 walk-forward

        # Not validated on other pools
        return 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_confidence(climax: float, ema_dist: float) -> float:
    """Composite confidence [0, 1] from climax score and EMA distance.

    Formula: climax * 0.6 + min(|ema_dist| / 0.05, 1.0) * 0.4
    """
    ema_component = min(abs(ema_dist) / 0.05, 1.0)
    return float(np.clip(climax * 0.6 + ema_component * 0.4, 0.0, 1.0))
