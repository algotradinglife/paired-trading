"""Unit tests for analyze_second_entry.classify_test_ordinal — 测试序数分类器
（当前测试=信号 bar 低 / 无前视计数已确认前低 / ATR 容差 / 中间反弹）。"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.analyze_second_entry import classify_test_ordinal  # noqa: E402


def _bars(lows: list[float], highs: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"low": lows, "high": highs})


def _atr(n: int, val: float = 1.0) -> pd.Series:
    return pd.Series([val] * n)


def test_returns_none_when_atr_invalid():
    bars = _bars([100] * 5, [101] * 5)
    out = classify_test_ordinal(bars, 3, np.array([]), _atr(5, 0.0))
    assert out is None


def test_first_test_when_no_prior_same_level():
    # 信号低 100.5，唯一前低 90（差 10.5 > 1.0×ATR）→ 非同位 → ordinal 1
    lows = [0, 0, 90.0, 0, 0, 0, 0, 0, 100.5]
    highs = [0, 0, 91, 102.5, 0, 0, 0, 0, 101]
    bars = _bars(lows, highs)
    out = classify_test_ordinal(bars, 8, np.array([2]), _atr(9),
                                swing_n=1, tol_atr=1.0, bounce_atr=1.5)
    assert out["ordinal"] == 1
    assert out["ref_low_idx"] == 8          # 锚在信号 bar 自身
    assert out["ref_low"] == 100.5
    assert out["n_prior_same_level"] == 0


def test_second_test_signal_low_retests_prior_with_bounce():
    # 信号低 100.5 回踩前低 100（差 0.5<=1.0），中间反弹 102.5-100.5=2.0>=1.5 → ordinal 2
    # 关键：前低当根(idx2)确认(2+1<=8)，信号低(idx8)无需被确认为 swing
    lows = [0, 0, 100.0, 0, 0, 0, 0, 0, 100.5]
    highs = [0, 0, 100, 102.5, 0, 0, 0, 0, 101]
    bars = _bars(lows, highs)
    out = classify_test_ordinal(bars, 8, np.array([2]), _atr(9),
                                swing_n=1, tol_atr=1.0, bounce_atr=1.5)
    assert out["ordinal"] == 2
    assert out["n_prior_same_level"] == 1


def test_no_bounce_not_counted():
    # 前低同位但中间无足够反弹（峰 100.8，bounce 0.3<1.5）→ 不计 → ordinal 1
    lows = [0, 0, 100.0, 0, 0, 0, 0, 0, 100.5]
    highs = [0, 0, 100, 100.8, 0, 0, 0, 0, 101]
    bars = _bars(lows, highs)
    out = classify_test_ordinal(bars, 8, np.array([2]), _atr(9),
                                swing_n=1, tol_atr=1.0, bounce_atr=1.5)
    assert out["ordinal"] == 1


def test_signal_bar_high_excluded_from_bounce():
    # 前低同位，但唯一的"反弹"来自信号 bar 自身的大高点（outside/反转当根）；
    # 两低之间无真实中间反弹 → 不计 → ordinal 1（codex P2 端点排除）
    lows = [0, 0, 100.0, 0, 0, 0, 0, 0, 100.5]
    highs = [0, 0, 100, 100.3, 100.3, 100.3, 100.3, 100.3, 108.0]  # 高点全在信号 bar
    bars = _bars(lows, highs)
    out = classify_test_ordinal(bars, 8, np.array([2]), _atr(9),
                                swing_n=1, tol_atr=1.0, bounce_atr=1.5)
    assert out["ordinal"] == 1


def test_no_lookahead_excludes_unconfirmed_prior():
    # 前低在 idx 7，但 signal_idx=8 当下未确认(7+3=10>8) → 不计入 → ordinal 1
    lows = [0] * 7 + [100.0, 100.5]
    highs = [0, 0, 0, 102.5, 0, 0, 0, 100, 101]
    bars = _bars(lows, highs)
    out = classify_test_ordinal(bars, 8, np.array([7]), _atr(9),
                                swing_n=3, tol_atr=1.0, bounce_atr=1.5)
    assert out["ordinal"] == 1   # idx7 未确认，不算前测

def test_lookback_window_excludes_far_prior():
    # 同位前低 + 反弹，但距信号 > lookback → 不计
    lows = [100.0] + [0] * 70 + [0, 100.5]
    highs = [100] + [0] * 70 + [0, 101]
    highs[40] = 103.0
    bars = _bars(lows, highs)
    out = classify_test_ordinal(bars, 72, np.array([0]), _atr(73),
                                swing_n=1, tol_atr=1.0, bounce_atr=1.5,
                                lookback=60)
    assert out["ordinal"] == 1
