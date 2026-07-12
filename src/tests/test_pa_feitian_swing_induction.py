from __future__ import annotations

from datetime import date, timedelta

import pytest

from engine.pa_feitian.swing_induction import DailyBar
from engine.pa_feitian.swing_induction import SourceSeries
from engine.pa_feitian.swing_induction import build_swing_atlas
from engine.pa_feitian.swing_induction import select_corpus_files
from engine.pa_feitian.swing_induction import select_coverage_qualified_series
from engine.pa_feitian.swing_induction import trace_classification
from engine.pa_feitian.swing_induction import validate_atlas


def _bars(start: date, count: int, *, offset: float) -> tuple[DailyBar, ...]:
    rows = []
    for index in range(count):
        base = offset + index
        rows.append(
            DailyBar(
                trading_date=start + timedelta(days=index),
                open=base + 1,
                high=base + 3,
                low=base,
                close=base + (2 if index % 3 else 0.5),
                volume=10,
            )
        )
    return tuple(rows)


def _series() -> list[SourceSeries]:
    return [
        SourceSeries("AU", "sha256:" + "a" * 64, _bars(date(2025, 10, 1), 220, offset=10)),
        SourceSeries("AG", "sha256:" + "b" * 64, _bars(date(2025, 10, 1), 220, offset=100)),
    ]


def test_trace_is_invariant_to_post_decision_bars() -> None:
    bars = _bars(date(2025, 10, 1), 65, offset=10)
    original = trace_classification(bars[:60])
    changed_future = bars[:60] + (
        DailyBar(date(2026, 1, 1), 999, 1000, 998, 999, 10),
    )
    assert original == trace_classification(changed_future[:60])


def test_atlas_uses_frozen_training_and_holdout_roles() -> None:
    artifact = build_swing_atlas(_series(), protocol_sha256="sha256:" + "c" * 64)
    validate_atlas(artifact)
    assert artifact["coverage"]["candidate_windows_by_product_and_split"]["AU"]["training"] > 0
    assert artifact["coverage"]["candidate_windows_by_product_and_split"]["AG"]["holdout"] > 0
    assert artifact["holdout_result"]["performance_metrics_present"] is False


def test_atlas_is_deterministic_and_has_no_raw_price_fields() -> None:
    first = build_swing_atlas(_series(), protocol_sha256="sha256:" + "d" * 64)
    second = build_swing_atlas(_series(), protocol_sha256="sha256:" + "d" * 64)
    assert first == second
    text = str(first).lower()
    for forbidden in ("'open'", "'high'", "'low'", "'close'", "'outcome'", "'pnl'"):
        assert forbidden not in text


def test_atlas_rejects_forbidden_public_fields() -> None:
    artifact = build_swing_atlas(_series(), protocol_sha256="sha256:" + "f" * 64)
    artifact["representative_specimens"][0]["close"] = 99
    with pytest.raises(ValueError, match="forbidden fields"):
        validate_atlas(artifact)


def test_requires_both_products_and_holdout_coverage() -> None:
    with pytest.raises(ValueError, match="both AU and AG"):
        build_swing_atlas(_series()[:1], protocol_sha256="sha256:" + "e" * 64)


def test_corpus_selection_is_product_local_and_bounded(tmp_path) -> None:
    files = []
    for product in ("au", "ag"):
        for strike in (100, 200, 300):
            path = tmp_path / f"SHFE.{product}2606C{strike}.parquet"
            path.touch()
            files.append((product.upper(), path))
    selected = select_corpus_files(files, max_series_per_product=2)
    assert [product for product, _ in selected].count("AU") == 2
    assert [product for product, _ in selected].count("AG") == 2


def test_coverage_selection_requires_both_split_windows(monkeypatch, tmp_path) -> None:
    paths = []
    for product in ("AU", "AG"):
        path = tmp_path / f"SHFE.{product.lower()}2606C100.parquet"
        path.touch()
        paths.append((product, path))
    monkeypatch.setattr(
        "engine.pa_feitian.swing_induction.load_source_series",
        lambda product, path: SourceSeries(product, "sha256:" + product.lower() * 32, _bars(date(2025, 10, 1), 220, offset=1)),
    )
    selected, scanned = select_coverage_qualified_series(paths, max_series_per_product=1)
    assert len(selected) == 2
    assert scanned == {"AU": 1, "AG": 1}
