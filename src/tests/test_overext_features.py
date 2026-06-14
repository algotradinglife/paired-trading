"""Parity tests: engine.divergence.overext_features must match the validated
analysis-script feature definitions exactly (numeric agreement), so production
weights reproduce the backtested numbers."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine.divergence import overext_features as of  # noqa: E402
from scripts.analyze_second_entry import classify_test_ordinal  # noqa: E402
from scripts.analyze_signalbar_quality import signal_bar_features  # noqa: E402
from scripts.backtest_rr_pool import compute_atr  # noqa: E402
from engine.features.swing_context import detect_swing_points  # noqa: E402


def _synthetic_bars() -> pd.DataFrame:
    """Deterministic OHLC with two same-level swing lows separated by a rally
    (so the later index classifies as a retest)."""
    rng = np.random.default_rng(7)
    n = 90
    base = 100.0
    closes = []
    price = base
    for i in range(n):
        # gentle drift + two dips to ~92 around i=30 and i=60 with a rally between
        if i in range(28, 33):
            price = 92.0 + (i - 30) * 0.2
        elif i in range(43, 50):
            price = 99.0            # rally between the two lows
        elif i in range(58, 63):
            price = 92.2 + (i - 60) * 0.2
        else:
            price = base + rng.normal(0, 0.6)
        closes.append(price)
    close = np.array(closes)
    high = close + np.abs(rng.normal(0.5, 0.3, n))
    low = close - np.abs(rng.normal(0.5, 0.3, n))
    open_ = close + rng.normal(0, 0.2, n)
    return pd.DataFrame({
        "timestamp": pd.date_range("2020-01-01", periods=n, freq="D"),
        "open": open_, "high": high, "low": low, "close": close,
    })


def test_range_vs_avg_matches_analysis_script():
    bars = _synthetic_bars()
    for idx in range(of.LEN_WIN + 5, len(bars)):
        engine_val = of.range_vs_avg(bars, idx)
        feats = signal_bar_features(bars, idx)
        script_val = feats["range_vs_avg"] if feats else None
        if engine_val is None or script_val is None or not np.isfinite(script_val):
            continue
        assert abs(engine_val - script_val) < 1e-9, f"idx={idx}"


def test_test_ordinal_matches_analysis_script():
    bars = _synthetic_bars()
    atr = compute_atr(bars)
    _, sl_idx = detect_swing_points(bars, n=of.SWING_N)
    ctx = of.prepare_context(bars)
    # context must reproduce the same swing lows + ATR the script would use
    assert np.array_equal(ctx.swing_low_idx, sl_idx)
    assert np.allclose(ctx.atr.values, atr.values, equal_nan=True)
    saw_retest = False
    for idx in range(of.SWING_N + 1, len(bars)):
        engine_ord = of.test_ordinal(bars, idx, ctx)
        script = classify_test_ordinal(bars, idx, sl_idx, atr)
        script_ord = script["ordinal"] if script else None
        assert engine_ord == script_ord, f"idx={idx}: {engine_ord} != {script_ord}"
        if engine_ord and engine_ord >= 2:
            saw_retest = True
    assert saw_retest, "fixture should produce at least one retest (ordinal>=2)"


def test_signal_deweight_fail_open_non_applicable():
    bars = _synthetic_bars()
    ctx = of.prepare_context(bars)
    # top side never de-weighted
    assert of.signal_deweight_factor(bars, 50, "top", "opposing", ctx) == 1.0
    # bottom supporting not a validated lane
    assert of.signal_deweight_factor(bars, 50, "bottom", "supporting", ctx) == 1.0


def test_signal_deweight_fail_open_too_early():
    bars = _synthetic_bars()
    ctx = of.prepare_context(bars)
    # idx < LEN_WIN → range_vs_avg None → fail open
    assert of.signal_deweight_factor(bars, 5, "bottom", "opposing", ctx) == 1.0


def test_fail_open_on_nonfinite_ohlc():
    """codex P2: nan in the feature window must fail open (factor 1.0), not apply
    the max over-extension penalty via w_a(nan)=W_MIN."""
    bars = _synthetic_bars()
    ctx = of.prepare_context(bars)
    idx = 50
    # corrupt a prior-window bar so np.mean(prior range) is nan
    bars.loc[idx - 3, "high"] = float("nan")
    assert of.range_vs_avg(bars, idx) is None
    assert of.signal_deweight_factor(bars, idx, "bottom", "opposing", ctx) == 1.0


def test_signal_deweight_applies_on_bottom_opposing():
    bars = _synthetic_bars()
    ctx = of.prepare_context(bars)
    # find an over-extended bottom signal index and confirm factor < 1
    for idx in range(of.LEN_WIN + 5, len(bars)):
        rva = of.range_vs_avg(bars, idx)
        if rva is not None and rva > 1.5:
            f = of.signal_deweight_factor(bars, idx, "bottom", "opposing", ctx)
            assert f < 1.0
            break
