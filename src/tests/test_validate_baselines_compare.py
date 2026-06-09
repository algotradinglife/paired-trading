from scripts.validate_baselines import _resolve_tolerance, _aggregate_symbols, GLOBAL_TOLERANCE


def test_resolve_tolerance_uses_global_default():
    assert _resolve_tolerance({})["ev_r_abs"] == GLOBAL_TOLERANCE["ev_r_abs"]


def test_resolve_tolerance_applies_override():
    tol = _resolve_tolerance({"tolerance_policy": {"ev_r_abs": 0.25}})
    assert tol["ev_r_abs"] == 0.25
    assert tol["n_pct"] == GLOBAL_TOLERANCE["n_pct"]


def test_aggregate_symbols_n_weighted():
    block = {
        "cu": {"n": 10, "ev_r": 0.20, "win_pct": 60.0},
        "sc": {"n": 30, "ev_r": 0.00, "win_pct": 40.0},
        "ag": {"n": 5, "ev_r": -1.0, "win_pct": 0.0},
    }
    cell = _aggregate_symbols(block, ["cu", "sc"])
    assert cell["n"] == 40
    assert cell["ev_r"] == 0.05
    assert cell["win_pct"] == 45.0


def test_aggregate_symbols_empty_returns_zero_n():
    assert _aggregate_symbols({}, ["cu"]) == {"n": 0, "ev_r": None, "win_pct": None}


from scripts.validate_baselines import _compare_cell

TOL = _resolve_tolerance({})


def _cell(n, ev, win=None):
    return {"n": n, "ev_r": ev, "win_pct": win}


def test_compare_within_tolerance_ok():
    st, _ = _compare_cell(_cell(50, 0.20), _cell(50, 0.25), TOL)
    assert st == "OK"


def test_compare_ev_drift():
    st, d = _compare_cell(_cell(50, 0.20), _cell(50, 0.40), TOL)
    assert st == "DRIFT" and "ev_r" in d


def test_compare_sign_flip_is_drift():
    st, _ = _compare_cell(_cell(50, 0.05), _cell(50, -0.05), TOL)
    assert st == "DRIFT"


def test_compare_n_inflation_drift():
    st, d = _compare_cell(_cell(50, 0.20), _cell(70, 0.20), TOL)
    assert st == "DRIFT" and "n " in d


def test_compare_tiny_n_downgrades_to_warn():
    st, _ = _compare_cell(_cell(6, 0.20), _cell(6, 0.90), TOL)
    assert st == "WARN"


def test_compare_win_pct_is_warn_only():
    st, _ = _compare_cell(_cell(50, 0.20, 60.0), _cell(50, 0.20, 80.0), TOL)
    assert st == "WARN"


def test_compare_skips_n_pct_when_baseline_n_null():
    st, _ = _compare_cell(_cell(None, 0.20), _cell(99, 0.22), TOL)
    assert st == "OK"


from scripts.validate_baselines import _compare_against_baseline


def _baseline():
    return {
        "lane": "pa_h2", "pool": "cn_bond",
        "full_stack_lane": "pa_cn_bond",
        "symbols_included": ["tf", "t"],
        "samples_full_stack_5y": {"n": 40, "ev_r": 0.12, "win_pct": 65.0},
        "samples": {"f1": {"n": 16, "ev_r": 0.22, "win_pct": None}},
        "data_snapshot_hash": "sha256:OLD",
    }


def test_primary_anchor_ok():
    fs = {"pa_cn_bond": {"tf": {"n": 20, "ev_r": 0.10, "win_pct": 64.0},
                          "t": {"n": 20, "ev_r": 0.14, "win_pct": 66.0}}}
    status, details = _compare_against_baseline(_baseline(), fs, None)
    assert status == "OK"


def test_primary_anchor_drift():
    fs = {"pa_cn_bond": {"tf": {"n": 20, "ev_r": 0.40, "win_pct": 64.0},
                          "t": {"n": 20, "ev_r": 0.50, "win_pct": 66.0}}}
    status, details = _compare_against_baseline(_baseline(), fs, None)
    assert status == "DRIFT"
    assert any("full_stack" in d for d in details)


def test_fold_secondary_drift():
    fs = {"pa_cn_bond": {"tf": {"n": 20, "ev_r": 0.10, "win_pct": 64.0},
                          "t": {"n": 20, "ev_r": 0.14, "win_pct": 66.0}}}
    fold_emitted = {"samples": {"f1": {"n": 16, "ev_r": 0.80, "win_pct": None}}}
    status, details = _compare_against_baseline(_baseline(), fs, fold_emitted)
    assert status == "DRIFT"
    assert any(d.startswith("f1") for d in details)


def test_data_changed_attribution():
    fs = {"pa_cn_bond": {"tf": {"n": 20, "ev_r": 0.40, "win_pct": 64.0},
                          "t": {"n": 20, "ev_r": 0.50, "win_pct": 66.0}}}
    fold_emitted = {"data_hash": "sha256:NEW"}
    status, details = _compare_against_baseline(_baseline(), fs, fold_emitted)
    assert status == "DRIFT"
    assert any("data changed" in d for d in details)


def test_no_full_stack_lane_skips_primary():
    b = _baseline()
    del b["full_stack_lane"]
    status, details = _compare_against_baseline(b, {}, None)
    assert status == "OK"
