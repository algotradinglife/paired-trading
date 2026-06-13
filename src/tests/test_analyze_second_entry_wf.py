"""Unit tests for analyze_second_entry_wf — ordinal_gradient / nested_walk_forward /
chronological_folds（纯聚合，合成行；验序数分组、无前视嵌套 WF、时间序折分）。
镜像 test_analyze_range_gate.py。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.analyze_second_entry_wf import (  # noqa: E402
    chronological_folds,
    nested_walk_forward,
    ordinal_gradient,
)


def _row(ordinal: int, r: float, date: str = "2024-07-01",
         pool: str = "CN_METAL", outcome: str = "tp1_tp2") -> dict:
    return {"ordinal": ordinal, "realized_r": r, "date": date, "pool": pool,
            "outcome": outcome}


def test_ordinal_gradient_groups_first_second_third():
    rows = [_row(1, 1.0), _row(2, -0.5), _row(3, -1.0), _row(4, 0.2)]
    g = ordinal_gradient(rows)
    assert g["first"]["n"] == 1               # ord == 1
    assert g["second_plus"]["n"] == 3         # ord >= 2: {2,3,4}
    assert g["third_plus"]["n"] == 2          # ord >= 3: {3,4}
    assert g["first"]["ev"] == 1.0
    # 2nd+ EV = mean(-0.5,-1.0,0.2) = -0.433333
    assert g["second_plus"]["ev"] == -0.433333


def test_ordinal_gradient_gap_and_bootstrap_sign():
    # first 全盈利，2nd+ 全亏损 → gap>0, bootstrap p_gt0 高
    rows = [_row(1, 1.0)] * 10 + [_row(2, -1.0)] * 10
    g = ordinal_gradient(rows)
    assert g["first_minus_second_plus_gap"] == 2.0
    bs = g["first_vs_second_plus_bootstrap"]
    assert bs["gap"] == 2.0
    assert bs["p_gt0"] == 1.0                  # 完全分离
    assert bs["ci95"][0] > 0


def test_ordinal_gradient_win_rate_uses_tp1_outcomes():
    rows = [_row(1, 1.0, outcome="tp1_tp2"), _row(1, -1.0, outcome="full_stop")]
    g = ordinal_gradient(rows)
    assert g["first"]["win_rate"] == 0.5       # 1/2 tp1 outcome


def test_nested_walk_forward_selects_cutoff_on_is_only():
    # IS（<=2025-06-30）：first 盈利、2nd+ 亏损 → IS 选紧 cutoff(=1, 只留 first)；
    # OOS（>2025-06-30）：同结构 → 选出的 cutoff 在 OOS 也应有正 lane_improvement（无前视）
    is_rows = ([_row(1, 1.0, date="2025-01-01")] * 5
               + [_row(2, -1.0, date="2025-02-01")] * 5)
    oos_rows = ([_row(1, 1.0, date="2025-12-01")] * 4
                + [_row(2, -1.0, date="2025-12-15")] * 4)
    nw = nested_walk_forward(is_rows + oos_rows)
    assert nw["applicable"] is True
    assert nw["is_selected_cutoff"] == 1                 # 只留 first 才剔掉亏损 2nd+
    assert nw["oos_improvement_at_selected_cutoff"] > 0  # 选出的 cutoff OOS 仍提升
    assert nw["oos_kept_vs_dropped_bootstrap"]["p_gt0"] == 1.0


def test_nested_walk_forward_not_applicable_when_oos_empty():
    rows = [_row(1, 1.0, date="2025-01-01")] * 3         # 全在 IS
    nw = nested_walk_forward(rows)
    assert nw["applicable"] is False
    assert nw["reason"] == "IS or OOS empty"


def test_nested_walk_forward_not_applicable_when_is_empty():
    rows = [_row(1, 1.0, date="2025-12-01")] * 3         # 全在 OOS
    nw = nested_walk_forward(rows)
    assert nw["applicable"] is False


def test_chronological_folds_split_and_dates_sorted():
    rows = [_row(1 if m % 2 else 2, 0.5, date=f"2024-{m:02d}-01")
            for m in range(1, 13)]
    cf = chronological_folds(rows, k=3)
    assert cf["k"] == 3
    f = cf["chronological_folds"]
    assert f["F1"]["n"] == 4 and f["F3"]["n"] == 4
    # 折按时间序：F1 起始日 <= F3 起始日
    assert f["F1"]["date_range"][0] <= f["F3"]["date_range"][0]


def test_chronological_folds_is_oos_split_by_cutoff_date():
    rows = ([_row(1, 1.0, date="2025-01-01")] * 3
            + [_row(2, -1.0, date="2025-12-01")] * 2)
    cf = chronological_folds(rows, k=2)
    assert cf["is_oos"]["is"]["n"] == 3        # <= 2025-06-30
    assert cf["is_oos"]["oos"]["n"] == 2       # > 2025-06-30


def test_chronological_folds_gap_none_when_group_missing():
    # 某折全是 first（无 2nd+）→ gap 应为 None（不崩）
    rows = [_row(1, 1.0, date=f"2024-{m:02d}-01") for m in range(1, 4)]
    cf = chronological_folds(rows, k=1)
    assert cf["chronological_folds"]["F1"]["first_minus_second_plus_gap"] is None
