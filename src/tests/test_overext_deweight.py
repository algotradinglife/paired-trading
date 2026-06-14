"""Unit tests for engine.divergence.overext_deweight — bottom-side de-weight factor."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.divergence.overext_deweight import (  # noqa: E402
    W_MIN,
    deweight_factor,
    w_a,
    w_b,
)


def test_w_a_full_weight_at_or_below_cut():
    assert w_a(0.4) == 1.0
    assert w_a(1.0) == 1.0


def test_w_a_linear_decay_above_cut():
    # rva=1.5 → (1.0-1.5)/1.0 + 1 = 0.5
    assert abs(w_a(1.5) - 0.5) < 1e-9
    # rva=1.25 → 0.75
    assert abs(w_a(1.25) - 0.75) < 1e-9


def test_w_a_floored_at_w_min():
    assert w_a(2.0) == W_MIN          # would be 0.0 → floored
    assert w_a(10.0) == W_MIN
    assert w_a(float("inf")) == W_MIN
    assert w_a(float("nan")) == W_MIN
    assert w_a(None) == W_MIN


def test_w_b_first_vs_retest():
    assert w_b(1) == 1.0
    assert w_b(2) < 1.0
    assert w_b(3) == w_b(2)           # all retests share the retest weight
    assert w_b(None) == w_b(2)        # unknown ordinal treated as retest


def test_deweight_only_bottom_applicable_lanes():
    # top side: never de-weighted regardless of features
    assert deweight_factor("top", "opposing", 3.0, 5) == 1.0
    assert deweight_factor("top", "supporting", 3.0, 5) == 1.0
    # bottom but supporting: not a validated lane → no change
    assert deweight_factor("bottom", "supporting", 3.0, 5) == 1.0
    # bottom × opposing / neutral: applies
    assert deweight_factor("bottom", "opposing", 0.5, 1) == 1.0      # clean first test
    assert deweight_factor("bottom", "neutral", 0.5, 1) == 1.0


def test_deweight_multiplicative_combination():
    # bottom×opposing, over-extended (rva=1.5 → w_a=0.5) retest (w_b<1) → product
    f = deweight_factor("bottom", "opposing", 1.5, 2)
    assert abs(f - (w_a(1.5) * w_b(2))) < 1e-9
    assert f < w_a(1.5)              # retest penalty compounds the over-extension penalty
    assert f >= W_MIN * W_MIN


def test_deweight_never_exceeds_one():
    # factor is a de-weight: bounded above by 1.0 across the grid
    for rva in (0.1, 0.9, 1.0, 1.2, 2.0, 5.0):
        for ordn in (1, 2, 3):
            assert deweight_factor("bottom", "opposing", rva, ordn) <= 1.0
