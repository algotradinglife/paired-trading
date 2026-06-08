"""Tests for engine.divergence.pa_direction_assessment.

The DIR module is annotation-only at this step (Step 1) — it returns a
DirectionVerdict that score_today attaches to PA records without gating
emission.  The tests therefore focus on:

  1. Each source can be driven to ``bull`` independently.
  2. Each source can be driven to ``bear`` independently
     (or its acknowledged limitation: bear context isn't implemented).
  3. Mixed votes that fail to clear the 0.50 threshold collapse to ``skip``.
  4. Missing optional inputs (hourly_bars=None, macd_df=None) degrade
     gracefully to neutral on the affected source.
  5. Confidence sums match the per-source weight contributions.
  6. Backward-compat: importing the module and exercising the synthesiser
     does not touch ``PASignal`` or any other shared dataclass.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.divergence.pa_direction_assessment import (
    DirectionSource,
    DirectionVerdict,
    _SOURCE_WEIGHT,
    _find_prior_pivot,
    _vote_from_context,
    _vote_from_daily_structure,
    _vote_from_divergence,
    _vote_from_hourly_state,
    assess_direction,
)
from engine.features.macd import macd as compute_macd


# ---------------------------------------------------------------------------
# Helpers — synthetic bar builders
# ---------------------------------------------------------------------------


def _daily_bars(closes: list[float], *, start: str = "2024-01-02") -> pd.DataFrame:
    """Build daily bars from a close-price series."""
    n = len(closes)
    ts = pd.date_range(start, periods=n, freq="B", tz="UTC")
    close = pd.Series(closes, dtype=float)
    return pd.DataFrame({
        "timestamp": ts,
        "open":      close * 0.999,
        "high":      close * 1.005,
        "low":       close * 0.995,
        "close":     close,
        "volume":    [1_000_000] * n,
    }).reset_index(drop=True)


def _hourly_bars(closes: list[float], *, start: str = "2024-01-02") -> pd.DataFrame:
    """Build hourly bars from a close-price series."""
    n = len(closes)
    ts = pd.date_range(start, periods=n, freq="1h", tz="UTC")
    close = pd.Series(closes, dtype=float)
    return pd.DataFrame({
        "timestamp": ts,
        "open":      close * 0.999,
        "high":      close * 1.002,
        "low":       close * 0.998,
        "close":     close,
        "volume":    [1_000] * n,
    }).reset_index(drop=True)


def _strong_uptrend_daily(n: int = 200) -> pd.DataFrame:
    """Long uptrend that produces a BULL phase verdict.

    Constructed as a series of higher highs and higher lows (HH/HL) using
    rallying segments separated by deeper pullbacks so the pivot
    detector (5 bars each side) confirms multiple pivots.
    """
    # Segment design: 12 bars up, 6 bars down, repeat.
    # Each rally adds more than each pullback so the trend is net up.
    closes: list[float] = []
    price = 100.0
    seg = 0
    while len(closes) < n:
        if seg % 2 == 0:
            # Rally 12 bars: +1.0 each
            for _ in range(12):
                price += 1.0
                closes.append(price)
        else:
            # Pullback 6 bars: -0.5 each (net rally 12 - 3 = +9 per cycle)
            for _ in range(6):
                price -= 0.5
                closes.append(price)
        seg += 1
    closes = closes[:n]
    return _daily_bars(closes)


def _strong_downtrend_daily(n: int = 200) -> pd.DataFrame:
    """Long downtrend that produces a BEAR phase verdict.

    Mirror of ``_strong_uptrend_daily`` — lower highs and lower lows.
    """
    closes: list[float] = []
    price = 300.0
    seg = 0
    while len(closes) < n:
        if seg % 2 == 0:
            # Decline 12 bars: -1.0 each
            for _ in range(12):
                price -= 1.0
                closes.append(price)
        else:
            # Bounce 6 bars: +0.5 each (net decline 12 - 3 = -9 per cycle)
            for _ in range(6):
                price += 0.5
                closes.append(price)
        seg += 1
    closes = closes[:n]
    return _daily_bars(closes)


# ---------------------------------------------------------------------------
# Source 1 — daily_structure
# ---------------------------------------------------------------------------


class TestStructureSource:
    def test_bull_phase_votes_bull(self):
        bars = _strong_uptrend_daily(180)
        src = _vote_from_daily_structure(bars, len(bars) - 1)
        assert src.name == "daily_structure"
        assert src.vote == "bull"
        assert src.weight == _SOURCE_WEIGHT
        assert "phase=BULL" in src.rationale

    def test_bear_phase_votes_bear(self):
        bars = _strong_downtrend_daily(180)
        src = _vote_from_daily_structure(bars, len(bars) - 1)
        assert src.vote == "bear"
        assert "phase=BEAR" in src.rationale

    def test_tr_phase_votes_neutral(self):
        # Long flat band — should map to TR / TR_FORMING (or UNCLEAR)
        # but never to BULL or BEAR.
        closes = [100.0 + 2.0 * np.sin(i / 7.0) for i in range(180)]
        bars = _daily_bars(closes)
        src = _vote_from_daily_structure(bars, len(bars) - 1)
        assert src.vote == "neutral"

    def test_unclear_short_history_votes_neutral(self):
        # < 30 bars: pivots can't form
        bars = _daily_bars([100.0 + i for i in range(20)])
        src = _vote_from_daily_structure(bars, 19)
        assert src.vote == "neutral"
        assert "phase=UNCLEAR" in src.rationale


# ---------------------------------------------------------------------------
# Source 2 — hourly_state
# ---------------------------------------------------------------------------


class TestHourlySource:
    def test_strong_uptrend_1h_votes_bull(self):
        # Long uptrend on 1h drives DIF positive and well above 0.2*ATR.
        closes = [100.0 + i * 0.5 for i in range(200)]
        h_bars = _hourly_bars(closes)
        # Sign-only fallback used if ATR=0 — keep ranges nonzero for ATR.
        sig_ts = h_bars["timestamp"].iloc[-1]
        src = _vote_from_hourly_state(h_bars, sig_ts)
        assert src.vote == "bull"
        assert "dif=+" in src.rationale or "dif=" in src.rationale

    def test_strong_downtrend_1h_votes_bear(self):
        closes = [200.0 - i * 0.5 for i in range(200)]
        h_bars = _hourly_bars(closes)
        sig_ts = h_bars["timestamp"].iloc[-1]
        src = _vote_from_hourly_state(h_bars, sig_ts)
        assert src.vote == "bear"

    def test_flat_close_votes_neutral(self):
        closes = [100.0] * 200
        h_bars = _hourly_bars(closes)
        sig_ts = h_bars["timestamp"].iloc[-1]
        src = _vote_from_hourly_state(h_bars, sig_ts)
        assert src.vote == "neutral"

    def test_none_bars_votes_neutral_with_marker(self):
        src = _vote_from_hourly_state(None, pd.Timestamp("2024-06-01", tz="UTC"))
        assert src.vote == "neutral"
        assert src.rationale == "no_1h_data"

    def test_signal_before_history_votes_neutral(self):
        closes = [100.0 + i * 0.5 for i in range(50)]
        h_bars = _hourly_bars(closes, start="2024-06-01")
        sig_ts = pd.Timestamp("2023-01-01", tz="UTC")
        src = _vote_from_hourly_state(h_bars, sig_ts)
        assert src.vote == "neutral"
        assert "before" in src.rationale


# ---------------------------------------------------------------------------
# Source 3 — context
# ---------------------------------------------------------------------------


class TestContextSource:
    def test_no_macd_votes_neutral(self):
        bars = _strong_uptrend_daily(120)
        src = _vote_from_context(bars, 100, macd_df=None)
        assert src.vote == "neutral"
        assert "no_macd_df" in src.rationale
        assert "bear context not implemented" in src.rationale

    def test_uptrend_pullback_can_vote_bull(self):
        # Uptrend then 5% pullback — classify_context tests already prove
        # this hits "A" on some bar in the pullback window.
        prices = [100 + i * 0.8 for i in range(100)] + [180 - i * 1.2 for i in range(15)]
        bars = _daily_bars(prices)
        m = compute_macd(bars["close"], hist_scale=1.0)
        # Scan across the pullback and assert at least one bar votes bull.
        votes = [_vote_from_context(bars, i, m).vote for i in range(100, 113)]
        assert "bull" in votes

    def test_strong_downtrend_does_not_vote_bull(self):
        bars = _strong_downtrend_daily(180)
        m = compute_macd(bars["close"], hist_scale=1.0)
        src = _vote_from_context(bars, len(bars) - 1, m)
        assert src.vote == "neutral"
        # Honesty note for reviewers
        assert "bear context not implemented" in src.rationale


# ---------------------------------------------------------------------------
# Source 4 — divergence
# ---------------------------------------------------------------------------


class TestDivergenceSource:
    def test_no_macd_votes_neutral(self):
        bars = _strong_uptrend_daily(120)
        src = _vote_from_divergence(bars, 100, macd_df=None)
        assert src.vote == "neutral"
        assert "no_macd_df" in src.rationale

    def test_bull_divergence_at_lower_low_with_higher_hist(self):
        # Build a series with two troughs: an early deep trough and a
        # later lower trough whose hist has recovered (less negative).
        closes: list[float] = []
        # 50 bar uptrend warm-up to seed MACD
        for i in range(50):
            closes.append(100.0 + i * 0.4)
        # First trough — sharp dip
        for i in range(10):
            closes.append(120.0 - i * 2.5)
        # Recovery 1
        for i in range(8):
            closes.append(95.0 + i * 2.0)
        # Second trough — slightly lower low than the first
        for i in range(10):
            closes.append(110.0 - i * 2.6)

        bars = _daily_bars(closes)
        m = compute_macd(bars["close"], hist_scale=1.0)
        # Force a synthetic lower-low and higher-hist at the last bar to
        # make the test independent of MACD calibration.
        last = len(bars) - 1
        bars = bars.copy()
        bars.loc[last, "low"] = float(bars["low"].iloc[:last].min()) - 1.0
        m = m.copy()
        m.loc[last, "hist"] = float(m["hist"].iloc[:last].min()) + 0.5
        src = _vote_from_divergence(bars, last, m)
        assert src.vote == "bull"
        assert "bull" in src.rationale

    def test_bear_divergence_at_higher_high_with_lower_hist(self):
        # Build a series with a clear pivot high in the recent 30 bars,
        # then make the last bar produce a strictly higher high.  Force
        # the histogram lower on the last bar so the source registers
        # bearish momentum divergence.
        closes: list[float] = []
        # 50-bar warm-up climb so MACD seeds.
        for i in range(50):
            closes.append(100.0 + i * 0.4)
        # First peak — sharp rise then fall (creates a pivot high).
        for i in range(8):
            closes.append(120.0 + i * 1.5)
        for i in range(8):
            closes.append(132.0 - i * 1.5)
        # Recovery toward the prior peak so the new bar can poke higher.
        for i in range(10):
            closes.append(120.0 + i * 1.0)
        bars = _daily_bars(closes)
        m = compute_macd(bars["close"], hist_scale=1.0)
        last = len(bars) - 1
        bars = bars.copy()
        m = m.copy()
        # Force a strictly higher high than the prior 30-bar window.
        bars.loc[last, "high"] = float(bars["high"].iloc[:last].max()) + 5.0
        # Force a lower hist than the prior pivot high's hist.
        m.loc[last, "hist"] = float(m["hist"].iloc[:last].min()) - 0.5
        src = _vote_from_divergence(bars, last, m)
        assert src.vote == "bear"
        assert "bear" in src.rationale

    def test_no_divergence_votes_neutral(self):
        # Monotonic climb — no lower low, no higher hist at low → neutral.
        # Also no bear divergence (rising hist + rising high).
        bars = _daily_bars([100.0 + i * 0.5 for i in range(120)])
        m = compute_macd(bars["close"], hist_scale=1.0)
        src = _vote_from_divergence(bars, 100, m)
        assert src.vote == "neutral"

    def test_find_prior_pivot_picks_a_real_low(self):
        # Pivot helper sanity — verify a deliberately planted V picks up.
        closes = [10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        bars = _daily_bars(closes)
        idx = _find_prior_pivot(bars["low"], bar_idx=10, lookback=10, kind="low")
        assert idx is not None
        # The minimum low in the series sits at index 5
        assert 4 <= idx <= 6


# ---------------------------------------------------------------------------
# Synthesis — direction verdict
# ---------------------------------------------------------------------------


class TestSynthesis:
    def test_all_bull_sources_long_call(self):
        # Manufacture all four sources as bull.
        sources = [
            DirectionSource("daily_structure", "bull", _SOURCE_WEIGHT, "x"),
            DirectionSource("hourly_state",    "bull", _SOURCE_WEIGHT, "x"),
            DirectionSource("context",         "bull", _SOURCE_WEIGHT, "x"),
            DirectionSource("divergence",      "bull", _SOURCE_WEIGHT, "x"),
        ]
        bull_votes = sum(s.weight for s in sources if s.vote == "bull")
        assert bull_votes == pytest.approx(1.0)

    def test_assess_direction_uptrend_returns_long_call(self):
        bars = _strong_uptrend_daily(180)
        # 1h aligned with daily timestamps so hourly lookup lands inside history.
        h_closes = [100.0 + i * 0.05 for i in range(2000)]
        h_bars = _hourly_bars(h_closes, start="2024-01-01")
        m = compute_macd(bars["close"], hist_scale=1.0)
        v = assess_direction(bars, h_bars, len(bars) - 1, macd_df=m)
        assert v.direction == "long_call"
        # Confidence ≥ 0.50 once long_call clears the threshold.
        assert v.confidence >= 0.50
        # Four sources, in spec order.
        assert [s.name for s in v.sources] == [
            "daily_structure", "hourly_state", "context", "divergence",
        ]

    def test_assess_direction_downtrend_returns_long_put(self):
        bars = _strong_downtrend_daily(180)
        h_closes = [200.0 - i * 0.05 for i in range(2000)]
        h_bars = _hourly_bars(h_closes, start="2024-01-01")
        m = compute_macd(bars["close"], hist_scale=1.0)
        v = assess_direction(bars, h_bars, len(bars) - 1, macd_df=m)
        # Two bear votes guaranteed (structure + hourly).  Confidence at
        # least 0.50 → long_put.  Bear context source intentionally
        # cannot vote bear today, so the confidence floor is 0.50.
        assert v.direction == "long_put"
        assert v.confidence >= 0.50

    def test_assess_direction_mixed_votes_skip(self):
        # Flat 1h + flat daily → all sources should land neutral, hence skip.
        closes = [100.0 + 0.5 * np.sin(i / 5.0) for i in range(180)]
        bars = _daily_bars(closes)
        h_closes = [100.0 + 0.1 * np.sin(i / 3.0) for i in range(500)]
        h_bars = _hourly_bars(h_closes, start="2024-01-01")
        m = compute_macd(bars["close"], hist_scale=1.0)
        v = assess_direction(bars, h_bars, len(bars) - 1, macd_df=m)
        assert v.direction == "skip"
        # Skip ⇒ confidence equals max(bull, bear) which both lose the 0.50 bar
        assert v.confidence < 0.50

    def test_assess_direction_no_hourly_marks_neutral(self):
        bars = _strong_uptrend_daily(180)
        m = compute_macd(bars["close"], hist_scale=1.0)
        v = assess_direction(bars, None, len(bars) - 1, macd_df=m)
        hourly_src = next(s for s in v.sources if s.name == "hourly_state")
        assert hourly_src.vote == "neutral"
        assert hourly_src.rationale == "no_1h_data"

    def test_assess_direction_no_macd_marks_neutral(self):
        bars = _strong_uptrend_daily(180)
        h_closes = [100.0 + i * 0.05 for i in range(2000)]
        h_bars = _hourly_bars(h_closes, start="2024-01-01")
        v = assess_direction(bars, h_bars, len(bars) - 1, macd_df=None)
        div_src = next(s for s in v.sources if s.name == "divergence")
        ctx_src = next(s for s in v.sources if s.name == "context")
        assert div_src.vote == "neutral"
        assert ctx_src.vote == "neutral"
        assert "no_macd_df" in div_src.rationale

    def test_confidence_equals_sum_of_supporting_weights(self):
        # Long_call case: confidence == sum of bull weights
        bars = _strong_uptrend_daily(180)
        h_closes = [100.0 + i * 0.05 for i in range(2000)]
        h_bars = _hourly_bars(h_closes, start="2024-01-01")
        m = compute_macd(bars["close"], hist_scale=1.0)
        v = assess_direction(bars, h_bars, len(bars) - 1, macd_df=m)
        expected = sum(s.weight for s in v.sources if s.vote == "bull")
        assert v.confidence == pytest.approx(expected, abs=1e-9)

    def test_bar_idx_oob_returns_skip(self):
        bars = _strong_uptrend_daily(60)
        v = assess_direction(bars, None, 9999, macd_df=None)
        assert v.direction == "skip"
        assert v.confidence == 0.0
        # All sources present with neutral votes
        assert len(v.sources) == 4
        assert all(s.vote == "neutral" for s in v.sources)


# ---------------------------------------------------------------------------
# Backward-compatibility — no shared dataclass changes
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    def test_pasignal_dataclass_unchanged(self):
        """Importing DIR module must not touch PASignal / PABottomDetector."""
        # Defer the import until after the DIR module loads.
        from engine.divergence.pa_detector import (
            PASignal, PABottomDetector, PATopDetector,
        )
        # Field set unchanged on PASignal
        field_names = {f.name for f in PASignal.__dataclass_fields__.values()}
        assert field_names == {
            "pattern", "bar_idx", "timestamp", "confidence", "features",
            "higher_tf_relation", "direction",
        }
        # Constructors still work with the same positional arguments
        s = PASignal(
            pattern="h2_bottom", bar_idx=0,
            timestamp=pd.Timestamp("2024-01-01", tz="UTC"),
            confidence=0.5, features={},
        )
        assert s.direction == "long"
        # Detectors still scan a tiny synthetic series end-to-end
        bars = _daily_bars([100.0 + i * 0.1 for i in range(60)])
        # Should not raise
        _ = PABottomDetector().scan(bars)
        _ = PATopDetector().scan(bars)
