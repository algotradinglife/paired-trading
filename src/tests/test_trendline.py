"""Tests for engine/features/trendline.py — pivot-pair trendline geometry."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.features.trendline import Trendline, fit_trendline


def make_bars(rows: list[tuple[float, float, float]]) -> pd.DataFrame:
    """rows = (high, low, close). Timestamps daily UTC from 2024-01-01."""
    ts = pd.date_range("2024-01-01", periods=len(rows), freq="D", tz="UTC")
    return pd.DataFrame({
        "timestamp": ts,
        "open":  [c for _, _, c in rows],
        "high":  [h for h, _, _ in rows],
        "low":   [l for _, l, _ in rows],
        "close": [c for _, _, c in rows],
    })


# Rising support fixture, pivot_n=2.
# Pivot lows: idx2 (low=8.0, confirmed at 4), idx7 (low=9.5, confirmed at 9).
# Support line: (2, 8.0) -> (7, 9.5), slope=0.3/bar.
UPTREND_ROWS = [
    # (high,  low,  close)
    (11.0, 10.0, 10.5),   # 0
    (10.5,  9.0,  9.5),   # 1
    ( 9.5,  8.0,  9.0),   # 2  pivot low (8.0)
    (10.5,  9.0, 10.0),   # 3
    (11.5, 10.0, 11.0),   # 4
    (12.0, 11.0, 11.5),   # 5
    (11.5, 10.0, 11.0),   # 6
    (10.8,  9.5, 10.2),   # 7  pivot low (9.5)
    (11.5, 10.5, 11.0),   # 8
    (12.5, 11.5, 12.0),   # 9  pivot idx7 confirmed here
    (13.0, 12.0, 12.5),   # 10
    (13.0, 12.0, 12.2),   # 11
    (12.5, 11.8, 12.0),   # 12  line value = 8 + 0.3*10 = 11.0; close 12.0 above
]


def test_value_at_interpolates_and_extrapolates():
    tl = Trendline(kind="support", idx1=2, price1=8.0, idx2=7, price2=9.5)
    assert tl.slope == pytest.approx(0.3)
    assert tl.value_at(7) == pytest.approx(9.5)
    assert tl.value_at(12) == pytest.approx(11.0)


def test_fit_support_line_on_rising_lows():
    bars = make_bars(UPTREND_ROWS)
    tl = fit_trendline(bars, up_to_idx=12, kind="support", pivot_n=2)
    assert tl is not None
    assert (tl.idx1, tl.price1) == (2, 8.0)
    assert (tl.idx2, tl.price2) == (7, 9.5)


def test_fit_requires_confirmed_pivots():
    bars = make_bars(UPTREND_ROWS)
    # At up_to_idx=8 the idx7 pivot is NOT yet confirmed (needs idx 9).
    tl = fit_trendline(bars, up_to_idx=8, kind="support", pivot_n=2)
    assert tl is None or tl.idx2 != 7


def test_fit_returns_none_when_lows_not_rising():
    rows = [(r[0], r[1], r[2]) for r in UPTREND_ROWS]
    # Make second pivot LOWER than first (9.5 -> 7.0): not a rising support.
    rows[7] = (10.8, 7.0, 10.2)
    bars = make_bars(rows)
    tl = fit_trendline(bars, up_to_idx=12, kind="support", pivot_n=2)
    assert tl is None


def test_fit_resistance_line_on_falling_highs():
    # Mirror image: falling pivot highs at idx2 (12.0) and idx7 (10.5).
    rows = [
        ( 9.0,  8.0,  8.5),   # 0
        (10.5,  9.5, 10.0),   # 1
        (12.0, 10.5, 11.0),   # 2  pivot high (12.0)
        (10.5,  9.0,  9.5),   # 3
        ( 9.5,  8.0,  8.5),   # 4
        ( 9.0,  7.5,  8.0),   # 5
        ( 9.5,  8.0,  9.0),   # 6
        (10.5,  9.0,  9.8),   # 7  pivot high (10.5)
        ( 9.5,  8.0,  8.5),   # 8
        ( 8.5,  7.0,  7.5),   # 9
        ( 8.0,  6.5,  7.0),   # 10
    ]
    bars = make_bars(rows)
    tl = fit_trendline(bars, up_to_idx=10, kind="resistance", pivot_n=2)
    assert tl is not None
    assert (tl.idx1, tl.price1) == (2, 12.0)
    assert (tl.idx2, tl.price2) == (7, 10.5)
    assert tl.slope == pytest.approx(-0.3)


def test_causality_prefix_invariance():
    """Fitting at up_to_idx=k must not change when future bars are appended."""
    bars = make_bars(UPTREND_ROWS)
    full = fit_trendline(bars, up_to_idx=10, kind="support", pivot_n=2)
    prefix = fit_trendline(bars.iloc[:11].reset_index(drop=True), up_to_idx=10,
                           kind="support", pivot_n=2)
    assert (full is None) == (prefix is None)
    if full is not None:
        assert (full.idx1, full.price1, full.idx2, full.price2) == \
               (prefix.idx1, prefix.price1, prefix.idx2, prefix.price2)
