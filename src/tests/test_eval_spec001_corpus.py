"""Hermetic unit tests for eval_spec001_corpus pure helpers — guard cycle/decision
extraction口径 against drift (reviewer t_5f95925e #4). No data/cn_data dependency."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.eval_spec001_corpus import (  # noqa: E402
    _bootstrap_mean,
    _cycle,
    _decision_dir,
    _order_from_decision,
    _stats,
)


def test_cycle_extraction_prefers_cycle_position():
    assert _cycle({"diagnosis_summary": {"cycle_position": "trending_tr"}}) == "trending_tr"
    # fallback to 'cycle' if cycle_position absent
    assert _cycle({"diagnosis_summary": {"cycle": "broad_channel"}}) == "broad_channel"
    # missing → None (record won't match any --cycle filter)
    assert _cycle({"diagnosis_summary": {}}) is None
    assert _cycle({}) is None


def test_cycle_filter_set_membership():
    # the SPEC-001 vs SPEC-002 split is `_cycle(r) in {...}`; verify the predicate
    recs = [{"diagnosis_summary": {"cycle_position": c}} for c in
            ["trending_tr", "broad_channel", "trading_range", "spike", None]]
    spec002 = [r for r in recs if _cycle(r) in {"trending_tr"}]
    spec001 = [r for r in recs if _cycle(r) in {"broad_channel", "trading_range"}]
    assert len(spec002) == 1
    assert len(spec001) == 2
    # disjoint: no record in both (independence-by-cycle invariant)
    assert not ({id(r) for r in spec002} & {id(r) for r in spec001})


def test_decision_dir_and_order():
    d = {"order_type": "突破单", "direction": "做多", "entry": 100, "stop": 95, "target": 110}
    assert _decision_dir(d) == "做多"
    assert _decision_dir({"order_direction": "做空"}) == "做空"
    o = _order_from_decision(d)
    assert o == {"order_direction": "做多", "entry": 100.0, "stop": 95.0, "target": 110.0}
    # missing E/S/T → None
    assert _order_from_decision({"order_type": "突破单", "direction": "做多"}) is None


def test_stats_and_bootstrap():
    grs = [2.0, -1.0, 2.0, -1.0, 3.0]
    s = _stats(grs)
    assert s["n"] == 5 and abs(s["mean_gross_r"] - 1.0) < 1e-9 and s["win_rate"] == 0.6
    bs = _bootstrap_mean(grs)
    assert bs["ci95"][0] <= 1.0 <= bs["ci95"][1] and 0.0 <= bs["p_gt0"] <= 1.0
    # too few for bootstrap → None CI
    assert _bootstrap_mean([1.0])["ci95"] == [None, None]
