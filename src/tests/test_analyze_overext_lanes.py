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


def test_run_symbol_all_lanes_single_enrich_and_lane_bucketing(monkeypatch):
    # 验：每 symbol 只 detect+enrich 一次；按 direction×higher_relation 分桶；
    # simulate_trade 按各信号自身方向调用（monkeypatch 伪造管道，无需真数据）。
    import pandas as pd
    import scripts.analyze_overext_lanes as mod

    _ts = pd.to_datetime(
        ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"], utc=True)

    class _Sig:
        def __init__(self, idx, direction, h_rel):
            self.candidate_bar_idx = idx
            self.direction = direction
            self.multi_tf_context = {"higher_relation": h_rel}
            self.timestamp = _ts[idx]

    df = pd.DataFrame({"timestamp": _ts})
    calls = {"detect": 0, "enrich": 0, "sim_dirs": []}

    def fake_load_sym(sym, level, qr):
        return df
    def fake_atr(d, period=14):
        return pd.Series([1.0] * len(d))
    def fake_detect(d, instrument_class="x"):
        calls["detect"] += 1
        return [_Sig(0, "bottom", "opposing"), _Sig(1, "top", "supporting"),
                _Sig(2, "bottom", "neutral"), _Sig(3, "bottom", "leading")]  # leading 不在 6 lane
    def fake_enrich(sigs, daily, sixty, higher_tf_level_id="1h"):
        calls["enrich"] += 1
        return sigs
    def fake_feat(daily, idx):
        return {"range_vs_avg": 1.0}
    def fake_sim(daily, idx, direction, stop, atr):
        calls["sim_dirs"].append(direction)
        return ("tp1_tp2", 1.5, None, 1)

    monkeypatch.setattr(mod, "_load_sym", fake_load_sym)
    monkeypatch.setattr(mod, "compute_atr", fake_atr)
    monkeypatch.setattr(mod, "detect_signals", fake_detect)
    monkeypatch.setattr(mod, "enrich_with_higher_tf", fake_enrich)
    monkeypatch.setattr(mod, "signal_bar_features", fake_feat)
    monkeypatch.setattr(mod, "simulate_trade", fake_sim)

    rows = mod.run_symbol_all_lanes("FOO", "cn_metal_futures", quant_root=None)
    assert calls["detect"] == 1 and calls["enrich"] == 1   # 各一次
    lanes = sorted(r["lane"] for r in rows)
    assert lanes == ["bottomxneutral", "bottomxopposing", "topxsupporting"]  # leading 丢
    # simulate 按各信号方向调用
    assert sorted(calls["sim_dirs"]) == ["bottom", "bottom", "top"]
