# tests/test_swing_context.py
import numpy as np
import pandas as pd
import pytest
from engine.features.swing_context import classify_trend_structure, detect_swing_points
from engine.features.swing_context import count_legs_down
from engine.features.swing_context import market_regime_label
from engine.features.swing_context import compute_swing_context


def _zigzag_bars(highs, lows):
    """Build minimal bars DataFrame from high/low lists."""
    n = len(highs)
    return pd.DataFrame({
        "high":  highs,
        "low":   lows,
        "open":  [(h + l) / 2 for h, l in zip(highs, lows)],
        "close": [(h + l) / 2 for h, l in zip(highs, lows)],
    })


class TestDetectSwingPoints:
    def test_uptrend_zigzag_n1(self):
        bars = _zigzag_bars(
            highs=[11, 9, 13, 11, 15, 13, 17, 15, 19, 17],
            lows= [ 9, 7, 11,  9, 13, 11, 15, 13, 17, 15],
        )
        sh_idx, sl_idx = detect_swing_points(bars, n=1)
        assert list(sh_idx) == [2, 4, 6, 8]
        assert list(sl_idx) == [1, 3, 5, 7]

    def test_monotone_downtrend_no_swings(self):
        bars = _zigzag_bars(
            highs=[19, 17, 15, 13, 11,  9,  7,  5,  3,  1],
            lows= [17, 15, 13, 11,  9,  7,  5,  3,  1,  0],
        )
        sh_idx, sl_idx = detect_swing_points(bars, n=1)
        assert len(sh_idx) == 0
        assert len(sl_idx) == 0

    def test_flat_double_top_not_swing(self):
        bars = _zigzag_bars(
            highs=[8, 10, 10, 8],
            lows= [6,  8,  8, 6],
        )
        sh_idx, sl_idx = detect_swing_points(bars, n=1)
        assert len(sh_idx) == 0  # tie → no strict local max

    def test_requires_n_bars_on_each_side(self):
        bars = _zigzag_bars(
            highs=[5, 3, 7, 3, 5, 3, 7, 3, 5],
            lows= [3, 1, 5, 1, 3, 1, 5, 1, 3],
        )
        sh_idx, sl_idx = detect_swing_points(bars, n=2)
        assert 2 in sh_idx
        assert 6 in sh_idx
        assert 0 not in sh_idx
        assert 8 not in sh_idx
        assert len(sl_idx) == 0  # ties at lows[3]=lows[5]=lows[1]=lows[7]=1 → no strict local min


class TestClassifyTrendStructure:
    def _uptrend_inputs(self):
        bars = _zigzag_bars(
            highs=[11, 9, 13, 11, 15, 13, 17, 15, 19, 17],
            lows= [ 9, 7, 11,  9, 13, 11, 15, 13, 17, 15],
        )
        sh, sl = detect_swing_points(bars, n=1)
        return bars, sh, sl

    def test_uptrend_returns_uptrend(self):
        bars, sh, sl = self._uptrend_inputs()
        result = classify_trend_structure(bars, as_of=9, sh_idx=sh, sl_idx=sl, n=1)
        assert result == "uptrend"

    def test_downtrend_returns_downtrend(self):
        bars = _zigzag_bars(
            highs=[17, 15, 13, 11,  9,  7,  5,  3,  1,  2],
            lows= [15, 13, 11,  9,  7,  5,  3,  1,  0,  0],
        )
        sh_idx = np.array([0, 2, 4, 6], dtype=np.int64)
        sl_idx = np.array([1, 3, 5, 7], dtype=np.int64)
        result = classify_trend_structure(bars, as_of=9, sh_idx=sh_idx, sl_idx=sl_idx, n=1)
        assert result == "downtrend"

    def test_mixed_returns_ranging(self):
        bars2 = _zigzag_bars(
            highs=[14, 8, 12, 9, 10, 7],
            lows= [12, 6, 10, 7,  8, 5],
        )
        sh_idx2 = np.array([0, 2], dtype=np.int64)   # highs: 14 → 12 → LH
        sl_idx2 = np.array([1, 3], dtype=np.int64)   # lows: 6 → 7 → HL
        result2 = classify_trend_structure(bars2, as_of=5, sh_idx=sh_idx2, sl_idx=sl_idx2, n=1)
        assert result2 == "ranging"

    def test_insufficient_data_returns_ranging(self):
        bars = _zigzag_bars([10, 8], [8, 6])
        sh_idx = np.array([0], dtype=np.int64)
        sl_idx = np.array([1], dtype=np.int64)
        result = classify_trend_structure(bars, as_of=1, sh_idx=sh_idx, sl_idx=sl_idx, n=1)
        assert result == "ranging"


class TestCountLegsDown:
    def test_zero_legs_no_swing_low_after_high(self):
        # sh at bar 4, no sl after bar 4 → 0 legs
        sh_idx = np.array([4], dtype=np.int64)
        sl_idx = np.array([1, 3], dtype=np.int64)  # all before last SH
        assert count_legs_down(as_of=6, sh_idx=sh_idx, sl_idx=sl_idx, n=1) == 0

    def test_one_leg(self):
        # sh at bar 2, sl at bar 5 → 1 leg down
        sh_idx = np.array([2], dtype=np.int64)
        sl_idx = np.array([5], dtype=np.int64)
        assert count_legs_down(as_of=7, sh_idx=sh_idx, sl_idx=sl_idx, n=1) == 1

    def test_two_legs_from_last_sh(self):
        # sh at [2, 7], sl at [5, 9]
        # last_sh = 7; sl after 7 = [9] → 1 leg from last SH
        sh_idx = np.array([2, 7], dtype=np.int64)
        sl_idx = np.array([5, 9], dtype=np.int64)
        assert count_legs_down(as_of=11, sh_idx=sh_idx, sl_idx=sl_idx, n=1) == 1

    def test_two_legs_from_dominant(self):
        # dominant high is bar 2 (highest); sl after bar 2 = [5, 9] → 2 legs
        highs = [0] * 12
        highs[2] = 100  # dominant high
        highs[7] = 50   # lower swing high
        lows = [50] * 12
        bars = pd.DataFrame({
            "high": highs, "low": lows,
            "open": lows, "close": lows,
        })
        sh_idx = np.array([2, 7], dtype=np.int64)
        sl_idx = np.array([5, 9], dtype=np.int64)
        assert count_legs_down(as_of=11, sh_idx=sh_idx, sl_idx=sl_idx,
                               n=1, from_dominant=True, bars=bars) == 2

    def test_no_swing_high_returns_zero(self):
        sh_idx = np.array([], dtype=np.int64)
        sl_idx = np.array([3, 6], dtype=np.int64)
        assert count_legs_down(as_of=8, sh_idx=sh_idx, sl_idx=sl_idx, n=1) == 0


def _make_bars_from_close(closes):
    c = pd.Series(closes, dtype=float)
    return pd.DataFrame({
        "high":  c * 1.005,
        "low":   c * 0.995,
        "open":  c.shift(1).fillna(c.iloc[0]),
        "close": c,
    })


class TestMarketRegimeLabel:
    def test_linear_uptrend_is_trending(self):
        closes = list(range(100, 160))   # 60 steadily rising bars
        bars = _make_bars_from_close(closes)
        regime = market_regime_label(bars, ema_period=20)
        assert regime.iloc[-1] == "trending"

    def test_oscillating_flat_is_ranging(self):
        closes = [100 + (1 if i % 2 == 0 else -1) for i in range(60)]
        bars = _make_bars_from_close(closes)
        regime = market_regime_label(bars, ema_period=20)
        assert regime.iloc[-1] == "ranging"

    def test_returns_series_aligned_to_index(self):
        closes = list(range(50))
        bars = _make_bars_from_close(closes)
        regime = market_regime_label(bars, ema_period=20)
        assert isinstance(regime, pd.Series)
        assert len(regime) == len(bars)
        assert (regime.index == bars.index).all()


class TestComputeSwingContext:
    def test_output_columns_present(self):
        bars = _zigzag_bars(
            highs=[11, 9, 13, 11, 15, 13, 17, 15, 19, 17] * 3,
            lows= [ 9, 7, 11,  9, 13, 11, 15, 13, 17, 15] * 3,
        )
        ctx = compute_swing_context(bars, swing_n=1)
        for col in ["trend_structure", "leg_count_down", "market_regime",
                    "bars_since_swing_low", "bars_since_swing_high"]:
            assert col in ctx.columns, f"missing column: {col}"

    def test_output_aligned_to_bars_index(self):
        bars = _zigzag_bars(
            highs=[11, 9, 13, 11, 15, 13, 17, 15, 19, 17] * 2,
            lows= [ 9, 7, 11,  9, 13, 11, 15, 13, 17, 15] * 2,
        )
        ctx = compute_swing_context(bars, swing_n=1)
        assert len(ctx) == len(bars)
        assert (ctx.index == bars.index).all()

    def test_uptrend_classified_correctly(self):
        highs = []
        lows = []
        base = 100
        for i in range(15):
            highs += [base + i * 2 + 1, base + i * 2 - 1]
            lows  += [base + i * 2 - 1, base + i * 2 - 3]
        bars = _zigzag_bars(highs[:30], lows[:30])
        ctx = compute_swing_context(bars, swing_n=1)
        last_structures = ctx["trend_structure"].iloc[-5:]
        assert (last_structures == "uptrend").any(), \
            f"Expected uptrend in last 5 bars, got: {last_structures.tolist()}"

    def test_leg_count_nonnegative_int(self):
        bars = _zigzag_bars(
            highs=[11, 9, 13, 11, 15, 13, 17, 15, 19, 17] * 2,
            lows= [ 9, 7, 11,  9, 13, 11, 15, 13, 17, 15] * 2,
        )
        ctx = compute_swing_context(bars, swing_n=1)
        assert (ctx["leg_count_down"] >= 0).all()
        assert ctx["leg_count_down"].dtype in [int, np.int64]
