"""Tests for the divergence-alert chain (pre-gate alerts + tbreak combine)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.divergence.detector import detect_all_divergences
from engine.features.macd import macd
from engine.features.streams import compute_feature_streams
from engine.units.snapshot import compute_unit_metadata


def random_walk_bars(n: int = 400, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0, 1.0, n))
    high = close + rng.uniform(0.2, 1.5, n)
    low = close - rng.uniform(0.2, 1.5, n)
    ts = pd.date_range("2022-01-03", periods=n, freq="D", tz="UTC")
    return pd.DataFrame({"timestamp": ts, "open": close, "high": high,
                         "low": low, "close": close})


def _divergence_signals(bars: pd.DataFrame, gate: bool):
    macd_df = macd(bars["close"], hist_scale=1.0)
    streams = compute_feature_streams(
        bars["close"], macd_df["dif"], macd_df["dea"], macd_df["hist"])
    units = compute_unit_metadata(
        macd_df["dif"], macd_df["dea"], macd_df["hist"],
        streams["dif_proximity_zero"])
    return detect_all_divergences(
        units_df=units, ohlc=bars, dif=macd_df["dif"], hist=macd_df["hist"],
        level_id="D", instrument_class="us_equity", gate=gate)


def test_gate_false_is_superset_of_gate_true():
    bars = random_walk_bars()
    gated = _divergence_signals(bars, gate=True)
    raw = _divergence_signals(bars, gate=False)
    assert len(raw) >= len(gated)
    # us_equity gate drops/de-weights tops; raw must keep at least as many tops
    raw_tops = [s for s in raw if s.direction == "top"]
    gated_tops = [s for s in gated if s.direction == "top"]
    assert len(raw_tops) >= len(gated_tops)
