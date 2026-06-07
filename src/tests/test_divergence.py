"""Unit tests for engine/divergence."""

from __future__ import annotations

import pandas as pd
from engine.divergence.downstream_policies import apply_policy
import pytest
from engine.features.swing_context import compute_swing_context
from engine.divergence.pa_detector import PABottomDetector, PASignal
from engine.divergence.bpull_detector import BPullDetector, BPullSignal

from engine.divergence.comparator import compare
from engine.divergence.detector import (
    detect_all_divergences,
    detect_intra_cycle,
    detect_inter_cycle,
)
from engine.divergence.direction_gate import (
    apply_direction_gate,
    gate_signals,
)
from engine.divergence.events import (
    CycleEvent,
    HeapEvent,
    build_cycle_events,
    build_heap_events,
)
from engine.divergence.signal import (
    AmplitudeSide,
    DivergenceSignal,
    PriceSide,
)
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Comparator
# ---------------------------------------------------------------------------

class TestCompare:
    def test_standard_top_divergence(self):
        # Price broke higher, amplitude decayed
        result = compare(
            direction="top",
            amplitude_ref=10.0,
            amplitude_cand=6.0,
            price_extreme_ref=100.0,
            price_extreme_cand=105.0,
        )
        assert result.subtype == "standard"
        assert result.is_new_price_extreme is True
        assert result.decay_ratio == pytest.approx(0.4)
        assert result.confidence > 0.0

    def test_standard_bottom_divergence(self):
        result = compare(
            direction="bottom",
            amplitude_ref=10.0,
            amplitude_cand=6.0,
            price_extreme_ref=100.0,
            price_extreme_cand=95.0,  # lower low
        )
        assert result.subtype == "standard"
        assert result.is_new_price_extreme is True

    def test_weakness_top(self):
        # Amplitude decayed but price didn't break
        result = compare(
            direction="top",
            amplitude_ref=10.0,
            amplitude_cand=6.0,
            price_extreme_ref=100.0,
            price_extreme_cand=98.0,  # price LOWER than ref
        )
        assert result.subtype == "weakness"
        assert result.is_new_price_extreme is False

    def test_hidden_amplitude_near_zero(self):
        # Amplitude essentially zero
        result = compare(
            direction="top",
            amplitude_ref=10.0,
            amplitude_cand=0.1,  # 1% of ref
            price_extreme_ref=100.0,
            price_extreme_cand=105.0,
        )
        assert result.subtype == "hidden"
        assert result.is_hidden is True

    def test_non_divergence_when_candidate_exceeds(self):
        result = compare(
            direction="top",
            amplitude_ref=10.0,
            amplitude_cand=15.0,
            price_extreme_ref=100.0,
            price_extreme_cand=105.0,
        )
        assert result.subtype == "non_divergence"

    def test_degenerate_zero_reference(self):
        result = compare(
            direction="top",
            amplitude_ref=0.0,
            amplitude_cand=5.0,
            price_extreme_ref=100.0,
            price_extreme_cand=105.0,
        )
        assert result.subtype == "none"
        assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# Intra-cycle detector
# ---------------------------------------------------------------------------

class TestDetectIntraCycle:
    def _df(self, n: int) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC"),
                "high": [100.0] * n,
                "low": [100.0] * n,
            }
        )

    def test_intra_cycle_standard_top(self):
        df = self._df(20)
        # 2 positive heaps in same cycle: peaks decay, prices rise
        heaps = [
            HeapEvent(
                heap_id=0, sign=1, cycle_id=0, segment_id=0,
                start_idx=0, end_idx=4, bars_in_heap=5,
                peak_abs_hist=10.0, peak_bar_idx=2,
                max_high=100.0, min_low=98.0,
                is_continuous_gap=False,
            ),
            HeapEvent(
                heap_id=1, sign=1, cycle_id=0, segment_id=0,
                start_idx=10, end_idx=14, bars_in_heap=5,
                peak_abs_hist=6.0, peak_bar_idx=12,
                max_high=105.0, min_low=102.0,
                is_continuous_gap=False,
            ),
        ]
        signals = detect_intra_cycle(heaps, "1D", df)
        assert len(signals) == 1
        sig = signals[0]
        assert sig.level == "intra_cycle"
        assert sig.subtype == "standard"
        assert sig.direction == "top"
        assert sig.confidence > 0.0

    def test_no_divergence_when_candidate_exceeds(self):
        df = self._df(20)
        # heap2 peak > heap1 peak → reset, no divergence emitted
        heaps = [
            HeapEvent(
                heap_id=0, sign=1, cycle_id=0, segment_id=0,
                start_idx=0, end_idx=4, bars_in_heap=5,
                peak_abs_hist=6.0, peak_bar_idx=2,
                max_high=100.0, min_low=98.0,
                is_continuous_gap=False,
            ),
            HeapEvent(
                heap_id=1, sign=1, cycle_id=0, segment_id=0,
                start_idx=10, end_idx=14, bars_in_heap=5,
                peak_abs_hist=10.0, peak_bar_idx=12,
                max_high=105.0, min_low=102.0,
                is_continuous_gap=False,
            ),
        ]
        signals = detect_intra_cycle(heaps, "1D", df)
        assert len(signals) == 0

    def test_different_cycles_not_compared(self):
        df = self._df(30)
        # Two heaps in DIFFERENT cycles → not compared
        heaps = [
            HeapEvent(
                heap_id=0, sign=1, cycle_id=0, segment_id=0,
                start_idx=0, end_idx=4, bars_in_heap=5,
                peak_abs_hist=10.0, peak_bar_idx=2,
                max_high=100.0, min_low=98.0,
                is_continuous_gap=False,
            ),
            HeapEvent(
                heap_id=1, sign=1, cycle_id=1, segment_id=0,
                start_idx=15, end_idx=19, bars_in_heap=5,
                peak_abs_hist=6.0, peak_bar_idx=17,
                max_high=105.0, min_low=102.0,
                is_continuous_gap=False,
            ),
        ]
        signals = detect_intra_cycle(heaps, "1D", df)
        assert len(signals) == 0

    def test_opposite_sign_heaps_not_compared(self):
        df = self._df(20)
        heaps = [
            HeapEvent(
                heap_id=0, sign=1, cycle_id=0, segment_id=0,
                start_idx=0, end_idx=4, bars_in_heap=5,
                peak_abs_hist=10.0, peak_bar_idx=2,
                max_high=100.0, min_low=98.0,
                is_continuous_gap=False,
            ),
            HeapEvent(
                heap_id=1, sign=-1, cycle_id=0, segment_id=0,
                start_idx=10, end_idx=14, bars_in_heap=5,
                peak_abs_hist=6.0, peak_bar_idx=12,
                max_high=105.0, min_low=92.0,
                is_continuous_gap=False,
            ),
        ]
        signals = detect_intra_cycle(heaps, "1D", df)
        # Opposite sign → not the same group → no signal (only one in each group)
        assert len(signals) == 0


# ---------------------------------------------------------------------------
# Inter-cycle detector
# ---------------------------------------------------------------------------

class TestDetectInterCycle:
    def _df(self, n: int) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC"),
                "high": [100.0] * n,
                "low": [100.0] * n,
            }
        )

    def test_inter_cycle_standard_top(self):
        df = self._df(30)
        cycles = [
            CycleEvent(
                cycle_id=0, segment_id=0, segment_direction="up",
                start_idx=0, end_idx=10, bars_in_cycle=11,
                peak_abs_dif=10.0, peak_bar_idx=5, reference_heap_id=0,
                max_high=100.0, min_low=95.0,
                is_completed=True,
            ),
            CycleEvent(
                cycle_id=1, segment_id=0, segment_direction="up",
                start_idx=15, end_idx=25, bars_in_cycle=11,
                peak_abs_dif=6.0, peak_bar_idx=20, reference_heap_id=2,
                max_high=105.0, min_low=98.0,
                is_completed=True,
            ),
        ]
        signals = detect_inter_cycle(cycles, "1D", df)
        assert len(signals) >= 1
        # Should find a top divergence (price ↑, amplitude ↓)
        top_signal = next((s for s in signals if s.direction == "top"), None)
        assert top_signal is not None
        assert top_signal.subtype == "standard"


# ---------------------------------------------------------------------------
# End-to-end integration with real-ish data
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_pipeline_on_synthetic_series(self):
        """Build a small synthetic series with a clear top divergence pattern."""
        import numpy as np

        from engine.features.macd import macd
        from engine.features.streams import compute_feature_streams
        from engine.units.snapshot import compute_unit_metadata

        # Synthesize: price ramp + slight pullback + another ramp to higher high
        rng = np.random.default_rng(42)
        n = 200
        trend1 = np.linspace(100, 110, 80)
        pullback = np.linspace(110, 105, 30)
        trend2 = np.linspace(105, 112, 90)
        close_raw = np.concatenate([trend1, pullback, trend2])
        close = pd.Series(close_raw + rng.normal(0, 0.3, len(close_raw)))

        ohlc = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=len(close), freq="D", tz="UTC"),
            "high": close.values + 0.5,
            "low": close.values - 0.5,
            "close": close.values,
        })

        macd_df = macd(close, hist_scale=1.0)
        streams = compute_feature_streams(close, macd_df["dif"], macd_df["dea"], macd_df["hist"])
        units = compute_unit_metadata(
            macd_df["dif"], macd_df["dea"], macd_df["hist"], streams["dif_proximity_zero"]
        )

        signals = detect_all_divergences(
            units_df=units,
            ohlc=ohlc,
            dif=macd_df["dif"],
            hist=macd_df["hist"],
            level_id="1D",
        )

        # Should produce some signals (we constructed a top-divergence-like structure)
        assert isinstance(signals, list)
        # All signals must have valid fields
        for s in signals:
            assert 0.0 <= s.confidence <= 1.0
            assert s.level in ("intra_cycle", "intra_cycle_hist", "inter_cycle", "inter_segment")
            assert s.subtype in ("standard", "weakness", "hidden")
            assert s.direction in ("top", "bottom")


# ---------------------------------------------------------------------------
# direction_gate per-instrument-class behavior
# ---------------------------------------------------------------------------

def _mock_top_signal(subtype: str = "weakness", level: str = "inter_segment",
                     is_continuous_gap: bool | None = None, conf: float = 0.80) -> DivergenceSignal:
    return DivergenceSignal(
        level=level, subtype=subtype, direction="top",
        level_id="D", timestamp=datetime.now(timezone.utc),
        candidate_bar_idx=10, reference_bar_idx=5,
        container_type="heap", container_segment_id=1, reference_id=0, candidate_id=1,
        price_side=PriceSide(reference_value=100.0, candidate_value=99.0, is_new_extreme=False),
        amplitude_side=AmplitudeSide(reference_value=2.0, candidate_value=1.0, decay_ratio=0.5),
        confidence=conf,
        is_continuous_gap=is_continuous_gap,
    )


class TestDirectionGateInstrumentClass:
    def test_us_equity_de_weights_top_weakness_inter_segment(self):
        # US: top + weakness × inter_segment = 0.7 × 0.5 = 0.35
        sig = _mock_top_signal(subtype="weakness", level="inter_segment", conf=0.80)
        adj = apply_direction_gate(sig, instrument_class="us_equity")
        assert adj == pytest.approx(0.80 * 0.7 * 0.5, abs=1e-6)

    def test_cn_futures_passes_through_top_unchanged(self):
        # CN: same signal should pass through (multipliers all 1.0)
        sig = _mock_top_signal(subtype="weakness", level="inter_segment", conf=0.80)
        adj = apply_direction_gate(sig, instrument_class="cn_futures")
        assert adj == 0.80

    def test_us_equity_drops_top_hidden_to_zero(self):
        # US: top + hidden multiplier = 0.0
        sig = _mock_top_signal(subtype="hidden", conf=0.95)
        adj = apply_direction_gate(sig, instrument_class="us_equity")
        assert adj == 0.0

    def test_cn_futures_keeps_top_hidden(self):
        # CN: same signal preserved
        sig = _mock_top_signal(subtype="hidden", conf=0.95)
        adj = apply_direction_gate(sig, instrument_class="cn_futures")
        assert adj == 0.95

    def test_bottom_unchanged_in_both_classes(self):
        sig = _mock_top_signal(subtype="weakness", conf=0.80)
        sig_bottom = sig.model_copy(update={"direction": "bottom"})
        assert apply_direction_gate(sig_bottom, instrument_class="us_equity") == 0.80
        assert apply_direction_gate(sig_bottom, instrument_class="cn_futures") == 0.80

    def test_gate_signals_drops_below_threshold_us_only(self):
        # Top + hidden in US → confidence 0.0 → dropped
        # Top + hidden in CN → confidence preserved → kept
        sig = _mock_top_signal(subtype="hidden", conf=0.80)
        us_out = gate_signals([sig], instrument_class="us_equity")
        cn_out = gate_signals([sig], instrument_class="cn_futures")
        assert len(us_out) == 0
        assert len(cn_out) == 1
        assert cn_out[0].confidence == 0.80

    def test_unknown_class_raises(self):
        sig = _mock_top_signal()
        with pytest.raises(ValueError, match="instrument_class"):
            apply_direction_gate(sig, instrument_class="crypto")  # type: ignore[arg-type]

    def test_default_is_us_equity(self):
        sig = _mock_top_signal(subtype="weakness", level="inter_segment", conf=0.80)
        adj_default = apply_direction_gate(sig)
        adj_us = apply_direction_gate(sig, instrument_class="us_equity")
        assert adj_default == adj_us


def _ohlc_bars(*rows: tuple[float, float, float, float]) -> pd.DataFrame:
    """Build an OHLC DataFrame from tuples of (open, high, low, close)."""
    return pd.DataFrame([
        {"timestamp": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=i),
         "open": o, "high": h, "low": l, "close": c, "volume": 0}
        for i, (o, h, l, c) in enumerate(rows)
    ])


class TestCandidateContextFeatures:
    """Z1: candle-geometry annotations on the bar that produced the price extreme.

    `candidate_rejection_wick_ratio` measures how much of the bar's range
    is the signal-direction-side wick (upper wick for tops, lower wick
    for bottoms). Z roadmap step 1 of stepping out of pure-MACD scope
    into candle geometry.

    Codex 2026-05-25 review caveat: the wick must be measured on the bar
    that produced the container's price extreme (max-high for top,
    min-low for bottom), NOT on the container's last bar. The extreme
    can occur mid-container while the container closes elsewhere.
    """

    def test_top_with_big_upper_wick_single_bar(self):
        from engine.divergence.detector import _candidate_context_features
        # bar: O=100 H=110 L=99 C=101 — upper wick = 110-101 = 9; range 11
        ohlc = _ohlc_bars((100, 110, 99, 101))
        feats = _candidate_context_features("top", 0, 0, ohlc)
        assert feats is not None
        assert feats["candidate_rejection_wick_ratio"] == pytest.approx(9 / 11, abs=1e-6)

    def test_bottom_with_big_lower_wick_single_bar(self):
        from engine.divergence.detector import _candidate_context_features
        # bar: O=100 H=101 L=90 C=99 — lower wick = 99-90 = 9; range 11
        ohlc = _ohlc_bars((100, 101, 90, 99))
        feats = _candidate_context_features("bottom", 0, 0, ohlc)
        assert feats["candidate_rejection_wick_ratio"] == pytest.approx(9 / 11, abs=1e-6)

    def test_top_picks_max_high_bar_not_last_bar(self):
        """Container spans 3 bars; max-high is on the MIDDLE bar with a
        long upper wick (the rejection event); the container closes on
        the last bar (uneventful inside bar). Wick must be measured on
        the middle bar, not the closing bar."""
        from engine.divergence.detector import _candidate_context_features
        ohlc = _ohlc_bars(
            (100, 105, 99, 103),   # bar 0: ordinary
            (103, 120, 102, 104),  # bar 1: MAX HIGH 120, long upper wick (120-104=16, range 18)
            (104, 106, 103, 105),  # bar 2: container's last bar (uneventful)
        )
        feats = _candidate_context_features("top", 0, 2, ohlc)
        assert feats["candidate_rejection_wick_ratio"] == pytest.approx(16 / 18, abs=1e-6)

    def test_bottom_picks_min_low_bar_not_last_bar(self):
        from engine.divergence.detector import _candidate_context_features
        ohlc = _ohlc_bars(
            (100, 101, 95, 96),    # bar 0: ordinary
            (96, 97, 80, 96),      # bar 1: MIN LOW 80, long lower wick (96-80=16, range 17)
            (96, 98, 94, 97),      # bar 2: container's last bar
        )
        feats = _candidate_context_features("bottom", 0, 2, ohlc)
        assert feats["candidate_rejection_wick_ratio"] == pytest.approx(16 / 17, abs=1e-6)

    def test_top_no_upper_wick(self):
        from engine.divergence.detector import _candidate_context_features
        # bar: O=100 H=101 L=99 C=101 — high == max(O,C), no upper wick
        ohlc = _ohlc_bars((100, 101, 99, 101))
        feats = _candidate_context_features("top", 0, 0, ohlc)
        assert feats["candidate_rejection_wick_ratio"] == 0.0

    def test_zero_range_bar_gives_zero(self):
        from engine.divergence.detector import _candidate_context_features
        ohlc = _ohlc_bars((100, 100, 100, 100))
        feats = _candidate_context_features("top", 0, 0, ohlc)
        assert feats["candidate_rejection_wick_ratio"] == 0.0
        feats_b = _candidate_context_features("bottom", 0, 0, ohlc)
        assert feats_b["candidate_rejection_wick_ratio"] == 0.0

    def test_missing_open_close_returns_none(self):
        from engine.divergence.detector import _candidate_context_features
        ohlc = pd.DataFrame([{
            "timestamp": pd.Timestamp("2026-01-01", tz="UTC"),
            "high": 110, "low": 99,
        }])
        assert _candidate_context_features("top", 0, 0, ohlc) is None

    def test_full_body_no_wick_either_side(self):
        from engine.divergence.detector import _candidate_context_features
        # Marubozu-like: O=L, C=H — no wick at all on either side
        ohlc = _ohlc_bars((99, 110, 99, 110))
        feats_top = _candidate_context_features("top", 0, 0, ohlc)
        feats_bot = _candidate_context_features("bottom", 0, 0, ohlc)
        assert feats_top["candidate_rejection_wick_ratio"] == 0.0
        assert feats_bot["candidate_rejection_wick_ratio"] == 0.0

    def test_inverted_range_returns_none(self):
        from engine.divergence.detector import _candidate_context_features
        ohlc = _ohlc_bars((100, 105, 99, 102))
        # start > end is defensive guard, not a real case — should return None
        assert _candidate_context_features("top", 5, 2, ohlc) is None

    def test_nan_high_in_window_does_not_get_selected(self):
        """Codex 2026-05-25 caveat: numpy argmax treats NaN as max; using
        nanargmax keeps the helper aligned with the comparator's NaN-skip
        semantics. Window has NaN high on bar 1 + finite extreme on bar 2.
        The wick must come from bar 2, not bar 1."""
        from engine.divergence.detector import _candidate_context_features
        import math
        ohlc = pd.DataFrame([
            {"timestamp": pd.Timestamp("2026-01-01", tz="UTC"),
             "open": 100, "high": 105, "low": 99, "close": 103, "volume": 0},
            {"timestamp": pd.Timestamp("2026-01-02", tz="UTC"),
             "open": 103, "high": math.nan, "low": 102, "close": 104, "volume": 0},
            {"timestamp": pd.Timestamp("2026-01-03", tz="UTC"),
             "open": 104, "high": 120, "low": 103, "close": 105, "volume": 0},  # MAX, big upper wick
        ])
        feats = _candidate_context_features("top", 0, 2, ohlc)
        # Bar 2 wick: 120 - max(104,105) = 15; range = 17 → 15/17
        assert feats is not None
        assert feats["candidate_rejection_wick_ratio"] == pytest.approx(15 / 17, abs=1e-6)

    def test_all_nan_window_returns_none(self):
        from engine.divergence.detector import _candidate_context_features
        import math
        ohlc = pd.DataFrame([
            {"timestamp": pd.Timestamp("2026-01-01", tz="UTC"),
             "open": 100, "high": math.nan, "low": 99, "close": 100, "volume": 0},
            {"timestamp": pd.Timestamp("2026-01-02", tz="UTC"),
             "open": 100, "high": math.nan, "low": 99, "close": 100, "volume": 0},
        ])
        # All-NaN highs → can't pick a top extreme → return None
        assert _candidate_context_features("top", 0, 1, ohlc) is None

    def test_extreme_bar_with_nan_ohlc_returns_none(self):
        """Even if argmax picks a valid bar, if its OHLC has NaN in
        open/close the ratio is undefined — return None not fabricated zero."""
        from engine.divergence.detector import _candidate_context_features
        import math
        ohlc = pd.DataFrame([
            {"timestamp": pd.Timestamp("2026-01-01", tz="UTC"),
             "open": math.nan, "high": 120, "low": 99, "close": 105, "volume": 0},
        ])
        assert _candidate_context_features("top", 0, 0, ohlc) is None

    def test_z2a_invalidation_level_top_equals_extreme_high(self):
        from engine.divergence.detector import _candidate_context_features
        ohlc = _ohlc_bars(
            (100, 105, 99, 103),
            (103, 120, 102, 104),   # max-high 120
            (104, 106, 103, 105),
        )
        feats = _candidate_context_features("top", 0, 2, ohlc)
        assert feats["invalidation_level"] == 120.0

    def test_z2a_invalidation_level_bottom_equals_extreme_low(self):
        from engine.divergence.detector import _candidate_context_features
        ohlc = _ohlc_bars(
            (100, 101, 95, 96),
            (96, 97, 80, 96),       # min-low 80
            (96, 98, 94, 97),
        )
        feats = _candidate_context_features("bottom", 0, 2, ohlc)
        assert feats["invalidation_level"] == 80.0

    def test_z2b_prior_swing_distance_top_positive_when_rally_extended(self):
        """Top divergence: candidate extreme (120) > reference (100) →
        rally extended by 20% → positive sign."""
        from engine.divergence.detector import _candidate_context_features
        ohlc = _ohlc_bars((100, 120, 99, 105))
        feats = _candidate_context_features("top", 0, 0, ohlc, reference_price=100.0)
        assert feats["prior_swing_distance_pct"] == pytest.approx(20.0, abs=1e-6)

    def test_z2b_prior_swing_distance_bottom_positive_when_decline_extended(self):
        """Bottom divergence: candidate extreme (80) < reference (100) →
        decline extended by 20% → positive sign (direction-consistent)."""
        from engine.divergence.detector import _candidate_context_features
        ohlc = _ohlc_bars((100, 101, 80, 95))
        feats = _candidate_context_features("bottom", 0, 0, ohlc, reference_price=100.0)
        assert feats["prior_swing_distance_pct"] == pytest.approx(20.0, abs=1e-6)

    def test_z2b_skipped_when_reference_not_supplied(self):
        from engine.divergence.detector import _candidate_context_features
        ohlc = _ohlc_bars((100, 120, 99, 105))
        feats = _candidate_context_features("top", 0, 0, ohlc)
        assert "prior_swing_distance_pct" not in feats

    def test_z2b_skipped_on_zero_reference(self):
        from engine.divergence.detector import _candidate_context_features
        ohlc = _ohlc_bars((100, 120, 99, 105))
        feats = _candidate_context_features("top", 0, 0, ohlc, reference_price=0.0)
        # zero ref → divide-by-zero risk → skip key entirely
        assert "prior_swing_distance_pct" not in feats

    def test_z2_full_feature_set_when_reference_supplied(self):
        """All three Z keys present together on a healthy top with reference."""
        from engine.divergence.detector import _candidate_context_features
        ohlc = _ohlc_bars((100, 110, 99, 101))
        feats = _candidate_context_features("top", 0, 0, ohlc, reference_price=95.0)
        assert set(feats) == {
            "candidate_rejection_wick_ratio",
            "invalidation_level",
            "prior_swing_distance_pct",
        }

    def test_z3_candidate_volume_ratio_above_average(self):
        """Z3: extreme bar volume / trailing-20-bar mean. Extreme bar at
        index 20 has volume 200; prior 20 bars have volume 100 each →
        ratio = 200/100 = 2.0."""
        from engine.divergence.detector import _candidate_context_features
        # 20 trailing bars (idx 0-19) + 1 extreme bar (idx 20)
        bars = []
        for i in range(20):
            bars.append({
                "timestamp": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=i),
                "open": 100, "high": 101, "low": 99, "close": 100, "volume": 100,
            })
        # Extreme bar with 2x volume
        bars.append({
            "timestamp": pd.Timestamp("2026-01-21", tz="UTC"),
            "open": 100, "high": 110, "low": 99, "close": 101, "volume": 200,
        })
        ohlc = pd.DataFrame(bars)
        feats = _candidate_context_features("top", 20, 20, ohlc)
        assert feats["candidate_volume_ratio"] == pytest.approx(2.0, abs=1e-6)

    def test_z3_skipped_when_lookback_insufficient(self):
        """When extreme bar is too early (idx < VOLUME_LOOKBACK_BARS) the
        volume ratio is undefined — skip key entirely."""
        from engine.divergence.detector import _candidate_context_features
        ohlc = _ohlc_bars(
            (100, 105, 99, 101),
            (101, 110, 100, 102),
        )
        feats = _candidate_context_features("top", 0, 1, ohlc)
        assert "candidate_volume_ratio" not in feats

    def test_z3_skipped_when_volume_column_missing(self):
        from engine.divergence.detector import _candidate_context_features
        bars = []
        for i in range(25):
            bars.append({
                "timestamp": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=i),
                "open": 100, "high": 101, "low": 99, "close": 100,
                # NOTE: no volume column
            })
        ohlc = pd.DataFrame(bars)
        feats = _candidate_context_features("top", 20, 20, ohlc)
        assert "candidate_volume_ratio" not in feats

    def test_z3_skipped_on_zero_lookback_volume(self):
        from engine.divergence.detector import _candidate_context_features
        bars = []
        for i in range(20):
            bars.append({
                "timestamp": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=i),
                "open": 100, "high": 101, "low": 99, "close": 100, "volume": 0,
            })
        bars.append({
            "timestamp": pd.Timestamp("2026-01-21", tz="UTC"),
            "open": 100, "high": 110, "low": 99, "close": 101, "volume": 100,
        })
        ohlc = pd.DataFrame(bars)
        feats = _candidate_context_features("top", 20, 20, ohlc)
        assert "candidate_volume_ratio" not in feats

    def test_z3_below_average_volume(self):
        """Verify sub-1.0 ratio also computed correctly (low-volume warning)."""
        from engine.divergence.detector import _candidate_context_features
        bars = []
        for i in range(20):
            bars.append({
                "timestamp": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=i),
                "open": 100, "high": 101, "low": 99, "close": 100, "volume": 200,
            })
        bars.append({
            "timestamp": pd.Timestamp("2026-01-21", tz="UTC"),
            "open": 100, "high": 110, "low": 99, "close": 101, "volume": 50,
        })
        ohlc = pd.DataFrame(bars)
        feats = _candidate_context_features("top", 20, 20, ohlc)
        # 50 / 200 = 0.25
        assert feats["candidate_volume_ratio"] == pytest.approx(0.25, abs=1e-6)

    def test_pandas_nullable_pdNA_returns_none(self):
        """Codex 2026-05-25 caveat: pandas nullable dtypes (Float64) emit
        pd.NA, and float(pd.NA) raises TypeError. The helper must reject
        before casting."""
        from engine.divergence.detector import _candidate_context_features
        ohlc = pd.DataFrame({
            "timestamp": pd.to_datetime(["2026-01-01"], utc=True),
            "open":  pd.array([pd.NA], dtype="Float64"),
            "high":  pd.array([120.0], dtype="Float64"),
            "low":   pd.array([99.0], dtype="Float64"),
            "close": pd.array([105.0], dtype="Float64"),
            "volume": [0],
        })
        # Should return None, NOT crash on float(pd.NA)
        assert _candidate_context_features("top", 0, 0, ohlc) is None


# ---------------------------------------------------------------------------
# CNI1 policy gate: bottom × h=opposing × DIF<0 sub-level disabled
# ---------------------------------------------------------------------------

def _mock_bottom_signal(level: str, h_rel: str | None, conf: float = 0.60) -> DivergenceSignal:
    ctx = {}
    if h_rel is not None:
        ctx["higher_relation"] = h_rel
    return DivergenceSignal(
        level=level, subtype="standard", direction="bottom",
        level_id="D", timestamp=datetime.now(timezone.utc),
        candidate_bar_idx=10, reference_bar_idx=5,
        container_type="heap", container_segment_id=1, reference_id=0, candidate_id=1,
        price_side=PriceSide(reference_value=100.0, candidate_value=99.0, is_new_extreme=True),
        amplitude_side=AmplitudeSide(reference_value=2.0, candidate_value=1.0, decay_ratio=0.5),
        confidence=conf,
        multi_tf_context=ctx if ctx else None,
    )


class TestCNI1Gate:
    """CNI1: bottom × h=opposing × DIF<0 sub-level → weight=0."""

    _DIF_NEG_LEVELS = ["intra_cycle_hist", "intra_cycle_dea", "intra_cycle_slope"]

    def test_cni1_blocks_opposing_dif_neg_sublevels(self):
        for level in self._DIF_NEG_LEVELS:
            sig = _mock_bottom_signal(level, h_rel="opposing")
            dec = apply_policy(sig, instrument_class="cn_index_futures")
            assert dec.weight == 0.0, f"expected block for {level} h=opposing"
            assert dec.rule_id == "CNI1-dif-neg-sublevel-disabled"

    def test_cni1_passes_supporting_dif_neg_sublevels(self):
        for level in self._DIF_NEG_LEVELS:
            sig = _mock_bottom_signal(level, h_rel="supporting")
            dec = apply_policy(sig, instrument_class="cn_index_futures")
            assert dec.weight != 0.0, f"supporting {level} should not be blocked"

    def test_cni1_passes_neutral_dif_neg_sublevels(self):
        for level in self._DIF_NEG_LEVELS:
            sig = _mock_bottom_signal(level, h_rel="neutral")
            dec = apply_policy(sig, instrument_class="cn_index_futures")
            assert dec.weight != 0.0, f"neutral {level} should not be blocked"

    def test_cni1_passes_no_context_dif_neg_sublevels(self):
        for level in self._DIF_NEG_LEVELS:
            sig = _mock_bottom_signal(level, h_rel=None)
            dec = apply_policy(sig, instrument_class="cn_index_futures")
            assert dec.weight != 0.0, f"no-context {level} should not be blocked"

    def test_cni1_passes_heap_level_opposing(self):
        sig = _mock_bottom_signal("intra_cycle", h_rel="opposing")
        dec = apply_policy(sig, instrument_class="cn_index_futures")
        assert dec.weight != 0.0

    def test_cni1_passes_inter_segment_opposing(self):
        sig = _mock_bottom_signal("inter_segment", h_rel="opposing")
        dec = apply_policy(sig, instrument_class="cn_index_futures")
        assert dec.weight != 0.0


def _mock_top_with_ctx(level: str, h_rel: str | None, conf: float = 0.60) -> DivergenceSignal:
    ctx = {}
    if h_rel is not None:
        ctx["higher_relation"] = h_rel
    return DivergenceSignal(
        level=level, subtype="standard", direction="top",
        level_id="D", timestamp=datetime.now(timezone.utc),
        candidate_bar_idx=10, reference_bar_idx=5,
        container_type="heap", container_segment_id=1, reference_id=0, candidate_id=1,
        price_side=PriceSide(reference_value=100.0, candidate_value=101.0, is_new_extreme=True),
        amplitude_side=AmplitudeSide(reference_value=2.0, candidate_value=1.0, decay_ratio=0.5),
        confidence=conf,
        multi_tf_context=ctx if ctx else None,
    )


class TestCNM1Gate:
    """CNM1: top × inter_segment → weight=0 for cn_metal_futures."""

    def test_cnm1_blocks_top_inter_segment(self):
        for h_rel in ["opposing", "supporting", "neutral", None]:
            sig = _mock_top_with_ctx("inter_segment", h_rel=h_rel)
            dec = apply_policy(sig, instrument_class="cn_metal_futures")
            assert dec.weight == 0.0, f"expected block for h_rel={h_rel}"
            assert dec.rule_id == "CNM1-top-inter-segment-disabled"

    def test_cnm1_passes_top_heap(self):
        sig = _mock_top_with_ctx("intra_cycle", h_rel="opposing")
        dec = apply_policy(sig, instrument_class="cn_metal_futures")
        assert dec.weight != 0.0

    def test_cnm1_passes_bottom_inter_segment(self):
        sig = _mock_bottom_signal("inter_segment", h_rel="opposing")
        dec = apply_policy(sig, instrument_class="cn_metal_futures")
        assert dec.weight != 0.0

    def test_cnm1_does_not_affect_cn_futures(self):
        sig = _mock_top_with_ctx("inter_segment", h_rel="opposing")
        dec = apply_policy(sig, instrument_class="cn_futures")
        assert dec.weight != 0.0, "CNM1 should not affect cn_futures"


# ---------------------------------------------------------------------------
# CN2 policy gate: bottom × intra_cycle_dea/slope → weight=0 for
# cn_futures and cn_metal_futures ONLY (not cn_index_futures, not czce)
# ---------------------------------------------------------------------------

class TestCN2Gate:
    """CN2: bottom × intra_cycle_dea or intra_cycle_slope → disabled."""

    _WEAK_LEVELS = ["intra_cycle_dea", "intra_cycle_slope"]

    def test_cn2_blocks_cn_futures(self):
        for level in self._WEAK_LEVELS:
            sig = _mock_bottom_signal(level, h_rel="opposing")
            dec = apply_policy(sig, instrument_class="cn_futures")
            assert dec.weight == 0.0, f"expected block for cn_futures/{level}"
            assert dec.rule_id == "CN2-bottom-weak-sublevel-disabled"

    def test_cn2_blocks_cn_metal_futures(self):
        for level in self._WEAK_LEVELS:
            sig = _mock_bottom_signal(level, h_rel="opposing")
            dec = apply_policy(sig, instrument_class="cn_metal_futures")
            assert dec.weight == 0.0, f"expected block for cn_metal_futures/{level}"
            assert dec.rule_id == "CN2-bottom-weak-sublevel-disabled"

    def test_cn2_does_not_block_cn_index_futures(self):
        """CNI1 governs cn_index_futures; CN2 must not interfere."""
        for level in self._WEAK_LEVELS:
            sig = _mock_bottom_signal(level, h_rel="supporting")
            dec = apply_policy(sig, instrument_class="cn_index_futures")
            assert dec.weight != 0.0, f"CN2 must not block cn_index_futures/{level}"
            assert dec.rule_id != "CN2-bottom-weak-sublevel-disabled"

    def test_cn2_does_not_block_czce(self):
        for level in self._WEAK_LEVELS:
            sig = _mock_bottom_signal(level, h_rel="opposing")
            dec = apply_policy(sig, instrument_class="czce")
            assert dec.weight != 0.0, f"CN2 must not block czce/{level}"

    def test_cn2_passes_strong_intra_cycle(self):
        """intra_cycle (without _dea/_slope suffix) must remain active."""
        sig = _mock_bottom_signal("intra_cycle", h_rel="opposing")
        dec = apply_policy(sig, instrument_class="cn_futures")
        assert dec.weight != 0.0
        assert dec.rule_id != "CN2-bottom-weak-sublevel-disabled"

    def test_cn2_passes_top_direction(self):
        """CN2 only gates bottom direction."""
        for level in self._WEAK_LEVELS:
            sig = _mock_top_with_ctx(level, h_rel="opposing")
            dec = apply_policy(sig, instrument_class="cn_futures")
            assert dec.rule_id != "CN2-bottom-weak-sublevel-disabled"

    def test_cn2_does_not_block_supporting_h_rel(self):
        """WF calibration is h=opposing only; supporting/neutral must pass through."""
        for level in self._WEAK_LEVELS:
            sig = _mock_bottom_signal(level, h_rel="supporting")
            dec = apply_policy(sig, instrument_class="cn_futures")
            assert dec.rule_id != "CN2-bottom-weak-sublevel-disabled", \
                f"CN2 must not block cn_futures/{level} when h=supporting"

    def test_cn2_does_not_block_neutral_h_rel(self):
        """WF calibration is h=opposing only; neutral h_rel must pass through."""
        for level in self._WEAK_LEVELS:
            sig = _mock_bottom_signal(level, h_rel="neutral")
            dec = apply_policy(sig, instrument_class="cn_futures")
            assert dec.rule_id != "CN2-bottom-weak-sublevel-disabled", \
                f"CN2 must not block cn_futures/{level} when h=neutral"


class TestPABottomDetectorSwingFilter:
    def _make_bars(self, n=60):
        """60 daily bars with a clear uptrend zigzag."""
        highs, lows = [], []
        for i in range(n):
            base = 100 + i * 0.5
            highs.append(base + (2 if i % 4 < 2 else 0.5))
            lows.append(base - (2 if i % 4 >= 2 else 0.5))
        return pd.DataFrame({
            "timestamp": pd.date_range("2023-01-01", periods=n, freq="D", tz="UTC"),
            "high": highs, "low": lows,
            "open": [h - 0.5 for h in highs],
            "close": [h - 0.5 for h in highs],
            "volume": [1000] * n,
        })

    def test_require_trend_uptrend_allows_uptrend_signals(self):
        bars = self._make_bars(60)
        ctx = compute_swing_context(bars, swing_n=2)
        det = PABottomDetector(
            min_h_legs=1, min_quality=0.0, ema_threshold=10.0,
            min_gap=1, require_trend={"uptrend"},
        )
        sigs = det.scan(bars, swing_context=ctx)
        for sig in sigs:
            assert sig.features.get("trend_structure") == "uptrend", \
                f"Signal trend_structure={sig.features.get('trend_structure')!r}"

    def test_require_trend_none_does_not_filter(self):
        bars = self._make_bars(60)
        ctx = compute_swing_context(bars, swing_n=2)
        det_all = PABottomDetector(
            min_h_legs=1, min_quality=0.0, ema_threshold=10.0,
            min_gap=1, require_trend=None,
        )
        det_up = PABottomDetector(
            min_h_legs=1, min_quality=0.0, ema_threshold=10.0,
            min_gap=1, require_trend={"uptrend"},
        )
        sigs_all = det_all.scan(bars, swing_context=ctx)
        sigs_up = det_up.scan(bars, swing_context=ctx)
        assert len(sigs_all) >= len(sigs_up)

    def test_signal_features_include_swing_fields(self):
        bars = self._make_bars(60)
        ctx = compute_swing_context(bars, swing_n=2)
        det = PABottomDetector(
            min_h_legs=1, min_quality=0.0, ema_threshold=10.0,
            min_gap=1,
        )
        sigs = det.scan(bars, swing_context=ctx)
        for sig in sigs:
            assert "trend_structure" in sig.features
            assert "leg_count_down" in sig.features
            assert "market_regime" in sig.features


def _make_pa_signal(
    trend: str = "uptrend",
    h_rel: str | None = "opposing",
    leg_count: int = 2,
) -> PASignal:
    return PASignal(
        pattern="h2_bottom",
        bar_idx=0,
        timestamp=pd.Timestamp("2024-01-01", tz="UTC"),
        confidence=0.6,
        features={
            "trend_structure": trend,
            "leg_count_down": leg_count,
            "market_regime": "trending",
            "h_leg_count": 2,
        },
        higher_tf_relation=h_rel,
    )


class TestPABottomDetectorPolicyWeight:
    def test_us_equity_uptrend_opposing_base(self):
        sig = _make_pa_signal("uptrend", "opposing", leg_count=2)
        w = PABottomDetector.policy_weight(sig, "us_equity")
        assert w == pytest.approx(0.80)

    def test_us_equity_uptrend_opposing_legs1_bonus(self):
        sig = _make_pa_signal("uptrend", "opposing", leg_count=1)
        w = PABottomDetector.policy_weight(sig, "us_equity")
        assert w == pytest.approx(0.90)

    def test_us_equity_uptrend_supporting(self):
        sig = _make_pa_signal("uptrend", "supporting", leg_count=2)
        w = PABottomDetector.policy_weight(sig, "us_equity")
        assert w == pytest.approx(0.40)

    def test_us_equity_downtrend_suppressed(self):
        sig = _make_pa_signal("downtrend", "opposing", leg_count=2)
        w = PABottomDetector.policy_weight(sig, "us_equity")
        assert w == pytest.approx(0.0)

    def test_us_equity_ranging_suppressed(self):
        sig = _make_pa_signal("ranging", "opposing", leg_count=2)
        w = PABottomDetector.policy_weight(sig, "us_equity")
        assert w == pytest.approx(0.0)

    def test_cn_metal_opposing_unchanged(self):
        sig = _make_pa_signal("uptrend", "opposing")
        w = PABottomDetector.policy_weight(sig, "cn_metal_futures")
        assert w == pytest.approx(0.75)

    def test_czce_suppressed(self):
        sig = _make_pa_signal("uptrend", "opposing")
        w = PABottomDetector.policy_weight(sig, "czce")
        assert w == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# BPullDetector tests
# ---------------------------------------------------------------------------

def _make_bpull_bars(n: int = 80) -> pd.DataFrame:
    """Bars with DIF>0 and price bouncing near EMA20.

    Price rises from 100 to ~140 over n bars (so DIF stays positive),
    with periodic dips to EMA20 every ~15 bars.
    """
    import numpy as np
    rng = np.random.default_rng(42)
    closes = []
    c = 100.0
    for i in range(n):
        # Long uptrend with periodic dips
        drift = 0.4
        noise = rng.normal(0, 0.5)
        if i % 15 == 14:
            c -= 3.0  # dip toward EMA20
        else:
            c += drift + noise
        c = max(c, 80.0)
        closes.append(c)
    closes = np.array(closes)
    highs = closes + rng.uniform(0.5, 1.5, n)
    lows = closes - rng.uniform(0.5, 2.5, n)
    opens = closes - rng.uniform(-0.5, 0.5, n)
    return pd.DataFrame({
        "timestamp": pd.date_range("2022-01-01", periods=n, freq="D", tz="UTC"),
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": [1000] * n,
    })


class TestBPullDetector:
    def test_scan_returns_list(self):
        bars = _make_bpull_bars(80)
        det = BPullDetector()
        sigs = det.scan(bars)
        assert isinstance(sigs, list)

    def test_signals_have_required_fields(self):
        bars = _make_bpull_bars(80)
        det = BPullDetector(min_gap=5)
        sigs = det.scan(bars)
        for sig in sigs:
            assert hasattr(sig, "bar_idx")
            assert hasattr(sig, "timestamp")
            assert hasattr(sig, "features")
            assert "dif" in sig.features
            assert "ema_touch_pct_actual" in sig.features
            assert "ema_floor_actual" in sig.features

    def test_all_signals_have_positive_dif(self):
        """Every BPull signal must fire on a bar where DIF>0."""
        from engine.features.macd import macd as compute_macd
        bars = _make_bpull_bars(80)
        det = BPullDetector(min_gap=5)
        sigs = det.scan(bars)
        if not sigs:
            return  # no signals is acceptable for this synthetic data
        md = compute_macd(bars["close"])
        for sig in sigs:
            d = float(md["dif"].iloc[sig.bar_idx])
            assert d > 0, f"Signal at bar {sig.bar_idx} has DIF={d:.4f} (must be >0)"

    def test_tight_touch_produces_fewer_signals(self):
        bars = _make_bpull_bars(80)
        det_loose = BPullDetector(ema_touch_pct=0.020, min_gap=5)
        det_tight = BPullDetector(ema_touch_pct=0.002, min_gap=5)
        n_loose = len(det_loose.scan(bars))
        n_tight = len(det_tight.scan(bars))
        assert n_tight <= n_loose

    def test_min_gap_enforced(self):
        bars = _make_bpull_bars(80)
        det = BPullDetector(ema_touch_pct=0.020, ema_floor_pct=0.10, min_gap=15)
        sigs = det.scan(bars)
        for i in range(1, len(sigs)):
            gap = sigs[i].bar_idx - sigs[i - 1].bar_idx
            assert gap >= 15, f"Gap {gap} < min_gap=15 between signals"

    def test_htf_relation_annotated_when_h_bars_provided(self):
        bars = _make_bpull_bars(80)
        # Make h_bars with DIF < 0 (many bars flat at a low level)
        h_closes = pd.Series([95.0] * 400)
        h_bars = pd.DataFrame({
            "timestamp": pd.date_range("2022-01-01", periods=400, freq="h", tz="UTC"),
            "close": h_closes,
        })
        det = BPullDetector(ema_touch_pct=0.020, min_gap=5)
        sigs = det.scan(bars, h_bars)
        for sig in sigs:
            # htf_relation must be set (not None) when h_bars supplied
            assert sig.higher_tf_relation is not None


class TestBPullDetectorPolicyWeight:
    def _make_sig(self, h_rel: str | None) -> BPullSignal:
        return BPullSignal(
            bar_idx=0,
            timestamp=pd.Timestamp("2024-01-01", tz="UTC"),
            features={"dif": 0.05, "ema_touch_pct_actual": -0.002},
            higher_tf_relation=h_rel,
        )

    def test_cn_futures_suppressed(self):
        # DCE agri drags full CN_COMMODITY pool negative — suppress
        sig = self._make_sig("opposing")
        w = BPullDetector.policy_weight(sig, "cn_futures")
        assert w == pytest.approx(0.0)

    def test_cn_futures_supporting_suppressed(self):
        sig = self._make_sig("supporting")
        w = BPullDetector.policy_weight(sig, "cn_futures")
        assert w == pytest.approx(0.0)

    def test_us_equity_not_validated(self):
        sig = self._make_sig("opposing")
        w = BPullDetector.policy_weight(sig, "us_equity")
        assert w == pytest.approx(0.0)

    def test_cn_index_futures_not_validated(self):
        sig = self._make_sig("opposing")
        w = BPullDetector.policy_weight(sig, "cn_index_futures")
        assert w == pytest.approx(0.0)

    def test_cn_metal_futures_opposing_weight(self):
        sig = self._make_sig("opposing")
        w = BPullDetector.policy_weight(sig, "cn_metal_futures", symbol="kq_m_shfe_au")
        assert w == pytest.approx(0.75)

    def test_cn_metal_futures_rb_excluded(self):
        sig = self._make_sig("opposing")
        w = BPullDetector.policy_weight(sig, "cn_metal_futures", symbol="kq_m_shfe_rb")
        assert w == pytest.approx(0.0)

    def test_cn_metal_futures_no_symbol_still_routes(self):
        # Without symbol arg, policy cannot enforce exclusion — caller's responsibility.
        sig = self._make_sig("opposing")
        w = BPullDetector.policy_weight(sig, "cn_metal_futures")
        assert w == pytest.approx(0.75)
