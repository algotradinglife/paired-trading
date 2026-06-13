"""Unit tests for analyze_signalbar_quality.signal_bar_features — 信号棒几何特征
（无前视均长 / close_pos / body_pct / range_vs_avg / not_overext）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.analyze_signalbar_quality import (  # noqa: E402
    OVEREXT_MULT,
    signal_bar_features,
)


def _bars(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


def test_returns_none_before_range20():
    bars = _bars([(1, 2, 0, 1)] * 10)
    assert signal_bar_features(bars, 5) is None   # idx < RANGE20


def test_returns_none_on_degenerate_bar():
    # 21 根，信号 bar high==low（range 0）→ None
    rows = [(1, 2, 0, 1)] * 21
    rows[20] = (1.0, 1.0, 1.0, 1.0)
    assert signal_bar_features(_bars(rows), 20) is None


def test_close_pos_and_body_pct_formulas():
    # 信号 bar: o=10 c=14 h=15 l=10 → range5, body4, close_pos=(14-10)/5=0.8, body_pct=0.8
    rows = [(10, 11, 9, 10)] * 21
    rows[20] = (10.0, 15.0, 10.0, 14.0)
    f = signal_bar_features(_bars(rows), 20)
    assert abs(f["close_pos"] - 0.8) < 1e-9
    assert abs(f["body_pct"] - 0.8) < 1e-9
    assert abs(f["bar_quality_bull"] - 0.64) < 1e-9   # 0.8 * 0.8
    # wick_lo = (min(o,c)-l)/range = (10-10)/5 = 0
    assert abs(f["wick_lo"] - 0.0) < 1e-9


def test_range_vs_avg_excludes_signal_bar_no_lookahead():
    # 前 20 根 range=2（high-low），信号 bar range=6 → range_vs_avg=3.0 > 1.5 → 过度延伸
    rows = [(10.0, 11.0, 9.0, 10.0)] * 20      # range 2 each
    rows.append((10.0, 13.0, 7.0, 12.0))       # 信号 bar range 6
    f = signal_bar_features(_bars(rows), 20)
    assert abs(f["range_vs_avg"] - 3.0) < 1e-9
    assert f["not_overext"] == 0               # 3.0 > 1.5


def test_not_overext_true_when_within_15x():
    rows = [(10.0, 12.0, 8.0, 10.0)] * 20      # range 4 each
    rows.append((10.0, 14.0, 9.0, 13.0))       # 信号 bar range 5 → 5/4=1.25 <= 1.5
    f = signal_bar_features(_bars(rows), 20)
    assert f["range_vs_avg"] <= OVEREXT_MULT
    assert f["not_overext"] == 1
