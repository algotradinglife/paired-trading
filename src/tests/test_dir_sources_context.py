"""Tests for engine.divergence.dir_sources_context.

Two helpers — ``force_balance_source`` and ``exhaustion_source`` —
return ``DirectionSource`` entries that the orchestrator will wire into
``assess_direction``'s source list.  Tests live here (not in the DIR
test module) because the wiring is not the parent module's job at this
step — Agent β only adds the source helpers + tests.

Coverage:
  1. force_balance: upswing → bull-on-bottom + bear-on-top? (polarity:
     bull-strength is bullish regardless of pattern — see module
     docstring).  Downswing → bear vote; flat → neutral.
  2. exhaustion: bull-exhausting top → bear-on-top + neutral-on-bottom;
     bear-exhausting bottom → bull-on-bottom + neutral-on-top;
     no-exhaustion → neutral.
  3. Edge case: insufficient history returns neutral with
     ``rationale="insufficient_history"``.
  4. Volume column absent: source still returns a vote with no crash.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.divergence.dir_sources_context import (
    _DEFAULT_WEIGHT,
    _EXHAUSTION_SCORE_THRESHOLD,
    _FORCE_RATIO_THRESHOLD,
    exhaustion_source,
    force_balance_source,
)
from engine.divergence.pa_direction_assessment import DirectionSource


# ---------------------------------------------------------------------------
# Bar builders
# ---------------------------------------------------------------------------


def _bars_from_ohlcv(
    rows: list[tuple[float, float, float, float, float]],
    *,
    start: str = "2024-01-02",
) -> pd.DataFrame:
    """Build a DataFrame from a list of (open, high, low, close, volume)."""
    n = len(rows)
    ts = pd.date_range(start, periods=n, freq="B", tz="UTC")
    o, h, l, c, v = zip(*rows) if n > 0 else ([], [], [], [], [])
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": list(o),
            "high": list(h),
            "low": list(l),
            "close": list(c),
            "volume": list(v),
        }
    ).reset_index(drop=True)


def _bull_window(n: int = 12) -> pd.DataFrame:
    """Strong bull window — every bar closes near its high after a long body."""
    rows: list[tuple[float, float, float, float, float]] = []
    price = 100.0
    for _ in range(n):
        o = price
        c = price + 2.0
        h = c + 0.2          # tiny upper wick
        l = o - 0.2          # tiny lower wick
        v = 1_500.0
        rows.append((o, h, l, c, v))
        price = c
    return _bars_from_ohlcv(rows)


def _bear_window(n: int = 12) -> pd.DataFrame:
    """Strong bear window — every bar closes near its low after a long body."""
    rows: list[tuple[float, float, float, float, float]] = []
    price = 100.0
    for _ in range(n):
        o = price
        c = price - 2.0
        h = o + 0.2
        l = c - 0.2
        v = 1_500.0
        rows.append((o, h, l, c, v))
        price = c
    return _bars_from_ohlcv(rows)


def _flat_window(n: int = 12) -> pd.DataFrame:
    """Tight oscillation around 100 — neither side dominates."""
    rows: list[tuple[float, float, float, float, float]] = []
    price = 100.0
    for i in range(n):
        # Alternating tiny up/down bodies of equal size.
        if i % 2 == 0:
            o, c = price, price + 0.05
        else:
            o, c = price, price - 0.05
        h = max(o, c) + 0.4
        l = min(o, c) - 0.4
        v = 1_000.0
        rows.append((o, h, l, c, v))
        price = c
    return _bars_from_ohlcv(rows)


def _bull_exhaustion_top_window(n: int = 8) -> pd.DataFrame:
    """Bull-exhausting top — early bull bars give way to wicky drift up.

    Engineered so that:
      * net price still moves up (price_trend > 0 → bull_price_gate fires)
      * bodies shrink (early big-body up bars, late tiny bodies)
      * upper wicks grow (rejection at highs late in the window)
      * volume falls
      * closes drift toward the lower half
    """
    rows: list[tuple[float, float, float, float, float]] = []
    price = 100.0
    # Early strong rally — 3 fat-body bull bars
    for _ in range(3):
        o = price
        c = price + 3.0
        h = c + 0.1
        l = o - 0.1
        rows.append((o, h, l, c, 2_000.0))
        price = c
    # Late drift — tiny bodies, huge upper wicks, low volume.  Each bar's
    # range encloses the previous close so the trend nominally continues
    # up while bodies fade.
    for i in range(n - 3):
        body = max(0.2 - i * 0.05, 0.05)
        o = price
        c = price + body
        h = c + 2.5 + i * 0.5      # large upper wick
        l = o - 0.05
        # Close near the bottom of the bar
        rows.append((o, h, l, c, 600.0 - i * 50.0))
        price = c
    return _bars_from_ohlcv(rows)


def _bear_exhaustion_bottom_window(n: int = 8) -> pd.DataFrame:
    """Bear-exhausting bottom — early bear bars give way to wicky drift down.

    Mirror image of ``_bull_exhaustion_top_window``.
    """
    rows: list[tuple[float, float, float, float, float]] = []
    price = 100.0
    for _ in range(3):
        o = price
        c = price - 3.0
        h = o + 0.1
        l = c - 0.1
        rows.append((o, h, l, c, 2_000.0))
        price = c
    for i in range(n - 3):
        body = max(0.2 - i * 0.05, 0.05)
        o = price
        c = price - body
        l = c - 2.5 - i * 0.5
        h = o + 0.05
        rows.append((o, h, l, c, 600.0 - i * 50.0))
        price = c
    return _bars_from_ohlcv(rows)


# ---------------------------------------------------------------------------
# force_balance_source
# ---------------------------------------------------------------------------


class TestForceBalance:
    def test_returns_direction_source(self):
        bars = _bull_window(10)
        src = force_balance_source(bars, len(bars) - 1, lookback=10)
        assert isinstance(src, DirectionSource)
        assert src.name == "force_balance"
        assert src.weight == _DEFAULT_WEIGHT

    def test_strong_upswing_votes_bull_on_h2_bottom(self):
        bars = _bull_window(10)
        src = force_balance_source(
            bars, len(bars) - 1, lookback=10, ambush_pattern="h2_bottom",
        )
        assert src.vote == "bull"
        assert "bull_strength=" in src.rationale
        assert "bear_strength=" in src.rationale
        assert "ratio=" in src.rationale
        assert "pattern=h2_bottom" in src.rationale

    def test_strong_upswing_still_votes_bull_on_h2_top(self):
        # Polarity convention: the source describes the ambient force
        # balance, not the pattern's expected direction.  A bull-leaning
        # window still says "bull" when evaluated under h2_top.
        bars = _bull_window(10)
        src = force_balance_source(
            bars, len(bars) - 1, lookback=10, ambush_pattern="h2_top",
        )
        assert src.vote == "bull"
        assert "pattern=h2_top" in src.rationale

    def test_strong_downswing_votes_bear_on_h2_bottom(self):
        bars = _bear_window(10)
        src = force_balance_source(
            bars, len(bars) - 1, lookback=10, ambush_pattern="h2_bottom",
        )
        assert src.vote == "bear"

    def test_strong_downswing_votes_bear_on_h2_top(self):
        bars = _bear_window(10)
        src = force_balance_source(
            bars, len(bars) - 1, lookback=10, ambush_pattern="h2_top",
        )
        assert src.vote == "bear"

    def test_flat_window_votes_neutral(self):
        bars = _flat_window(20)
        src = force_balance_source(bars, len(bars) - 1, lookback=10)
        assert src.vote == "neutral"

    def test_insufficient_history_returns_neutral(self):
        bars = _bull_window(5)
        src = force_balance_source(bars, len(bars) - 1, lookback=10)
        assert src.vote == "neutral"
        assert src.rationale == "insufficient_history"

    def test_missing_volume_column_no_crash(self):
        bars = _bull_window(10).drop(columns=["volume"])
        src = force_balance_source(bars, len(bars) - 1, lookback=10)
        # No crash; vote follows the remaining components.  A bull
        # window without volume is still strongly bull-tilted in the
        # other three components, so we expect bull (or at worst
        # neutral when ratio narrowly misses 1.5).
        assert src.vote in ("bull", "neutral")

    def test_ratio_threshold_is_15x(self):
        # Sanity — the module-level constant lines up with the docstring.
        assert _FORCE_RATIO_THRESHOLD == 1.5

    def test_unknown_ambush_pattern_returns_neutral(self):
        bars = _bull_window(10)
        src = force_balance_source(
            bars, len(bars) - 1, lookback=10,
            ambush_pattern="garbage",  # type: ignore[arg-type]
        )
        assert src.vote == "neutral"
        assert "unknown_ambush_pattern" in src.rationale


# ---------------------------------------------------------------------------
# exhaustion_source
# ---------------------------------------------------------------------------


class TestExhaustion:
    def test_returns_direction_source(self):
        bars = _bull_window(8)
        src = exhaustion_source(bars, len(bars) - 1, lookback=5)
        assert isinstance(src, DirectionSource)
        assert src.name == "exhaustion"
        assert src.weight == _DEFAULT_WEIGHT

    def test_bull_exhausting_top_votes_bear_on_h2_top(self):
        bars = _bull_exhaustion_top_window(8)
        src = exhaustion_source(
            bars, len(bars) - 1, lookback=5, ambush_pattern="h2_top",
        )
        assert src.vote == "bear"
        # Both scores must appear in the rationale per the task spec.
        assert "bull_ex=" in src.rationale
        assert "bear_ex=" in src.rationale

    def test_bull_exhausting_at_bottom_votes_neutral(self):
        bars = _bull_exhaustion_top_window(8)
        src = exhaustion_source(
            bars, len(bars) - 1, lookback=5, ambush_pattern="h2_bottom",
        )
        # A bull exhausting at a bottom is NOT a buy signal.
        assert src.vote == "neutral"
        assert "bull_ex=" in src.rationale
        assert "bear_ex=" in src.rationale

    def test_bear_exhausting_bottom_votes_bull_on_h2_bottom(self):
        bars = _bear_exhaustion_bottom_window(8)
        src = exhaustion_source(
            bars, len(bars) - 1, lookback=5, ambush_pattern="h2_bottom",
        )
        assert src.vote == "bull"
        assert "bull_ex=" in src.rationale
        assert "bear_ex=" in src.rationale

    def test_bear_exhausting_at_top_votes_neutral(self):
        bars = _bear_exhaustion_bottom_window(8)
        src = exhaustion_source(
            bars, len(bars) - 1, lookback=5, ambush_pattern="h2_top",
        )
        assert src.vote == "neutral"
        assert "bull_ex=" in src.rationale
        assert "bear_ex=" in src.rationale

    def test_no_exhaustion_votes_neutral(self):
        # A flat window has neither bull nor bear exhaustion.
        bars = _flat_window(20)
        src = exhaustion_source(bars, len(bars) - 1, lookback=5)
        assert src.vote == "neutral"
        assert "no_exhaustion" in src.rationale
        # Even on a no-fire vote, both scores still appear so reviewers
        # can see why we abstained.
        assert "bull_ex=" in src.rationale
        assert "bear_ex=" in src.rationale

    def test_strong_uniform_uptrend_does_not_fire(self):
        # Long strong uptrend with growing bodies = no bull exhaustion
        # signal — bull is alive, not dying.
        bars = _bull_window(10)
        src = exhaustion_source(
            bars, len(bars) - 1, lookback=5, ambush_pattern="h2_top",
        )
        assert src.vote == "neutral"

    def test_insufficient_history_returns_neutral(self):
        bars = _bull_window(3)
        src = exhaustion_source(bars, len(bars) - 1, lookback=5)
        assert src.vote == "neutral"
        assert src.rationale == "insufficient_history"

    def test_missing_volume_column_no_crash(self):
        bars = _bull_exhaustion_top_window(8).drop(columns=["volume"])
        src = exhaustion_source(
            bars, len(bars) - 1, lookback=5, ambush_pattern="h2_top",
        )
        # No crash; result should still meaningfully read as bull
        # exhaustion (the structural cues are still present).  We assert
        # bear vote on h2_top, but accept neutral if the missing volume
        # component lowers the score below 0.6 — both are valid.
        assert src.vote in ("bear", "neutral")

    def test_score_threshold_is_06(self):
        # Sanity — the module-level constant lines up with the task spec.
        assert _EXHAUSTION_SCORE_THRESHOLD == 0.6

    def test_unknown_ambush_pattern_returns_neutral(self):
        bars = _bull_window(10)
        src = exhaustion_source(
            bars, len(bars) - 1, lookback=5,
            ambush_pattern="garbage",  # type: ignore[arg-type]
        )
        assert src.vote == "neutral"
        assert "unknown_ambush_pattern" in src.rationale


# ---------------------------------------------------------------------------
# Polarity matrix — explicit cross-check
# ---------------------------------------------------------------------------


class TestPolarityMatrix:
    """Spell the bull-exhaustion × pattern matrix in one place.

        pattern    | bull_exhaustion | bear_exhaustion
        -----------+-----------------+-----------------
        h2_bottom  | neutral         | bull
        h2_top     | bear            | neutral
    """

    @pytest.mark.parametrize(
        "pattern,window_builder,expected_vote",
        [
            ("h2_bottom", _bull_exhaustion_top_window, "neutral"),
            ("h2_top",    _bull_exhaustion_top_window, "bear"),
            ("h2_bottom", _bear_exhaustion_bottom_window, "bull"),
            ("h2_top",    _bear_exhaustion_bottom_window, "neutral"),
        ],
    )
    def test_matrix_cell(self, pattern, window_builder, expected_vote):
        bars = window_builder(8)
        src = exhaustion_source(
            bars, len(bars) - 1, lookback=5, ambush_pattern=pattern,
        )
        assert src.vote == expected_vote, (
            f"pattern={pattern} window={window_builder.__name__} "
            f"got vote={src.vote} rationale={src.rationale}"
        )
