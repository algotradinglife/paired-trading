"""Unit tests for analyze_range_gate — gate_split / threshold_sweep / walk_forward
（纯聚合，合成行；验 gate 过滤、阈值扫描、时间序折分）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.analyze_range_gate import (  # noqa: E402
    GATE_CUTOFF,
    gate_split,
    threshold_sweep,
    walk_forward,
)


def _row(rva: float, r: float, date: str = "2024-07-01", pool: str = "CN_METAL") -> dict:
    return {"range_vs_avg": rva, "realized_r": r, "date": date, "pool": pool}


def test_gate_split_keeps_below_cutoff_drops_above():
    rows = [_row(0.8, 1.0), _row(1.2, 0.5), _row(2.0, -1.0), _row(3.0, -1.0)]
    g = gate_split(rows, 1.5)
    assert g["kept"]["n"] == 2          # 0.8, 1.2 <= 1.5
    assert g["dropped"]["n"] == 2       # 2.0, 3.0 > 1.5
    assert g["kept"]["ev"] == 0.75      # mean(1.0, 0.5)
    assert g["dropped"]["ev"] == -1.0


def test_gate_split_ignores_nonfinite_range():
    rows = [_row(0.8, 1.0), _row(float("nan"), 0.5), _row(2.0, -1.0)]
    g = gate_split(rows, 1.5)
    assert g["n"] == 2                  # nan 行被排除
    assert g["kept"]["n"] == 1 and g["dropped"]["n"] == 1


def test_threshold_sweep_monotone_keep_frac():
    rows = [_row(v / 10, 0.0) for v in range(5, 35)]  # rva 0.5..3.4
    sw = threshold_sweep(rows)
    fracs = [sw["by_cutoff"][f"cutoff_{c}"]["keep_frac"]
             for c in (1.0, 1.5, 2.0, 3.0)]
    assert fracs == sorted(fracs)       # cutoff 越大保留越多（单调不减）
    assert sw["by_cutoff"]["cutoff_3.0"]["keep_frac"] >= fracs[0]


def test_walk_forward_chronological_split_and_dates_sorted():
    rows = [_row(0.8, 1.0, date=f"2024-{m:02d}-01") for m in range(1, 13)]
    wf = walk_forward(rows, GATE_CUTOFF, k=3)
    assert wf["k"] == 3
    f = wf["chronological_folds"]
    assert f["F1"]["n"] == 4 and f["F3"]["n"] == 4
    # 折按时间序：F1 起始日 <= F3 起始日
    assert f["F1"]["date_range"][0] <= f["F3"]["date_range"][0]


def test_walk_forward_is_oos_split_by_cutoff_date():
    rows = ([_row(0.8, 1.0, date="2025-01-01")] * 3
            + [_row(0.8, 1.0, date="2025-12-01")] * 2)
    wf = walk_forward(rows, GATE_CUTOFF, k=2)
    assert wf["is_oos"]["is"]["n"] == 3    # <= 2025-06-30
    assert wf["is_oos"]["oos"]["n"] == 2   # > 2025-06-30
