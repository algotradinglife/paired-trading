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


from engine.divergence.alert_chain import (
    ChainEvent, DivAlert, combine, divergence_alerts,
)
from engine.divergence.tbreak_detector import TBreakSignal


def _alert(bar_idx: int, direction: str) -> DivAlert:
    return DivAlert(bar_idx=bar_idx,
                    timestamp=pd.Timestamp("2024-01-01", tz="UTC"),
                    direction=direction, level="intra_cycle",
                    subtype="standard", confidence=0.6)


def _tbreak(bar_idx: int, direction: str) -> TBreakSignal:
    return TBreakSignal(bar_idx=bar_idx,
                        timestamp=pd.Timestamp("2024-02-01", tz="UTC"),
                        direction=direction, features={})


def test_combine_top_plus_breakdown_is_put_candidate():
    events = combine([_alert(95, "top")], [_tbreak(100, "breakdown")], lookback=20)
    assert len(events) == 1
    ev = events[0]
    assert ev.candidate == "put_candidate"
    assert ev.gap_bars == 5


def test_combine_bottom_plus_breakout_is_call_candidate():
    events = combine([_alert(90, "bottom")], [_tbreak(100, "breakout")], lookback=20)
    assert [e.candidate for e in events] == ["call_candidate"]


def test_combine_respects_lookback_window():
    # Alert 25 bars before the break, lookback 20 -> no pairing.
    assert combine([_alert(75, "top")], [_tbreak(100, "breakdown")], lookback=20) == []
    # Alert AFTER the break never pairs.
    assert combine([_alert(105, "top")], [_tbreak(100, "breakdown")], lookback=20) == []


def test_combine_direction_mismatch_does_not_pair():
    assert combine([_alert(95, "bottom")], [_tbreak(100, "breakdown")], lookback=20) == []


def test_combine_picks_most_recent_matching_alert():
    events = combine([_alert(85, "top"), _alert(95, "top")],
                     [_tbreak(100, "breakdown")], lookback=20)
    assert len(events) == 1
    assert events[0].alert.bar_idx == 95


def test_divergence_alerts_smoke_and_threshold():
    bars = random_walk_bars()
    alerts = divergence_alerts(bars, instrument_class="us_equity",
                               min_confidence=0.0)
    assert isinstance(alerts, list)
    assert all(a.direction in ("top", "bottom") for a in alerts)
    assert all(a.level in ("intra_cycle", "inter_cycle", "inter_segment")
               for a in alerts)
    high = divergence_alerts(bars, instrument_class="us_equity",
                             min_confidence=0.9)
    assert len(high) <= len(alerts)
