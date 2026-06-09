import numpy as np
import pandas as pd
from scripts.backtest_pa_atop import simulate_short, htf_relation_top, fold_period


def _bars(closes, highs=None, lows=None):
    n = len(closes)
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, tz="UTC"),
        "open": closes, "close": closes,
        "high": highs if highs is not None else [c * 1.001 for c in closes],
        "low":  lows if lows is not None else [c * 0.999 for c in closes],
        "volume": [1] * n,
    })


def test_simulate_short_profits_on_downmove():
    # entry at 100, ATR=1, stop_mult=1.5 → stop=101.5, tp1=98.5, tp2=97
    closes = [100, 99, 97, 96, 95]
    bars = _bars(closes, highs=[100.5] * 5, lows=[c - 0.2 for c in closes])
    atr = pd.Series([1.0] * 5)
    r = simulate_short(bars, 0, atr, stop_mult=1.5, max_hold=4)
    assert r is not None and r > 0  # price fell → short profits


def test_simulate_short_tp1_at_boundary_credits_partial_exit():
    # entry 100, ATR 1, stop_mult 1.5 → stop 101.5, tp1 98.5, tp2 97.
    # TP1 is first touched ONLY on the last hold bar (offset==max_hold), then the
    # close fades back to entry (mark-to-market = 0). The fixed sim must credit the
    # banked TP1 (0.5 + 0.5*mtm = 0.5), not score it as flat (the pre-fix bug → 0.0).
    closes = [100, 100, 100]
    bars = _bars(closes, highs=[100.5] * 3, lows=[99.8, 99.8, 98.4])
    atr = pd.Series([1.0] * 3)
    r = simulate_short(bars, 0, atr, stop_mult=1.5, max_hold=2)
    assert r == 0.5


def test_simulate_short_stopped_on_upmove():
    closes = [100, 100, 100, 100, 100]
    bars = _bars(closes, highs=[102.0] * 5, lows=[99.8] * 5)  # high 102 ≥ stop 101.5
    atr = pd.Series([1.0] * 5)
    r = simulate_short(bars, 0, atr, stop_mult=1.5, max_hold=4)
    assert r == -1.0


def test_htf_relation_top_convention():
    h_ts = pd.to_datetime(["2024-01-01", "2024-01-02"], utc=True).values
    # HTF DIF < 0 → bearish → SUPPORTS a short
    assert htf_relation_top(pd.Timestamp("2024-01-03", tz="UTC"), h_ts,
                            np.array([-0.5, -0.3])) == "supporting"
    # HTF DIF > 0 → bullish → OPPOSES a short
    assert htf_relation_top(pd.Timestamp("2024-01-03", tz="UTC"), h_ts,
                            np.array([0.5, 0.3])) == "opposing"
    # no HTF bar before ts
    assert htf_relation_top(pd.Timestamp("2023-12-01", tz="UTC"), h_ts,
                            np.array([0.5, 0.3])) is None


def test_fold_period_k3():
    c1 = pd.Timestamp("2022-12-31", tz="UTC")
    c2 = pd.Timestamp("2023-12-31", tz="UTC")
    c3 = pd.Timestamp("2024-12-31", tz="UTC")
    assert fold_period(pd.Timestamp("2022-06-01", tz="UTC"), c1, c2, c3) == "IS"
    assert fold_period(pd.Timestamp("2023-06-01", tz="UTC"), c1, c2, c3) == "OOS1"
    assert fold_period(pd.Timestamp("2024-06-01", tz="UTC"), c1, c2, c3) == "OOS2"
    assert fold_period(pd.Timestamp("2025-06-01", tz="UTC"), c1, c2, c3) == "OOS3"
