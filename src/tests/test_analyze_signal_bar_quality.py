"""Hermetic unit tests for analyze_signal_bar_quality.stratify — no data/cn_data dependency.
Guards the median-split + EV-delta logic (researcher hardening exploration)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.analyze_signal_bar_quality import (  # noqa: E402
    combined_filter,
    quality_directions,
    stratify,
)


def test_combined_filter_requires_all_fields_and_reports_retention():
    # 8 trades; both medians are 0.5. Only trades 0,1 are >= median on BOTH fields.
    rows = _rows([(str(i), g) for i, g in enumerate([3.0, 2.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0])])
    feats = {
        "0": {"body_frac": 0.9, "close_pos": 0.9},   # high body, high close → PASS
        "1": {"body_frac": 0.8, "close_pos": 0.8},   # high body, high close → PASS
        "2": {"body_frac": 0.7, "close_pos": 0.2},   # high body, low close  → fail
        "3": {"body_frac": 0.6, "close_pos": 0.1},   # high body, low close  → fail
        "4": {"body_frac": 0.4, "close_pos": 0.7},   # low body, high close  → fail
        "5": {"body_frac": 0.3, "close_pos": 0.6},   # low body, high close  → fail
        "6": {"body_frac": 0.2, "close_pos": 0.3},   # low, low              → fail
        "7": {"body_frac": 0.1, "close_pos": 0.4},   # low, low              → fail
    }
    qdir = quality_directions("做多")
    cf = combined_filter(rows, feats, ("body_frac", "close_pos"), qdir)
    assert cf is not None
    assert cf["n_pass"] == 2 and cf["n_usable"] == 8 and cf["retention"] == 0.25
    assert cf["pass_ev"]["mean_gross_r"] > cf["fail_ev"]["mean_gross_r"]
    assert cf["ev_delta_pass_minus_fail"] > 0
    # 2x2 partition + marginal contrasts are reported (honest additivity test)
    assert set(cf["two_by_two"]) == {"A&B", "A_only", "B_only", "neither"}
    assert cf["two_by_two"]["A&B"]["n"] == 2
    # disjoint within-condition marginal contrasts (A&B vs A_only / B_only)
    marg = [k for k in cf["marginals"] if "given" in k]
    assert len(marg) == 2
    assert all("ci95_diff" in cf["marginals"][k] for k in marg)


def test_close_pos_orientation_flips_with_trade_direction():
    # close_pos = (c-low)/range: strong bull bar closes near high (+1 for long),
    # strong bear bar closes near low (-1 for short). body_frac/range penalties stay.
    long_dir = quality_directions("做多")
    short_dir = quality_directions("做空")
    assert long_dir["close_pos"] == 1 and short_dir["close_pos"] == -1
    assert long_dir["body_frac"] == short_dir["body_frac"] == 1
    assert long_dir["range_vs_avg"] == short_dir["range_vs_avg"] == -1


def _rows(pairs):
    # pairs: list of (id, gross_r)
    return [{"id": i, "gross_r": g, "triggered": True, "resolved": True} for i, g in pairs]


def test_stratify_higher_is_better():
    # higher q (>= median) carries the winners; with direction=+1 that is "better quality"
    rows = _rows([("a", 2.0), ("b", 3.0), ("c", -1.0), ("d", -1.0),
                  ("e", 2.5), ("f", -1.0), ("g", 1.5), ("h", -1.0)])
    feats = {"a": {"q": 0.9}, "b": {"q": 0.8}, "e": {"q": 0.95}, "g": {"q": 0.7},   # high q
             "c": {"q": 0.2}, "d": {"q": 0.1}, "f": {"q": 0.3}, "h": {"q": 0.15}}   # low q
    s = stratify(rows, feats, "q", direction=1)
    assert s is not None
    assert s["better_quality"]["n"] == 4 and s["worse_quality"]["n"] == 4
    assert s["better_quality"]["mean_gross_r"] > s["worse_quality"]["mean_gross_r"]
    assert s["ev_delta_better_minus_worse"] > 0


def test_stratify_penalty_metric_lower_is_better():
    # SAME data, but now the metric is a length penalty (direction=-1): the LOW-value
    # half is the better-quality one. Winners sit on the high-value side here, so a
    # penalty orientation must report a NEGATIVE better-minus-worse delta.
    rows = _rows([("a", 2.0), ("b", 3.0), ("c", -1.0), ("d", -1.0),
                  ("e", 2.5), ("f", -1.0), ("g", 1.5), ("h", -1.0)])
    feats = {"a": {"q": 0.9}, "b": {"q": 0.8}, "e": {"q": 0.95}, "g": {"q": 0.7},
             "c": {"q": 0.2}, "d": {"q": 0.1}, "f": {"q": 0.3}, "h": {"q": 0.15}}
    s = stratify(rows, feats, "q", direction=-1)
    assert s is not None
    # better_quality = LOW-value half (the losers) → delta is negative
    assert s["direction"].startswith("lower_is_better")
    assert s["ev_delta_better_minus_worse"] < 0


def test_stratify_none_when_too_few_metrics():
    # only 3 trades carry the metric → below the 8-trade floor
    rows = _rows([("a", 1.0), ("b", -1.0), ("c", 2.0), ("d", 1.0)])
    feats = {"a": {"q": 0.5}, "b": {"q": 0.4}, "c": {"q": 0.6}}
    assert stratify(rows, feats, "q") is None


def test_stratify_skips_rows_missing_metric():
    rows = _rows([(str(i), 1.0 if i % 2 else -1.0) for i in range(16)])
    feats = {str(i): {"q": float(i)} for i in range(16)}  # all present
    s = stratify(rows, feats, "q")
    assert s is not None and s["n_with_metric"] == 16
    # missing-metric variant: only 10 carry the metric (still above the 8-trade floor)
    feats2 = {str(i): {"q": float(i)} for i in range(10)}
    s2 = stratify(rows, feats2, "q")
    assert s2 is not None and s2["n_with_metric"] == 10
