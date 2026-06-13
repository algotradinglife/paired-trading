"""Unit tests for analyze_overext_lanes — lane 分桶 + lane_report 结构（合成行）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.analyze_overext_lanes import (  # noqa: E402
    LANES,
    build_report,
    lane_report,
)


def _row(lane: str, rva: float, r: float, date: str = "2024-07-01") -> dict:
    d, h = lane.split("x")
    return {"symbol": "x", "pool": "CN_METAL", "date": date,
            "direction": d, "higher_relation": h, "lane": lane,
            "range_vs_avg": rva, "outcome": "tp1_tp2", "realized_r": r,
            "win": int(r > 0)}


def test_build_report_buckets_by_lane():
    rows = ([_row("bottomxopposing", 0.8, 1.0)] * 3
            + [_row("topxopposing", 2.0, -1.0)] * 2)
    rep = build_report(rows, ["CN_METAL"])
    # 所有 6 lane 都出现在 by_lane（无样本的 n=0）
    assert set(rep["by_lane"]) == {f"{d}x{h}" for d, h in LANES}
    assert rep["by_lane"]["bottomxopposing"]["n"] == 3
    assert rep["by_lane"]["topxopposing"]["n"] == 2
    assert rep["by_lane"]["bottomxneutral"]["n"] == 0
    assert rep["n_events_total"] == 5


def test_lane_report_has_gate_and_nested_keys():
    rows = ([_row("bottomxopposing", 0.8, 1.0, date="2025-01-01")] * 5
            + [_row("bottomxopposing", 2.0, -1.0, date="2025-12-01")] * 5)
    lr = lane_report(rows)
    assert lr["n"] == 10
    assert "threshold_sweep" in lr
    assert "gate_at_empirical_cutoff" in lr
    assert "nested_walk_forward" in lr
    # gate@1.0 应保留低 rva 行（盈利）、剔高 rva 行（亏损）
    g = lr["gate_at_empirical_cutoff"]
    assert g["kept"]["n"] == 5 and g["dropped"]["n"] == 5


def test_lane_report_empty():
    lr = lane_report([])
    assert lr["n"] == 0 and lr["full_lane_ev"] is None
