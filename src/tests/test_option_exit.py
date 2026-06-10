import pandas as pd
from engine.options.option_exit import simulate_entry


def _daily(prices):
    return pd.DataFrame({"open": prices, "high": prices, "low": prices,
                         "close": prices, "volume": [1] * len(prices)})


def test_take2_blended_exit():
    # Validated half/half model: a single bar spanning t1(20)->t2(40) banks 0.5
    # at take1 (=10) then 0.5 at take2 (=20) -> proceeds 30 -> mult 3.0.
    # A pure 4.0x is unreachable by construction (take1 always banks first).
    daily = _daily([10, 12, 40, 11])
    daily.loc[2, "high"] = 40.0
    e = {"entry_idx": 0, "entry_price": 10.0, "stop_price": 9.0}
    r = simulate_entry(daily, e, take1_mult=2.0, take2_mult=4.0, max_hold=30)
    assert r["take1"] is True and r["take2"] is True
    assert r["exit_reason"] == "take2" and r["mult"] == 3.0


def test_tp1_then_runs_to_boundary_credits_partial():
    daily = _daily([10, 20, 10, 10])
    daily.loc[1, "high"] = 20.0
    e = {"entry_idx": 0, "entry_price": 10.0, "stop_price": 9.0}
    r = simulate_entry(daily, e, take1_mult=2.0, take2_mult=4.0, max_hold=2)
    assert r["take1"] is True and r["take2"] is False
    assert r["mult"] == 1.5


def test_stop_exit():
    daily = _daily([10, 8, 8, 8])
    e = {"entry_idx": 0, "entry_price": 10.0, "stop_price": 9.0}
    r = simulate_entry(daily, e, take1_mult=2.0, take2_mult=4.0, max_hold=30)
    assert r["exit_reason"] == "stop" and r["mult"] < 1.0
