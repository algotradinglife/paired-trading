"""Context A bottom detector — DIF>0 uptrend pullback.

Context A: DIF>0 (bull trend intact), price 3-10% below 20-bar rolling
high, below EMA20, above EMA60×0.98, no recent acceleration bar.

K=3 walk-forward results (backtest_context_a_ev.py, stop=1.5×ATR, max_hold=40):
  US h=opposing   : n=153  EV=+0.100R  IS=−0.304R(n=46)  F1=+0.106R(n=33)  F2=+0.179R(n=42)  F3=+0.574R(n=32)
  CN_METAL h=opp  : n=73   EV=+0.220R  IS=+0.143R(n=28)  F1=+0.342R(n=19)  F2=−0.192R(n=13)  F3=+0.619R(n=13)

CONDITIONAL PASS for both pools, h=opposing only:
  US: OOS 3/3 positive and improving (IS negative due to incomplete 60m coverage pre-2022).
  CN_METAL: F2 fails (known 2024 regime break); F3 strongly recovers.
  policy_weight = 0.60 for h=opposing; 0.0 for all other h_rel.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from engine.divergence.b1_bottom_detector import _compute_htf_dif, _htf_relation_at
from engine.divergence.pa_context_classifier import classify_context
from engine.features.macd import macd as compute_macd


# ---------------------------------------------------------------------------
# Signal dataclass
# ---------------------------------------------------------------------------


@dataclass
class ContextASignal:
    """A Context A signal — DIF>0 uptrend pullback entry.

    Attributes:
        bar_idx: integer position in the source bars DataFrame
        timestamp: UTC timestamp of the signal bar
        features: raw feature values at signal bar (dif, close, ema20, ema60)
        higher_tf_relation: HTF DIF direction
            "opposing"   — 60m DIF < 0 (validates long entry during pullback)
            "supporting" — 60m DIF > 0 (trend-following — not validated)
            "neutral"    — 60m DIF ≈ 0
            None         — no HTF data
    """
    bar_idx: int
    timestamp: pd.Timestamp
    features: dict[str, object] = field(default_factory=dict)
    higher_tf_relation: str | None = None


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class ContextADetector:
    """Context A detector — wraps pa_context_classifier "A" context.

    Fires when classify_context() returns "A" for a bar:
      - DIF > 0 (uptrend intact)
      - Close >= EMA60 × 0.98 (not deeply broken below trend base)
      - Close < EMA20 (in pullback)
      - 3% ≤ pullback from 20-bar high ≤ 10%
      - No recent acceleration bar (no panic selling)

    Args:
        min_gap: minimum bars between consecutive signals (default 10).
            Context A can persist for many bars; min_gap prevents multiple
            entries from the same pullback window.
    """

    def __init__(self, min_gap: int = 10) -> None:
        self.min_gap = min_gap

    def scan(
        self,
        bars: pd.DataFrame,
        h_bars: pd.DataFrame | None = None,
    ) -> list[ContextASignal]:
        """Scan daily bars for Context A patterns.

        Args:
            bars: daily OHLCV with 'timestamp', 'open', 'high', 'low',
                  'close', 'volume' columns
            h_bars: optional 60min bars for HTF relation annotation.

        Returns:
            List of ContextASignal, sorted by bar_idx.
        """
        macd_df = compute_macd(bars["close"])
        ema20   = bars["close"].ewm(span=20, adjust=False).mean()
        ema60   = bars["close"].ewm(span=60, adjust=False).mean()

        h_dif, h_ts = _compute_htf_dif(h_bars) if h_bars is not None else (None, None)

        signals: list[ContextASignal] = []
        last_sig_idx = -999

        for i in range(65, len(bars)):
            if i - last_sig_idx < self.min_gap:
                continue
            ctx = classify_context(bars, i, macd_df, ema20, ema60)
            if ctx != "A":
                continue

            ts    = bars["timestamp"].iloc[i]
            h_rel = _htf_relation_at(ts, h_ts, h_dif) if h_dif is not None else None

            signals.append(ContextASignal(
                bar_idx=i,
                timestamp=ts,
                features={
                    "dif":   round(float(macd_df["dif"].iloc[i]), 6),
                    "ema20": round(float(ema20.iloc[i]), 4),
                    "ema60": round(float(ema60.iloc[i]), 4),
                },
                higher_tf_relation=h_rel,
            ))
            last_sig_idx = i

        return signals

    @staticmethod
    def policy_weight(
        sig: ContextASignal,
        instrument_class: str = "cn_metal_futures",
        symbol: str | None = None,
    ) -> float:
        """Policy weight for Context A signal.

        CONDITIONAL PASS for h=opposing only (US + CN_METAL):
          - US OOS F1=+0.106R / F2=+0.179R / F3=+0.574R (3/3 positive)
          - CN_METAL OOS F1=+0.342R / F2=−0.192R / F3=+0.619R (F2 fail = 2024 regime)
        All other h_rel return 0.0 — not validated.
        """
        if sig.higher_tf_relation != "opposing":
            return 0.0
        if instrument_class in ("us_equity", "cn_metal_futures"):
            return 0.60
        return 0.0
