from scripts.backtest_options_attribution import fold_of, verdict_for


def test_fold_split_is_oos():
    assert fold_of(2023) == "is" and fold_of(2024) == "oos" and fold_of(2026) == "oos"


def test_verdict_promote_regime_reject():
    assert verdict_for(is_ev=1.3, oos_ev=1.2) == "PROMOTE"
    assert verdict_for(is_ev=0.2, oos_ev=1.4) == "REGIME_ONLY"
    assert verdict_for(is_ev=0.9, oos_ev=0.8) == "REJECT"
