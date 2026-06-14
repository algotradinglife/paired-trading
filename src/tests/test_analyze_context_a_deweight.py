"""Unit tests for analyze_context_a_deweight.build_report — scheme cells + factor wiring."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from scripts.analyze_context_a_deweight import (  # noqa: E402
    _factor,
    _live_lane_weight,
    build_report,
)


def _row(rva: float, ordinal: int, r: float, pool: str = "US", period: str = "IS") -> dict:
    return {"pool": pool, "symbol": "x", "bar_idx": 100, "date": "2024-07-01",
            "period": period, "realized_r": r, "range_vs_avg": rva,
            "ordinal": ordinal, "win": int(r > 0)}


def _rec(h_rel: str = "opposing"):
    return {"bar_idx": 100, "timestamp": pd.Timestamp("2024-07-01", tz="UTC"),
            "h_rel": h_rel}


def test_live_lane_weight_applies_production_suppression():
    # t_b186d176 fix: population must match the live ContextADetector policy lane.
    # US broad-market suppressions → weight 0 (excluded from population)
    assert _live_lane_weight(_rec(), "us_equity", "SPY") == 0.0
    assert _live_lane_weight(_rec(), "us_equity", "DIA") == 0.0
    assert _live_lane_weight(_rec(), "us_equity", "XLU") == 0.0
    # CN_METAL crude suppression → weight 0
    assert _live_lane_weight(_rec(), "cn_metal_futures", "kq_m_ine_sc") == 0.0
    # non-suppressed symbols pass (weight > 0)
    assert _live_lane_weight(_rec(), "us_equity", "QQQ") > 0.0
    assert _live_lane_weight(_rec(), "cn_metal_futures", "kq_m_shfe_au") > 0.0
    # non-opposing always excluded regardless of symbol
    assert _live_lane_weight(_rec("supporting"), "us_equity", "QQQ") == 0.0


def test_factor_bottom_opposing_only():
    # clean first test, not over-extended → factor 1.0
    assert _factor(_row(0.5, 1, 1.0)) == 1.0
    # over-extended retest → factor < 1
    assert _factor(_row(1.5, 2, 1.0)) < 1.0


def test_build_report_schemes_and_eff_n():
    rows = [
        _row(0.8, 1, 1.0),    # clean → full weight
        _row(0.8, 2, 0.5),    # retest → de-weighted
        _row(2.0, 1, -0.5),   # over-ext → de-weighted
        _row(2.0, 3, -1.0),   # over-ext retest → max de-weight
    ]
    rep = build_report(rows)
    sc = rep["combined"]["scheme_comparison"]
    assert sc["full_equal"]["n"] == 4
    assert sc["full_equal"]["ev"] == 0.0          # (1.0+0.5-0.5-1.0)/4
    # hard-AND keeps only the clean first test (rva<=1.0 & ord==1)
    assert sc["hard_AND_gate"]["n"] == 1
    # continuous keeps all 4 but with reduced effective n
    assert sc["continuous_weight"]["n"] == 4
    assert sc["continuous_weight"]["eff_n"] < 4.0


def test_build_report_by_pool_split():
    rows = [_row(0.8, 1, 1.0, pool="US"), _row(0.8, 1, -1.0, pool="CN_METAL")]
    rep = build_report(rows)
    assert rep["by_pool"]["US"]["n"] == 1
    assert rep["by_pool"]["CN_METAL"]["n"] == 1
    assert rep["by_pool"]["US"]["scheme_comparison"]["full_equal"]["ev"] == 1.0
