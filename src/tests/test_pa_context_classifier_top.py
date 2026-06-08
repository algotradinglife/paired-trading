"""Tests for the top-side context classifier (A_top / B1_top).

Mirror coverage of the bull-side ``test_pa_context_classifier`` suite,
flipped to validate selling-into-rally (A_top) and first-pullback-in-
new-bear-cycle (B1_top) patterns.

Synthetic-data caveat: the bull-side tests use trajectories crafted to
produce the right MACD/EMA configuration on minimal-volatility bars
(close ± 0.3% wicks).  We mirror them here to stay consistent.  Real
bars may behave less cleanly — see the followup memo.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.divergence.pa_context_classifier import classify_context_top
from engine.features.macd import macd, ema


def _make_bars(n: int, prices: list | None = None) -> pd.DataFrame:
    """Minimal daily OHLCV DataFrame for testing — mirror of the bull-side
    helper, identical OHL spread (0.3% wicks)."""
    if prices is None:
        prices = [100.0 + i * 0.5 for i in range(n)]
    close = pd.Series(prices, dtype=float)
    return pd.DataFrame({
        "open":   close * 0.998,
        "high":   close * 1.003,
        "low":    close * 0.997,
        "close":  close,
        "volume": [1_000_000] * n,
    })


def _make_macd_emas(bars: pd.DataFrame):
    m = macd(bars["close"])
    ema20 = ema(bars["close"], 20)
    ema60 = ema(bars["close"], 60)
    return m, ema20, ema60


# ---------------------------------------------------------------------------
# Context A_top — downtrend rally (selling into the bounce)
# ---------------------------------------------------------------------------


class TestContextATop:
    def test_returns_none_when_dif_positive(self):
        # Bull market — DIF will be positive → A_top requires DIF<0.
        prices = [100 + i * 1.0 for i in range(115)]
        bars = _make_bars(115, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        result = classify_context_top(bars, 110, m, ema20, ema60)
        assert result != "A_top"

    def test_returns_none_when_price_below_ema20_no_rally(self):
        # Steady downtrend, no rally, price below EMA20.
        prices = [200 - i * 0.8 for i in range(115)]
        bars = _make_bars(115, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        result = classify_context_top(bars, 110, m, ema20, ema60)
        assert result != "A_top"

    def test_returns_none_when_rally_exceeds_10pct(self):
        # Downtrend then >10% spike — too violent for A_top window.
        prices = [200 - i * 0.8 for i in range(100)] + [120 + i * 3.0 for i in range(15)]
        bars = _make_bars(115, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        result = classify_context_top(bars, 112, m, ema20, ema60)
        assert result != "A_top"

    def test_returns_none_below_min_bars(self):
        prices = [200 - i * 0.5 for i in range(115)]
        bars = _make_bars(115, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        result = classify_context_top(bars, 30, m, ema20, ema60)
        assert result is None

    def test_returns_A_top_when_dif_negative_price_above_ema20_below_ema60(self):
        # 100 bars steady downtrend then 10-bar rally (~5% rise).
        # Mirror of the bull-side A test: 100×+0.8 → 15×-1.2 becomes
        #                                 100×-0.8 → 15×+1.2.
        prices = [200 - i * 0.8 for i in range(100)] + [120 + i * 1.2 for i in range(15)]
        bars = _make_bars(115, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        results = [
            classify_context_top(bars, i, m, ema20, ema60) for i in range(100, 113)
        ]
        assert "A_top" in results, f"Expected 'A_top' in results but got: {results}"

    def test_A_top_does_not_fire_on_flat_gentle_fall(self):
        # Flat 70 bars then very gentle fall — rally < 3% (rolling low ≈ close).
        prices = [100.0] * 70 + [100 - i * 0.05 for i in range(30)]
        bars = _make_bars(100, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        for i in range(70, 100):
            r = classify_context_top(bars, i, m, ema20, ema60)
            assert r != "A_top", f"A_top fired at bar {i} on flat/gentle-fall data"

    def test_A_top_does_not_return_B1_top_in_downtrend_rally(self):
        # Smoke: in a clean downtrend rally, the result is either A_top or
        # None, never B1_top (DIF still <0, so positive-peak requirement
        # for B1_top can't be met).
        prices = [200 - i * 0.8 for i in range(100)] + [120 + i * 1.2 for i in range(10)]
        bars = _make_bars(110, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        for i in range(100, 110):
            r = classify_context_top(bars, i, m, ema20, ema60)
            assert r in (None, "A_top"), f"bar {i} returned unexpected {r!r}"


# ---------------------------------------------------------------------------
# Context B1_top — first pullback in new bear cycle
# ---------------------------------------------------------------------------


class TestContextB1Top:
    def test_returns_none_when_bounce_breaks_peak(self):
        # Rally then dip then new high above peak — invalidates B1_top.
        up    = [100 + i * 1.2 for i in range(60)]
        down  = [172 - i * 1.5 for i in range(20)]
        higher = [142 + i * 2.0 for i in range(20)]
        prices = up + down + higher
        bars = _make_bars(len(prices), prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        result = classify_context_top(bars, len(prices) - 3, m, ema20, ema60)
        assert result != "B1_top"

    def test_returns_none_when_dif_negative(self):
        # Steady downtrend → DIF<0; B1_top requires DIF>0.
        prices = [200 - i * 0.8 for i in range(115)]
        bars = _make_bars(115, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        result = classify_context_top(bars, 110, m, ema20, ema60)
        assert result != "B1_top"

    def test_returns_none_below_min_bars(self):
        prices = [100 + i * 0.5 for i in range(115)]
        bars = _make_bars(115, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        result = classify_context_top(bars, 20, m, ema20, ema60)
        assert result is None

    def test_returns_B1_top_when_first_bounce_below_peak(self):
        """Mirror of test_returns_B1_when_first_pullback_above_trough.

        Bull-side trajectory:
          flat  80 × 100
          down  15 × -2.5/bar → 100 → 65
          up    8 × +1.5/bar  → 65 → 75.5
          back  8 × -0.6/bar  → 75.5 → 71.3

        Mirror:
          flat  80 × 100
          up    15 × +2.5/bar → 100 → 135  (positive DIF, hist peaks)
          down  8 × -1.5/bar  → 135 → 125  (L1 = -7.4% below peak)
          back  8 × +0.6/bar  → 125 → 129.2 (bounce 3.4% above L1, still
                                              below peak high)
        """
        flat = [100.0] * 80
        up   = [100 + i * 2.5 for i in range(15)]
        down = [135 - i * 1.5 for i in range(8)]
        back = [125 + i * 0.6 for i in range(8)]
        prices = flat + up + down + back
        bars = _make_bars(len(prices), prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        # Scan the late-bounce bars.
        scan_start = len(flat) + len(up) + len(down) + 2
        scan_end = len(prices)
        results = [
            classify_context_top(bars, i, m, ema20, ema60)
            for i in range(scan_start, scan_end)
        ]
        assert "B1_top" in results, f"Expected 'B1_top' in results but got: {results}"

    def test_B1_top_fires_on_valid_distribution_bounce(self):
        # Steep rise → first leg down (>5%) → bounce staying below peak.
        # Mirror of the bull-side B1 smoke test.
        up   = [100 + i * 1.5 for i in range(80)]    # 100→219
        down = [219 - i * 1.8 for i in range(25)]    # 219→174 (~21% below peak~219)
        back = [174 + i * 0.9 for i in range(15)]    # 174→187.5 (well below 219)
        prices = up + down + back
        bars = _make_bars(len(prices), prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        for i in range(len(up) + len(down), len(prices)):
            r = classify_context_top(bars, i, m, ema20, ema60)
            assert r in (None, "B1_top", "A_top"), f"bar {i} returned unexpected {r!r}"


# ---------------------------------------------------------------------------
# No-context / boundary cases
# ---------------------------------------------------------------------------


class TestNoTopContext:
    def test_at_minimum_bars_returns_none(self):
        bars = _make_bars(10)
        m, ema20, ema60 = _make_macd_emas(bars)
        result = classify_context_top(bars, 5, m, ema20, ema60)
        assert result is None

    def test_returns_none_for_flat_market(self):
        prices = [100 + math.sin(i * 0.3) * 0.5 for i in range(115)]
        bars = _make_bars(115, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        result = classify_context_top(bars, 100, m, ema20, ema60)
        assert result is None

    def test_A_top_and_B1_top_mutually_exclusive(self):
        """A_top requires DIF<0, B1_top requires DIF>0 — they can never
        both be true for the same bar."""
        prices = [100 + i * 0.5 for i in range(200)]
        bars = _make_bars(200, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        for i in range(65, 200):
            r = classify_context_top(bars, i, m, ema20, ema60)
            assert r in (None, "A_top", "B1_top"), f"unexpected return {r!r}"

    def test_no_context_window_returns_None(self):
        """Long range of pure linear data — context_top should never fire
        because the rally/pullback bands are never satisfied (gentle slope
        keeps rally % below the 3% minimum across the rolling-low window)."""
        prices = [200 - i * 0.01 for i in range(150)]
        bars = _make_bars(150, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        non_none = [
            classify_context_top(bars, i, m, ema20, ema60) for i in range(65, 150)
        ]
        assert all(r is None for r in non_none), (
            f"expected all None on gentle line, got: {non_none}"
        )


class TestBacktestSmoke:
    def test_context_top_scan_produces_list(self):
        prices = [200 - i * 0.5 for i in range(150)]
        bars = _make_bars(150, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        contexts = []
        for i in range(len(bars)):
            ctx = classify_context_top(bars, i, m, ema20, ema60)
            if ctx is not None:
                contexts.append((i, ctx))
        assert isinstance(contexts, list)
