"""Regression: TP1-at-boundary partial-exit credit across all trade simulators.

Shared latent bug (first found + fixed in backtest_pa_atop.simulate_short):
when TP1 is banked but the trade then runs to the holding boundary — either
TP1 first touches on the very last hold bar, or the bar window runs out after
TP1 — the post-loop fall-through scored raw mark-to-market and skipped the
+0.5R partial-exit credit. A TP1-then-fade trade was thus mis-scored as flat.

Scenario used below (the "ran out of bars after TP1" path): 4 bars, large
MAX_HOLD. entry=100, ATR=1, stop_mult=1.5 → risk=1.5. Long: stop=98.5,
tp1=101.5, tp2=103. TP1 is touched on bar 1 (high 102, < tp2), no stop, then
price fades back to entry close (mark = 0). Correct result = 0.5 + 0.5*0 = 0.5,
labelled tp1_max; the pre-fix bug returned raw 0.0 labelled max_hold.
"""
import pandas as pd
import pytest

from scripts.backtest_pa_standalone import simulate_trade as pa_standalone_sim
from scripts.backtest_pa_swing import simulate_trade as pa_swing_sim
from scripts.backtest_pa_us_k3 import simulate_trade as pa_us_k3_sim
from scripts.backtest_pa_incycle import simulate_trade as pa_incycle_sim
from scripts.backtest_bpull import simulate_trade as bpull_sim
from scripts.backtest_vflush import simulate_trade as vflush_sim
from scripts.backtest_b1_bottom import simulate_trade as b1_sim
from scripts.backtest_context_a_ev import simulate_trade as context_a_sim
from scripts.backtest_dif_crossing import simulate_trade as dif_sim
from scripts.backtest_rr_pool import simulate_trade as rr_sim
from scripts.backtest_pa_top_grid import simulate_short as patop_short
from scripts.backtest_full_stack import _simulate_forward


def _long_bars():
    # TP1 touched on bar 1 (high 102 ≥ 101.5, < tp2 103); no stop (lows ≥ 99 > 98.5);
    # then 2 more flat bars and the window ends → fall-through with TP1 banked.
    closes = [100.0, 100.0, 100.0, 100.0]
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=4, tz="UTC"),
        "open": closes, "close": closes,
        "high": [100.5, 102.0, 100.5, 100.5],
        "low":  [99.5, 99.0, 99.0, 99.0],
        "volume": [1] * 4,
    })


def _short_bars():
    # Mirror for the short side: TP1 (low ≤ 98.5, > tp2 97) on bar 1, no stop
    # (highs ≤ 100.5 < 101.5), then fade back to entry close.
    closes = [100.0, 100.0, 100.0, 100.0]
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=4, tz="UTC"),
        "open": closes, "close": closes,
        "high": [100.5, 100.5, 100.5, 100.5],
        "low":  [99.5, 98.0, 99.0, 99.0],
        "volume": [1] * 4,
    })


_ATR = pd.Series([1.0] * 4)


def test_pa_standalone_credits_tp1_at_boundary():
    assert pa_standalone_sim(_long_bars(), 0, 1.5, _ATR) == 0.5


def test_pa_swing_credits_tp1_at_boundary():
    assert pa_swing_sim(_long_bars(), 0, 1.5, _ATR, 20) == 0.5


def test_pa_us_k3_credits_tp1_at_boundary():
    assert pa_us_k3_sim(_long_bars(), 0, 1.5, _ATR) == 0.5


def test_pa_incycle_credits_tp1_at_boundary():
    assert pa_incycle_sim(_long_bars(), 0, 1.5, _ATR) == 0.5


def test_bpull_credits_tp1_at_boundary():
    assert bpull_sim(_long_bars(), 0, 1.5, _ATR) == 0.5


def test_vflush_credits_tp1_at_boundary():
    assert vflush_sim(_long_bars(), 0, 1.5, _ATR, max_hold=20) == 0.5


def test_b1_bottom_credits_tp1_at_boundary():
    assert b1_sim(_long_bars(), 0, 1.5, _ATR) == 0.5


def test_context_a_credits_tp1_at_boundary():
    assert context_a_sim(_long_bars(), 0, 1.5, _ATR) == 0.5


def test_dif_crossing_credits_tp1_at_boundary():
    outcome, realized = dif_sim(_long_bars(), 0, 1.5, _ATR)
    assert outcome == "tp1_max"
    assert realized == 0.5


def test_rr_pool_credits_tp1_at_boundary():
    outcome, realized, _bars_to_tp1, _bars_to_exit = rr_sim(
        _long_bars(), 0, "bottom", 1.5, _ATR)
    assert outcome == "tp1_max"
    assert realized == 0.5


def test_pa_top_grid_short_credits_tp1_at_boundary():
    assert patop_short(_short_bars(), 0, _ATR, stop_mult=1.5, max_hold=40) == 0.5


def test_full_stack_simulate_forward_credits_tp1_at_boundary():
    out = _simulate_forward(_long_bars(), 0, 100.0, 98.5, 20)
    assert out.outcome == "tp1_max"
    assert out.realized_r == 0.5
