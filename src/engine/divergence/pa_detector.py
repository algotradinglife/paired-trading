"""PA bottom detector — Brooks H2-style standalone pattern detector.

Detects swing bottom setups from daily OHLCV bars without requiring MACD
divergence state. Designed as a recall expansion mechanism complementary
to the existing MACD divergence detector.

Recall validation (vs ZigZag 5%+ up swings, 2026-06-08):
  - US (10 ETFs, 2015 swings):   MACD 52.9% / PA 53.7% / +24.1pp PA-only
                                  combined 77.0%, overlap 29.6% (PA is additive)
  - CN_METAL (cu/au/ag/sc, 264): MACD 44.7% / PA 46.6% / +22.0pp PA-only
                                  combined 66.7%
  → PA catches +22-24pp of bottoms MACD misses; not a shadow of MACD.
    B1 context 40-day max return: US +11.6%, CN +13.2%.
    Residual blind spot (no detector hits): US 23%, CN 33%.

Core pattern — H2 Bottom:
  1. Price in downswing (below EMA20, ema_distance_norm < threshold)
  2. At least 2 prior recovery attempts (h_leg_count >= min_h_legs)
  3. Current bar shows bullish reversal quality (bar_quality_bull >= min_quality)
  4. Optional: recent selling climax (adds exhaustion context)

Integration with MACD engine:
  - PABottomDetector.scan() runs independently of MACD detector
  - PASignal annotated with higher_tf_relation for policy routing
  - Policy weights calibrated by instrument_class (see policy_weight()):
      us_equity uptrend+h=opp:      0.80 (legs=1 bonus → 0.90)
      us_equity us long-bond ETFs:  0.0  (tlt/tlh/iei/ief/shy — see policy_weight)
      cn_metal_futures h=opp:       0.75
      cn_bond h=opp:                0.70 (cffex_tf/t/ts, 3-fold all positive)
      cn_futures h=opp:             0.55 (marginal, monitoring only)
      czce/cn_agri:                 0.0  (OOS EV ≈ 0 with fold degradation — suppressed)
  - Ensemble boost: PA + MACD divergence within 3 bars → weight +0.15
  - legs=1 bonus validated K=3: 4/4 folds positive, n too small for production

Walk-forward status: K=2 + K=3 validated (see scripts/backtest_pa_swing.py).
US equity uptrend+h=opp at monitoring-grade; production requires n ≥ 50 per fold.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from engine.features.macd import macd as compute_macd
from engine.features.pa_features import compute_pa_features


# ---------------------------------------------------------------------------
# Signal dataclass
# ---------------------------------------------------------------------------

@dataclass
class PASignal:
    """A standalone PA pattern signal (independent of MACD state).

    Attributes:
        pattern: pattern name, e.g. "h2_bottom" or "h2_top"
        bar_idx: integer position in the source bars DataFrame
        timestamp: UTC timestamp of the signal bar
        confidence: [0, 1] composite score from feature values
        features: raw PA feature values at signal bar
        higher_tf_relation: DIF direction on the higher TF, encoded
            relative to the signal direction:
              For a BOTTOM signal:
                "opposing"   = HTF DIF negative (HTF bearish — validates bottom)
                "supporting" = HTF DIF positive (HTF bullish — counter-trend ctx)
              For a TOP signal (mirrored convention):
                "opposing"   = HTF DIF positive (HTF bullish — validates top)
                "supporting" = HTF DIF negative (HTF bearish — counter-trend ctx)
              "neutral" / None = no HTF data or DIF ≈ 0
        direction: "long" for a bottom signal, "short" for a top signal.
            Defaults to "long" for backward compatibility with the bottom
            detector — older PASignal consumers see no behavioural change.
    """
    pattern: str
    bar_idx: int
    timestamp: pd.Timestamp
    confidence: float
    features: dict[str, object]
    higher_tf_relation: str | None = None
    direction: str = "long"


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class PABottomDetector:
    """H2-style standalone bottom detector from daily OHLCV bars.

    Fires when:
      1. h_leg_count >= min_h_legs  (Brooks H1/H2 recovery attempts)
      2. bar_quality_bull >= min_quality  (bullish reversal bar)
      3. ema_distance_norm < ema_threshold  (price below EMA — downswing)
      4. At least min_gap bars since the previous signal

    Args:
        min_h_legs: minimum prior recovery attempts (2 = classic H2)
        min_quality: minimum bullish bar quality score [0, 1]
        ema_threshold: ema_distance_norm must be below this (< 0 means below EMA)
        min_gap: minimum bars between consecutive signals
        require_climax: if True, also require selling_climax_score in recent
            lookback to be >= climax_threshold (adds exhaustion context)
        climax_lookback: bars to look back for recent climax
        climax_threshold: minimum climax score in the lookback window
    """

    def __init__(
        self,
        min_h_legs: int = 2,
        min_quality: float = 0.3,
        ema_threshold: float = 0.0,
        min_gap: int = 10,
        h_lookback: int = 8,
        require_climax: bool = False,
        climax_lookback: int = 5,
        climax_threshold: float = 0.4,
        require_trend: set[str] | None = None,
    ) -> None:
        self.min_h_legs = min_h_legs
        self.min_quality = min_quality
        self.ema_threshold = ema_threshold
        self.min_gap = min_gap
        self.h_lookback = h_lookback
        self.require_climax = require_climax
        self.climax_lookback = climax_lookback
        self.climax_threshold = climax_threshold
        self.require_trend = require_trend

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(
        self,
        bars: pd.DataFrame,
        h_bars: pd.DataFrame | None = None,
        swing_context: pd.DataFrame | None = None,
    ) -> list[PASignal]:
        """Scan daily bars for H2 bottom patterns.

        Args:
            bars: daily OHLCV with 'timestamp', 'open', 'high', 'low',
                  'close', 'volume' columns
            h_bars: optional higher-TF (60min) bars for HTF relation annotation.
                    Must have 'timestamp' and 'close' columns.

        Returns:
            List of PASignal, sorted by bar_idx.
        """
        pa = compute_pa_features(bars, h_lookback=self.h_lookback)
        h_dif, h_ts = _compute_htf_dif(h_bars) if h_bars is not None else (None, None)

        signals: list[PASignal] = []
        last_sig_idx = -999

        for i in range(30, len(bars)):
            if i - last_sig_idx < self.min_gap:
                continue

            row = pa.iloc[i]

            if int(row["h_leg_count"]) < self.min_h_legs:
                continue
            if float(row["bar_quality_bull"]) < self.min_quality:
                continue
            if float(row["ema_distance_norm"]) >= self.ema_threshold:
                continue
            if self.require_climax:
                start = max(0, i - self.climax_lookback)
                recent_climax = pa["selling_climax_score"].iloc[start:i + 1].max()
                if float(recent_climax) < self.climax_threshold:
                    continue

            # Apply trend filter if swing context provided
            if self.require_trend is not None and swing_context is not None:
                ts_val = swing_context["trend_structure"].iloc[i]
                if ts_val not in self.require_trend:
                    continue

            # Extract swing context features for the signal
            swing_feats: dict[str, object] = {}
            if swing_context is not None:
                row_ctx = swing_context.iloc[i]
                swing_feats = {
                    "trend_structure": str(row_ctx["trend_structure"]),
                    "leg_count_down":  int(row_ctx["leg_count_down"]),
                    "market_regime":   str(row_ctx["market_regime"]),
                }

            confidence = _compute_confidence(row)
            ts = bars["timestamp"].iloc[i]
            h_rel = _htf_relation_at(ts, h_ts, h_dif) if h_dif is not None else None

            # Store recent climax max (prior 5 bars, excludes signal bar)
            # so post-hoc filters can check it without contradicting the bull bar.
            clx_start = max(0, i - 5)
            recent_climax_max_5 = float(
                pa["selling_climax_score"].iloc[clx_start:i].max()
            ) if i > 0 else 0.0

            signals.append(PASignal(
                pattern="h2_bottom",
                bar_idx=i,
                timestamp=ts,
                confidence=round(confidence, 4),
                features={
                    "h_leg_count": int(row["h_leg_count"]),
                    "bar_quality_bull": round(float(row["bar_quality_bull"]), 4),
                    "selling_climax_score": round(float(row["selling_climax_score"]), 4),
                    "recent_climax_max_5": round(recent_climax_max_5, 4),
                    "ema_distance_norm": round(float(row["ema_distance_norm"]), 4),
                    "body_compression": bool(row["body_compression"]),
                    "consec_bear_before": int(row["consec_bear_before"]),
                    **swing_feats,
                },
                higher_tf_relation=h_rel,
            ))
            last_sig_idx = i

        return signals

    # ------------------------------------------------------------------
    # Policy weights (calibrated from WF backtest 2026-06-02)
    # ------------------------------------------------------------------

    # US long-duration treasury ETFs structurally break the PA H2 setup
    # (see policy_weight() docstring).  Module-level so test setups can
    # extend it without touching the function body.
    US_LONG_BOND_SUPPRESS: frozenset[str] = frozenset({"tlt", "tlh", "iei", "ief", "shy"})

    @staticmethod
    def policy_weight(
        sig: PASignal,
        instrument_class: str = "cn_metal_futures",
        *,
        symbol: str | None = None,
    ) -> float:
        """Policy weight for a PA H2 bottom signal.

        Calibrated from WF backtests (latest: 2026-06-08):

          us_equity (backtest_pa_swing.py, 60min):
            K=2 (IS≤2022, OOS1=2023-2024H1, OOS2>2024H2):
              uptrend + h=opp:          F1=+0.625R(n=12) F2=+0.708R(n=24) PASS → 0.80
              uptrend + h=opp + legs=1: F1=+1.000R(n=5)  F2=+0.750R(n=10) → base+0.10
              downtrend:                F1=-0.177R                          REJECT → 0.0
            K=3 (IS≤2021, OOS1=2022-2023H1, OOS2=2023H2-2024, OOS3>2025):
              uptrend + h=opp:          F1=+0.147R(n=17) F2=+0.600R(n=10) F3=+0.636R(n=22)
              uptrend + h=opp + legs=1: F1=+0.500R(n=5)  F2=+0.667R(n=3)  F3=+0.750R(n=10)
                4/4 folds positive (incl IS), monotone increasing — monitoring-grade

          us_equity long-bond ETFs (tlt/tlh/iei/ief/shy):
            backtest_pa_us_k3 (2026-06-08, tlt only): n=27 EV=-0.519R, hit=15%
              4/4 folds negative: IS=-0.56 F1=-0.86 F2=-0.17 F3=-0.33
              All years 2021-2026 negative (covers hike/yield-peak/cut regimes)
              → suppress lane to 0.0; PA H2 doesn't survive duration shock dynamics

          cn_metal_futures (backtest_pa_standalone.py, gap-fix 2026-06-03;
            confirmed by backtest_pa_cn_structural.py via Parquet 2026-06-08):
            K=3 corrected: IS=-0.095R(n=39) F1=+0.348R(n=23) F2=+0.682R(n=16) F3=+0.097R(n=19)
            cn_structural 2026-06-08 (Parquet): all h=opp n=46 EV=+0.524R,
              F1+0.591 F2+1.045 F3+0.255 — all 3 OOS folds positive
            TR phase × h=opp: n=38 EV=+0.666R, F1+1.143 F2+1.250 F3+0.229
              (TR phase is the strongest sub-cell; phase filter is a real signal)

          cn_bond (cffex_tf/t/ts treasury futures; previously routed to cn_futures):
            backtest_pa_cn_phasefilter --pool CN_BOND (2026-06-08):
              All h=opp: n=31 EV=+0.548R, F1=+0.219(n=16) F2=+1.500(n=6) F3=+0.500(n=9)
              TR phase 28/31 (90%); 3/3 OOS folds positive — STRONG PASS → 0.70
              CAVEAT: F2=+1.500R(n=6) is a small-sample outlier; aggregate
              EV is overstated. Full-stack 5.5y confirms direction (+0.123R EV
              n=73 win 66%) but at lower magnitude.
              BASELINE_REF: baselines/pa_h2_cn_bond.json

          cn_futures (mixed):         F1=+0.183R        F2=+0.124R       marginal → 0.55
          cn_agri_pos (m/p/ta/ma/sr, require_climax=True, h=opp):
            STALE 2026-06-08: original K=3 STRONG PASS claim NOT REPRODUCIBLE.
              Documented: F1=+0.640R(n=8) F2=+0.516R(n=7) F3=+0.571R(n=7), 2026-06-04
              Reproduced (--cutoff3 2024-12-31): F1=+0.622R(n=18) F2=-0.444R(n=9) F3=-0.316R(n=17)
              Reproduced (--cutoff3 2025-06-30): F1=+0.622R(n=18) F2=-0.458R(n=15) F3=-0.227R(n=11)
              Full-stack 5.5y replay: EV -0.040R / n=64 / win 47%.
              Lane suspended (policy_weight=0). See:
                doc/repro/pa_h2_climax_anomaly_2026-06-08.md
                baselines/pa_h2_climax_cn_agri_pos.json
          czce / cn_agri (no climax):
            backtest_pa_cn_phasefilter 2026-06-08 sub-pool slice:
              CZCE only (ta/ma/cf/sr): n=46 OOS EV=+0.032R, F1+0.294 F2-0.068 F3-0.100
              DCE_AGRI (m/i/j/jm/p/y): n=105 OOS EV=+0.017R, F1+0.239 F2-0.086 F3-0.014
              IS→OOS degradation (CZCE +0.278R→+0.032R) is overfit signature.
              OOS EV ≈ 0 with fold degradation, hit 35-37% → suppressed at 0.0

        Args:
            sig: the PA signal
            instrument_class: routing class
            symbol: optional lowercased symbol stem, used to short-circuit
                lanes that are structurally broken at the symbol level
                (e.g. US long-bond ETFs under us_equity).
        """
        sym = (symbol or "").lower()
        rel = sig.higher_tf_relation

        # Symbol-level suppression: PA H2 fails on US long-duration
        # treasury ETFs across every macro regime (see docstring).
        if sym in PABottomDetector.US_LONG_BOND_SUPPRESS:
            return 0.0

        if instrument_class == "cn_metal_futures":
            # K=3 corrected (gap-fix): OOS folds all positive; IS=-0.095R; F3=+0.097R (marginal)
            if rel == "opposing":
                return 0.75
            if rel == "supporting":
                return 0.45
            return 0.60  # neutral/unknown

        if instrument_class == "cn_bond":
            # CFFEX treasury futures (tf/t/ts).  K=3 all OOS folds positive;
            # 90% of signals fire in TR phase.
            if rel == "opposing":
                return 0.70
            return 0.40  # neutral fallback; bond futures rarely trade BULL phase

        if instrument_class == "cn_futures":
            # Mixed commodity: marginal positive OOS, metal sub-pool drives
            # Not validated — monitoring only
            if rel == "opposing":
                return 0.55
            return 0.35

        if instrument_class == "us_equity":
            # Backtest backtest_pa_swing.py WF K=2 (2026-06-02):
            #   uptrend + h=opp:         F1=+0.625R(n=28) F2=+0.708R(n=56) PASS
            #   legs_down=1 sub-cell:    F1=+1.000R(n=5)  F2=+0.750R(n=10) bonus
            #   ranging + h=opp:         F1=+0.625R        F2=-0.150R unstable
            #   downtrend:               F1=-0.177R                          REJECT
            trend = str(sig.features.get("trend_structure", ""))
            leg_count = int(sig.features.get("leg_count_down", 0))
            if trend == "uptrend":
                if rel == "opposing":
                    base = 0.80
                    # legs=1 (ABC two-leg pullback completing) shows extra lift
                    return base + (0.10 if leg_count == 1 else 0.0)
                # uptrend but no HTF confirmation — partial evidence
                return 0.40
            # downtrend: negative OOS — suppress
            if trend == "downtrend":
                return 0.0
            # ranging or unknown trend — not validated
            return 0.0

        # czce, cn_agri: OOS EV ≈ 0 with fold degradation — suppress
        return 0.0

    @staticmethod
    def ensemble_weight(pa_sig: PASignal, instrument_class: str,
                        macd_within_bars: int | None,
                        *, symbol: str | None = None) -> float:
        """Weight when PA and MACD both fire near the same bar.

        Args:
            pa_sig: the PA signal
            instrument_class: routing class
            macd_within_bars: bars between PA and nearest MACD signal,
                None if no nearby MACD signal
            symbol: forwarded to ``policy_weight`` for symbol-level
                suppression (US long-bond ETFs)

        Returns:
            Combined weight for the ensemble signal.
        """
        base = PABottomDetector.policy_weight(pa_sig, instrument_class, symbol=symbol)
        if base == 0.0:
            return 0.0
        if macd_within_bars is not None and macd_within_bars <= 3:
            return min(base + 0.15, 1.20)
        return base


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_confidence(row: pd.Series) -> float:
    """Composite confidence [0, 1] from PA feature values (bottom side)."""
    h_norm = min(float(row["h_leg_count"]) / 3.0, 1.0)
    quality = float(row["bar_quality_bull"])
    climax = float(row["selling_climax_score"])
    return h_norm * 0.35 + quality * 0.45 + climax * 0.20


def _compute_confidence_top(row: pd.Series) -> float:
    """Composite confidence [0, 1] from PA feature values (top side).

    Mirror of ``_compute_confidence``: L-leg count + bear bar quality +
    buying climax magnitude.
    """
    l_norm = min(float(row["l_leg_count"]) / 3.0, 1.0)
    quality = float(row["bar_quality_bear"])
    climax = float(row["buying_climax_score"])
    return l_norm * 0.35 + quality * 0.45 + climax * 0.20


def _compute_htf_dif(
    h_bars: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute MACD DIF on higher-TF bars; return (dif_values, timestamps)."""
    md = compute_macd(h_bars["close"], hist_scale=1.0)
    dif_vals = md["dif"].values.astype(float)
    ts_vals = h_bars["timestamp"].values  # numpy datetime64
    return dif_vals, ts_vals


def _htf_relation_at(
    ts: pd.Timestamp,
    h_ts: np.ndarray,
    h_dif: np.ndarray,
) -> str | None:
    """Return HTF DIF direction at or before ts (bottom-signal convention).

    "opposing"   — HTF DIF < 0 (bearish — validates a bottom signal)
    "supporting" — HTF DIF > 0 (bullish — counter-trend context)
    "neutral"    — HTF DIF ≈ 0
    None         — no HTF bar found before ts
    """
    ts_np = np.datetime64(ts.to_datetime64())
    mask = h_ts <= ts_np
    if not mask.any():
        return None
    idx = int(np.flatnonzero(mask)[-1])
    v = float(h_dif[idx])
    if not np.isfinite(v):
        return None
    if v < 0:
        return "opposing"
    if v > 0:
        return "supporting"
    return "neutral"


def _htf_relation_at_top(
    ts: pd.Timestamp,
    h_ts: np.ndarray,
    h_dif: np.ndarray,
) -> str | None:
    """Return HTF DIF direction at or before ts (top-signal convention).

    Mirror of ``_htf_relation_at`` with the polarity flipped so that
    "opposing" still means "HTF momentum is going against the proposed
    reversal":

    "opposing"   — HTF DIF > 0 (bullish — validates a top signal)
    "supporting" — HTF DIF < 0 (bearish — counter-trend context)
    "neutral"    — HTF DIF ≈ 0
    None         — no HTF bar found before ts
    """
    ts_np = np.datetime64(ts.to_datetime64())
    mask = h_ts <= ts_np
    if not mask.any():
        return None
    idx = int(np.flatnonzero(mask)[-1])
    v = float(h_dif[idx])
    if not np.isfinite(v):
        return None
    if v > 0:
        return "opposing"
    if v < 0:
        return "supporting"
    return "neutral"


# ---------------------------------------------------------------------------
# Top detector (mirror of PABottomDetector)
# ---------------------------------------------------------------------------

class PATopDetector:
    """H2-style standalone swing-top detector from daily OHLCV bars.

    Symmetric mirror of :class:`PABottomDetector`.  Fires when:
      1. l_leg_count >= min_l_legs  (Brooks L1/L2 failed-rally attempts)
      2. bar_quality_bear >= min_quality  (bearish reversal bar)
      3. ema_distance_norm > ema_threshold  (price above EMA — upswing)
      4. At least min_gap bars since the previous signal

    NOTE on production status:
      The detection plumbing is symmetric with the validated bottom
      detector, but the policy weights (see :meth:`policy_weight`) are
      currently a no-emit stub — every routing path returns 0.0 until a
      dedicated walk-forward validation pass calibrates them.  This
      detector is intentionally NOT wired into ``score_today``; it is
      exposed for backtests and offline analysis only.

    Args:
        min_l_legs: minimum prior failed-rally attempts (2 = classic L2)
        min_quality: minimum bearish bar quality score [0, 1]
        ema_threshold: ema_distance_norm must be above this (> 0 = above EMA)
        min_gap: minimum bars between consecutive signals
        h_lookback: lookback window for ``l_leg_count``
        require_climax: if True, require a buying climax in recent lookback
        climax_lookback: bars to look back for recent climax
        climax_threshold: minimum buying climax score in the lookback window
        require_trend: optional set of trend_structure values to require
            from a swing-context DataFrame (e.g. {"downtrend"} for a top)
    """

    def __init__(
        self,
        min_l_legs: int = 2,
        min_quality: float = 0.3,
        ema_threshold: float = 0.0,
        min_gap: int = 10,
        h_lookback: int = 8,
        require_climax: bool = False,
        climax_lookback: int = 5,
        climax_threshold: float = 0.4,
        require_trend: set[str] | None = None,
    ) -> None:
        self.min_l_legs = min_l_legs
        self.min_quality = min_quality
        self.ema_threshold = ema_threshold
        self.min_gap = min_gap
        self.h_lookback = h_lookback
        self.require_climax = require_climax
        self.climax_lookback = climax_lookback
        self.climax_threshold = climax_threshold
        self.require_trend = require_trend

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(
        self,
        bars: pd.DataFrame,
        h_bars: pd.DataFrame | None = None,
        swing_context: pd.DataFrame | None = None,
    ) -> list[PASignal]:
        """Scan bars for H2 top patterns (mirror of PABottomDetector.scan).

        Args:
            bars: OHLCV with 'timestamp', 'open', 'high', 'low',
                  'close', 'volume' columns
            h_bars: optional higher-TF (e.g. 60min) bars for HTF relation
                    annotation.  Must have 'timestamp' and 'close' columns.
            swing_context: optional swing/trend context DataFrame aligned
                    to ``bars`` (same columns the bottom detector consumes
                    — trend_structure, leg_count_up, market_regime).

        Returns:
            List of PASignal with ``pattern='h2_top'`` and
            ``direction='short'``, sorted by bar_idx.
        """
        if len(bars) == 0:
            return []

        pa = compute_pa_features(bars, h_lookback=self.h_lookback)
        h_dif, h_ts = _compute_htf_dif(h_bars) if h_bars is not None else (None, None)

        signals: list[PASignal] = []
        last_sig_idx = -999

        for i in range(30, len(bars)):
            if i - last_sig_idx < self.min_gap:
                continue

            row = pa.iloc[i]

            if int(row["l_leg_count"]) < self.min_l_legs:
                continue
            if float(row["bar_quality_bear"]) < self.min_quality:
                continue
            if float(row["ema_distance_norm"]) <= self.ema_threshold:
                continue
            if self.require_climax:
                start = max(0, i - self.climax_lookback)
                recent_climax = pa["buying_climax_score"].iloc[start:i + 1].max()
                if float(recent_climax) < self.climax_threshold:
                    continue

            if self.require_trend is not None and swing_context is not None:
                ts_val = swing_context["trend_structure"].iloc[i]
                if ts_val not in self.require_trend:
                    continue

            swing_feats: dict[str, object] = {}
            if swing_context is not None:
                row_ctx = swing_context.iloc[i]
                # Top-side mirror: leg_count_up is the analogue of
                # leg_count_down used by the bottom routing table.
                up_legs_col = (
                    "leg_count_up" if "leg_count_up" in swing_context.columns
                    else "leg_count_down"
                )
                swing_feats = {
                    "trend_structure": str(row_ctx["trend_structure"]),
                    "leg_count_up":    int(row_ctx[up_legs_col]),
                    "market_regime":   str(row_ctx["market_regime"]),
                }

            confidence = _compute_confidence_top(row)
            ts = bars["timestamp"].iloc[i]
            h_rel = _htf_relation_at_top(ts, h_ts, h_dif) if h_dif is not None else None

            clx_start = max(0, i - 5)
            recent_climax_max_5 = float(
                pa["buying_climax_score"].iloc[clx_start:i].max()
            ) if i > 0 else 0.0

            signals.append(PASignal(
                pattern="h2_top",
                bar_idx=i,
                timestamp=ts,
                confidence=round(confidence, 4),
                features={
                    "l_leg_count": int(row["l_leg_count"]),
                    "bar_quality_bear": round(float(row["bar_quality_bear"]), 4),
                    "buying_climax_score": round(float(row["buying_climax_score"]), 4),
                    "recent_climax_max_5": round(recent_climax_max_5, 4),
                    "ema_distance_norm": round(float(row["ema_distance_norm"]), 4),
                    "body_compression": bool(row["body_compression"]),
                    "consec_bull_before": int(row["consec_bull_before"]),
                    **swing_feats,
                },
                higher_tf_relation=h_rel,
                direction="short",
            ))
            last_sig_idx = i

        return signals

    # ------------------------------------------------------------------
    # Policy weights — SKELETON, no-emit until walk-forward validation
    # ------------------------------------------------------------------

    @staticmethod
    def policy_weight(
        sig: PASignal,
        instrument_class: str = "cn_metal_futures",
        *,
        symbol: str | None = None,
    ) -> float:
        """Policy weight for a PA H2 top signal.

        SKELETON — needs walk-forward validation.

        This routing table is intentionally a no-emit stub: every
        instrument_class returns 0.0 so the detector cannot accidentally
        emit live trades before a dedicated TOP walk-forward validation
        pass calibrates the weights.  The table preserves the same
        signature and lane structure as :meth:`PABottomDetector.policy_weight`
        so that, when validated numbers arrive, swapping them in is a
        local edit.

        Placeholder lanes (all 0.0 until WF-validated):
          us_equity downtrend + h=opposing : 0.0
          us_equity (any other state)      : 0.0
          cn_metal_futures h=opposing      : 0.0
          cn_bond h=opposing               : 0.0
          cn_futures h=opposing            : 0.0
          everything else                  : 0.0

        Args:
            sig: the PA top signal (``pattern='h2_top'``)
            instrument_class: routing class (same vocabulary as the
                bottom detector — us_equity / cn_metal_futures /
                cn_bond / cn_futures / czce / cn_agri / ...)
            symbol: optional lowercased symbol stem, threaded through
                for symmetry with the bottom detector even though no
                symbol-level top suppression is active yet.

        Returns:
            0.0 for every input (current stub behaviour).
        """
        # TODO(2026-06-08, TASK C4): K=3 walk-forward grid validation across
        # us_60min / cn_metal_daily / cn_bond_daily / cn_commodity_daily
        # found NO cell that clears (n_oos >= 20 AND EV_oos > 0 AND OOS
        # folds same sign).  Closest contender — cn_commodity_daily ×
        # TR_FORMING × h=opp × top_div=True — was n=20 EV=+0.073R with
        # OOS1/2/3 = -0.25 / +0.43 / -0.005 (sign-unstable).  CN bond
        # tops fade systematically (-0.44R / n=24 across folds).
        # See doc/repro/pa_top_wf_2026-06-08.md for the full grid and the
        # CN-short-emphasis verdict (mixed → leaning no under this config).
        # Keep weights at 0.0 until 15min-confirm overlay or looser
        # detector params lift a cell over the promotion bar.
        # All lanes intentionally suppressed.  Reference ``sig``,
        # ``instrument_class``, and ``symbol`` so that future calibration
        # edits can attach numbers without restructuring the signature.
        _ = (sig, instrument_class, (symbol or "").lower())
        return 0.0

    @staticmethod
    def ensemble_weight(
        pa_sig: PASignal,
        instrument_class: str,
        macd_within_bars: int | None,
        *,
        symbol: str | None = None,
    ) -> float:
        """Ensemble weight for top signals — also a no-emit stub.

        Mirrors :meth:`PABottomDetector.ensemble_weight` so future
        validation can drop in numbers without changing the call sites.
        Because :meth:`policy_weight` returns 0.0 across the board, this
        always returns 0.0 today.
        """
        base = PATopDetector.policy_weight(pa_sig, instrument_class, symbol=symbol)
        if base == 0.0:
            return 0.0
        if macd_within_bars is not None and macd_within_bars <= 3:
            return min(base + 0.15, 1.20)
        return base
