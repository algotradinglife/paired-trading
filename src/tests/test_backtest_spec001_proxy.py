"""Unit tests for backtest_spec001_proxy — deterministic SPEC-001 proxy detector (hermetic)."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from scripts.backtest_spec001_proxy import (  # noqa: E402
    PAYOFF_MIN,
    _atr,
    _swing_lows,
    detect_signals,
)

_T0 = dt.datetime(2025, 1, 1, 0, 0, tzinfo=dt.timezone.utc)


def _bar(i, o, h, lo, c):
    return {"ts_open": int((_T0 + dt.timedelta(minutes=5 * i)).timestamp()),
            "open": o, "high": h, "low": lo, "close": c}


def test_atr_positive_and_finite():
    bars = [_bar(i, 100, 101, 99, 100) for i in range(30)]
    atr = _atr(bars)
    assert len(atr) == 30
    assert np.all(np.isfinite(atr)) and np.all(atr > 0)


def test_swing_lows_finds_planted_low():
    # flat 100s with a single dip at index 10 → swing low
    bars = [_bar(i, 100, 101, 99, 100) for i in range(21)]
    bars[10] = _bar(10, 98, 98.5, 95, 97)
    sl = _swing_lows(bars, n=3)
    assert 10 in sl.tolist()


def _downleg_then_signal():
    """Build a down-leg (prior high ~110 → low ~100), a retest swing low, then a strong
    bull signal bar at the low — a SPEC-001-shaped setup. Length >= LOOKBACK+ATR_PERIOD+2."""
    bars = []
    # 0-19: high plateau ~110 (prior swing high / down-leg origin)
    for i in range(20):
        bars.append(_bar(i, 110, 110.5, 109.5, 110))
    # 20-37: decline 109 → ~100
    for k, i in enumerate(range(20, 38)):
        px = 109 - k * 0.5
        bars.append(_bar(i, px + 0.3, px + 0.5, px - 0.5, px))
    # 38-42: first low ~100 (swing low #1)
    for i in range(38, 43):
        bars.append(_bar(i, 100.3, 100.6, 99.8, 100.1))
    bars[40] = _bar(40, 100.2, 100.5, 99.6, 99.9)   # local min → swing low #1
    # 43-49: small bounce to ~103
    for k, i in enumerate(range(43, 50)):
        px = 100.5 + k * 0.3
        bars.append(_bar(i, px - 0.2, px + 0.4, px - 0.4, px))
    # 50-54: retest back to ~100 (swing low #2, second entry)
    for i in range(50, 55):
        bars.append(_bar(i, 100.2, 100.5, 99.7, 100.0))
    bars[52] = _bar(52, 100.1, 100.4, 99.6, 99.8)   # local min → swing low #2
    # 55: strong bull signal bar at the low
    bars.append(_bar(55, 99.8, 101.6, 99.6, 101.5))  # body 1.7/2.0=0.85, close_pos 0.95
    # 56-61: tail
    for i in range(56, 62):
        bars.append(_bar(i, 101.5, 102.0, 101.0, 101.8))
    return bars


def test_detect_signals_emits_well_formed_long():
    sigs = detect_signals(_downleg_then_signal())
    assert sigs, "expected at least one SPEC-001 proxy signal"
    s = sigs[0]
    assert s["order_direction"] == "做多"
    assert s["entry"] > s["stop"]                    # long: entry above stop
    assert s["target"] > s["entry"]
    assert s["payoff"] >= PAYOFF_MIN                 # trader's-equation gate satisfied


def test_no_signal_on_flat_series():
    bars = [_bar(i, 100, 100.5, 99.5, 100) for i in range(80)]
    assert detect_signals(bars) == []


def test_no_signal_when_too_short():
    assert detect_signals([_bar(i, 100, 101, 99, 100) for i in range(10)]) == []
