"""B1 bottom detector — first pullback in a new MACD cycle.

Wraps the B1 context from pa_context_classifier: DIF<0 but recovering,
histogram >50% back from trough, H1 leg formed, price pulling back above trough.

K=3 walk-forward results (backtest_b1_bottom.py, stop=1.5×ATR, max_hold=40):
  All signals  : n=86  EV=+0.109R  IS=+0.274R(n=57) F1=+0.200R(n=5) F2=+0.250R(n=10) F3=-0.697R(n=14)
  h=opposing   : n=10  EV=-0.150R  IS=+0.500R(n=4)  F1=—            F2=+0.250R(n=2)  F3=-1.000R(n=4)

REJECTED: h=opposing cell has n=10 total (too sparse), F3=-1.000R (4 straight losses),
and no F1 signals at all. policy_weight() returns 0.0 for all cases.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from engine.features.macd import macd as compute_macd
from engine.divergence.pa_context_classifier import classify_context

# ---------------------------------------------------------------------------
# HTF helpers — copied from pa_detector to avoid circular imports
# ---------------------------------------------------------------------------


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
    """Return HTF DIF direction at or before ts.

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


# ---------------------------------------------------------------------------
# Signal dataclass
# ---------------------------------------------------------------------------


@dataclass
class B1BottomSignal:
    """A B1 bottom signal — first pullback in a new MACD recovery cycle.

    Attributes:
        bar_idx: integer position in the source bars DataFrame
        timestamp: UTC timestamp of the signal bar
        features: raw feature values at signal bar (dif, hist)
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


class B1BottomDetector:
    """B1 bottom detector — wraps pa_context_classifier B1 context.

    Fires when classify_context() returns "B1" for a bar:
      - DIF < 0 but recovering (DIF higher than N bars ago)
      - Histogram > 50% recovered from its trough
      - H1 leg formed (first bounce ≥ 5% above trough low)
      - Price pulling back ≥ 2% from H1 but still above trough low
      - No recent acceleration bar

    Args:
        min_gap: minimum bars between consecutive signals (default 10).
            B1 contexts can persist for several bars; min_gap prevents
            back-to-back signals from the same setup window.
    """

    def __init__(self, min_gap: int = 10) -> None:
        self.min_gap = min_gap

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(
        self,
        bars: pd.DataFrame,
        h_bars: pd.DataFrame | None = None,
    ) -> list[B1BottomSignal]:
        """Scan daily bars for B1 bottom patterns.

        Args:
            bars: daily OHLCV with 'timestamp', 'open', 'high', 'low',
                  'close', 'volume' columns
            h_bars: optional higher-TF (60min) bars for HTF relation annotation.
                    Must have 'timestamp' and 'close' columns.

        Returns:
            List of B1BottomSignal, sorted by bar_idx.
        """
        macd_df = compute_macd(bars["close"])
        ema20 = bars["close"].ewm(span=20, adjust=False).mean()
        ema60 = bars["close"].ewm(span=60, adjust=False).mean()

        h_dif, h_ts = _compute_htf_dif(h_bars) if h_bars is not None else (None, None)

        signals: list[B1BottomSignal] = []
        last_sig_idx = -999

        for i in range(65, len(bars)):
            if i - last_sig_idx < self.min_gap:
                continue

            ctx = classify_context(bars, i, macd_df, ema20, ema60)
            if ctx != "B1":
                continue

            ts = bars["timestamp"].iloc[i]
            h_rel = _htf_relation_at(ts, h_ts, h_dif) if h_dif is not None else None

            signals.append(B1BottomSignal(
                bar_idx=i,
                timestamp=ts,
                features={
                    "dif": round(float(macd_df["dif"].iloc[i]), 6),
                    "hist": round(float(macd_df["hist"].iloc[i]), 6),
                },
                higher_tf_relation=h_rel,
            ))
            last_sig_idx = i

        return signals

    # ------------------------------------------------------------------
    # Policy weights (placeholder — pending K=3 walk-forward validation)
    # ------------------------------------------------------------------

    @staticmethod
    def policy_weight(
        sig: B1BottomSignal,
        instrument_class: str = "cn_metal_futures",
        symbol: str | None = None,
    ) -> float:
        """Returns 0.0 — B1BottomDetector REJECTED by K=3 walk-forward.

        h=opposing cell: n=10 (too sparse), F3=-1.000R (4/4 losses in 2025).
        No cell passes validation. Do not use for live scoring until re-validated
        with richer data or an improved B1 definition.
        """
        return 0.0
