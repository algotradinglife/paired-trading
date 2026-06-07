"""Tests for B1BottomDetector."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.divergence.b1_bottom_detector import B1BottomDetector, B1BottomSignal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_ag_bars() -> pd.DataFrame:
    bars_path = (
        Path(__file__).resolve().parents[1] / "data" / "raw" / "kq_m_shfe_ag_daily.json"
    )
    if not bars_path.exists():
        pytest.skip("no local bar data")
    payload = json.loads(bars_path.read_text())
    raw = payload.get("bars", payload)
    bars = pd.DataFrame(raw)
    bars["timestamp"] = pd.to_datetime(bars["time"], unit="s", utc=True)
    bars = bars.sort_values("timestamp").reset_index(drop=True)
    return bars


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScanReturnsListOnRealData:
    def test_scan_returns_list_on_real_data(self):
        bars = _load_ag_bars()
        detector = B1BottomDetector()
        result = detector.scan(bars)
        assert isinstance(result, list)
        assert all(isinstance(s, B1BottomSignal) for s in result)
        # Expose the count so the test output is informative
        print(f"\n  B1 signals on kq_m_shfe_ag: {len(result)}")


class TestMinGap:
    def test_scan_respects_min_gap(self):
        bars = _load_ag_bars()
        min_gap = 10
        detector = B1BottomDetector(min_gap=min_gap)
        result = detector.scan(bars)
        if len(result) < 2:
            pytest.skip("fewer than 2 signals — cannot check gap")
        for a, b in zip(result, result[1:]):
            assert b.bar_idx - a.bar_idx >= min_gap, (
                f"consecutive signals too close: {a.bar_idx} and {b.bar_idx} "
                f"(gap={b.bar_idx - a.bar_idx} < min_gap={min_gap})"
            )


class TestPolicyWeight:
    def _make_sig(self, h_rel: str | None) -> B1BottomSignal:
        return B1BottomSignal(
            bar_idx=100,
            timestamp=pd.Timestamp("2024-01-01", tz="UTC"),
            features={"dif": -0.5, "hist": -0.1},
            higher_tf_relation=h_rel,
        )

    def test_policy_weight_opposing(self):
        # B1 is REJECTED — policy_weight() returns 0.0 for all cases
        sig = self._make_sig("opposing")
        assert B1BottomDetector.policy_weight(sig, "cn_metal_futures") == 0.0

    def test_policy_weight_non_opposing_returns_zero(self):
        sig = self._make_sig("supporting")
        assert B1BottomDetector.policy_weight(sig, "cn_metal_futures") == 0.0

    def test_policy_weight_wrong_class_returns_zero(self):
        sig = self._make_sig("opposing")
        assert B1BottomDetector.policy_weight(sig, "us_equity") == 0.0
