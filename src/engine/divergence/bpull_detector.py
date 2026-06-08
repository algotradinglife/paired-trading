"""BPull (Bullish Pullback) detector — DIF>0 in-cycle recall expansion.

Detects swing bottoms during bullish MACD phases (DIF>0) when price pulls
back to EMA20 with higher-timeframe DIF<0 (opposing) providing macro context.
Designed as a recall-expansion detector for the ~49% of CN_COMMODITY missed
swings that have DIF>0 on the daily and are therefore invisible to divergence-
based detectors.

Core pattern — BPull:
  1. Daily DIF > 0 (bullish MACD phase, DIF above zero line)
  2. Price pulls back to EMA20: low ≤ EMA20 × (1 + touch_pct) [default 0.5%]
  3. Close does not collapse below EMA20: close ≥ EMA20 × (1 − floor_pct) [3%]
  4. HTF DIF < 0 (opposing — validates entry timing against macro downtrend)

Research basis (in-cycle-recall-research.md, 2026-06-02):
  Missed-swing-dataset (CN_COMMODITY, DIF>0 + h=opp subset, n=81):
    All:  EV=+0.892R, hit=65%
    IS:   n=37, +0.813R, 62%
    OOS1: n=16, +0.767R, 62%
    OOS2: n=28, +1.069R, 71%
  +EMA20 touch filter (missed-swing, pre-filtered):
    OOS1: n=9,  +1.475R, 89%;  OOS2: n=7,  +1.498R, 86%

Full-pool WF validation (backtest_bpull.py, 2026-06-02, gap-fixed):
  CN_METAL h=opposing (K=2): IS=+0.171R(n=92) F1=+0.121R(n=71) F2=+0.419R(n=93)
  CN_METAL h=opposing (K=3): IS=+0.171R(n=92) F1=+0.121R(n=71) F2=+0.348R(n=48) F3=+0.495R(n=45)
    → K=3 STRONG PASS, monotone F1→F3; upgraded from monitoring-grade
    → Drivers: au=+0.542R, cu=+0.242R, ag=+0.240R, sc=+0.149R
    → rb EXCLUDED: IS=+0.218R but OOS1=-0.448R/OOS2=-0.252R/OOS3=-0.240R (all 3 OOS negative)
       rb stop rate 56% — policy-driven instrument, EMA20 pullback not a technical signal
  CN_COMMODITY h=opposing: DCE agri drag makes it non-actionable; not routed

Routing: cn_metal_futures only (policy_weight 0.65 h=opp).

BASELINE_REF: baselines/bpull_cn_metal_futures.json
  Single source of truth for policy_weight evidence. The F1/F2/F3 numbers
  above are HISTORICAL — see the JSON for current verdict, valid_until, and
  re-validation status. Run `scripts/validate_baselines.py` to audit.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from engine.features.macd import macd as compute_macd
from engine.divergence.pa_detector import _compute_htf_dif, _htf_relation_at

# Symbols excluded from cn_metal_futures BPull routing.
# rb: all 3 OOS folds negative (OOS1=-0.448R/OOS2=-0.252R/OOS3=-0.240R),
# 56% stop rate — policy-driven instrument, EMA20 pullback not a technical signal.
_BPULL_EXCLUDED_CN_METAL: frozenset[str] = frozenset({"kq_m_shfe_rb"})


# ---------------------------------------------------------------------------
# Signal dataclass
# ---------------------------------------------------------------------------

@dataclass
class BPullSignal:
    """A BPull (Bullish Pullback) signal.

    Attributes:
        bar_idx: integer position in the source bars DataFrame
        timestamp: UTC timestamp of the signal bar
        features: raw feature values at signal bar (dif, ema20, ema_touch_pct, etc.)
        higher_tf_relation: HTF DIF direction
            "opposing"   — HTF DIF < 0 (bearish macro — validates bottom entry)
            "supporting" — HTF DIF > 0 (bullish macro — weaker setup)
            "neutral"    — HTF DIF ≈ 0
            None         — no HTF data
    """
    bar_idx: int
    timestamp: pd.Timestamp
    features: dict[str, object] = field(default_factory=dict)
    higher_tf_relation: str | None = None


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class BPullDetector:
    """Bullish-Pullback detector for DIF>0 in-cycle bottom recall.

    Fires when:
      1. daily DIF > 0 (bullish MACD phase)
      2. bar low ≤ EMA20 × (1 + ema_touch_pct): price touches the EMA20
      3. bar close ≥ EMA20 × (1 − ema_floor_pct): not a breakdown below EMA20
      4. at least min_gap bars since previous signal

    Args:
        ema_touch_pct: how far above EMA20 the low can be (0.005 = 0.5%)
        ema_floor_pct: maximum close drop below EMA20 allowed (0.03 = 3%)
        min_gap: minimum bars between consecutive signals
        macd_fast, macd_slow, macd_signal: MACD parameters (default 12/26/9)
        ema_period: EMA period for pullback detection (default 20)
    """

    def __init__(
        self,
        ema_touch_pct: float = 0.005,
        ema_floor_pct: float = 0.030,
        min_gap: int = 10,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        ema_period: int = 20,
    ) -> None:
        self.ema_touch_pct = ema_touch_pct
        self.ema_floor_pct = ema_floor_pct
        self.min_gap = min_gap
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.ema_period = ema_period

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(
        self,
        bars: pd.DataFrame,
        h_bars: pd.DataFrame | None = None,
    ) -> list[BPullSignal]:
        """Scan daily bars for BPull patterns.

        Args:
            bars: daily OHLCV with 'timestamp', 'open', 'high', 'low',
                  'close', 'volume' columns
            h_bars: optional higher-TF (60min) bars for HTF relation annotation.
                    Must have 'timestamp' and 'close' columns.

        Returns:
            List of BPullSignal, sorted by bar_idx.
        """
        md = compute_macd(
            bars["close"],
            fast=self.macd_fast,
            slow=self.macd_slow,
            signal=self.macd_signal,
        )
        dif = md["dif"].values.astype(float)
        ema20 = bars["close"].ewm(span=self.ema_period, adjust=False).mean().values
        low = bars["low"].values.astype(float)
        close = bars["close"].values.astype(float)

        h_dif, h_ts = _compute_htf_dif(h_bars) if h_bars is not None else (None, None)

        warmup = max(self.macd_slow + self.macd_signal, self.ema_period) + 5
        signals: list[BPullSignal] = []
        last_sig_idx = -999

        for i in range(warmup, len(bars)):
            if i - last_sig_idx < self.min_gap:
                continue

            d = dif[i]
            e20 = ema20[i]
            lo = low[i]
            cl = close[i]

            if not np.isfinite(d) or not np.isfinite(e20) or e20 <= 0:
                continue

            # Condition 1: DIF > 0 (bullish MACD phase)
            if d <= 0:
                continue

            # Condition 2: bar low touches EMA20 (from above or slight below)
            touch_ceil = e20 * (1.0 + self.ema_touch_pct)
            if lo > touch_ceil:
                continue

            # Condition 3: close doesn't collapse far below EMA20
            floor = e20 * (1.0 - self.ema_floor_pct)
            if cl < floor:
                continue

            ts = bars["timestamp"].iloc[i]
            h_rel = _htf_relation_at(ts, h_ts, h_dif) if h_dif is not None else None

            ema_touch_actual = (lo - e20) / e20  # negative = low was below EMA20
            signals.append(BPullSignal(
                bar_idx=i,
                timestamp=ts,
                features={
                    "dif": round(float(d), 6),
                    "ema20": round(float(e20), 4),
                    "low": round(float(lo), 4),
                    "close": round(float(cl), 4),
                    "ema_touch_pct_actual": round(ema_touch_actual, 5),
                    "ema_floor_actual": round((cl - e20) / e20, 5),
                },
                higher_tf_relation=h_rel,
            ))
            last_sig_idx = i

        return signals

    # ------------------------------------------------------------------
    # Policy weights (calibrated from research; full-pool WF pending)
    # ------------------------------------------------------------------

    @staticmethod
    def policy_weight(sig: BPullSignal, instrument_class: str = "cn_futures",
                      symbol: str | None = None) -> float:
        """Policy weight for a BPull signal.

        Full-pool WF K=2 backtest results (backtest_bpull.py, 2026-06-02):

          cn_metal_futures (SHFE au/cu/ag/sc), h=opposing — K=3 STRONG PASS:
            IS=+0.171R(n=92)  F1=+0.121R(n=71)  F2=+0.348R(n=48)  F3=+0.495R(n=45)
            Monotone increasing F1→F3 → 0.75 (upgraded from monitoring-grade)
            Per-symbol: au=+0.542R, cu=+0.242R, ag=+0.240R, sc=+0.149R
          rb (kq_m_shfe_rb) EXCLUDED:
            IS=+0.218R but OOS1=-0.448R/OOS2=-0.252R/OOS3=-0.240R (all OOS negative)
            56% stop rate — policy-driven, EMA20 not a valid technical signal → 0.0

          cn_futures (full CN_COMMODITY 15-symbol pool), h=opposing:
            IS=+0.176R(n=186)  F1=+0.124R(n=171)  F2=+0.106R(n=208)
            Mixed: DCE agri y=-0.292R, jm=-0.217R, ma=-0.226R drag heavily
            Not actionable without sub-pool routing → 0.0

          czce: not separately validated; included in cn_futures pool above

          us_equity / cn_index_futures: not validated for BPull

        NOTE: missed-swing analysis (pre-filtered to confirmed bottoms) showed
        higher EV (+0.767-1.475R OOS) because it only counted confirmed swings.
        Full-pool figures above are the realistic signal-frequency-weighted EV.
        """
        rel = sig.higher_tf_relation

        if instrument_class == "cn_metal_futures":
            # K=3 STRONG PASS (F1=+0.121R F2=+0.348R F3=+0.495R, monotone increasing)
            if symbol is not None and symbol.lower() in _BPULL_EXCLUDED_CN_METAL:
                return 0.0
            if rel == "opposing":
                return 0.75
            return 0.0

        # cn_futures full pool: DCE agri drags heavily — suppress
        # czce: not separately validated
        # us_equity, cn_index_futures: not validated
        return 0.0
