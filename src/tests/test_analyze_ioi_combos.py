"""Unit tests for analyze_ioi_combos pure pattern detectors (inside / outside /
ioi) on synthetic bars — positive + negative cases, no-lookahead."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.analyze_ioi_combos import (  # noqa: E402
    flag_patterns,
    is_inside_bar,
    is_ioi,
    is_outside_bar,
)


def _hl(highs: list[float], lows: list[float]):
    return np.asarray(highs, dtype=float), np.asarray(lows, dtype=float)


# --- inside bar -----------------------------------------------------------

def test_inside_positive():
    # bar1 strictly inside bar0
    high, low = _hl([10, 9], [0, 1])
    assert is_inside_bar(high, low, 1) is True


def test_inside_equal_bounds_counts():
    # high==prev_high and low==prev_low qualifies (<= / >=)
    high, low = _hl([10, 10], [0, 0])
    assert is_inside_bar(high, low, 1) is True


def test_inside_negative_higher_high():
    high, low = _hl([10, 11], [0, 1])
    assert is_inside_bar(high, low, 1) is False


def test_inside_negative_lower_low():
    high, low = _hl([10, 9], [0, -1])
    assert is_inside_bar(high, low, 1) is False


def test_inside_first_bar_is_false():
    # t=0 has no predecessor → cannot be inside (no lookahead, no wrap)
    high, low = _hl([10, 9], [0, 1])
    assert is_inside_bar(high, low, 0) is False


# --- outside bar ----------------------------------------------------------

def test_outside_positive():
    high, low = _hl([9, 10], [1, 0])
    assert is_outside_bar(high, low, 1) is True


def test_outside_equal_bounds_counts():
    high, low = _hl([10, 10], [0, 0])
    assert is_outside_bar(high, low, 1) is True


def test_outside_negative_inside():
    high, low = _hl([10, 9], [0, 1])
    assert is_outside_bar(high, low, 1) is False


def test_outside_negative_one_sided():
    # higher high but also higher low → not engulfing
    high, low = _hl([10, 11], [0, 1])
    assert is_outside_bar(high, low, 1) is False


def test_outside_first_bar_is_false():
    high, low = _hl([9, 10], [1, 0])
    assert is_outside_bar(high, low, 0) is False


# --- ioi (inside -> outside -> inside) ------------------------------------

def test_ioi_positive():
    # idx: 0 base, 1 inside, 2 outside, 3 inside  → ioi confirms at t=3
    #   bar0: H=20 L=0  (base)
    #   bar1: H=18 L=2  inside of bar0
    #   bar2: H=21 L=1  outside of bar1 (H>=18, L<=2)
    #   bar3: H=20 L=2  inside of bar2 (H<=21, L>=1)
    high, low = _hl([20, 18, 21, 20], [0, 2, 1, 2])
    assert is_inside_bar(high, low, 1) is True
    assert is_outside_bar(high, low, 2) is True
    assert is_inside_bar(high, low, 3) is True
    assert is_ioi(high, low, 3) is True


def test_ioi_negative_middle_not_outside():
    # middle bar (t-1) is inside, not outside → not ioi
    high, low = _hl([20, 18, 17, 16], [0, 2, 3, 4])
    assert is_ioi(high, low, 3) is False


def test_ioi_negative_last_not_inside():
    # last bar breaks out (higher high) → not inside → not ioi
    high, low = _hl([20, 18, 21, 22], [0, 2, 1, 2])
    assert is_outside_bar(high, low, 2) is True
    assert is_inside_bar(high, low, 3) is False
    assert is_ioi(high, low, 3) is False


def test_ioi_no_lookahead_left_edge():
    # t<3 can never be ioi regardless of values (needs t-2,t-1,t + predecessor)
    high, low = _hl([20, 18, 21], [0, 2, 1])
    assert is_ioi(high, low, 0) is False
    assert is_ioi(high, low, 1) is False
    assert is_ioi(high, low, 2) is False


def test_ioi_does_not_use_future_bars():
    # appending future bars must not change the t=3 verdict (no lookahead)
    base_h, base_l = [20, 18, 21, 20], [0, 2, 1, 2]
    h1, l1 = _hl(base_h, base_l)
    h2, l2 = _hl(base_h + [99, -99], base_l + [99, -99])
    assert is_ioi(h1, l1, 3) == is_ioi(h2, l2, 3) is True


# --- flag_patterns vectorised wrapper -------------------------------------

def test_flag_patterns_matches_scalar():
    highs = [20, 18, 21, 20, 25, 24]
    lows = [0, 2, 1, 2, -5, -4]
    bars = pd.DataFrame({"high": highs, "low": lows})
    flags = flag_patterns(bars)
    h, lo = _hl(highs, lows)
    for t in range(len(bars)):
        assert flags["inside"][t] == is_inside_bar(h, lo, t)
        assert flags["outside"][t] == is_outside_bar(h, lo, t)
        assert flags["ioi"][t] == is_ioi(h, lo, t)
    # spot-check known ioi at t=3
    assert flags["ioi"][3]


def test_flag_patterns_length_and_left_edge_zero():
    bars = pd.DataFrame({"high": [1, 2, 3], "low": [0, -1, -2]})
    flags = flag_patterns(bars)
    assert len(flags["inside"]) == 3
    # first bar never flags
    assert not flags["inside"][0]
    assert not flags["outside"][0]
    assert not flags["ioi"][0]
