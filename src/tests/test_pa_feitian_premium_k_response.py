from __future__ import annotations

from datetime import date, timedelta

import pytest

from engine.pa_feitian.premium_k_response import HORIZONS
from engine.pa_feitian.premium_k_response import _Observation
from engine.pa_feitian.premium_k_response import _is_training_candidate
from engine.pa_feitian.premium_k_response import _summary
from engine.pa_feitian.premium_k_response import build_response_atlas
from engine.pa_feitian.premium_k_response import validate_atlas
from engine.pa_feitian.swing_induction import DailyBar, SourceSeries
from engine.pa_feitian.swing_line_induction import classify_prefix


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


def _flat_series() -> list[SourceSeries]:
    bars = tuple(
        DailyBar(
            trading_date=date(2025, 9, 1) + timedelta(days=index),
            open=10,
            high=11,
            low=9,
            close=10,
            volume=10,
        )
        for index in range(240)
    )
    identities = ["a", "b", "c", "d", "e", "f", "1", "2"]
    return [
        SourceSeries("AU" if index < 4 else "AG", "sha256:" + value * 64, bars)
        for index, value in enumerate(identities)
    ]


def _artifact() -> dict:
    return build_response_atlas(
        _series(),
        protocol_sha256="sha256:" + "3" * 64,
        source_inventory_digest="sha256:" + "4" * 64,
        files_scanned_by_product={"AU": 4, "AG": 4},
    )


def test_causal_label_does_not_change_when_a_future_bar_is_appended() -> None:
    bars = _bars(date(2025, 9, 1), 90, offset=10)
    assert classify_prefix(bars[:70]) == classify_prefix((bars[:70] + (bars[80],))[:70])


def test_summary_candidate_gate_is_fixed() -> None:
    observations = [
        _Observation("sha256:" + str(index), "long_right_break", 1, "training", 0.01)
        for index in range(20)
    ]
    summary = _summary(observations, label="long_right_break", horizon=1)
    assert _is_training_candidate(summary) is True
    assert _is_training_candidate({**summary, "median_signed_change": 0.0}) is False


def test_response_atlas_is_deterministic_and_uses_fixed_matrix_shape() -> None:
    first = _artifact()
    second = _artifact()
    assert first == second
    validate_atlas(first)
    assert len(first["training_response_matrix"]) == 6 * len(HORIZONS)
    assert first["training_candidate_freeze"]["frozen_before_holdout_application"] is True
    assert [
        {"structural_label": row["structural_label"], "horizon_completed_daily_bars": row["horizon_completed_daily_bars"]}
        for row in first["holdout_application"]["candidate_response_matrix"]
    ] == first["training_candidate_freeze"]["candidate_set"]


def test_no_candidate_does_not_apply_holdout() -> None:
    rows = build_response_atlas(
        _flat_series(),
        protocol_sha256="sha256:" + "5" * 64,
        source_inventory_digest="sha256:" + "6" * 64,
        files_scanned_by_product={"AU": 4, "AG": 4},
    )
    assert rows["training_candidate_freeze"]["candidate_set"] == []
    assert rows["holdout_application"]["status"] == "not_applied_no_training_candidates"
    assert rows["holdout_application"]["candidate_response_matrix"] == []


def test_public_artifact_rejects_forbidden_fields() -> None:
    artifact = _artifact()
    artifact["contract"] = "not_public"
    with pytest.raises(ValueError, match="forbidden fields"):
        validate_atlas(artifact)


def test_public_artifact_rejects_extra_matrix_fields() -> None:
    artifact = _artifact()
    artifact["training_response_matrix"][0]["unexpected"] = "not_allowed"
    with pytest.raises(ValueError, match="aggregate matrix fields"):
        validate_atlas(artifact)
