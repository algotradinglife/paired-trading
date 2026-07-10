from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.evaluation import (  # noqa: E402
    PA_FEITIAN_EVALUATION_AGGREGATE_RESULT_SCHEMA_VERSION,
    PA_FEITIAN_EVALUATION_DATASET_SCHEMA_VERSION,
    PA_FEITIAN_EVALUATION_FAILURE_MODE_REPORT_SCHEMA_VERSION,
    PA_FEITIAN_EVALUATION_SCREENING_REPORT_SCHEMA_VERSION,
    load_evaluation_aggregate_result,
    load_evaluation_dataset,
    load_evaluation_failure_mode_report,
    load_evaluation_screening_report,
    validate_evaluation_aggregate_result,
    validate_evaluation_dataset,
    validate_evaluation_failure_mode_report,
    validate_evaluation_screening_report,
    write_evaluation_dataset,
)
from engine.pa_feitian.manifest import (  # noqa: E402
    build_run_manifest,
    run_manifest_to_jsonable,
    sha256_file,
    validate_run_manifest,
)
from engine.pa_feitian.schema_validation import (  # noqa: E402
    JsonSchemaValidationError,
    validate_pa_feitian_evaluation_aggregate_result_schema,
    validate_pa_feitian_evaluation_dataset_schema,
    validate_pa_feitian_evaluation_failure_mode_report_schema,
    validate_pa_feitian_evaluation_screening_report_schema,
    validate_pa_feitian_run_manifest_schema,
)


SRC_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC_ROOT.parent
FIXTURE_DIR = SRC_ROOT / "tests" / "fixtures"
DATASET_PATH = FIXTURE_DIR / "pa_feitian_evaluation_dataset_v1.json"
AGGREGATE_PATH = FIXTURE_DIR / "pa_feitian_evaluation_aggregate_result_v1.json"
FAILURE_PATH = FIXTURE_DIR / "pa_feitian_evaluation_failure_mode_report_v1.json"
SCREENING_PATH = FIXTURE_DIR / "pa_feitian_evaluation_screening_report_v1.json"


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def test_m6_fixtures_validate_against_models_and_local_schemas(tmp_path: Path):
    dataset_data = _load_json(DATASET_PATH)
    aggregate_data = _load_json(AGGREGATE_PATH)
    failure_data = _load_json(FAILURE_PATH)
    screening_data = _load_json(SCREENING_PATH)

    validate_pa_feitian_evaluation_dataset_schema(dataset_data)
    validate_pa_feitian_evaluation_aggregate_result_schema(aggregate_data)
    validate_pa_feitian_evaluation_failure_mode_report_schema(failure_data)
    validate_pa_feitian_evaluation_screening_report_schema(screening_data)

    dataset = load_evaluation_dataset(DATASET_PATH)
    aggregate = load_evaluation_aggregate_result(AGGREGATE_PATH)
    failure = load_evaluation_failure_mode_report(FAILURE_PATH)
    screening = load_evaluation_screening_report(SCREENING_PATH)

    assert dataset.schema_version == PA_FEITIAN_EVALUATION_DATASET_SCHEMA_VERSION
    assert dataset.rows[0].iv_gate_status == "unknown"
    assert aggregate.schema_version == PA_FEITIAN_EVALUATION_AGGREGATE_RESULT_SCHEMA_VERSION
    assert aggregate.groups[0].premium_r is not None
    assert failure.schema_version == PA_FEITIAN_EVALUATION_FAILURE_MODE_REPORT_SCHEMA_VERSION
    assert failure.failure_modes[0].input_refs == ["scorecard_record:2"]
    assert screening.schema_version == PA_FEITIAN_EVALUATION_SCREENING_REPORT_SCHEMA_VERSION
    assert screening.candidates[0].classification == "inconclusive"

    out = tmp_path / "dataset.json"
    write_evaluation_dataset(dataset, out)
    assert _load_json(out) == dataset_data


def test_m6_models_keep_missing_evidence_out_of_observed_metrics():
    dataset = _load_json(DATASET_PATH)
    dataset["rows"][0]["evaluation_status"] = "ambiguous"

    with pytest.raises(ValidationError, match="non-observed rows"):
        validate_evaluation_dataset(dataset)

    dataset = _load_json(DATASET_PATH)
    dataset["provenance"]["input_hashes"]["premium_outcome_artifact"] = (
        "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    )

    with pytest.raises(ValidationError, match="premium_outcome_artifact_sha256"):
        validate_evaluation_dataset(dataset)


def test_m6_reports_validate_link_hashes_and_status_counts():
    aggregate = _load_json(AGGREGATE_PATH)
    aggregate["groups"][0]["status_counts"]["observed"] = 0

    with pytest.raises(ValidationError, match="sum to sample_count"):
        validate_evaluation_aggregate_result(aggregate)

    failure = _load_json(FAILURE_PATH)
    failure["failure_modes"][0]["outcome_ids"] = []
    failure["failure_modes"][0]["source_signal_ids"] = []

    with pytest.raises(ValidationError, match="require outcome_ids"):
        validate_evaluation_failure_mode_report(failure)

    screening = _load_json(SCREENING_PATH)
    screening["provenance"]["input_hashes"]["aggregate_result"] = (
        "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    )

    with pytest.raises(ValidationError, match="aggregate_result.sha256"):
        validate_evaluation_screening_report(screening)


def test_m6_local_schema_rejects_wrong_artifact_and_unknown_row_field():
    aggregate = _load_json(AGGREGATE_PATH)
    aggregate["evaluation_dataset"]["kind"] = "premium_outcome"

    with pytest.raises(JsonSchemaValidationError, match=r"evaluation_dataset\.kind"):
        validate_pa_feitian_evaluation_aggregate_result_schema(aggregate)

    dataset = _load_json(DATASET_PATH)
    dataset["rows"][0]["posterior_label"] = "not allowed"

    with pytest.raises(JsonSchemaValidationError, match="posterior_label"):
        validate_pa_feitian_evaluation_dataset_schema(dataset)


def test_m6_typed_report_refs_reject_wrong_schema_versions_at_runtime_and_schema():
    aggregate = _load_json(AGGREGATE_PATH)
    aggregate["evaluation_dataset"]["schema_version"] = "pa_feitian_evaluation_dataset_v2"

    with pytest.raises(ValidationError, match=r"evaluation_dataset\.schema_version"):
        validate_evaluation_aggregate_result(aggregate)
    with pytest.raises(JsonSchemaValidationError, match=r"evaluation_dataset\.schema_version"):
        validate_pa_feitian_evaluation_aggregate_result_schema(aggregate)

    failure = _load_json(FAILURE_PATH)
    failure["evaluation_dataset"]["schema_version"] = "pa_feitian_evaluation_dataset_v2"

    with pytest.raises(ValidationError, match=r"evaluation_dataset\.schema_version"):
        validate_evaluation_failure_mode_report(failure)
    with pytest.raises(JsonSchemaValidationError, match=r"evaluation_dataset\.schema_version"):
        validate_pa_feitian_evaluation_failure_mode_report_schema(failure)

    screening = _load_json(SCREENING_PATH)
    screening["evaluation_dataset"]["schema_version"] = "pa_feitian_evaluation_dataset_v2"

    with pytest.raises(ValidationError, match=r"evaluation_dataset\.schema_version"):
        validate_evaluation_screening_report(screening)
    with pytest.raises(JsonSchemaValidationError, match=r"evaluation_dataset\.schema_version"):
        validate_pa_feitian_evaluation_screening_report_schema(screening)

    screening = _load_json(SCREENING_PATH)
    screening["aggregate_result"]["schema_version"] = (
        "pa_feitian_evaluation_aggregate_result_v2"
    )

    with pytest.raises(ValidationError, match=r"aggregate_result\.schema_version"):
        validate_evaluation_screening_report(screening)
    with pytest.raises(JsonSchemaValidationError, match=r"aggregate_result\.schema_version"):
        validate_pa_feitian_evaluation_screening_report_schema(screening)


def test_manifest_can_hash_bind_all_optional_m6_artifacts(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    manifest_fixture = _load_json(FIXTURE_DIR / "pa_feitian_run_manifest_v1.json")
    manifest = build_run_manifest(
        scorecard_path=manifest_fixture["scorecard_artifact"]["path"],
        snapshot_path=manifest_fixture["snapshot_artifact"]["path"],
        source_commit=manifest_fixture["source_commit"],
        cli_args=manifest_fixture["cli_args"],
        run_config=manifest_fixture["run_config"],
        data_access=manifest_fixture["data_access"],
        evaluation_dataset_path="src/tests/fixtures/pa_feitian_evaluation_dataset_v1.json",
        evaluation_aggregate_result_path=(
            "src/tests/fixtures/pa_feitian_evaluation_aggregate_result_v1.json"
        ),
        evaluation_failure_mode_report_path=(
            "src/tests/fixtures/pa_feitian_evaluation_failure_mode_report_v1.json"
        ),
        evaluation_screening_report_path=(
            "src/tests/fixtures/pa_feitian_evaluation_screening_report_v1.json"
        ),
    )
    payload = run_manifest_to_jsonable(manifest)

    validate_pa_feitian_run_manifest_schema(payload)
    validated = validate_run_manifest(payload)
    assert validated.evaluation_dataset_artifact is not None
    assert validated.evaluation_dataset_artifact.sha256 == sha256_file(DATASET_PATH)
    assert validated.evaluation_aggregate_result_artifact is not None
    assert validated.evaluation_failure_mode_report_artifact is not None
    assert validated.evaluation_screening_report_artifact is not None

    for artifact_field in (
        "evaluation_dataset_artifact",
        "evaluation_aggregate_result_artifact",
        "evaluation_failure_mode_report_artifact",
        "evaluation_screening_report_artifact",
    ):
        broken = deepcopy(payload)
        broken[artifact_field]["schema_version"] = "pa_feitian_evaluation_v2"

        with pytest.raises(ValidationError, match=rf"{artifact_field}\.schema_version"):
            validate_run_manifest(broken)
        with pytest.raises(JsonSchemaValidationError, match=rf"{artifact_field}\.schema_version"):
            validate_pa_feitian_run_manifest_schema(broken)

    broken = deepcopy(payload)
    broken["output_hashes"]["evaluation_dataset_artifact"] = broken["snapshot_artifact"][
        "sha256"
    ]
    with pytest.raises(ValidationError, match="evaluation_dataset_artifact.sha256"):
        validate_run_manifest(broken)


def test_manifest_schema_accepts_m5_model_dump_without_m6_artifacts():
    """Optional M6 fields must not invalidate an existing M5 manifest dump."""
    manifest = validate_run_manifest(
        _load_json(FIXTURE_DIR / "pa_feitian_run_manifest_with_premium_outcome_v1.json")
    )

    validate_pa_feitian_run_manifest_schema(manifest.model_dump(mode="json", exclude_none=False))
