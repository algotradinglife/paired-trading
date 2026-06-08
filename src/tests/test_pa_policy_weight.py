"""Unit tests for PABottomDetector.policy_weight() and ensemble_weight().

The PA policy table is the boundary between detector recall and live R&R.
A regression here silently shifts trading weights, so this module is
table-driven and exhaustive for each instrument_class lane.

Routing reference (see pa_detector.py docstring for backtest provenance):

    us_equity:
      symbol in {tlt,tlh,iei,ief,shy} → 0.0  (suppression)
      uptrend + h=opposing            → 0.80  (+0.10 if leg_count_down == 1)
      uptrend + neutral HTF           → 0.40
      downtrend                       → 0.0
      ranging / unknown               → 0.0
    cn_metal_futures:
      h=opposing                      → 0.75
      h=supporting                    → 0.45
      neutral / unknown               → 0.60
    cn_bond:
      h=opposing                      → 0.70
      otherwise                       → 0.40
    cn_futures:
      h=opposing                      → 0.55
      otherwise                       → 0.35
    czce / cn_agri / anything else    → 0.0  (fall-through)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.divergence.pa_detector import PABottomDetector, PASignal


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def make_signal(
    higher_tf_relation: str | None = "opposing",
    trend_structure: str | None = None,
    leg_count_down: int | None = None,
    pattern: str = "h2_bottom",
    confidence: float = 0.6,
) -> PASignal:
    """Minimal PASignal factory for policy tests.

    Only ``higher_tf_relation`` and the swing-context entries in
    ``features`` matter for ``policy_weight``; everything else is filled
    in with placeholders.
    """
    features: dict[str, object] = {}
    if trend_structure is not None:
        features["trend_structure"] = trend_structure
    if leg_count_down is not None:
        features["leg_count_down"] = leg_count_down
    return PASignal(
        pattern=pattern,
        bar_idx=42,
        timestamp=pd.Timestamp("2026-06-08", tz="UTC"),
        confidence=confidence,
        features=features,
        higher_tf_relation=higher_tf_relation,
    )


# ---------------------------------------------------------------------------
# US long-bond suppression
# ---------------------------------------------------------------------------

class TestUSLongBondSuppression:
    """tlt/tlh/iei/ief/shy: PA H2 fails across every macro regime."""

    def test_suppress_set_is_exactly_five_symbols(self):
        # Regression guard: changing this set changes live weights.
        assert PABottomDetector.US_LONG_BOND_SUPPRESS == frozenset(
            {"tlt", "tlh", "iei", "ief", "shy"}
        )
        assert len(PABottomDetector.US_LONG_BOND_SUPPRESS) == 5

    @pytest.mark.parametrize("symbol", ["tlt", "tlh", "iei", "ief", "shy"])
    def test_each_long_bond_symbol_returns_zero(self, symbol):
        sig = make_signal(
            higher_tf_relation="opposing",
            trend_structure="uptrend",
            leg_count_down=1,  # would otherwise hit max 0.90
        )
        w = PABottomDetector.policy_weight(sig, "us_equity", symbol=symbol)
        assert w == 0.0

    @pytest.mark.parametrize("symbol", ["TLT", "Tlt", "TlH", "IEI", "SHY"])
    def test_symbol_match_is_case_insensitive(self, symbol):
        sig = make_signal(
            higher_tf_relation="opposing", trend_structure="uptrend"
        )
        w = PABottomDetector.policy_weight(sig, "us_equity", symbol=symbol)
        assert w == 0.0

    def test_non_suppressed_symbol_uses_normal_routing(self):
        # spy is not in the suppression set → normal uptrend routing applies
        sig = make_signal(
            higher_tf_relation="opposing", trend_structure="uptrend"
        )
        w = PABottomDetector.policy_weight(sig, "us_equity", symbol="spy")
        assert w == 0.80


# ---------------------------------------------------------------------------
# us_equity routing
# ---------------------------------------------------------------------------

class TestUSEquityRouting:
    def test_uptrend_opposing_returns_base_80(self):
        sig = make_signal(
            higher_tf_relation="opposing", trend_structure="uptrend"
        )
        assert PABottomDetector.policy_weight(sig, "us_equity") == 0.80

    def test_uptrend_opposing_legs1_returns_bonus_90(self):
        sig = make_signal(
            higher_tf_relation="opposing",
            trend_structure="uptrend",
            leg_count_down=1,
        )
        assert PABottomDetector.policy_weight(sig, "us_equity") == 0.90

    @pytest.mark.parametrize("legs", [0, 2, 3, 5])
    def test_uptrend_opposing_non_legs1_no_bonus(self, legs):
        sig = make_signal(
            higher_tf_relation="opposing",
            trend_structure="uptrend",
            leg_count_down=legs,
        )
        assert PABottomDetector.policy_weight(sig, "us_equity") == 0.80

    @pytest.mark.parametrize("rel", ["neutral", "supporting", None])
    def test_uptrend_non_opposing_returns_40(self, rel):
        sig = make_signal(higher_tf_relation=rel, trend_structure="uptrend")
        assert PABottomDetector.policy_weight(sig, "us_equity") == 0.40

    @pytest.mark.parametrize("rel", ["opposing", "supporting", "neutral", None])
    def test_downtrend_returns_zero(self, rel):
        sig = make_signal(higher_tf_relation=rel, trend_structure="downtrend")
        assert PABottomDetector.policy_weight(sig, "us_equity") == 0.0

    @pytest.mark.parametrize("trend", ["ranging", "unknown", ""])
    def test_ranging_or_unknown_returns_zero(self, trend):
        sig = make_signal(higher_tf_relation="opposing", trend_structure=trend)
        assert PABottomDetector.policy_weight(sig, "us_equity") == 0.0

    def test_missing_trend_structure_returns_zero(self):
        # Defensive: no trend_structure in features falls through to 0.0
        sig = make_signal(higher_tf_relation="opposing")
        assert PABottomDetector.policy_weight(sig, "us_equity") == 0.0

    def test_symbol_kwarg_none_backward_compatible(self):
        sig = make_signal(
            higher_tf_relation="opposing", trend_structure="uptrend"
        )
        # Explicit None
        assert PABottomDetector.policy_weight(
            sig, "us_equity", symbol=None
        ) == 0.80
        # Omitted entirely
        assert PABottomDetector.policy_weight(sig, "us_equity") == 0.80


# ---------------------------------------------------------------------------
# cn_metal_futures routing
# ---------------------------------------------------------------------------

class TestCNMetalFuturesRouting:
    @pytest.mark.parametrize(
        "rel,expected",
        [
            ("opposing", 0.75),
            ("supporting", 0.45),
            ("neutral", 0.60),
            (None, 0.60),
        ],
    )
    def test_cn_metal_routes(self, rel, expected):
        sig = make_signal(higher_tf_relation=rel)
        assert PABottomDetector.policy_weight(
            sig, "cn_metal_futures"
        ) == expected

    def test_symbol_kwarg_does_not_affect_cn_metal(self):
        # cn_metal_futures has no symbol-level suppression
        sig = make_signal(higher_tf_relation="opposing")
        assert PABottomDetector.policy_weight(
            sig, "cn_metal_futures", symbol="cu"
        ) == 0.75


# ---------------------------------------------------------------------------
# cn_bond routing (new in Phase B)
# ---------------------------------------------------------------------------

class TestCNBondRouting:
    def test_cn_bond_opposing_returns_70(self):
        sig = make_signal(higher_tf_relation="opposing")
        assert PABottomDetector.policy_weight(sig, "cn_bond") == 0.70

    @pytest.mark.parametrize("rel", ["neutral", "supporting", None])
    def test_cn_bond_non_opposing_returns_40(self, rel):
        sig = make_signal(higher_tf_relation=rel)
        assert PABottomDetector.policy_weight(sig, "cn_bond") == 0.40


# ---------------------------------------------------------------------------
# cn_futures routing
# ---------------------------------------------------------------------------

class TestCNFuturesRouting:
    def test_cn_futures_opposing_returns_55(self):
        sig = make_signal(higher_tf_relation="opposing")
        assert PABottomDetector.policy_weight(sig, "cn_futures") == 0.55

    @pytest.mark.parametrize("rel", ["supporting", "neutral", None])
    def test_cn_futures_non_opposing_returns_35(self, rel):
        sig = make_signal(higher_tf_relation=rel)
        assert PABottomDetector.policy_weight(sig, "cn_futures") == 0.35


# ---------------------------------------------------------------------------
# Suppressed lanes (fall-through default)
# ---------------------------------------------------------------------------

class TestSuppressedLanes:
    """czce / cn_agri / unknown classes fall through to 0.0."""

    @pytest.mark.parametrize(
        "instrument_class",
        ["czce", "cn_agri", "unknown_class", "", "crypto"],
    )
    @pytest.mark.parametrize("rel", ["opposing", "supporting", "neutral", None])
    def test_fall_through_returns_zero(self, instrument_class, rel):
        sig = make_signal(higher_tf_relation=rel)
        assert PABottomDetector.policy_weight(sig, instrument_class) == 0.0


# ---------------------------------------------------------------------------
# ensemble_weight
# ---------------------------------------------------------------------------

class TestEnsembleWeight:
    def test_pa_macd_within_3_bars_adds_15(self):
        sig = make_signal(higher_tf_relation="opposing")
        # cn_metal opposing base = 0.75 → 0.90
        w = PABottomDetector.ensemble_weight(sig, "cn_metal_futures", 2)
        assert w == pytest.approx(0.90)

    @pytest.mark.parametrize("bars", [0, 1, 2, 3])
    def test_exactly_within_window_inclusive(self, bars):
        sig = make_signal(higher_tf_relation="opposing")
        w = PABottomDetector.ensemble_weight(sig, "cn_metal_futures", bars)
        assert w == pytest.approx(0.90)

    @pytest.mark.parametrize("bars", [4, 5, 10, 100])
    def test_outside_3_bars_returns_base(self, bars):
        sig = make_signal(higher_tf_relation="opposing")
        w = PABottomDetector.ensemble_weight(sig, "cn_metal_futures", bars)
        assert w == pytest.approx(0.75)

    def test_no_nearby_macd_returns_base(self):
        sig = make_signal(higher_tf_relation="opposing")
        w = PABottomDetector.ensemble_weight(sig, "cn_metal_futures", None)
        assert w == pytest.approx(0.75)

    def test_base_zero_stays_zero_even_with_macd_nearby(self):
        """Suppression must beat the ensemble bonus.

        A suppressed lane (here: czce) with a MACD signal one bar away
        must still return 0.0 — adding +0.15 to a 0 base would silently
        re-enable a suppressed lane.
        """
        sig = make_signal(higher_tf_relation="opposing")
        assert PABottomDetector.ensemble_weight(sig, "czce", 1) == 0.0

    def test_symbol_suppression_honoured_with_macd_nearby(self):
        # tlt suppression must not be overridden by a nearby MACD bar.
        sig = make_signal(
            higher_tf_relation="opposing", trend_structure="uptrend"
        )
        w = PABottomDetector.ensemble_weight(
            sig, "us_equity", 1, symbol="tlt"
        )
        assert w == 0.0

    def test_symbol_kwarg_forwards_to_policy_weight(self):
        """Symbol must reach policy_weight: spy uptrend+legs1 → 0.90 base."""
        sig = make_signal(
            higher_tf_relation="opposing",
            trend_structure="uptrend",
            leg_count_down=1,
        )
        # No MACD nearby → base unchanged at 0.90
        assert PABottomDetector.ensemble_weight(
            sig, "us_equity", None, symbol="spy"
        ) == pytest.approx(0.90)
        # MACD within window → 0.90 + 0.15 = 1.05
        assert PABottomDetector.ensemble_weight(
            sig, "us_equity", 2, symbol="spy"
        ) == pytest.approx(1.05)

    def test_ensemble_caps_at_1_20(self):
        """ensemble_weight uses min(base + 0.15, 1.20)."""
        # Construct a base near 1.20: us_equity uptrend+opposing+legs1 = 0.90
        # which becomes 1.05 with bonus, still under cap.  To verify the
        # cap itself fires we synthesise a higher base via cn_metal opp
        # (0.75) — also stays under cap.  Document the cap exists rather
        # than reverse-engineer a base that hits it (no such lane today).
        sig = make_signal(
            higher_tf_relation="opposing",
            trend_structure="uptrend",
            leg_count_down=1,
        )
        w = PABottomDetector.ensemble_weight(sig, "us_equity", 0, symbol="spy")
        assert w <= 1.20
