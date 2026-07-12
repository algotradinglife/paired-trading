from __future__ import annotations

from datetime import date, timedelta

import pytest

from engine.pa_feitian.swing_induction import DailyBar, SourceSeries
from engine.pa_feitian.swing_line_induction import TOLERANCE_LOOKBACK_BARS
from engine.pa_feitian.swing_line_induction import build_swing_line_atlas
from engine.pa_feitian.swing_line_induction import causal_pivots
from engine.pa_feitian.swing_line_induction import classify_prefix
from engine.pa_feitian.swing_line_induction import global_label
from engine.pa_feitian.swing_line_induction import prior_tolerance
from engine.pa_feitian.swing_line_induction import validate_atlas


def _bars(start: date, count: int, *, offset: float) -> tuple[DailyBar, ...]:
    values = [10, 8, 11, 7, 12, 9, 13, 8, 14, 10, 15, 9]
    rows = []
    for index in range(count):
        value = offset + values[index % len(values)]
        rows.append(
            DailyBar(
                trading_date=start + timedelta(days=index),
                open=value,
                high=value + 2,
                low=value - 2,
                close=value + (1 if index % 2 else -1),
                volume=10,
            )
        )
    return tuple(rows)


def _series() -> list[SourceSeries]:
    return [
        SourceSeries("AU", "sha256:" + "a" * 64, _bars(date(2025, 9, 1), 240, offset=100)),
        SourceSeries("AU", "sha256:" + "b" * 64, _bars(date(2025, 9, 1), 240, offset=120)),
        SourceSeries("AU", "sha256:" + "c" * 64, _bars(date(2025, 9, 1), 240, offset=140)),
        SourceSeries("AU", "sha256:" + "d" * 64, _bars(date(2025, 9, 1), 240, offset=160)),
        SourceSeries("AG", "sha256:" + "e" * 64, _bars(date(2025, 9, 1), 240, offset=200)),
        SourceSeries("AG", "sha256:" + "f" * 64, _bars(date(2025, 9, 1), 240, offset=220)),
        SourceSeries("AG", "sha256:" + "1" * 64, _bars(date(2025, 9, 1), 240, offset=240)),
        SourceSeries("AG", "sha256:" + "2" * 64, _bars(date(2025, 9, 1), 240, offset=260)),
    ]


def test_pivot_requires_its_right_confirmation_bar() -> None:
    bars = _bars(date(2025, 9, 1), TOLERANCE_LOOKBACK_BARS + 5, offset=10)
    highs_before, lows_before = causal_pivots(bars[:2])
    highs_after, lows_after = causal_pivots(bars[:3])
    assert highs_before == [] and lows_before == []
    assert len(highs_after) + len(lows_after) >= 1


def test_tolerance_excludes_current_decision_bar() -> None:
    bars = _bars(date(2025, 9, 1), TOLERANCE_LOOKBACK_BARS + 1, offset=10)
    expected = prior_tolerance(bars)
    changed = bars[:-1] + (
        DailyBar(bars[-1].trading_date, 10, 1000, 1, 999, 10),
    )
    assert expected == prior_tolerance(changed)


def test_future_append_does_not_change_existing_prefix_classification() -> None:
    bars = _bars(date(2025, 9, 1), 80, offset=10)
    original = classify_prefix(bars[:70])
    extended = bars[:70] + (DailyBar(date(2026, 1, 1), 1, 999, 1, 999, 10),)
    assert original == classify_prefix(extended[:70])


def test_conflict_abstains_globally() -> None:
    assert global_label("long_left_touch", "short_left_touch") == "conflict"
    assert global_label("long_abstain", "short_abstain") == "abstain"


def test_atlas_is_deterministic_and_outcome_free() -> None:
    kwargs = {
        "protocol_sha256": "sha256:" + "3" * 64,
        "exp_011_atlas_sha256": "sha256:" + "4" * 64,
        "source_inventory_digest": "sha256:" + "5" * 64,
        "files_scanned_by_product": {"AU": 4, "AG": 4},
    }
    first = build_swing_line_atlas(_series(), **kwargs)
    second = build_swing_line_atlas(_series(), **kwargs)
    assert first == second
    validate_atlas(first)
    assert first["holdout_result"]["performance_metrics_present"] is False


def test_atlas_rejects_forbidden_public_fields() -> None:
    kwargs = {
        "protocol_sha256": "sha256:" + "6" * 64,
        "exp_011_atlas_sha256": "sha256:" + "7" * 64,
        "source_inventory_digest": "sha256:" + "8" * 64,
        "files_scanned_by_product": {"AU": 4, "AG": 4},
    }
    artifact = build_swing_line_atlas(_series(), **kwargs)
    artifact["representative_specimens"][0]["close"] = 12
    with pytest.raises(ValueError, match="forbidden fields"):
        validate_atlas(artifact)


def test_atlas_rejects_extra_structural_classification_fields() -> None:
    kwargs = {
        "protocol_sha256": "sha256:" + "9" * 64,
        "exp_011_atlas_sha256": "sha256:" + "a" * 64,
        "source_inventory_digest": "sha256:" + "b" * 64,
        "files_scanned_by_product": {"AU": 4, "AG": 4},
    }
    artifact = build_swing_line_atlas(_series(), **kwargs)
    artifact["representative_specimens"][0]["structural_classification"]["unexpected"] = "not_allowed"
    with pytest.raises(ValueError, match="structural classification fields"):
        validate_atlas(artifact)
