"""Tests for TBreakDetector — trendline-break alert detector."""
from __future__ import annotations

import pytest

from engine.divergence.tbreak_detector import TBreakDetector
from test_trendline import make_bars, UPTREND_ROWS


def breakdown_rows() -> list[tuple[float, float, float]]:
    """UPTREND_ROWS + a clean close below the support line at idx 13.

    Line (2,8.0)->(7,9.5) has value 8 + 0.3*11 = 11.3 at idx 13.
    Close 9.0 is far below value - buffer for any sane ATR buffer.
    """
    return UPTREND_ROWS + [(11.0, 8.8, 9.0)]   # idx 13


def test_emits_breakdown_below_support():
    det = TBreakDetector(pivot_n=2, buffer_atr=0.1, confirm_bars=1, min_gap=5)
    sigs = det.scan(make_bars(breakdown_rows()))
    breakdowns = [s for s in sigs if s.direction == "breakdown"]
    assert len(breakdowns) == 1
    assert breakdowns[0].bar_idx == 13
    f = breakdowns[0].features
    assert f["kind"] == "support"
    assert f["anchor_idx1"] == 2 and f["anchor_idx2"] == 7
    assert f["line_value"] == pytest.approx(11.3)


def test_no_signal_when_close_stays_above_line():
    det = TBreakDetector(pivot_n=2, buffer_atr=0.1, confirm_bars=1, min_gap=5)
    sigs = det.scan(make_bars(UPTREND_ROWS))
    assert [s for s in sigs if s.direction == "breakdown"] == []


def test_buffer_blocks_marginal_break():
    """A close a hair below the line must NOT fire (within ATR buffer)."""
    rows = UPTREND_ROWS + [(12.0, 11.0, 11.25)]  # idx13, line=11.3, gap=0.05
    det = TBreakDetector(pivot_n=2, buffer_atr=10.0,  # huge buffer
                         confirm_bars=1, min_gap=5)
    sigs = det.scan(make_bars(rows))
    assert [s for s in sigs if s.direction == "breakdown"] == []


def test_same_line_fires_once():
    """Bars keep closing below the same line — only one signal per anchor pair."""
    rows = breakdown_rows() + [(10.0, 8.5, 8.8), (9.5, 8.0, 8.5)]  # idx 14, 15
    det = TBreakDetector(pivot_n=2, buffer_atr=0.1, confirm_bars=1, min_gap=1)
    sigs = det.scan(make_bars(rows))
    assert len([s for s in sigs if s.direction == "breakdown"]) == 1


def test_confirm_bars_2_cancels_on_reclaim():
    """confirm_bars=2: candidate at idx13, reclaim above line at idx14 -> no signal."""
    rows = breakdown_rows() + [(13.0, 11.5, 12.5)]  # idx14 closes back above
    det = TBreakDetector(pivot_n=2, buffer_atr=0.1, confirm_bars=2, min_gap=5)
    sigs = det.scan(make_bars(rows))
    assert [s for s in sigs if s.direction == "breakdown"] == []


def test_confirm_bars_2_fires_on_followthrough():
    rows = breakdown_rows() + [(9.5, 8.2, 8.6)]  # idx14 stays below
    det = TBreakDetector(pivot_n=2, buffer_atr=0.1, confirm_bars=2, min_gap=5)
    sigs = det.scan(make_bars(rows))
    breakdowns = [s for s in sigs if s.direction == "breakdown"]
    assert len(breakdowns) == 1
    assert breakdowns[0].bar_idx == 14


def test_causality_prefix_invariance():
    rows = breakdown_rows() + [(10.0, 8.5, 8.8), (9.5, 8.0, 8.5)]
    det = TBreakDetector(pivot_n=2, buffer_atr=0.1, confirm_bars=1, min_gap=5)
    full = det.scan(make_bars(rows))
    prefix = det.scan(make_bars(rows[:14]))
    full_upto = [(s.bar_idx, s.direction) for s in full if s.bar_idx <= 13]
    pref = [(s.bar_idx, s.direction) for s in prefix]
    assert full_upto == pref


def test_policy_weight_always_zero():
    det = TBreakDetector(pivot_n=2)
    sigs = det.scan(make_bars(breakdown_rows()))
    assert sigs and TBreakDetector.policy_weight(sigs[0], "cn_futures", "kq_m_shfe_rb") == 0.0
