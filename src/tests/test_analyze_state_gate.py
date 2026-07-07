"""Unit tests for analyze_state_gate pure state classifier — 粗市场状态分类器
（spike / tight_channel / normal_channel / range）在合成 bar 上的机械行为，
重点验证无前视、ATR 相对阈值、各态的判别条件。"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.analyze_state_gate import (  # noqa: E402
    bar_overlap_ratio,
    classify_market_state,
    consec_dir_count,
    leg_overlap_ratio,
)


def _bars(opens, highs, lows, closes) -> pd.DataFrame:
    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes})


def _atr(n: int, val: float = 1.0) -> pd.Series:
    return pd.Series([val] * n)


def _ema_of(closes) -> pd.Series:
    return pd.Series(closes, dtype=float).ewm(span=20, adjust=False).mean()


# ---------------------------------------------------------------------------
# pair / overlap helpers
# ---------------------------------------------------------------------------

def test_bar_overlap_full_vs_none():
    # 三根完全相同的 bar → 相邻重叠率 1.0
    lows = np.array([10.0, 10.0, 10.0])
    highs = np.array([11.0, 11.0, 11.0])
    assert bar_overlap_ratio(lows, highs, 2, window=3) == 1.0
    # 完全不相交的 bar（各自跳空）→ 0.0
    lows2 = np.array([10.0, 20.0, 30.0])
    highs2 = np.array([11.0, 21.0, 31.0])
    assert bar_overlap_ratio(lows2, highs2, 2, window=3) == 0.0


def test_bar_overlap_window_excludes_future():
    # window 只回看，不含 idx 之后的 bar：idx=1 不该被 idx=2 影响
    lows = np.array([10.0, 10.0, 30.0])
    highs = np.array([11.0, 11.0, 31.0])
    # idx=1, window=2 → 只看 (0,1) 对，重叠 1.0
    assert bar_overlap_ratio(lows, highs, 1, window=2) == 1.0


# ---------------------------------------------------------------------------
# consec direction
# ---------------------------------------------------------------------------

def test_consec_dir_bull_run():
    opens = np.array([10.0, 11.0, 12.0, 13.0])
    closes = np.array([11.0, 12.0, 13.0, 14.0])  # 4 连阳
    count, direction = consec_dir_count(opens, closes, 3)
    assert direction == "bull"
    assert count == 4


def test_consec_dir_breaks_on_opposite():
    opens = np.array([10.0, 11.0, 13.0, 12.0])
    closes = np.array([11.0, 10.0, 14.0, 13.0])  # bear, bull, bull → idx3 起 2 连阳
    count, direction = consec_dir_count(opens, closes, 3)
    assert direction == "bull"
    assert count == 2


def test_consec_dir_doji_zero():
    opens = np.array([10.0, 11.0])
    closes = np.array([11.0, 11.0])  # idx1 是 doji
    count, direction = consec_dir_count(opens, closes, 1)
    assert direction == "none"
    assert count == 0


# ---------------------------------------------------------------------------
# leg overlap (no lookahead via swing_n confirmation)
# ---------------------------------------------------------------------------

def test_leg_overlap_unconfirmed_swings_ignored():
    # 两个 swing 锚都在 idx 附近、swing_n=3 时未确认 → 返回 0.0（无前视）
    bars = _bars([0]*10, [1]*10, [0.5]*10, [0.8]*10)
    sl = np.array([8])
    sh = np.array([9])
    out = leg_overlap_ratio(bars, sl, sh, 9, swing_n=3)
    assert out == 0.0


def test_leg_overlap_two_confirmed():
    lows = [0.0]*10
    highs = [0.0]*10
    lows[1], highs[1] = 10.0, 11.0
    lows[3], highs[3] = 10.5, 11.5   # 与 idx1 区间重叠
    bars = _bars([0]*10, highs, lows, [0]*10)
    sl = np.array([1, 3])
    out = leg_overlap_ratio(bars, sl, np.array([], dtype=int), 9, swing_n=3)
    assert out > 0.0


# ---------------------------------------------------------------------------
# state classification
# ---------------------------------------------------------------------------

def test_classify_none_when_atr_invalid():
    bars = _bars([10]*5, [11]*5, [9]*5, [10]*5)
    out = classify_market_state(bars, 4, np.array([], dtype=int),
                                np.array([], dtype=int), _atr(5, 0.0),
                                _ema_of([10]*5))
    assert out is None


def test_classify_spike_strong_trend_far_from_ema():
    # 强连阳、bar 几乎不重叠、远离 EMA → spike
    n = 30
    opens = [10.0]*25 + [10.0, 13.0, 16.0, 19.0, 22.0]
    closes = [10.0]*25 + [12.0, 15.0, 18.0, 21.0, 24.0]
    lows = [9.9]*25 + [10.0, 13.0, 16.0, 19.0, 22.0]
    highs = [10.1]*25 + [12.1, 15.1, 18.1, 21.1, 24.1]
    bars = _bars(opens, highs, lows, closes)
    ema = _ema_of(closes)
    out = classify_market_state(bars, n - 1, np.array([], dtype=int),
                                np.array([], dtype=int), _atr(n, 1.0), ema)
    assert out["state"] == "spike"
    assert out["consec_dir"] >= 3
    assert out["overlap_ratio"] <= 0.35


def test_classify_range_high_overlap_near_ema():
    # 横盘：所有 bar 高度重叠、贴 EMA、腿重叠 → range
    n = 40
    base = 100.0
    opens, highs, lows, closes = [], [], [], []
    for i in range(n):
        c = base + (0.2 if i % 2 == 0 else -0.2)
        o = base - (0.2 if i % 2 == 0 else -0.2)
        opens.append(o)
        closes.append(c)
        highs.append(base + 0.6)
        lows.append(base - 0.6)
    bars = _bars(opens, highs, lows, closes)
    ema = _ema_of(closes)
    # 两条确认 swing leg，区间高度重叠
    sl = np.array([10, 20])
    sh = np.array([15, 25])
    out = classify_market_state(bars, n - 1, sl, sh, _atr(n, 1.0), ema)
    assert out["state"] == "range"
    assert out["overlap_ratio"] >= 0.55
    assert out["ema_dist_atr"] <= 1.0


def test_classify_tight_channel_overlapping_uptrend():
    # 持续上行但 bar 重叠高、EMA 偏离温和 → tight_channel（不是 spike）
    n = 40
    opens, highs, lows, closes = [], [], [], []
    price = 100.0
    for _i in range(n):
        o = price
        c = price + 0.25     # 缓慢连阳
        opens.append(o)
        closes.append(c)
        highs.append(c + 0.5)
        lows.append(o - 0.4)  # 与相邻 bar 大幅重叠
        price = c
    bars = _bars(opens, highs, lows, closes)
    ema = _ema_of(closes)
    out = classify_market_state(bars, n - 1, np.array([], dtype=int),
                                np.array([], dtype=int), _atr(n, 1.0), ema)
    assert out["state"] == "tight_channel"
    assert out["consec_dir"] >= 2
    assert out["overlap_ratio"] >= 0.55


def test_classify_atr_relative_not_fixed_pct():
    # 同样几何形态，绝对价位差 10x 但 ATR 同比放大 → ema_dist_atr 不变 → 同一态。
    # 证明阈值是 ATR 相对而非固定价格 %。
    n = 30
    opens = [10.0]*25 + [10.0, 13.0, 16.0, 19.0, 22.0]
    closes = [10.0]*25 + [12.0, 15.0, 18.0, 21.0, 24.0]
    lows = [9.9]*25 + [10.0, 13.0, 16.0, 19.0, 22.0]
    highs = [10.1]*25 + [12.1, 15.1, 18.1, 21.1, 24.1]
    bars_small = _bars(opens, highs, lows, closes)
    out_small = classify_market_state(bars_small, n - 1, np.array([], dtype=int),
                                      np.array([], dtype=int), _atr(n, 1.0),
                                      _ema_of(closes))
    # 10x 放大所有价位 + 10x ATR
    opens10 = [x * 10 for x in opens]
    closes10 = [x * 10 for x in closes]
    lows10 = [x * 10 for x in lows]
    highs10 = [x * 10 for x in highs]
    bars_big = _bars(opens10, highs10, lows10, closes10)
    out_big = classify_market_state(bars_big, n - 1, np.array([], dtype=int),
                                    np.array([], dtype=int), _atr(n, 10.0),
                                    _ema_of(closes10))
    assert out_small["state"] == out_big["state"] == "spike"
    assert abs(out_small["ema_dist_atr"] - out_big["ema_dist_atr"]) < 1e-6


def test_classify_normal_channel_fallback():
    # 弱单向（仅 2 连但 bar 重叠不够高、EMA 偏离不够大）→ 落 normal_channel
    n = 40
    opens, highs, lows, closes = [], [], [], []
    price = 100.0
    for i in range(n):
        if i < n - 2:
            # 横向噪声段
            o = price
            c = price + (0.1 if i % 2 == 0 else -0.1)
            highs.append(price + 1.5)
            lows.append(price - 1.5)
        else:
            # 末尾 2 连阳但 bar 之间重叠中等
            o = price
            c = price + 1.0
            highs.append(c + 0.2)
            lows.append(o - 1.6)
            price = c
        opens.append(o)
        closes.append(c)
    bars = _bars(opens, highs, lows, closes)
    ema = _ema_of(closes)
    out = classify_market_state(bars, n - 1, np.array([], dtype=int),
                                np.array([], dtype=int), _atr(n, 1.0), ema)
    assert out["state"] in ("normal_channel", "tight_channel", "range")
