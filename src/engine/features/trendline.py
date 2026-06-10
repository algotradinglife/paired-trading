"""Pivot-pair trendlines — Xiao right-side confirmation geometry.

A trendline connects the two most recent CONFIRMED fractal pivots of the
same kind:
  support    = two rising swing lows  (older lower, newer higher)
  resistance = two falling swing highs (older higher, newer lower)

Causal: a pivot at index p with half-width n is confirmed at p + n; only
pivots with p + n <= up_to_idx are used. Spec:
docs/superpowers/specs/2026-06-10-phase-a-tbreak-chain-design.md
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Trendline:
    """Line through two anchor pivots, extrapolated forward."""
    kind: str          # "support" | "resistance"
    idx1: int          # older anchor bar index
    price1: float
    idx2: int          # newer anchor bar index
    price2: float

    @property
    def slope(self) -> float:
        return (self.price2 - self.price1) / (self.idx2 - self.idx1)

    def value_at(self, idx: int) -> float:
        return self.price1 + self.slope * (idx - self.idx1)


def _confirmed_pivots(
    values: np.ndarray, n: int, up_to_idx: int, find_high: bool,
) -> list[int]:
    """Fractal pivots confirmed by up_to_idx (pivot p needs p+n <= up_to_idx).

    Pivot rule mirrors swing_context.detect_swing_points: strictly greater
    (resp. smaller) than the n bars on each side.
    """
    out: list[int] = []
    last = min(up_to_idx - n, len(values) - 1 - n)
    for i in range(n, last + 1):
        v = values[i]
        left = values[i - n:i]
        right = values[i + 1:i + n + 1]
        if find_high:
            if np.all(v > left) and np.all(v > right):
                out.append(i)
        else:
            if np.all(v < left) and np.all(v < right):
                out.append(i)
    return out


def fit_trendline(
    bars: pd.DataFrame,
    up_to_idx: int,
    kind: str,
    pivot_n: int = 5,
) -> Trendline | None:
    """Fit the most recent valid 2-pivot trendline as of bar up_to_idx.

    support:    most recent pivot-low pair (older_low < newer_low)
    resistance: most recent pivot-high pair (older_high > newer_high)
    Returns None when no such pair exists among confirmed pivots.
    """
    if kind not in ("support", "resistance"):
        raise ValueError(f"unknown trendline kind: {kind!r}")

    find_high = kind == "resistance"
    col = "high" if find_high else "low"
    values = bars[col].values.astype(float)
    pivots = _confirmed_pivots(values, pivot_n, up_to_idx, find_high)
    if len(pivots) < 2:
        return None

    # Scan pairs from the most recent backwards: (p1 older, p2 newer).
    for j in range(len(pivots) - 1, 0, -1):
        p2 = pivots[j]
        for i in range(j - 1, -1, -1):
            p1 = pivots[i]
            rising = values[p2] > values[p1]
            if (kind == "support" and rising) or (kind == "resistance" and not rising):
                return Trendline(
                    kind=kind,
                    idx1=p1, price1=float(values[p1]),
                    idx2=p2, price2=float(values[p2]),
                )
        # Newest pivot has no valid partner — older pairs would be stale lines;
        # fall through and try the previous pivot as p2.
    return None
