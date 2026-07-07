"""Unit tests for analyze_combined_gate.build_report — A/B/both cells + 2x2 列联。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.analyze_combined_gate import build_report  # noqa: E402


def _row(rva: float, ordinal: int, r: float) -> dict:
    return {"symbol": "x", "pool": "CN_METAL", "date": "2024-07-01",
            "range_vs_avg": rva, "ordinal": ordinal, "realized_r": r,
            "win": int(r > 0)}


def test_cells_and_gate_membership():
    rows = [
        _row(0.8, 1, 1.0),   # not_overext & first  → A, B, both
        _row(0.8, 2, 0.5),   # not_overext & retest → A only
        _row(2.0, 1, -0.5),  # overext & first      → B only
        _row(2.0, 3, -1.0),  # overext & retest     → neither
    ]
    rep = build_report(rows, ["CN_METAL"])
    c = rep["cells"]
    assert c["full"]["n"] == 4
    assert c["gate_A_overext_only"]["n"] == 2   # rva<=1.0: rows 0,1
    assert c["gate_B_first_only"]["n"] == 2     # ordinal==1: rows 0,2
    assert c["both_A_and_B"]["n"] == 1          # row 0
    assert c["both_A_and_B"]["ev"] == 1.0


def test_contingency_2x2_partitions_all():
    rows = [_row(0.8, 1, 1.0), _row(0.8, 2, 0.5),
            _row(2.0, 1, -0.5), _row(2.0, 3, -1.0)]
    ct = build_report(rows, ["CN_METAL"])["contingency_2x2"]
    assert ct == {"first_and_not_overext": 1, "first_and_overext": 1,
                  "retest_and_not_overext": 1, "retest_and_overext": 1}
    assert sum(ct.values()) == 4   # 2x2 划分穷尽


def test_nonfinite_range_excluded():
    rows = [_row(0.8, 1, 1.0), _row(float("nan"), 1, 0.5)]
    rep = build_report(rows, ["CN_METAL"])
    assert rep["n"] == 1
