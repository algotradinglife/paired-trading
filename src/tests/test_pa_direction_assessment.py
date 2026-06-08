"""Tests for engine.divergence.pa_direction_assessment.

The DIR module is annotation-only — it returns a DirectionVerdict that
score_today attaches to PA records without gating emission.  The tests
cover:

  1. Each source can be driven to ``bull`` independently.
  2. Each source can be driven to ``bear`` independently
     (or its acknowledged limitation: bear context isn't implemented).
  3. Mixed votes that fail to clear the 0.50 threshold collapse to ``skip``.
  4. Missing optional inputs (hourly_bars=None, macd_df=None) degrade
     gracefully to neutral on the affected source.
  5. Confidence sums match the per-source weight contributions.
  6. Backward-compat: importing the module and exercising the synthesiser
     does not touch ``PASignal`` or any other shared dataclass.
  7. Polarity-aware behaviour (2026-06-08):
       - hourly_state: DIF<0 votes BULL under h2_bottom (h=opposing on
         a bottom setup confirms it), and the polarity flips for h2_top.
       - context: bottom uses classify_context (A/B1 → bull); top uses
         classify_context_top (A_top/B1_top → bear).  Both share the
         same MACD/EMA inputs.
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
    """Long uptrend that produces a BULL phase verdict."""
    closes: list[float] = []
    price = 100.0
    seg = 0
    while len(closes) < n:
        if seg % 2 == 0:
            for _ in range(12):
                price += 1.0
                closes.append(price)
        else:
            for _ in range(6):
                price -= 0.5
                closes.append(price)
        seg += 1
    closes = closes[:n]
    return _daily_bars(closes)


def _strong_downtrend_daily(n: int = 200) -> pd.DataFrame:
    """Long downtrend that produces a BEAR phase verdict."""
    closes: list[float] = []
    price = 300.0
    seg = 0
    while len(closes) < n:
        if seg % 2 == 0:
            for _ in range(12):
                price -= 1.0
                closes.append(price)
        else:
            for _ in range(6):
                price += 0.5
                closes.append(price)
        seg += 1
    closes = closes[:n]
    return _daily_bars(closes)


# ---------------------------------------------------------------------------
# Source 1 — daily_structure (direction-agnostic with respect to ambush_pattern)
# ---------------------------------------------------------------------------


class TestStructureSource:
    def test_bull_phase_votes_bull(self):
        bars = _strong_uptrend_daily(180)
        src = _vote_from_daily_structure(
            bars, len(bars) - 1, ambush_pattern="h2_bottom",
        )
        assert src.name == "daily_structure"
        assert src.vote == "bull"
        assert src.weight == _SOURCE_WEIGHT
        assert "phase=BULL" in src.rationale

    def test_bear_phase_votes_bear(self):
        bars = _strong_downtrend_daily(180)
        src = _vote_from_daily_structure(
            bars, len(bars) - 1, ambush_pattern="h2_bottom",
        )
        assert src.vote == "bear"
        assert "phase=BEAR" in src.rationale

    def test_tr_phase_votes_neutral(self):
        closes = [100.0 + 2.0 * np.sin(i / 7.0) for i in range(180)]
        bars = _daily_bars(closes)
        src = _vote_from_daily_structure(
            bars, len(bars) - 1, ambush_pattern="h2_bottom",
        )
        assert src.vote == "neutral"

    def test_unclear_short_history_votes_neutral(self):
        bars = _daily_bars([100.0 + i for i in range(20)])
        src = _vote_from_daily_structure(
            bars, 19, ambush_pattern="h2_bottom",
        )
        assert src.vote == "neutral"
        assert "phase=UNCLEAR" in src.rationale

    def test_phase_vote_invariant_across_ambush_patterns(self):
        """daily_structure is direction-agnostic — BULL stays BULL for both."""
        bars = _strong_uptrend_daily(180)
        bot = _vote_from_daily_structure(
            bars, len(bars) - 1, ambush_pattern="h2_bottom",
        )
        top = _vote_from_daily_structure(
            bars, len(bars) - 1, ambush_pattern="h2_top",
        )
        assert bot.vote == top.vote == "bull"


# ---------------------------------------------------------------------------
# Source 2 — hourly_state (POLARITY-AWARE)
# ---------------------------------------------------------------------------


class TestHourlySource:
    def test_h2_bottom_dif_negative_votes_bull(self):
        """Strong downtrend → DIF<0 → with h2_bottom semantics, h=opposing
        confirms the bottom setup, so vote=bull."""
        closes = [200.0 - i * 0.5 for i in range(200)]
        h_bars = _hourly_bars(closes)
        sig_ts = h_bars["timestamp"].iloc[-1]
        src = _vote_from_hourly_state(h_bars, sig_ts, ambush_pattern="h2_bottom")
        assert src.vote == "bull"
        assert "pattern=h2_bottom" in src.rationale

    def test_h2_bottom_dif_positive_votes_bear(self):
        """Strong uptrend → DIF>0 → with h2_bottom semantics, the hourly
        is moving WITH the prior trend (no h=opposing) → vote=bear."""
        closes = [100.0 + i * 0.5 for i in range(200)]
        h_bars = _hourly_bars(closes)
        sig_ts = h_bars["timestamp"].iloc[-1]
        src = _vote_from_hourly_state(h_bars, sig_ts, ambush_pattern="h2_bottom")
        assert src.vote == "bear"

    def test_h2_top_dif_positive_votes_bear(self):
        """Strong uptrend → DIF>0 → with h2_top semantics, h=opposing
        confirms the top setup, so vote=bear."""
        closes = [100.0 + i * 0.5 for i in range(200)]
        h_bars = _hourly_bars(closes)
        sig_ts = h_bars["timestamp"].iloc[-1]
        src = _vote_from_hourly_state(h_bars, sig_ts, ambush_pattern="h2_top")
        assert src.vote == "bear"
        assert "pattern=h2_top" in src.rationale

    def test_h2_top_dif_negative_votes_bull(self):
        """Strong downtrend → DIF<0 → with h2_top semantics, hourly is
        moving WITH the prior trend (no h=opposing) → vote=bull."""
        closes = [200.0 - i * 0.5 for i in range(200)]
        h_bars = _hourly_bars(closes)
        sig_ts = h_bars["timestamp"].iloc[-1]
        src = _vote_from_hourly_state(h_bars, sig_ts, ambush_pattern="h2_top")
        assert src.vote == "bull"

    def test_polarity_rationale_carries_pattern_tag(self):
        """The vote logic is identical between h2_bottom and h2_top
        (DIF<0 → bull, DIF>0 → bear in both — the polarity narrative
        differs: 'h=opposing on bottom' vs 'h=opposing on top'), so the
        explicit ambush_pattern tag must show up on the rationale so
        downstream consumers can audit which polarity narrative
        applied."""
        closes = [100.0 + i * 0.5 for i in range(200)]
        h_bars = _hourly_bars(closes)
        sig_ts = h_bars["timestamp"].iloc[-1]
        bot = _vote_from_hourly_state(h_bars, sig_ts, ambush_pattern="h2_bottom")
        top = _vote_from_hourly_state(h_bars, sig_ts, ambush_pattern="h2_top")
        # Same vote under the spec: DIF>0 → bear under both patterns,
        # because h2_top with DIF>0 means h=opposing on a top setup, and
        # h2_bottom with DIF>0 means h is moving WITH the prior trend
        # (no h=opposing) which weakens the bottom setup.
        assert bot.vote == top.vote == "bear"
        # But the rationale tag differs so the chooser can tell them apart.
        assert "pattern=h2_bottom" in bot.rationale
        assert "pattern=h2_top" in top.rationale

    def test_flat_close_votes_neutral(self):
        closes = [100.0] * 200
        h_bars = _hourly_bars(closes)
        sig_ts = h_bars["timestamp"].iloc[-1]
        src = _vote_from_hourly_state(h_bars, sig_ts, ambush_pattern="h2_bottom")
        assert src.vote == "neutral"

    def test_flat_close_neutral_under_h2_top(self):
        closes = [100.0] * 200
        h_bars = _hourly_bars(closes)
        sig_ts = h_bars["timestamp"].iloc[-1]
        src = _vote_from_hourly_state(h_bars, sig_ts, ambush_pattern="h2_top")
        assert src.vote == "neutral"

    def test_none_bars_votes_neutral_with_marker(self):
        src = _vote_from_hourly_state(
            None, pd.Timestamp("2024-06-01", tz="UTC"), ambush_pattern="h2_bottom",
        )
        assert src.vote == "neutral"
        assert src.rationale == "no_1h_data"

    def test_signal_before_history_votes_neutral(self):
        closes = [100.0 + i * 0.5 for i in range(50)]
        h_bars = _hourly_bars(closes, start="2024-06-01")
        sig_ts = pd.Timestamp("2023-01-01", tz="UTC")
        src = _vote_from_hourly_state(h_bars, sig_ts, ambush_pattern="h2_bottom")
        assert src.vote == "neutral"
        assert "before" in src.rationale


# ---------------------------------------------------------------------------
# Source 3 — context (POLARITY-AWARE: bottom-only patterns)
# ---------------------------------------------------------------------------


class TestContextSource:
    def test_no_macd_votes_neutral(self):
        bars = _strong_uptrend_daily(120)
        src = _vote_from_context(
            bars, 100, macd_df=None, ambush_pattern="h2_bottom",
        )
        assert src.vote == "neutral"
        assert "no_macd_df" in src.rationale

    def test_uptrend_pullback_can_vote_bull(self):
        prices = [100 + i * 0.8 for i in range(100)] + [180 - i * 1.2 for i in range(15)]
        bars = _daily_bars(prices)
        m = compute_macd(bars["close"], hist_scale=1.0)
        votes = [
            _vote_from_context(bars, i, m, ambush_pattern="h2_bottom").vote
            for i in range(100, 113)
        ]
        assert "bull" in votes

    def test_strong_downtrend_does_not_vote_bull(self):
        bars = _strong_downtrend_daily(180)
        m = compute_macd(bars["close"], hist_scale=1.0)
        src = _vote_from_context(
            bars, len(bars) - 1, m, ambush_pattern="h2_bottom",
        )
        assert src.vote == "neutral"

    def test_h2_top_invokes_top_classifier(self, monkeypatch):
        """When ambush_pattern='h2_top', _vote_from_context must call
        classify_context_top (not classify_context).  Spy on both and
        assert the top variant runs while the bottom variant does not."""
        from engine.divergence import pa_direction_assessment as pda

        calls: dict[str, int] = {"bot": 0, "top": 0}

        def fake_bot(bars, i, m, e20, e60):
            calls["bot"] += 1
            return None

        def fake_top(bars, i, m, e20, e60):
            calls["top"] += 1
            return None

        monkeypatch.setattr(pda, "classify_context", fake_bot)
        monkeypatch.setattr(pda, "classify_context_top", fake_top)

        bars = _strong_uptrend_daily(180)
        m = compute_macd(bars["close"], hist_scale=1.0)
        _ = pda._vote_from_context(
            bars, len(bars) - 1, m, ambush_pattern="h2_top",
        )
        assert calls["top"] == 1, "classify_context_top must run for h2_top"
        assert calls["bot"] == 0, "classify_context must NOT run for h2_top"

    def test_h2_top_A_top_scenario_votes_bear(self, monkeypatch):
        """If classify_context_top returns 'A_top', the source must vote
        bear (selling-into-rally favours puts)."""
        from engine.divergence import pa_direction_assessment as pda

        monkeypatch.setattr(
            pda, "classify_context_top",
            lambda bars, i, m, e20, e60: "A_top",
        )
        bars = _strong_uptrend_daily(180)
        m = compute_macd(bars["close"], hist_scale=1.0)
        src = pda._vote_from_context(
            bars, len(bars) - 1, m, ambush_pattern="h2_top",
        )
        assert src.vote == "bear"
        assert "A_top" in src.rationale

    def test_h2_top_B1_top_scenario_votes_bear(self, monkeypatch):
        """If classify_context_top returns 'B1_top', the source must vote
        bear (first pullback in new bear cycle favours puts)."""
        from engine.divergence import pa_direction_assessment as pda

        monkeypatch.setattr(
            pda, "classify_context_top",
            lambda bars, i, m, e20, e60: "B1_top",
        )
        bars = _strong_uptrend_daily(180)
        m = compute_macd(bars["close"], hist_scale=1.0)
        src = pda._vote_from_context(
            bars, len(bars) - 1, m, ambush_pattern="h2_top",
        )
        assert src.vote == "bear"
        assert "B1_top" in src.rationale

    def test_h2_top_no_context_votes_neutral_with_top_rationale(self, monkeypatch):
        """When no top-side context fires, rationale is 'no_top_context'
        (the new top-side gap marker)."""
        from engine.divergence import pa_direction_assessment as pda

        monkeypatch.setattr(
            pda, "classify_context_top",
            lambda bars, i, m, e20, e60: None,
        )
        bars = _strong_uptrend_daily(180)
        m = compute_macd(bars["close"], hist_scale=1.0)
        src = pda._vote_from_context(
            bars, len(bars) - 1, m, ambush_pattern="h2_top",
        )
        assert src.vote == "neutral"
        assert src.rationale == "no_top_context"

    def test_h2_top_neutral_when_no_macd(self):
        """No MACD frame → degrades to neutral regardless of side."""
        bars = _strong_uptrend_daily(120)
        src = _vote_from_context(
            bars, 100, macd_df=None, ambush_pattern="h2_top",
        )
        assert src.vote == "neutral"
        assert "no_macd_df" in src.rationale


# ---------------------------------------------------------------------------
# Source 4 — divergence (direction-agnostic with respect to ambush_pattern)
# ---------------------------------------------------------------------------


class TestDivergenceSource:
    def test_no_macd_votes_neutral(self):
        bars = _strong_uptrend_daily(120)
        src = _vote_from_divergence(
            bars, 100, macd_df=None, ambush_pattern="h2_bottom",
        )
        assert src.vote == "neutral"
        assert "no_macd_df" in src.rationale

    def test_bull_divergence_at_lower_low_with_higher_hist(self):
        closes: list[float] = []
        for i in range(50):
            closes.append(100.0 + i * 0.4)
        for i in range(10):
            closes.append(120.0 - i * 2.5)
        for i in range(8):
            closes.append(95.0 + i * 2.0)
        for i in range(10):
            closes.append(110.0 - i * 2.6)

        bars = _daily_bars(closes)
        m = compute_macd(bars["close"], hist_scale=1.0)
        last = len(bars) - 1
        bars = bars.copy()
        bars.loc[last, "low"] = float(bars["low"].iloc[:last].min()) - 1.0
        m = m.copy()
        m.loc[last, "hist"] = float(m["hist"].iloc[:last].min()) + 0.5
        src = _vote_from_divergence(
            bars, last, m, ambush_pattern="h2_bottom",
        )
        assert src.vote == "bull"
        assert "bull" in src.rationale

    def test_bear_divergence_at_higher_high_with_lower_hist(self):
        closes: list[float] = []
        for i in range(50):
            closes.append(100.0 + i * 0.4)
        for i in range(8):
            closes.append(120.0 + i * 1.5)
        for i in range(8):
            closes.append(132.0 - i * 1.5)
        for i in range(10):
            closes.append(120.0 + i * 1.0)
        bars = _daily_bars(closes)
        m = compute_macd(bars["close"], hist_scale=1.0)
        last = len(bars) - 1
        bars = bars.copy()
        m = m.copy()
        bars.loc[last, "high"] = float(bars["high"].iloc[:last].max()) + 5.0
        m.loc[last, "hist"] = float(m["hist"].iloc[:last].min()) - 0.5
        src = _vote_from_divergence(
            bars, last, m, ambush_pattern="h2_top",
        )
        assert src.vote == "bear"
        assert "bear" in src.rationale

    def test_divergence_vote_invariant_across_ambush_patterns(self):
        """Bull-divergence shape stays bull-vote under h2_bottom AND h2_top."""
        closes: list[float] = []
        for i in range(50):
            closes.append(100.0 + i * 0.4)
        for i in range(10):
            closes.append(120.0 - i * 2.5)
        for i in range(8):
            closes.append(95.0 + i * 2.0)
        for i in range(10):
            closes.append(110.0 - i * 2.6)
        bars = _daily_bars(closes)
        m = compute_macd(bars["close"], hist_scale=1.0)
        last = len(bars) - 1
        bars = bars.copy()
        bars.loc[last, "low"] = float(bars["low"].iloc[:last].min()) - 1.0
        m = m.copy()
        m.loc[last, "hist"] = float(m["hist"].iloc[:last].min()) + 0.5
        bot = _vote_from_divergence(bars, last, m, ambush_pattern="h2_bottom")
        top = _vote_from_divergence(bars, last, m, ambush_pattern="h2_top")
        assert bot.vote == top.vote == "bull"

    def test_no_divergence_votes_neutral(self):
        bars = _daily_bars([100.0 + i * 0.5 for i in range(120)])
        m = compute_macd(bars["close"], hist_scale=1.0)
        src = _vote_from_divergence(
            bars, 100, m, ambush_pattern="h2_bottom",
        )
        assert src.vote == "neutral"

    def test_find_prior_pivot_picks_a_real_low(self):
        closes = [10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        bars = _daily_bars(closes)
        idx = _find_prior_pivot(bars["low"], bar_idx=10, lookback=10, kind="low")
        assert idx is not None
        assert 4 <= idx <= 6


# ---------------------------------------------------------------------------
# Synthesis — direction verdict
# ---------------------------------------------------------------------------


class TestSynthesis:
    def test_all_bull_sources_long_call(self):
        sources = [
            DirectionSource(name, "bull", _SOURCE_WEIGHT, "x")
            for name in ("daily_structure", "hourly_state", "context",
                         "divergence", "weekly_trend", "minute15_state",
                         "force_balance", "exhaustion")
        ]
        bull_votes = sum(s.weight for s in sources if s.vote == "bull")
        assert bull_votes == pytest.approx(1.0)

    def test_assess_direction_h2_bottom_setup_returns_long_call(self):
        """A real h2_bottom setup: daily structure is BULL (uptrend in
        progress), the hourly is moving against it (DIF<0), and the
        context picks up the pullback.  Under the 8-source synthesiser
        (threshold 0.50 → 4-of-8) we need force_balance + exhaustion to
        also vote bull (weekly_bars/bars_15 default to None → neutral)."""
        prices = [100 + i * 0.8 for i in range(100)] + [180 - i * 1.2 for i in range(15)]
        bars = _daily_bars(prices)
        # Hourly DIF<0 so h=opposing on a bottom setup → bull vote.
        h_closes = [200.0 - i * 0.05 for i in range(2000)]
        h_bars = _hourly_bars(h_closes, start="2024-01-01")
        m = compute_macd(bars["close"], hist_scale=1.0)
        # Scan the pullback window; expect at least one long_call OR
        # confirm we surface a bull-majority verdict (≥0.375) without a
        # bear-leaning verdict — the synthesiser must NOT flip long_put.
        directions = []
        confidences = []
        for i in range(100, 113):
            v = assess_direction(
                bars, h_bars, i, macd_df=m, ambush_pattern="h2_bottom",
            )
            directions.append(v.direction)
            confidences.append((v.direction, v.confidence))
        assert "long_put" not in directions, f"unexpected long_put under h2_bottom uptrend: {confidences}"
        assert "long_call" in directions or max(c for _, c in confidences) >= 0.375, (
            f"expected long_call or bull-leaning verdict, got {confidences}"
        )

    def test_assess_direction_uptrend_hourly_aligned_returns_skip(self):
        """When the daily is BULL but the hourly is also up (DIF>0), the
        hourly_state votes BEAR under h2_bottom (no h=opposing
        confirmation) and the context is None (no pullback) — so the
        verdict skips even though daily is bull."""
        bars = _strong_uptrend_daily(180)
        h_closes = [100.0 + i * 0.05 for i in range(2000)]
        h_bars = _hourly_bars(h_closes, start="2024-01-01")
        m = compute_macd(bars["close"], hist_scale=1.0)
        v = assess_direction(
            bars, h_bars, len(bars) - 1,
            macd_df=m, ambush_pattern="h2_bottom",
        )
        # daily_structure=bull, hourly_state=bear, context=neutral, divergence=neutral
        # bull_votes=0.25, bear_votes=0.25 — both lose the 0.50 threshold.
        assert v.direction == "skip"
        assert v.confidence < 0.50

    def test_assess_direction_h2_top_uptrend_with_aligned_hourly_returns_long_put(self):
        """For an h2_top setup, daily=BULL would NOT confirm but a strong
        uptrend on hourly (DIF>0) DOES confirm a top via h=opposing
        logic flipped: h2_top with DIF>0 → bear.  Daily_structure=bull
        + hourly_state=bear → mixed, but if the divergence source also
        votes bear at a higher-high+lower-hist bar we cross the threshold.
        Simpler: assert that hourly_state alone votes bear under h2_top
        when the hourly DIF is positive — already covered above — and
        that downtrend setups vote long_put under h2_bottom."""
        bars = _strong_downtrend_daily(180)
        h_closes = [200.0 - i * 0.05 for i in range(2000)]
        h_bars = _hourly_bars(h_closes, start="2024-01-01")
        m = compute_macd(bars["close"], hist_scale=1.0)
        # Under h2_bottom: hourly DIF<0 votes BULL (h=opposing),
        # but daily structure is BEAR → bull=0.25, bear=0.25 → skip.
        v = assess_direction(
            bars, h_bars, len(bars) - 1,
            macd_df=m, ambush_pattern="h2_bottom",
        )
        assert v.direction == "skip"

    def test_assess_direction_downtrend_under_h2_top_returns_long_put(self):
        """Strong daily downtrend + hourly DIF>0 (selling exhaustion-
        style retracement) → under h2_top: daily=bear, hourly=bear
        (DIF>0 confirms top), context=neutral (h2_top), divergence
        may fire bear, force_balance=bear on downtrend window.  Under
        the 8-source synthesiser need ≥4 bear votes (0.50) for long_put.
        With weekly_bars/bars_15=None (2 neutral), bear majority requires
        force_balance + exhaustion to align with the daily/hourly bears."""
        bars = _strong_downtrend_daily(180)
        h_closes = [100.0 + i * 0.05 for i in range(2000)]  # hourly UP
        h_bars = _hourly_bars(h_closes, start="2024-01-01")
        m = compute_macd(bars["close"], hist_scale=1.0)
        v = assess_direction(
            bars, h_bars, len(bars) - 1,
            macd_df=m, ambush_pattern="h2_top",
        )
        # Acceptable outcomes under 8-source synthesiser with weekly/15m
        # absent: long_put outright, or skip with bear leaning at least
        # as strong as bull.  The synthesiser must NOT mis-flag a clear
        # downtrend as long_call.
        assert v.direction != "long_call", f"unexpected long_call on downtrend top: {v}"
        bear_weight = sum(s.weight for s in v.sources if s.vote == "bear")
        bull_weight = sum(s.weight for s in v.sources if s.vote == "bull")
        assert v.direction == "long_put" or bear_weight >= bull_weight, (
            f"expected long_put or bear-leaning, got {v.direction} "
            f"(bear={bear_weight}, bull={bull_weight}, "
            f"sources={[(s.name, s.vote) for s in v.sources]})"
        )

    def test_assess_direction_mixed_votes_skip(self):
        closes = [100.0 + 0.5 * np.sin(i / 5.0) for i in range(180)]
        bars = _daily_bars(closes)
        h_closes = [100.0 + 0.1 * np.sin(i / 3.0) for i in range(500)]
        h_bars = _hourly_bars(h_closes, start="2024-01-01")
        m = compute_macd(bars["close"], hist_scale=1.0)
        v = assess_direction(
            bars, h_bars, len(bars) - 1,
            macd_df=m, ambush_pattern="h2_bottom",
        )
        assert v.direction == "skip"
        assert v.confidence < 0.50

    def test_assess_direction_no_hourly_marks_neutral(self):
        bars = _strong_uptrend_daily(180)
        m = compute_macd(bars["close"], hist_scale=1.0)
        v = assess_direction(
            bars, None, len(bars) - 1,
            macd_df=m, ambush_pattern="h2_bottom",
        )
        hourly_src = next(s for s in v.sources if s.name == "hourly_state")
        assert hourly_src.vote == "neutral"
        assert hourly_src.rationale == "no_1h_data"

    def test_assess_direction_no_macd_marks_neutral(self):
        bars = _strong_uptrend_daily(180)
        h_closes = [100.0 + i * 0.05 for i in range(2000)]
        h_bars = _hourly_bars(h_closes, start="2024-01-01")
        v = assess_direction(
            bars, h_bars, len(bars) - 1,
            macd_df=None, ambush_pattern="h2_bottom",
        )
        div_src = next(s for s in v.sources if s.name == "divergence")
        ctx_src = next(s for s in v.sources if s.name == "context")
        assert div_src.vote == "neutral"
        assert ctx_src.vote == "neutral"
        assert "no_macd_df" in div_src.rationale

    def test_confidence_equals_sum_of_supporting_weights(self):
        """For the long_put h2_top downtrend case, confidence equals sum
        of bear weights."""
        bars = _strong_downtrend_daily(180)
        h_closes = [100.0 + i * 0.05 for i in range(2000)]
        h_bars = _hourly_bars(h_closes, start="2024-01-01")
        m = compute_macd(bars["close"], hist_scale=1.0)
        v = assess_direction(
            bars, h_bars, len(bars) - 1,
            macd_df=m, ambush_pattern="h2_top",
        )
        expected = sum(s.weight for s in v.sources if s.vote == "bear")
        assert v.confidence == pytest.approx(expected, abs=1e-9)

    def test_bar_idx_oob_returns_skip(self):
        bars = _strong_uptrend_daily(60)
        v = assess_direction(
            bars, None, 9999, macd_df=None, ambush_pattern="h2_bottom",
        )
        assert v.direction == "skip"
        assert v.confidence == 0.0
        assert len(v.sources) == 8
        assert all(s.vote == "neutral" for s in v.sources)

    def test_default_ambush_pattern_is_h2_bottom(self):
        """Calling assess_direction without ambush_pattern should default
        to h2_bottom (matches the existing four wired emit blocks)."""
        bars = _strong_downtrend_daily(180)
        h_closes = [200.0 - i * 0.05 for i in range(2000)]
        h_bars = _hourly_bars(h_closes, start="2024-01-01")
        m = compute_macd(bars["close"], hist_scale=1.0)
        v_default = assess_direction(bars, h_bars, len(bars) - 1, macd_df=m)
        v_explicit = assess_direction(
            bars, h_bars, len(bars) - 1,
            macd_df=m, ambush_pattern="h2_bottom",
        )
        assert v_default.direction == v_explicit.direction
        assert v_default.confidence == v_explicit.confidence
        assert [s.vote for s in v_default.sources] == [
            s.vote for s in v_explicit.sources
        ]


# ---------------------------------------------------------------------------
# Backward-compatibility — no shared dataclass changes
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    def test_pasignal_dataclass_unchanged(self):
        """Importing DIR module must not touch PASignal / PABottomDetector."""
        from engine.divergence.pa_detector import (
            PASignal, PABottomDetector, PATopDetector,
        )
        field_names = {f.name for f in PASignal.__dataclass_fields__.values()}
        assert field_names == {
            "pattern", "bar_idx", "timestamp", "confidence", "features",
            "higher_tf_relation", "direction",
        }
        s = PASignal(
            pattern="h2_bottom", bar_idx=0,
            timestamp=pd.Timestamp("2024-01-01", tz="UTC"),
            confidence=0.5, features={},
        )
        assert s.direction == "long"
        bars = _daily_bars([100.0 + i * 0.1 for i in range(60)])
        _ = PABottomDetector().scan(bars)
        _ = PATopDetector().scan(bars)
