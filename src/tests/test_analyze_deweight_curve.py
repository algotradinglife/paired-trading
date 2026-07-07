"""Unit tests for analyze_deweight_curve — w_a / calibrate_w_b / 三方案对比（合成行）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.analyze_deweight_curve import (  # noqa: E402
    W_MIN,
    build_report,
    calibrate_w_b,
    w_a,
)


def _row(rva: float, ordinal: int, r: float, date: str = "2025-01-01") -> dict:
    return {"symbol": "x", "pool": "CN_METAL", "date": date,
            "range_vs_avg": rva, "ordinal": ordinal, "realized_r": r,
            "win": int(r > 0)}


def test_w_a_full_below_cut_decays_above_floored():
    assert w_a(0.8) == 1.0          # ≤1.0 满权
    assert w_a(1.0) == 1.0
    assert w_a(1.5) == 0.5          # (1-1.5)/1+1 = 0.5
    assert w_a(5.0) == W_MIN        # 远超 → 下限
    assert w_a(float("nan")) == W_MIN


def test_calibrate_w_b_first_full_retest_downweighted():
    rows = ([_row(0.8, 1, 1.0)] * 5      # first EV +1.0
            + [_row(0.8, 2, 0.0)] * 5     # 2nd EV 0 → w_b 下限
            + [_row(0.8, 3, 0.5)] * 5)    # 3rd EV +0.5 → w_b 0.5
    wb = calibrate_w_b(rows)
    assert wb[1] == 1.0
    assert wb[2] == W_MIN              # ev/ev_first = 0 → 下限
    assert abs(wb[3] - 0.5) < 1e-9


def test_scheme_comparison_continuous_keeps_more_eff_n_than_hard_and():
    # 大部分是首测+非过度延伸的中性行 + 少量过度延伸亏损行
    rows = ([_row(0.8, 1, 0.3)] * 40       # 满权
            + [_row(2.0, 2, -1.0)] * 20)    # 低权（过度延伸+回踩）
    rep = build_report(rows, ["CN_METAL"])
    s = rep["scheme_comparison"]
    assert s["full_equal"]["n"] == 60
    assert s["hard_AND_gate"]["n"] == 40   # rva≤1.0 ∧ ord==1
    # 连续加权的有效 n 应远大于硬 AND 的 n（保信号量）
    assert s["continuous_weight"]["eff_n"] > s["hard_AND_gate"]["n"]


def test_nonfinite_range_excluded():
    rows = [_row(0.8, 1, 1.0), _row(float("nan"), 1, 0.5)]
    assert build_report(rows, ["CN_METAL"])["n"] == 1
