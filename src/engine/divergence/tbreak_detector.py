"""TBreak — trendline-break detector (Xiao right-side confirmation).

ALERT-ONLY: policy_weight is hard 0.0. This detector never enters the
production emit lanes / R-space scoring. Its events feed the
divergence-alert chain (engine/divergence/alert_chain.py) whose output is
validated post-migration in option-premium space.

Pattern:
  breakdown — close < rising-support-line value − buffer  (put-candidate leg)
  breakout  — close > falling-resistance-line value + buffer (call-candidate leg)
  buffer = buffer_atr × ATR(atr_period), guards against hairline fake breaks.
  confirm_bars=2 requires the next close to hold beyond the line (reclaim
  cancels). Each anchor pair fires at most once; min_gap spaces same-direction
  signals.

Spec: docs/superpowers/specs/2026-06-10-phase-a-tbreak-chain-design.md
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from engine.features.trendline import Trendline, fit_trendline


@dataclass
class TBreakSignal:
    """A trendline-break event.

    direction: "breakdown" (support broken) | "breakout" (resistance broken)
    features:  kind, anchor_idx1/2, anchor_price1/2, slope, line_value,
               buffer_abs, atr, close, touches
    """
    bar_idx: int
    timestamp: pd.Timestamp
    direction: str
    features: dict[str, object] = field(default_factory=dict)


def _compute_atr(bars: pd.DataFrame, period: int) -> pd.Series:
    hi, lo, pc = bars["high"], bars["low"], bars["close"].shift(1)
    tr = pd.concat([(hi - lo), (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


class TBreakDetector:
    """Trendline-break detector on pivot-pair lines. Alert-only.

    Args:
        pivot_n:      fractal half-width for pivot confirmation (default 5)
        buffer_atr:   break must clear line by buffer_atr × ATR (default 0.1)
        confirm_bars: 1 = close beyond line fires; 2 = next close must hold
        min_gap:      minimum bars between same-direction signals
        atr_period:   ATR period for the buffer (default 14)
    """

    def __init__(
        self,
        pivot_n: int = 5,
        buffer_atr: float = 0.1,
        confirm_bars: int = 1,
        min_gap: int = 10,
        atr_period: int = 14,
    ) -> None:
        if confirm_bars not in (1, 2):
            raise ValueError("confirm_bars must be 1 or 2")
        self.pivot_n = pivot_n
        self.buffer_atr = buffer_atr
        self.confirm_bars = confirm_bars
        self.min_gap = min_gap
        self.atr_period = atr_period

    def scan(
        self,
        bars: pd.DataFrame,
        h_bars: pd.DataFrame | None = None,  # unused; detector-API symmetry
    ) -> list[TBreakSignal]:
        closes = bars["close"].values.astype(float)
        atr = _compute_atr(bars, self.atr_period).values
        ts = bars["timestamp"]
        n = len(bars)

        signals: list[TBreakSignal] = []
        fired: set[tuple[str, int, int]] = set()   # (kind, idx1, idx2)
        last_fire: dict[str, int] = {}             # direction -> bar_idx
        # pending[direction] = (line, candidate_idx) awaiting follow-through
        pending: dict[str, tuple[Trendline, int]] = {}

        specs = (
            ("support", "breakdown", -1.0),
            ("resistance", "breakout", +1.0),
        )

        for i in range(2 * self.pivot_n + 1, n):
            for kind, direction, sgn in specs:
                # --- resolve pending confirm_bars=2 candidates first
                if direction in pending:
                    line, _cand = pending.pop(direction)
                    beyond = sgn * (closes[i] - line.value_at(i)) > 0.0
                    if beyond:
                        signals.append(self._make_signal(
                            line, i, ts.iloc[i], direction, closes[i], atr[i], bars))
                        fired.add((line.kind, line.idx1, line.idx2))
                        last_fire[direction] = i
                    continue  # reclaim -> candidate cancelled, nothing fires

                line = fit_trendline(bars, up_to_idx=i, kind=kind, pivot_n=self.pivot_n)
                if line is None or (line.kind, line.idx1, line.idx2) in fired:
                    continue
                if direction in last_fire and i - last_fire[direction] < self.min_gap:
                    continue
                buffer_abs = self.buffer_atr * float(atr[i])
                crossed = sgn * (closes[i] - line.value_at(i)) > buffer_abs
                if not crossed:
                    continue
                if self.confirm_bars == 2:
                    pending[direction] = (line, i)
                else:
                    signals.append(self._make_signal(
                        line, i, ts.iloc[i], direction, closes[i], atr[i], bars))
                    fired.add((line.kind, line.idx1, line.idx2))
                    last_fire[direction] = i

        return signals

    def _make_signal(
        self, line: Trendline, i: int, timestamp: pd.Timestamp,
        direction: str, close: float, atr_i: float, bars: pd.DataFrame,
    ) -> TBreakSignal:
        touch_col = "low" if line.kind == "support" else "high"
        vals = bars[touch_col].values.astype(float)
        tol = self.buffer_atr * atr_i
        touches = sum(
            1 for j in range(line.idx2 + 1, i)
            if abs(vals[j] - line.value_at(j)) <= tol
        )
        return TBreakSignal(
            bar_idx=i,
            timestamp=timestamp,
            direction=direction,
            features={
                "kind": line.kind,
                "anchor_idx1": line.idx1, "anchor_price1": line.price1,
                "anchor_idx2": line.idx2, "anchor_price2": line.price2,
                "slope": line.slope,
                "line_value": line.value_at(i),
                "buffer_abs": self.buffer_atr * float(atr_i),
                "atr": float(atr_i),
                "close": float(close),
                "touches": touches,
            },
        )

    @staticmethod
    def policy_weight(sig: TBreakSignal, instrument_class: str, symbol: str) -> float:
        """Alert-only detector: never weighted into production scoring."""
        return 0.0
