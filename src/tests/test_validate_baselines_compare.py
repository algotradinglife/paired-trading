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
