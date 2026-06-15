"""Unit tests for the ADVISORY signal-bar quality gate in scripts/score_today.py
(_signal_bar_quality). Binary double-strong conjunction, direction-aware, advisory only
(does NOT affect position_size). Guards geometry + orientation + degenerate bars."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

score_today = importlib.import_module("scripts.score_today")
_signal_bar_quality = score_today._signal_bar_quality


def test_double_strong_long_close_near_high():
    # big body, close at the high → double-strong for a bottom/long-like signal
    q = _signal_bar_quality(o=10.0, h=20.0, low=10.0, c=20.0, direction="bottom")
    assert q["body_frac"] == 1.0 and q["close_pos"] == 1.0
    assert q["double_strong"] is True


def test_long_strong_body_but_weak_close_is_not_double_strong():
    # body large but close mid-range (close_pos ~0.5 < 0.66) → single-strong only → False
    q = _signal_bar_quality(o=10.0, h=20.0, low=10.0, c=15.0, direction="bottom")
    assert q["body_frac"] == 0.5 and q["close_pos"] == 0.5
    assert q["double_strong"] is False


def test_close_pos_orientation_flips_for_short():
    # close near the LOW: weak for long (bottom), strong for short (top)
    o, h, low, c = 20.0, 20.0, 10.0, 10.0   # body full, close at low
    long_q = _signal_bar_quality(o, h, low, c, direction="bottom")
    short_q = _signal_bar_quality(o, h, low, c, direction="top")
    assert long_q["double_strong"] is False     # close at low is wrong way for long
    assert short_q["double_strong"] is True      # close at low is strong for short


def test_zero_range_bar_is_not_strong():
    q = _signal_bar_quality(o=15.0, h=15.0, low=15.0, c=15.0, direction="bottom")
    assert q["double_strong"] is False
    assert q["body_frac"] is None and q["close_pos"] is None
