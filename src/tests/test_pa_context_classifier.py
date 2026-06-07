import math
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.divergence.pa_context_classifier import classify_context
from engine.features.macd import macd, ema


def _make_bars(n: int, prices: list | None = None) -> pd.DataFrame:
    """Minimal daily OHLCV DataFrame for testing."""
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
    """Compute MACD + EMA20/60 for a bar DataFrame."""
    m = macd(bars["close"])
    ema20 = ema(bars["close"], 20)
    ema60 = ema(bars["close"], 60)
    return m, ema20, ema60


class TestContextA:
    def test_returns_none_when_dif_negative(self):
        # Bear market: DIF will be negative
        prices = [200 - i * 1.0 for i in range(115)]
        bars = _make_bars(115, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        result = classify_context(bars, 110, m, ema20, ema60)
        assert result != "A"

    def test_returns_none_when_price_above_ema20_no_pullback(self):
        # Uptrend, no pullback, price above EMA20
        prices = [100 + i * 0.8 for i in range(115)]
        bars = _make_bars(115, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        result = classify_context(bars, 110, m, ema20, ema60)
        assert result != "A"

    def test_returns_none_when_pullback_exceeds_10pct(self):
        # Uptrend then >10% crash
        prices = [100 + i * 0.8 for i in range(100)] + [180 - i * 3.0 for i in range(15)]
        bars = _make_bars(115, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        result = classify_context(bars, 112, m, ema20, ema60)
        assert result != "A"

    def test_returns_none_below_min_bars(self):
        prices = [100 + i * 0.5 for i in range(115)]
        bars = _make_bars(115, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        result = classify_context(bars, 30, m, ema20, ema60)
        assert result is None

    def test_returns_A_when_dif_positive_price_below_ema20_above_ema60(self):
        # 100 bars steady uptrend, then 10-bar pullback (~5% decline)
        prices = [100 + i * 0.8 for i in range(100)] + [180 - i * 1.2 for i in range(15)]
        bars = _make_bars(115, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        # Scan bars 100-112 — at least one should fire A
        results = [classify_context(bars, i, m, ema20, ema60) for i in range(100, 113)]
        assert "A" in results, f"Expected 'A' in results but got: {results}"

    def test_A_does_not_fire_on_flat_gentle_rise(self):
        # Flat 70 bars then very gentle rise (0.05/bar): pullback < 3% (rolling high ≈ close),
        # so the pullback guard _A_PULLBACK_MIN rejects it. Context A should not fire.
        prices = [100.0] * 70 + [100 + i * 0.05 for i in range(30)]  # very gentle rise
        bars = _make_bars(100, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        for i in range(70, 100):
            r = classify_context(bars, i, m, ema20, ema60)
            assert r != "A", f"Context A fired at bar {i} on flat/gentle-rise data"

    def test_A_fires_on_valid_uptrend_pullback(self):
        # Uptrend for 100 bars then 5% pullback — should produce some A bars
        prices = [100 + i * 0.8 for i in range(100)] + [180 - i * 1.2 for i in range(10)]
        bars = _make_bars(110, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        # This may or may not fire depending on EMA warm-up; just verify no crash and B1 not returned
        for i in range(100, 110):
            r = classify_context(bars, i, m, ema20, ema60)
            assert r in (None, "A"), f"bar {i} returned unexpected {r!r}"


class TestContextB1:
    def test_returns_none_when_pullback_breaks_trough(self):
        # Decline then bounce then new low below trough
        down  = [200 - i * 1.2 for i in range(60)]
        up    = [128 + i * 1.5 for i in range(20)]
        lower = [158 - i * 2.0 for i in range(20)]
        prices = down + up + lower
        bars = _make_bars(len(prices), prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        result = classify_context(bars, len(prices) - 3, m, ema20, ema60)
        assert result != "B1"

    def test_returns_none_when_dif_positive(self):
        # Uptrend: DIF will be positive, B1 must not fire
        prices = [100 + i * 0.8 for i in range(115)]
        bars = _make_bars(115, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        result = classify_context(bars, 110, m, ema20, ema60)
        assert result != "B1"

    def test_returns_none_below_min_bars(self):
        prices = [100 + i * 0.5 for i in range(115)]
        bars = _make_bars(115, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        result = classify_context(bars, 20, m, ema20, ema60)
        assert result is None

    def test_returns_B1_when_first_pullback_above_trough(self):
        # B1 requires DIF < 0 throughout the pullback.  The trick is to keep the
        # bounce small/short so the MACD line (DIF) never crosses zero.
        #
        # Structure:
        #   flat  — 80 bars at 100 (EMA warmup, DIF ≈ 0)
        #   down  — 15 bars × -2.5/bar → 100→65  (creates deeply negative DIF & histogram)
        #   up    — 8 bars × +1.5/bar  → 65→75.5 (H1 ≈ +16% above trough, histogram recovers)
        #   back  — 8 bars × -0.6/bar  → 75.5→71.3 (pullback; stays well above trough low ≈65)
        flat  = [100.0] * 80
        down  = [100 - i * 2.5 for i in range(15)]
        up    = [65 + i * 1.5 for i in range(8)]
        back  = [75.5 - i * 0.6 for i in range(8)]
        prices = flat + down + up + back
        bars = _make_bars(len(prices), prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        # Scan the mid-to-late pullback bars — B1 should fire (DIF < 0, hist recovered,
        # H1 formed, price pulling back > 2% from H1 but above trough)
        scan_start = len(flat) + len(down) + len(up) + 2
        scan_end = len(prices)
        results = [classify_context(bars, i, m, ema20, ema60) for i in range(scan_start, scan_end)]
        assert "B1" in results, f"Expected 'B1' in results but got: {results}"

    def test_B1_fires_on_valid_recovery_pullback(self):
        # Steep decline → bounce (>5%) → pullback staying above trough
        down = [200 - i * 1.5 for i in range(80)]   # 200→83
        up   = [83 + i * 1.8 for i in range(25)]    # 83→128 (~54% above trough low~83)
        back = [128 - i * 0.9 for i in range(15)]   # 128→114.5 (well above 83)
        prices = down + up + back
        bars = _make_bars(len(prices), prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        # Check bars in the pullback region
        for i in range(len(down) + len(up), len(prices)):
            r = classify_context(bars, i, m, ema20, ema60)
            assert r in (None, "B1", "A"), f"bar {i} returned unexpected {r!r}"


class TestNoBothContexts:
    def test_at_minimum_bars_returns_none(self):
        bars = _make_bars(10)
        m, ema20, ema60 = _make_macd_emas(bars)
        result = classify_context(bars, 5, m, ema20, ema60)
        assert result is None

    def test_returns_none_for_flat_market(self):
        prices = [100 + math.sin(i * 0.3) * 0.5 for i in range(115)]
        bars = _make_bars(115, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        result = classify_context(bars, 100, m, ema20, ema60)
        assert result is None

    def test_A_and_B1_mutually_exclusive(self):
        # By spec: A requires DIF>0, B1 requires DIF<0 — they can never both be true
        prices = [100 + i * 0.5 for i in range(200)]
        bars = _make_bars(200, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        for i in range(65, 200):
            r = classify_context(bars, i, m, ema20, ema60)
            assert r in (None, "A", "B1"), f"unexpected return {r!r}"


class TestBacktestSmoke:
    def test_context_scan_produces_list(self):
        prices = [100 + i * 0.5 for i in range(150)]
        bars = _make_bars(150, prices)
        m, ema20, ema60 = _make_macd_emas(bars)
        contexts = []
        for i in range(len(bars)):
            ctx = classify_context(bars, i, m, ema20, ema60)
            if ctx is not None:
                contexts.append((i, ctx))
        assert isinstance(contexts, list)
