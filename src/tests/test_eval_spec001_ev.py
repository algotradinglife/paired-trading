"""Unit tests for eval_spec001_ev.simulate_order — exit-sim convention (hermetic)."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.eval_spec001_ev import orders_from_replay, simulate_order  # noqa: E402

_T0 = dt.datetime(2025, 1, 1, 0, 0)


def _bar(minutes: int, o, h, lo, c):
    ts = int((_T0 + dt.timedelta(minutes=minutes)).replace(tzinfo=dt.timezone.utc).timestamp())
    return {"ts_open": ts, "open": o, "high": h, "low": lo, "close": c}


def _order(direction, entry, stop, target):
    return {"order_direction": direction, "entry": entry, "stop": stop, "target": target}


def test_long_hits_target():
    bars = [_bar(5, 100, 101, 99, 100),    # before entry
            _bar(10, 100, 105, 101, 104),  # high>=entry(103) → enters; low>stop; not target
            _bar(15, 104, 110, 103, 109)]  # high>=target(110)
    r = simulate_order(_order("做多", 103, 100, 110), bars, node_end=_T0)
    assert r["triggered"] and r["exit_kind"] == "target"
    assert abs(r["gross_r"] - (110 - 103) / (103 - 100)) < 1e-3


def test_long_hits_stop():
    bars = [_bar(5, 100, 104, 100, 103),   # enters (high>=103)
            _bar(10, 103, 104, 99, 100)]   # low<=stop(100)
    r = simulate_order(_order("做多", 103, 100, 110), bars, node_end=_T0)
    assert r["exit_kind"] == "stop"
    assert abs(r["gross_r"] - (-1.0)) < 1e-9


def test_same_bar_stop_first_conservative():
    # bar hits BOTH stop and target → conservative convention picks stop
    bars = [_bar(5, 103, 104, 103, 103),   # enters
            _bar(10, 103, 111, 99, 105)]   # both target(110) and stop(100) in one bar
    r = simulate_order(_order("做多", 103, 100, 110), bars, node_end=_T0)
    assert r["exit_kind"] == "stop"


def test_timeout_marks_to_close():
    # enough held bars (>= max_hold_bars) with no stop/target → genuine timeout
    bars = [_bar(5 + 5 * i, 103, 104, 103, 103) for i in range(3)]
    r = simulate_order(_order("做多", 103, 100, 110), bars, node_end=_T0, max_hold_bars=3)
    assert r["exit_kind"] == "timeout" and r["resolved"] is True


def test_exit_data_exhausted_is_unresolved():
    # codex P2: triggered but forward data runs out before max_hold_bars → unresolved,
    # NOT a synthetic timeout (must be excluded from EV).
    bars = [_bar(5, 103, 104, 103, 103), _bar(10, 103, 104, 103, 103)]
    r = simulate_order(_order("做多", 103, 100, 110), bars, node_end=_T0, max_hold_bars=50)
    assert r["triggered"] is True and r["resolved"] is False
    assert r["exit_kind"] == "exit_data_exhausted" and "gross_r" not in r


def test_entry_data_exhausted_is_unresolved():
    # no trigger AND data ran out before wait window → unresolved (can't conclude no-trade)
    bars = [_bar(5, 100, 102, 99, 100)]
    r = simulate_order(_order("做多", 103, 100, 110), bars, node_end=_T0, max_wait_bars=50)
    assert r["triggered"] is False and r["resolved"] is False
    assert r["exit_kind"] == "entry_data_exhausted"


def test_no_trigger_resolved_when_wait_window_covered():
    bars = [_bar(5 + 5 * i, 100, 102, 99, 100) for i in range(4)]
    r = simulate_order(_order("做多", 103, 100, 110), bars, node_end=_T0, max_wait_bars=3)
    assert r["triggered"] is False and r["resolved"] is True and r["exit_kind"] == "no_trigger"


def test_short_hits_target():
    bars = [_bar(5, 98, 99, 96, 97),       # low<=entry(97) → short enters; high<stop(100)
            _bar(10, 97, 98, 89, 90)]      # low<=target(90)
    r = simulate_order(_order("做空", 97, 100, 90), bars, node_end=_T0)
    assert r["exit_kind"] == "target"
    assert abs(r["gross_r"] - (97 - 90) / (100 - 97)) < 1e-3


def test_cost_r_applied():
    bars = [_bar(5, 100, 105, 100, 104), _bar(10, 104, 110, 103, 109)]
    r = simulate_order(_order("做多", 103, 100, 110), bars, node_end=_T0, cost_r=0.25)
    assert abs(r["net_r"] - (r["gross_r"] - 0.25)) < 1e-3


def test_orders_from_replay_filters():
    replay = {"results": [
        {"order_type": "不下单"},
        {"order_type": "突破单", "order_direction": "做多", "entry": 1, "stop": 0, "target": 3},
        {"order_type": "突破单", "order_direction": "做空", "entry": 5, "stop": 6, "target": 2},
    ]}
    assert len(orders_from_replay(replay, None)) == 2
    assert len(orders_from_replay(replay, "做多")) == 1
