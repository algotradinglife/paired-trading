from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.manifest import (  # noqa: E402
    PA_FEITIAN_RUN_MANIFEST_SCHEMA_VERSION,
    build_run_manifest,
    load_run_manifest,
    run_manifest_to_jsonable,
    sha256_file,
    validate_run_manifest,
    write_run_manifest,
)
from engine.pa_feitian.premium_outcome import (  # noqa: E402
    PA_FEITIAN_PREMIUM_OUTCOME_SCHEMA_VERSION,
)
from engine.pa_feitian.schema_validation import (  # noqa: E402
    JsonSchemaValidationError,
    validate_pa_feitian_decision_intent_schema,
    validate_pa_feitian_premium_outcome_schema,
    validate_pa_feitian_run_manifest_schema,
    validate_pa_feitian_snapshot_v1_schema,
)


SRC_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC_ROOT.parent
FIXTURE_DIR = SRC_ROOT / "tests" / "fixtures"
SCORECARD_FIXTURE = FIXTURE_DIR / "pa_feitian_scorecard_v1.json"
SNAPSHOT_V1_FIXTURE = FIXTURE_DIR / "pa_feitian_snapshot_v1.json"
DECISION_INTENT_FIXTURE = FIXTURE_DIR / "pa_feitian_decision_intent_v1.json"
PREMIUM_OUTCOME_FIXTURE = FIXTURE_DIR / "pa_feitian_premium_outcome_v1.json"
MANIFEST_FIXTURE = FIXTURE_DIR / "pa_feitian_run_manifest_v1.json"
MANIFEST_WITH_DECISION_INTENT_FIXTURE = (
    FIXTURE_DIR / "pa_feitian_run_manifest_with_decision_intent_v1.json"
)
MANIFEST_WITH_PREMIUM_OUTCOME_FIXTURE = (
    FIXTURE_DIR / "pa_feitian_run_manifest_with_premium_outcome_v1.json"
)
FRONTEND_COPY_FIXTURE = REPO_ROOT / "frontend" / "pa-feitian-dashboard" / "fixtures" / (
    "pa_feitian_snapshot_v1.json"
)


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def test_run_manifest_fixture_validates_against_model_and_schema():
    data = _load_json(MANIFEST_FIXTURE)

    validate_pa_feitian_run_manifest_schema(data)
    manifest = load_run_manifest(MANIFEST_FIXTURE)

    assert manifest.schema_version == PA_FEITIAN_RUN_MANIFEST_SCHEMA_VERSION
    assert manifest.source_commit == "cccccccccccccccccccccccccccccccccccccccc"
    assert manifest.scorecard_artifact.sha256 == sha256_file(SCORECARD_FIXTURE)
    assert manifest.snapshot_artifact.sha256 == sha256_file(SNAPSHOT_V1_FIXTURE)
    assert manifest.output_hashes["frontend_copy"] == sha256_file(FRONTEND_COPY_FIXTURE)
    assert manifest.frontend_copy_path == (
        "frontend/pa-feitian-dashboard/fixtures/pa_feitian_snapshot_v1.json"
    )
    assert manifest.data_access.status == "fixture_fallback"
    assert manifest.data_access.source == "src/tests/fixtures/pa_feitian_scorecard_v1.json"
    assert manifest.review_state.status == "pending"


def test_run_manifest_builder_and_writer_are_deterministic(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    expected = _load_json(MANIFEST_FIXTURE)

    manifest = build_run_manifest(
        scorecard_path=expected["scorecard_artifact"]["path"],
        snapshot_path=expected["snapshot_artifact"]["path"],
        source_commit=expected["source_commit"],
        cli_args=expected["cli_args"],
        run_config=expected["run_config"],
        data_access=expected["data_access"],
        generated_at_utc=datetime(2026, 7, 7, tzinfo=UTC),
        frontend_copy_path=expected["frontend_copy_path"],
    )

    assert run_manifest_to_jsonable(manifest) == expected

    out = tmp_path / "pa_feitian_run_manifest_v1.json"
    write_run_manifest(manifest, out)

    assert _load_json(out) == expected
    assert load_run_manifest(out) == manifest


def test_run_manifest_rejects_hash_drift():
    data = _load_json(MANIFEST_FIXTURE)
    data["input_hashes"]["scorecard_artifact"] = data["snapshot_artifact"]["sha256"]

    with pytest.raises(ValidationError, match="scorecard_artifact.sha256"):
        validate_run_manifest(data)


def test_run_manifest_can_reference_decision_intent_sidecar():
    data = _load_json(MANIFEST_FIXTURE)
    sidecar_hash = sha256_file(DECISION_INTENT_FIXTURE)
    data["decision_intent_artifact"] = {
        "kind": "decision_intent",
        "path": "src/tests/fixtures/pa_feitian_decision_intent_v1.json",
        "sha256": sidecar_hash,
        "schema_version": "pa_feitian_decision_intent_v1",
        "content_type": "application/json",
    }
    data["output_hashes"]["decision_intent_artifact"] = sidecar_hash

    validate_pa_feitian_decision_intent_schema(_load_json(DECISION_INTENT_FIXTURE))
    validate_pa_feitian_run_manifest_schema(data)
    manifest = validate_run_manifest(data)

    assert manifest.decision_intent_artifact is not None
    assert manifest.decision_intent_artifact.kind == "decision_intent"
    assert manifest.output_hashes["decision_intent_artifact"] == sidecar_hash


def test_run_manifest_with_decision_intent_fixture_validates():
    data = _load_json(MANIFEST_WITH_DECISION_INTENT_FIXTURE)
    sidecar = _load_json(DECISION_INTENT_FIXTURE)

    validate_pa_feitian_run_manifest_schema(data)
    manifest = validate_run_manifest(data)

    assert manifest.decision_intent_artifact is not None
    assert manifest.decision_intent_artifact.sha256 == sha256_file(DECISION_INTENT_FIXTURE)
    assert sidecar["provenance"]["source_manifest_path"] == (
        "src/tests/fixtures/pa_feitian_run_manifest_with_decision_intent_v1.json"
    )
    assert sidecar["provenance"]["snapshot_artifact_sha256"] == manifest.snapshot_artifact.sha256


def test_run_manifest_builder_includes_decision_intent_when_requested(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    expected = _load_json(MANIFEST_FIXTURE)

    manifest = build_run_manifest(
        scorecard_path=expected["scorecard_artifact"]["path"],
        snapshot_path=expected["snapshot_artifact"]["path"],
        source_commit=expected["source_commit"],
        cli_args=expected["cli_args"],
        run_config=expected["run_config"],
        data_access=expected["data_access"],
        generated_at_utc=datetime(2026, 7, 7, tzinfo=UTC),
        frontend_copy_path=expected["frontend_copy_path"],
        decision_intent_path="src/tests/fixtures/pa_feitian_decision_intent_v1.json",
    )
    payload = run_manifest_to_jsonable(manifest)
    sidecar_hash = sha256_file(DECISION_INTENT_FIXTURE)

    assert payload["decision_intent_artifact"] == {
        "kind": "decision_intent",
        "path": "src/tests/fixtures/pa_feitian_decision_intent_v1.json",
        "sha256": sidecar_hash,
        "schema_version": "pa_feitian_decision_intent_v1",
        "content_type": "application/json",
    }
    assert payload["output_hashes"]["decision_intent_artifact"] == sidecar_hash


def test_run_manifest_can_reference_premium_outcome_sidecar():
    data = _load_json(MANIFEST_WITH_DECISION_INTENT_FIXTURE)
    outcome_hash = sha256_file(PREMIUM_OUTCOME_FIXTURE)
    data["premium_outcome_artifact"] = {
        "kind": "premium_outcome",
        "path": "src/tests/fixtures/pa_feitian_premium_outcome_v1.json",
        "sha256": outcome_hash,
        "schema_version": PA_FEITIAN_PREMIUM_OUTCOME_SCHEMA_VERSION,
        "content_type": "application/json",
    }
    data["output_hashes"]["premium_outcome_artifact"] = outcome_hash

    validate_pa_feitian_premium_outcome_schema(_load_json(PREMIUM_OUTCOME_FIXTURE))
    validate_pa_feitian_run_manifest_schema(data)
    manifest = validate_run_manifest(data)

    assert manifest.premium_outcome_artifact is not None
    assert manifest.premium_outcome_artifact.kind == "premium_outcome"
    assert manifest.output_hashes["premium_outcome_artifact"] == outcome_hash


def test_run_manifest_with_premium_outcome_fixture_validates():
    data = _load_json(MANIFEST_WITH_PREMIUM_OUTCOME_FIXTURE)

    validate_pa_feitian_run_manifest_schema(data)
    manifest = validate_run_manifest(data)

    assert manifest.decision_intent_artifact is not None
    assert manifest.premium_outcome_artifact is not None
    assert manifest.premium_outcome_artifact.sha256 == sha256_file(PREMIUM_OUTCOME_FIXTURE)
    assert manifest.output_hashes["premium_outcome_artifact"] == sha256_file(
        PREMIUM_OUTCOME_FIXTURE
    )


def test_run_manifest_builder_includes_premium_outcome_when_requested(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    expected = _load_json(MANIFEST_FIXTURE)

    manifest = build_run_manifest(
        scorecard_path=expected["scorecard_artifact"]["path"],
        snapshot_path=expected["snapshot_artifact"]["path"],
        source_commit=expected["source_commit"],
        cli_args=expected["cli_args"],
        run_config=expected["run_config"],
        data_access=expected["data_access"],
        generated_at_utc=datetime(2026, 7, 7, tzinfo=UTC),
        frontend_copy_path=expected["frontend_copy_path"],
        decision_intent_path="src/tests/fixtures/pa_feitian_decision_intent_v1.json",
        premium_outcome_path="src/tests/fixtures/pa_feitian_premium_outcome_v1.json",
    )
    payload = run_manifest_to_jsonable(manifest)
    outcome_hash = sha256_file(PREMIUM_OUTCOME_FIXTURE)

    assert payload["premium_outcome_artifact"] == {
        "kind": "premium_outcome",
        "path": "src/tests/fixtures/pa_feitian_premium_outcome_v1.json",
        "sha256": outcome_hash,
        "schema_version": PA_FEITIAN_PREMIUM_OUTCOME_SCHEMA_VERSION,
        "content_type": "application/json",
    }
    assert payload["output_hashes"]["premium_outcome_artifact"] == outcome_hash


def test_run_manifest_rejects_premium_outcome_hash_drift():
    data = _load_json(MANIFEST_WITH_DECISION_INTENT_FIXTURE)
    outcome_hash = sha256_file(PREMIUM_OUTCOME_FIXTURE)
    data["premium_outcome_artifact"] = {
        "kind": "premium_outcome",
        "path": "src/tests/fixtures/pa_feitian_premium_outcome_v1.json",
        "sha256": outcome_hash,
        "schema_version": PA_FEITIAN_PREMIUM_OUTCOME_SCHEMA_VERSION,
        "content_type": "application/json",
    }
    data["output_hashes"]["premium_outcome_artifact"] = data["snapshot_artifact"]["sha256"]

    with pytest.raises(ValidationError, match="premium_outcome_artifact.sha256"):
        validate_run_manifest(data)


def test_run_manifest_rejects_decision_intent_hash_drift():
    data = _load_json(MANIFEST_FIXTURE)
    sidecar_hash = sha256_file(DECISION_INTENT_FIXTURE)
    data["decision_intent_artifact"] = {
        "kind": "decision_intent",
        "path": "src/tests/fixtures/pa_feitian_decision_intent_v1.json",
        "sha256": sidecar_hash,
        "schema_version": "pa_feitian_decision_intent_v1",
        "content_type": "application/json",
    }
    data["output_hashes"]["decision_intent_artifact"] = data["snapshot_artifact"]["sha256"]

    with pytest.raises(ValidationError, match="decision_intent_artifact.sha256"):
        validate_run_manifest(data)


def test_run_manifest_schema_requires_data_access():
    data = _load_json(MANIFEST_FIXTURE)
    data.pop("data_access")

    with pytest.raises(JsonSchemaValidationError, match="data_access"):
        validate_pa_feitian_run_manifest_schema(data)


def test_snapshot_v1_json_schema_validation_resolves_decision_trace_ref():
    data = _load_json(SNAPSHOT_V1_FIXTURE)
    validate_pa_feitian_snapshot_v1_schema(data)

    broken = deepcopy(data)
    broken["signals"][0]["decision_trace_v1"]["nodes"][0]["kind"] = "unknown_node"

    with pytest.raises(JsonSchemaValidationError, match=r"decision_trace_v1\.nodes\[0\]\.kind"):
        validate_pa_feitian_snapshot_v1_schema(broken)
