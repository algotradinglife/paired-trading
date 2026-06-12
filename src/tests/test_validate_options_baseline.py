"""Options-attribution baselines in validate_baselines --full.

Pure comparison: baseline net samples (is/oos ev_mult + n) and
modeled_fraction vs a fresh harness run. Tolerances: ev_mult ±0.10 or a
1.0-threshold flip -> DRIFT; n ±25% -> DRIFT; modeled_fraction back
above 0.5 -> DRIFT (re-model-dominated), +0.15 -> WARN.
"""
from __future__ import annotations

from scripts.validate_baselines import _compare_options_baseline


def _baseline(is_ev=1.5, oos_ev=1.37, is_n=8, oos_n=19, frac=0.22):
    return {
        "lane": "options_au",
        "samples": {"is": {"n": is_n, "ev_mult": is_ev, "win_pct": 60.0},
                    "oos": {"n": oos_n, "ev_mult": oos_ev, "win_pct": 63.0}},
        "pricing": {"modeled_fraction": frac},
        "window": {"since": "2024-07-01", "is_cutoff_year": 2024},
    }


def _run(is_ev=1.5, oos_ev=1.37, is_n=8, oos_n=19, frac=0.22):
    return {
        "samples": {"is": {"n": is_n, "ev_mult": is_ev, "win_pct": 60.0},
                    "oos": {"n": oos_n, "ev_mult": oos_ev, "win_pct": 63.0}},
        "pricing": {"modeled_fraction": frac},
    }


def test_within_tolerance_ok():
    st, _ = _compare_options_baseline(_baseline(), _run(is_ev=1.45, oos_n=21))
    assert st == "OK"


def test_ev_mult_drift_detected():
    st, det = _compare_options_baseline(_baseline(), _run(oos_ev=1.18))
    assert st == "DRIFT"
    assert any("oos" in d for d in det)


def test_threshold_flip_is_drift_even_within_band():
    # 1.05 -> 0.97: |d|=0.08 < 0.10 but crosses the 1.0 EV threshold
    st, det = _compare_options_baseline(
        _baseline(is_ev=1.05), _run(is_ev=0.97))
    assert st == "DRIFT"


def test_n_drift_detected():
    st, _ = _compare_options_baseline(_baseline(), _run(oos_n=12))
    assert st == "DRIFT"


def test_remodel_domination_is_drift():
    st, det = _compare_options_baseline(_baseline(), _run(frac=0.55))
    assert st == "DRIFT"
    assert any("modeled_fraction" in d for d in det)


def test_frac_creep_warns():
    st, _ = _compare_options_baseline(_baseline(), _run(frac=0.40))
    assert st == "WARN"


def test_run_failure_fails_open():
    st, det = _compare_options_baseline(_baseline(), None)
    assert st == "OK"
    assert any("UNAVAILABLE" in d for d in det)
