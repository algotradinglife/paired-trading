"""Tests for :class:`PATopDetector` — symmetric mirror of the bottom detector.

The TOP detector is currently a NO-EMIT stub: detection plumbing is in
place but :meth:`policy_weight` returns 0.0 across every instrument_class
until a dedicated walk-forward validation pass calibrates the table.
These tests therefore have two jobs:

  1. Plumbing — ``scan`` runs end-to-end, produces no signals on empty or
     all-zero data, and produces at least one signal on synthetic data
     with a clear upswing followed by a strong bearish reversal bar.
  2. Regression guard — every routing path of ``policy_weight`` returns
     exactly 0.0.  If a future edit accidentally enables a lane before
     walk-forward validation lands, this test fails loud.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.divergence.pa_detector import PASignal, PATopDetector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bars(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame.  ``rows`` = (open, high, low, close)."""
    n = len(rows)
    ts = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    df.insert(0, "timestamp", ts)
    df["volume"] = 1_000_000
    return df


def _synthetic_upswing_with_top(n_pre: int = 60, climb: int = 25) -> pd.DataFrame:
    """Synthesise bars: long upswing, then a hard bearish reversal bar.

    Construction:
      - ``n_pre`` quiet bars near 100 to seed the EMA and let the
        ``i >= 30`` warmup pass.
      - ``climb`` strong bull bars that march price well above EMA20 and
        accumulate L-legs ... wait — bull bars do NOT add L-legs.  L-legs
        require ``close[j] < low[j-1]``.  We need *some* failed-rally
        attempts inside the upswing for the detector to fire, otherwise
        ``l_leg_count < min_l_legs`` short-circuits.  So we interleave a
        few intra-upswing pullbacks that close below the previous bar's
        low (L-leg events) while the overall trend still climbs.
      - A final strong bearish bar: opens near the high, closes near the
        low, large body.  This drives ``bar_quality_bear`` high while
        ``ema_distance_norm`` is still positive (price above EMA20).
    """
    rows: list[tuple[float, float, float, float]] = []
    px = 100.0
    # Quiet bars to seed EMA
    for _ in range(n_pre):
        rows.append((px, px + 0.3, px - 0.3, px + 0.05))
        px += 0.05

    # Upswing with periodic intra-trend pullbacks to generate L-legs.
    # Pattern: 4 bull bars, then 1 bar that closes below the previous low
    # (an L-leg event) but the rally continues afterwards.
    for k in range(climb):
        if k > 0 and k % 4 == 0:
            # L-leg bar: high stays elevated, low dips below previous low,
            # close below prev low → l_leg_count increments.
            prev_low = rows[-1][2]
            new_low = prev_low - 1.5
            new_close = new_low + 0.2  # close below prev low
            new_high = rows[-1][1] + 0.5
            new_open = rows[-1][3] + 0.3
            rows.append((new_open, new_high, new_low, new_close))
            px = new_close + 1.0  # resume climb from here
        else:
            o = px
            c = px + 2.0
            h = c + 0.3
            l = o - 0.2
            rows.append((o, h, l, c))
            px = c

    # The reversal bar: large body, open near high, close near low.
    last_close = rows[-1][3]
    open_ = last_close + 0.2
    high_ = open_ + 0.3
    close_ = open_ - 6.0  # big bearish body
    low_ = close_ - 0.1
    rows.append((open_, high_, low_, close_))
    return _make_bars(rows)


def _make_signal(
    higher_tf_relation: str | None = "opposing",
    trend_structure: str | None = None,
    leg_count_up: int | None = None,
    pattern: str = "h2_top",
    confidence: float = 0.6,
    direction: str = "short",
) -> PASignal:
    """Minimal PASignal factory for top-side policy tests."""
    features: dict[str, object] = {}
    if trend_structure is not None:
        features["trend_structure"] = trend_structure
    if leg_count_up is not None:
        features["leg_count_up"] = leg_count_up
    return PASignal(
        pattern=pattern,
        bar_idx=42,
        timestamp=pd.Timestamp("2026-06-08", tz="UTC"),
        confidence=confidence,
        features=features,
        higher_tf_relation=higher_tf_relation,
        direction=direction,
    )


# ---------------------------------------------------------------------------
# Smoke: scan plumbing
# ---------------------------------------------------------------------------


class TestScanEmpty:
    def test_empty_bars_returns_empty_list(self):
        bars = pd.DataFrame(
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        det = PATopDetector()
        result = det.scan(bars)
        assert result == []

    def test_too_few_bars_returns_empty_list(self):
        # Detector starts scanning at i=30; fewer than 31 bars → no signals.
        rows = [(100.0, 101.0, 99.0, 100.5)] * 20
        bars = _make_bars(rows)
        det = PATopDetector()
        assert det.scan(bars) == []

    def test_flat_bars_emit_no_signals(self):
        # Perfectly flat data: no L-legs, no bearish quality → nothing fires.
        rows = [(100.0, 100.1, 99.9, 100.0)] * 80
        bars = _make_bars(rows)
        det = PATopDetector()
        assert det.scan(bars) == []


class TestScanFiresOnSyntheticTop:
    def test_synthetic_upswing_with_reversal_produces_signal(self):
        bars = _synthetic_upswing_with_top()
        det = PATopDetector(
            min_l_legs=1,        # synthetic data only gives a few L-legs
            min_quality=0.3,
            ema_threshold=0.0,
            min_gap=5,
        )
        signals = det.scan(bars)
        assert len(signals) >= 1, (
            "expected at least one h2_top signal on a synthetic upswing "
            "followed by a strong bearish reversal bar"
        )
        # Every signal should be a properly-tagged top.
        for s in signals:
            assert s.pattern == "h2_top"
            assert s.direction == "short"
            assert 0.0 <= s.confidence <= 1.0
            # The reversal bar must close below open (bearish bar).
            assert s.features["bar_quality_bear"] >= 0.3
            # Price must be above EMA20 at the signal (upswing context).
            assert s.features["ema_distance_norm"] > 0.0

    def test_signals_respect_min_gap(self):
        bars = _synthetic_upswing_with_top()
        det = PATopDetector(min_l_legs=1, min_quality=0.3, min_gap=10)
        signals = det.scan(bars)
        if len(signals) < 2:
            pytest.skip("only one signal — cannot test gap")
        for a, b in zip(signals, signals[1:]):
            assert b.bar_idx - a.bar_idx >= 10


# ---------------------------------------------------------------------------
# Policy weight: SKELETON regression guard — every lane must return 0.0
# ---------------------------------------------------------------------------


class TestPolicyWeightIsNoEmitStub:
    """Until walk-forward validation lands, every routing path → 0.0.

    This guard is deliberately exhaustive: if a future edit accidentally
    enables a lane before validation, exactly one of these parametrised
    cases will fail and surface the issue before the change goes live.
    """

    INSTRUMENT_CLASSES = [
        "us_equity",
        "cn_metal_futures",
        "cn_bond",
        "cn_futures",
        "czce",
        "cn_agri",
        "unknown_class",
        "",
        "crypto",
    ]
    HTF_RELATIONS = ["opposing", "supporting", "neutral", None]
    TRENDS = ["uptrend", "downtrend", "ranging", "unknown", None]

    @pytest.mark.parametrize("ic", INSTRUMENT_CLASSES)
    @pytest.mark.parametrize("rel", HTF_RELATIONS)
    def test_every_class_and_relation_returns_zero(self, ic, rel):
        sig = _make_signal(higher_tf_relation=rel)
        assert PATopDetector.policy_weight(sig, ic) == 0.0

    @pytest.mark.parametrize("trend", TRENDS)
    @pytest.mark.parametrize("rel", HTF_RELATIONS)
    def test_us_equity_all_trends_return_zero(self, trend, rel):
        sig = _make_signal(higher_tf_relation=rel, trend_structure=trend)
        assert PATopDetector.policy_weight(sig, "us_equity") == 0.0

    @pytest.mark.parametrize("legs", [0, 1, 2, 3, 5])
    def test_us_equity_legs_bonus_does_not_apply(self, legs):
        """No legs_up bonus until validation — even legs=1 returns 0.0."""
        sig = _make_signal(
            higher_tf_relation="opposing",
            trend_structure="downtrend",
            leg_count_up=legs,
        )
        assert PATopDetector.policy_weight(sig, "us_equity") == 0.0


class TestSymbolKwargThreaded:
    """Symbol kwarg must thread through the same way the bottom detector
    does — currently every call still returns 0.0 (stub), but the
    parameter must be accepted and not raise.
    """

    @pytest.mark.parametrize(
        "symbol",
        ["spy", "qqq", "tlt", "TLT", "cu", "ag", None, "", "unknown"],
    )
    def test_symbol_kwarg_accepted_without_raise(self, symbol):
        sig = _make_signal(
            higher_tf_relation="opposing", trend_structure="downtrend"
        )
        # Must accept symbol kwarg and still return 0.0.
        w = PATopDetector.policy_weight(sig, "us_equity", symbol=symbol)
        assert w == 0.0

    def test_symbol_kwarg_omitted_backward_compatible(self):
        sig = _make_signal(higher_tf_relation="opposing")
        # Calling without symbol kwarg must work.
        assert PATopDetector.policy_weight(sig, "cn_metal_futures") == 0.0

    def test_symbol_kwarg_keyword_only(self):
        """symbol is keyword-only to match the bottom detector signature."""
        sig = _make_signal(higher_tf_relation="opposing")
        with pytest.raises(TypeError):
            # Positional symbol should fail.
            PATopDetector.policy_weight(sig, "us_equity", "spy")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Ensemble weight: also stays at 0.0 until policy lanes are calibrated.
# ---------------------------------------------------------------------------


class TestEnsembleWeightStubbed:
    @pytest.mark.parametrize("ic", ["us_equity", "cn_metal_futures", "cn_bond"])
    @pytest.mark.parametrize("bars", [None, 0, 1, 3, 5, 100])
    def test_ensemble_weight_returns_zero_for_every_lane(self, ic, bars):
        sig = _make_signal(higher_tf_relation="opposing")
        assert PATopDetector.ensemble_weight(sig, ic, bars) == 0.0

    def test_ensemble_weight_accepts_symbol_kwarg(self):
        sig = _make_signal(higher_tf_relation="opposing")
        assert PATopDetector.ensemble_weight(
            sig, "us_equity", 1, symbol="spy"
        ) == 0.0


# ---------------------------------------------------------------------------
# PASignal direction field — backward-compatible default.
# ---------------------------------------------------------------------------


class TestPASignalDirection:
    def test_default_direction_is_long_for_backcompat(self):
        """Older callers that construct PASignal without ``direction`` must
        still get the previous behaviour (long / bottom-side signal)."""
        sig = PASignal(
            pattern="h2_bottom",
            bar_idx=0,
            timestamp=pd.Timestamp("2024-01-01", tz="UTC"),
            confidence=0.5,
            features={},
        )
        assert sig.direction == "long"

    def test_top_signals_carry_short_direction(self):
        bars = _synthetic_upswing_with_top()
        det = PATopDetector(min_l_legs=1, min_quality=0.3)
        for s in det.scan(bars):
            assert s.direction == "short"
