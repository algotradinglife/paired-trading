from __future__ import annotations

import copy
import os
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from engine.pa_feitian.historical_bare_k_episode_pack import (
    Candidate,
    HistoricalBareKEpisodePackError,
    NativeRow,
    SourceTask,
    _overlaps,
    assign_anonymous_blind_payload_ids,
    build_episode_pack,
    decode_sealed_reveal,
    discover_sources,
    enumerate_candidates,
    load_contract,
    pretty_json_bytes,
    read_source_task,
    reveal_with_annotations,
    validate_annotation_document,
    validate_blind_pack,
    validate_reveal_payload,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = (
    REPO_ROOT / "docs/research/pa-feitian-m6r-historical-bare-k-episode-pack-contract-v1.json"
)


def _table(
    start: datetime, rows: int, *, invalid_at: int | None = None, shape_seed: int = 0
) -> pa.Table:
    slope = 0.08 + shape_seed * 0.0007
    opens = [100.0 + index * slope for index in range(rows)]
    closes = [
        value + (0.55 + shape_seed * 0.01 if (index + shape_seed) % 7 else -0.25)
        for index, value in enumerate(opens)
    ]
    highs = [
        max(open_, close) + 1.2 + ((index + shape_seed) % 5) * 0.1
        for index, (open_, close) in enumerate(zip(opens, closes))
    ]
    lows = [min(open_, close) - 1.1 for open_, close in zip(opens, closes)]
    if invalid_at is not None:
        highs[invalid_at] = lows[invalid_at] - 1.0
    return pa.table(
        {
            "datetime": [start + timedelta(days=index) for index in range(rows)],
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [100.0 + index % 11 for index in range(rows)],
            "open_interest": [500.0 + index % 13 for index in range(rows)],
        }
    )


def _write_root(root: Path, *, invalid_at: int | None = None) -> None:
    contract = load_contract(CONTRACT_PATH)
    daily = root / "daily"
    daily.mkdir(parents=True)
    starts = [
        datetime(2022, 1, 3, tzinfo=UTC),
        datetime(2023, 1, 3, tzinfo=UTC),
        datetime(2024, 1, 3, tzinfo=UTC),
        datetime(2025, 1, 3, tzinfo=UTC),
    ]
    for family_index, family in enumerate(contract["candidate_universe"]):
        for era, start in enumerate(starts, start=1):
            suffix = f"{era + 20:02}01" if family["exchange"] != "CZCE" else f"{era + 20:03}"
            name = f"{family['exchange']}.{family['product']}{suffix}.parquet"
            pq.write_table(
                _table(
                    start,
                    180,
                    invalid_at=invalid_at if family_index == 0 and era == 1 else None,
                    shape_seed=family_index * 10 + era,
                ),
                daily / name,
            )


def _build(tmp_path: Path) -> tuple[dict, dict, Path]:
    root = tmp_path / "quant-data"
    _write_root(root)
    contract = load_contract(CONTRACT_PATH)
    artifacts = build_episode_pack(
        contract=contract,
        contract_path=CONTRACT_PATH,
        data_root=root,
        workers=3,
    )
    return contract, artifacts, root


def test_build_is_byte_stable_and_has_required_coverage(tmp_path: Path) -> None:
    contract, first, root = _build(tmp_path)
    assert (
        contract["episode_protocol"][
            "ranking_or_labeling_uses_reveal_direction_magnitude_metrics_outcomes_or_profitability"
        ]
        is False
    )
    second = build_episode_pack(
        contract=contract,
        contract_path=CONTRACT_PATH,
        data_root=root,
        workers=1,
    )
    assert {key: pretty_json_bytes(value) for key, value in first.items()} == {
        key: pretty_json_bytes(value) for key, value in second.items()
    }
    coverage = first["coverage"]
    assert coverage["aggregate"]["selected_episode_count"] == 72
    assert coverage["aggregate"]["candidate_activity_episode_count"] == 36
    assert coverage["aggregate"]["ordinary_control_episode_count"] == 36
    assert len(coverage["family_coverage"]) == 9
    assert len(coverage["exchange_coverage"]) == 3


def test_blind_surface_is_anonymous_and_sealed_reveal_has_mapping(tmp_path: Path) -> None:
    _, artifacts, _ = _build(tmp_path)
    blind = artifacts["blind"]
    validate_blind_pack(blind)
    assert set(blind) == {"schema_version", "issue_number", "episode_count", "episodes"}
    assert set(blind["episodes"][0]) == {"episode_id", "bars"}
    assert set(blind["episodes"][0]["bars"][0]) == {
        "bar_index",
        "open_index",
        "high_index",
        "low_index",
        "close_index",
    }
    blind_text = pretty_json_bytes(blind).decode().lower()
    for forbidden in (
        "family",
        "exchange",
        "product",
        "timestamp",
        "stratum",
        "activity",
        "control",
    ):
        assert forbidden not in blind_text
    reveal = decode_sealed_reveal(artifacts["sealed_reveal"])
    assert reveal["episode_count"] == 72
    assert set(reveal["episodes"][0]["provenance"]) >= {
        "instrument_family",
        "exchange",
        "product",
        "anchor_stratum",
        "sampling_role",
        "decision_timestamp",
    }
    first_family = reveal["episodes"][0]["provenance"]["instrument_family"]
    same_family = [
        episode
        for episode in reveal["episodes"]
        if episode["provenance"]["instrument_family"] == first_family
    ]
    tampered = copy.deepcopy(reveal)
    tampered_same_family = [
        episode
        for episode in tampered["episodes"]
        if episode["provenance"]["instrument_family"] == first_family
    ]
    assert len(same_family) >= 2
    tampered_same_family[0]["future_bars"][-1]["timestamp"] = "2030-01-01T00:00:00+00:00"
    with pytest.raises(HistoricalBareKEpisodePackError, match="calendar intervals overlap"):
        validate_reveal_payload(tampered)
    tampered = copy.deepcopy(reveal)
    tampered["episodes"][0]["provenance"]["blind_start_timestamp"] = tampered["episodes"][0][
        "provenance"
    ]["blind_bar_timestamps"][1]
    with pytest.raises(HistoricalBareKEpisodePackError, match="blind start timestamp drifted"):
        validate_reveal_payload(tampered)
    for field, replacement in (
        ("exchange", "DCE"),
        ("product", "not-the-frozen-product"),
        ("family_role", "not-the-frozen-role"),
    ):
        tampered = copy.deepcopy(reveal)
        tampered["episodes"][0]["provenance"][field] = replacement
        with pytest.raises(
            HistoricalBareKEpisodePackError, match="candidate-universe binding drifted"
        ):
            validate_reveal_payload(tampered)
    tampered = copy.deepcopy(reveal)
    tampered["episodes"][0]["provenance"]["blind_bar_timestamps"][1] = tampered["episodes"][0][
        "provenance"
    ]["blind_bar_timestamps"][0]
    with pytest.raises(
        HistoricalBareKEpisodePackError, match="blind timestamps are not strictly increasing"
    ):
        validate_reveal_payload(tampered)
    tampered = copy.deepcopy(reveal)
    tampered["episodes"][0]["future_bars"][1]["timestamp"] = tampered["episodes"][0]["future_bars"][
        0
    ]["timestamp"]
    with pytest.raises(
        HistoricalBareKEpisodePackError, match="future timestamps are not strictly increasing"
    ):
        validate_reveal_payload(tampered)
    tampered = copy.deepcopy(reveal)
    tampered["episodes"][0]["future_bars"][0]["high_index"] = (
        tampered["episodes"][0]["future_bars"][0]["low_index"] - 1
    )
    with pytest.raises(HistoricalBareKEpisodePackError, match="normalized OHLC is incoherent"):
        validate_reveal_payload(tampered)


def test_reveal_requires_complete_nonempty_blind_annotations(tmp_path: Path) -> None:
    _, artifacts, _ = _build(tmp_path)
    with pytest.raises(HistoricalBareKEpisodePackError, match="acknowledgement"):
        reveal_with_annotations(
            sealed=artifacts["sealed_reveal"],
            annotations=artifacts["annotation_template"],
            acknowledge_first_pass_complete=False,
        )
    with pytest.raises(HistoricalBareKEpisodePackError, match="requires a first-pass annotation"):
        reveal_with_annotations(
            sealed=artifacts["sealed_reveal"],
            annotations=artifacts["annotation_template"],
            acknowledge_first_pass_complete=True,
        )
    annotations = copy.deepcopy(artifacts["annotation_template"])
    for row in annotations["annotations"]:
        row["annotation"] = "first-pass structural observation"
    payload = reveal_with_annotations(
        sealed=artifacts["sealed_reveal"],
        annotations=annotations,
        acknowledge_first_pass_complete=True,
    )
    assert payload["episode_count"] == 72
    with pytest.raises(HistoricalBareKEpisodePackError, match="identity metadata"):
        leaked = copy.deepcopy(annotations)
        leaked["annotations"][0]["family"] = "leak"
        validate_annotation_document(
            leaked,
            blind_pack_sha256=annotations["blind_pack_sha256"],
            episode_ids={row["episode_id"] for row in annotations["annotations"]},
            require_complete=True,
        )


def test_discovered_source_that_disappears_is_explicitly_excluded(tmp_path: Path) -> None:
    root = tmp_path / "quant-data"
    _write_root(root)
    contract = load_contract(CONTRACT_PATH)
    pq.write_table(
        _table(datetime(2022, 1, 3, tzinfo=UTC), 180),
        root / "daily" / "SHFE.cu2102.parquet",
    )

    def disappear_after_discovery(tasks: list[SourceTask]) -> None:
        next(
            task
            for task in tasks
            if task.family == "SHFE.cu" and task.source_path.name.endswith("2101.parquet")
        ).source_path.unlink()

    artifacts = build_episode_pack(
        contract=contract,
        contract_path=CONTRACT_PATH,
        data_root=root,
        workers=3,
        after_discovery=disappear_after_discovery,
    )
    coverage = artifacts["coverage"]
    assert coverage["aggregate"]["source_disappeared_after_discovery_count"] == 1
    source_family = next(
        row for row in coverage["family_coverage"] if row["instrument_family"] == "SHFE.cu"
    )
    assert source_family["explicit_exclusion_counts"]["source_disappeared_after_discovery"] == 1


def test_discovered_source_that_becomes_unreadable_is_explicitly_excluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "quant-data"
    _write_root(root)
    contract = load_contract(CONTRACT_PATH)
    pq.write_table(
        _table(datetime(2022, 1, 3, tzinfo=UTC), 180),
        root / "daily" / "SHFE.cu2102.parquet",
    )
    import engine.pa_feitian.historical_bare_k_episode_pack as episode_pack

    capture = episode_pack._capture_regular_file

    def unreadable_after_discovery(path: Path) -> tuple[bytes | None, str | None]:
        if path.name == "SHFE.cu2101.parquet":
            return None, "source_unreadable_after_discovery"
        return capture(path)

    monkeypatch.setattr(episode_pack, "_capture_regular_file", unreadable_after_discovery)
    artifacts = build_episode_pack(
        contract=contract,
        contract_path=CONTRACT_PATH,
        data_root=root,
        workers=3,
    )
    coverage = artifacts["coverage"]
    assert coverage["aggregate"]["source_unreadable_after_discovery_count"] == 1
    source_family = next(
        row for row in coverage["family_coverage"] if row["instrument_family"] == "SHFE.cu"
    )
    assert source_family["explicit_exclusion_counts"]["source_unreadable_after_discovery"] == 1


def test_invalid_row_blocks_any_window_that_would_cross_it(tmp_path: Path) -> None:
    root = tmp_path / "quant-data"
    _write_root(root, invalid_at=90)
    contract = load_contract(CONTRACT_PATH)
    task = next(
        task
        for task in discover_sources(root, contract)
        if task.family == "SHFE.cu" and task.source_path.name.endswith("2101.parquet")
    )
    scan = read_source_task(task, date(2026, 7, 31))
    candidates, exclusions = enumerate_candidates(scan, contract)
    assert exclusions["blind_window_invalid_or_missing_row"] > 0
    assert exclusions["reveal_window_invalid_or_missing_row"] > 0
    assert all(not 70 <= candidate.anchor_index <= 129 for candidate in candidates)


def _candidate_for_overlap_test(*, family: str, source_alias: str, start: datetime) -> Candidate:
    rows = tuple(
        NativeRow(
            timestamp=(start + timedelta(days=index)).isoformat(),
            trading_date=(start + timedelta(days=index)).date(),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=100.0,
            open_interest=500.0,
            quality_findings=(),
        )
        for index in range(60)
    )
    exchange, product = family.split(".")
    task = SourceTask(
        family=family,
        exchange=exchange,
        product=product,
        role="test",
        source_alias=source_alias,
        source_path=Path("unused"),
    )
    return Candidate(
        task=task,
        source_sha256="sha256:" + "a" * 64,
        anchor_index=39,
        stratum="era_1",
        activity_score=1.0,
        blind_rows=rows[:40],
        reveal_rows=rows[40:],
    )


def test_calendar_overlap_is_blocked_across_different_source_aliases() -> None:
    first = _candidate_for_overlap_test(
        family="CZCE.CF",
        source_alias="sha256:" + "1" * 64,
        start=datetime(2022, 1, 1, tzinfo=UTC),
    )
    same_family_other_expiry = _candidate_for_overlap_test(
        family="CZCE.CF",
        source_alias="sha256:" + "2" * 64,
        start=datetime(2022, 1, 20, tzinfo=UTC),
    )
    other_family = _candidate_for_overlap_test(
        family="DCE.p",
        source_alias="sha256:" + "3" * 64,
        start=datetime(2022, 1, 20, tzinfo=UTC),
    )
    assert _overlaps(first, same_family_other_expiry)
    assert not _overlaps(first, other_family)


def test_anonymous_id_depends_only_on_normalized_blind_payload() -> None:
    original = _candidate_for_overlap_test(
        family="CZCE.CF",
        source_alias="sha256:" + "1" * 64,
        start=datetime(2022, 1, 1, tzinfo=UTC),
    )
    future_changed = replace(
        original,
        reveal_rows=tuple(
            replace(row, close=row.close + 7.0, high=row.high + 7.0) for row in original.reveal_rows
        ),
    )
    provenance_changed = replace(
        original,
        task=replace(
            original.task,
            family="DCE.p",
            exchange="DCE",
            product="p",
            source_alias="sha256:" + "f" * 64,
        ),
        stratum="era_4",
        sampling_role="ordinary_control",
        anchor_index=999,
    )
    original_id = assign_anonymous_blind_payload_ids([original])[0].episode_id
    assert assign_anonymous_blind_payload_ids([future_changed])[0].episode_id == original_id
    assert assign_anonymous_blind_payload_ids([provenance_changed])[0].episode_id == original_id


@pytest.mark.parametrize(
    "target",
    [
        REPO_ROOT
        / "doc/repro/pa-feitian-m6r-historical-bare-k-episode-pack-2026-07-31"
        / "blind_episode_pack_v1.json",
        REPO_ROOT
        / "doc/repro/pa-feitian-m6r-historical-bare-k-episode-pack-2026-07-31"
        / "episode_manifest_v1.json",
        CONTRACT_PATH,
    ],
)
def test_reveal_cli_rejects_committed_output_targets(tmp_path: Path, target: Path) -> None:
    before = target.read_bytes()
    annotations = tmp_path / "empty-annotations.json"
    annotations.write_text("{}", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "src/scripts/reveal_pa_feitian_m6r_historical_bare_k_episode_pack.py"),
            "--sealed-reveal",
            str(
                REPO_ROOT
                / "doc/repro/pa-feitian-m6r-historical-bare-k-episode-pack-2026-07-31"
                / "sealed_reveal_pack_v1.json"
            ),
            "--blind-annotations",
            str(annotations),
            "--output",
            str(target),
            "--acknowledge-first-pass-complete",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "outside the repository" in result.stderr
    assert target.read_bytes() == before
