from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from engine.pa_feitian.baseline_evaluator import BaselineEvaluationConfig, build_aggregate_result
from engine.pa_feitian.evaluation import (
    evaluation_screening_report_to_jsonable,
    load_evaluation_aggregate_result,
    load_evaluation_dataset,
    write_evaluation_aggregate_result,
    write_evaluation_dataset,
)
from engine.pa_feitian.policy_comparison import (
    CandidateArtifacts,
    PolicyComparisonConfig,
    build_policy_comparison_reports,
    canonical_config_sha256,
)
from engine.pa_feitian.schema_validation import (
    validate_pa_feitian_evaluation_screening_report_schema,
)


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
DATASET = FIXTURE_DIR / "pa_feitian_evaluation_dataset_v1.json"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare_pa_feitian_m6_policies.py"


def _write_artifacts(tmp_path: Path, name: str, *, candidate: bool = False) -> CandidateArtifacts:
    dataset = load_evaluation_dataset(DATASET)
    input_hashes = {
        **dataset.provenance.input_hashes,
        "decision_intent_artifact": "sha256:" + "1" * 64,
    }
    dataset = dataset.model_copy(
        update={"provenance": dataset.provenance.model_copy(update={"input_hashes": input_hashes})}
    )
    policy_hash = "sha256:" + ("e" if candidate else "d") * 64
    rows = [
        row.model_copy(
            update={
                "policy_id": "candidate_policy" if candidate else "baseline_policy",
                "policy_version": "v1",
                "policy_sha256": policy_hash,
                "evaluation_status": "observed",
                "exit_reason": "time_exit",
                "premium_r": float(index + (1 if candidate else 0)),
                "premium_mfe": 1.0,
                "premium_mae": -1.0,
            }
        )
        for index, row in enumerate(dataset.rows, start=1)
    ]
    # The contract fixture has one row. Duplicate chronological event groups so
    # the comparison exercises two non-overlapping OOS folds deterministically.
    rows = [
        row.model_copy(update={"row_id": f"{name}_{index}", "event_id": f"event:shared:{index}", "outcome_id": f"outcome:{name}:{index}", "decision_ts_utc": datetime(2026, 6, 30, tzinfo=UTC) + timedelta(days=index - 1)})
        for index, row in enumerate(rows * 4, start=1)
    ]
    dataset = dataset.model_copy(
        update={
            "rows": rows,
            "time_boundary": dataset.time_boundary.model_copy(
                update={
                    "decision_start_utc": datetime(2026, 6, 30, tzinfo=UTC),
                    "decision_end_utc": datetime(2026, 7, 3, tzinfo=UTC),
                    "split_method": "walk_forward",
                    "folds_declared": 2,
                }
            ),
        }
    )
    dataset_path = tmp_path / f"{name}_dataset.json"
    aggregate_path = tmp_path / f"{name}_aggregate.json"
    write_evaluation_dataset(dataset, dataset_path)
    aggregate = build_aggregate_result(
        dataset=dataset,
        dataset_path=dataset_path,
        config=BaselineEvaluationConfig(folds=2, minimum_effective_samples=1),
        generated_at_utc=datetime(2026, 7, 4, tzinfo=UTC),
    )
    write_evaluation_aggregate_result(aggregate, aggregate_path)
    return CandidateArtifacts(
        dataset_path=dataset_path,
        aggregate_path=aggregate_path,
        dataset=load_evaluation_dataset(dataset_path),
        aggregate=load_evaluation_aggregate_result(aggregate_path),
    )


def _config(baseline: CandidateArtifacts) -> PolicyComparisonConfig:
    return PolicyComparisonConfig.model_validate(
        {
            "schema_version": "pa_feitian_m6_policy_comparison_config_v1",
            "registration_id": "m6-c-fixture",
            "registered_at_utc": "2026-06-01T00:00:00Z",
            "baseline": {
                "policy_id": baseline.dataset.rows[0].policy_id,
                "policy_version": baseline.dataset.rows[0].policy_version,
                "policy_sha256s": sorted({row.policy_sha256 for row in baseline.dataset.rows}),
            },
            "candidates": [
                {
                    "candidate_id": "candidate_exit",
                    "policy_id": "candidate_policy",
                    "policy_version": "v1",
                    "policy_sha256s": ["sha256:" + "e" * 64],
                    "dimensions": ["exit_policy"],
                    "notes": ["fixture registration"],
                }
            ],
            "minimum_effective_events": 3,
            "minimum_comparable_oos_windows": 2,
            "alpha": 0.05,
            "bootstrap_replicates": 25,
            "random_seed": 7,
            "notes": ["pre-registered fixture"],
        }
    )


def _rewrite_artifacts(artifacts: CandidateArtifacts, dataset) -> CandidateArtifacts:
    write_evaluation_dataset(dataset, artifacts.dataset_path)
    aggregate = build_aggregate_result(
        dataset=dataset,
        dataset_path=artifacts.dataset_path,
        config=BaselineEvaluationConfig(folds=2, minimum_effective_samples=1),
        generated_at_utc=datetime(2026, 7, 4, tzinfo=UTC),
    )
    write_evaluation_aggregate_result(aggregate, artifacts.aggregate_path)
    return CandidateArtifacts(
        dataset_path=artifacts.dataset_path,
        aggregate_path=artifacts.aggregate_path,
        dataset=load_evaluation_dataset(artifacts.dataset_path),
        aggregate=load_evaluation_aggregate_result(artifacts.aggregate_path),
    )


def test_controlled_comparison_is_event_paired_oos_and_bonferroni_bound(tmp_path: Path):
    baseline = _write_artifacts(tmp_path, "baseline")
    candidate = _write_artifacts(tmp_path, "candidate", candidate=True)
    config = _config(baseline)
    config_path = tmp_path / "comparison_config.json"
    config_path.write_text(json.dumps(config.model_dump(mode="json")), encoding="utf-8")

    screening, failures = build_policy_comparison_reports(
        baseline=baseline,
        candidates={"candidate_exit": candidate},
        config=config,
        config_path=config_path,
        generated_at_utc=datetime(2026, 7, 4, tzinfo=UTC),
        cli_args=["test"],
    )

    result = screening.candidates[0]
    assert result.classification == "promising", result.classification_basis
    assert result.comparison is not None
    assert result.comparison.paired_effective_event_count == 4
    assert result.comparison.mean_premium_r_difference == pytest.approx(1.0)
    assert len(result.comparison.comparable_oos_windows) == 2
    assert screening.multiple_comparison is not None
    assert screening.multiple_comparison.configuration_sha256 == canonical_config_sha256(config)
    assert screening.multiple_comparison.adjusted_confidence_level == pytest.approx(0.95)
    assert "candidate_exit" in failures
    validate_pa_feitian_evaluation_screening_report_schema(
        evaluation_screening_report_to_jsonable(screening)
    )


def test_missing_registered_candidate_is_blocked_not_fabricated(tmp_path: Path):
    baseline = _write_artifacts(tmp_path, "baseline")
    config = _config(baseline)
    config_path = tmp_path / "comparison_config.json"
    config_path.write_text(json.dumps(config.model_dump(mode="json")), encoding="utf-8")

    screening, failures = build_policy_comparison_reports(
        baseline=baseline,
        candidates={},
        config=config,
        config_path=config_path,
        generated_at_utc=datetime(2026, 7, 4, tzinfo=UTC),
        cli_args=["test"],
    )

    result = screening.candidates[0]
    assert result.classification == "blocked"
    assert result.comparison is not None
    assert result.comparison.candidate_dataset_sha256 is None
    assert "no explicit comparable artifact" in result.classification_basis[0]
    assert failures["candidate_exit"].failure_modes[0].severity == "blocking"


def test_candidate_cannot_drop_an_adverse_observed_event_before_pairing(tmp_path: Path):
    baseline = _write_artifacts(tmp_path, "baseline")
    candidate = _write_artifacts(tmp_path, "candidate", candidate=True)
    dropped = candidate.dataset.rows[0].model_copy(
        update={
            "evaluation_status": "data_blocked",
            "exit_reason": "data_gap",
            "premium_r": None,
            "premium_mfe": None,
            "premium_mae": None,
        }
    )
    candidate = _rewrite_artifacts(
        candidate, candidate.dataset.model_copy(update={"rows": [dropped, *candidate.dataset.rows[1:]]})
    )
    config = _config(baseline)
    config_path = tmp_path / "comparison_config.json"
    config_path.write_text(json.dumps(config.model_dump(mode="json")), encoding="utf-8")

    screening, _ = build_policy_comparison_reports(
        baseline=baseline,
        candidates={"candidate_exit": candidate},
        config=config,
        config_path=config_path,
        generated_at_utc=datetime(2026, 7, 4, tzinfo=UTC),
        cli_args=["test"],
    )

    result = screening.candidates[0]
    assert result.classification == "blocked"
    assert result.comparison is not None
    assert result.comparison.paired_effective_event_count == 0
    assert "observed event-id set differs" in result.classification_basis[0]


def test_distinct_m5_manifest_provenance_with_same_decision_inputs_is_comparable(tmp_path: Path):
    baseline = _write_artifacts(tmp_path, "baseline")
    candidate = _write_artifacts(tmp_path, "candidate", candidate=True)
    alternate_manifest_hash = "sha256:" + "9" * 64
    candidate_provenance = candidate.dataset.provenance.model_copy(
        update={
            "source_manifest_path": "candidate_m5_manifest.json",
            "source_manifest_sha256": alternate_manifest_hash,
            "input_hashes": {
                **candidate.dataset.provenance.input_hashes,
                "source_manifest": alternate_manifest_hash,
            },
        }
    )
    candidate = _rewrite_artifacts(
        candidate, candidate.dataset.model_copy(update={"provenance": candidate_provenance})
    )
    config = _config(baseline)
    config_path = tmp_path / "comparison_config.json"
    config_path.write_text(json.dumps(config.model_dump(mode="json")), encoding="utf-8")

    screening, _ = build_policy_comparison_reports(
        baseline=baseline,
        candidates={"candidate_exit": candidate},
        config=config,
        config_path=config_path,
        generated_at_utc=datetime(2026, 7, 4, tzinfo=UTC),
        cli_args=["test"],
    )

    assert screening.candidates[0].classification == "promising"


def test_mixed_selected_contract_availability_has_a_stable_input_projection(tmp_path: Path):
    baseline = _write_artifacts(tmp_path, "baseline")
    candidate = _write_artifacts(tmp_path, "candidate", candidate=True)
    baseline_missing = baseline.dataset.rows[0].model_copy(
        update={"row_id": "baseline_missing_contract", "source_contract_id": None}
    )
    baseline_selected = baseline.dataset.rows[0].model_copy(
        update={"row_id": "baseline_selected_contract", "source_contract_id": "contract:available"}
    )
    candidate_missing = candidate.dataset.rows[0].model_copy(
        update={"row_id": "candidate_missing_contract", "source_contract_id": None}
    )
    candidate_selected = candidate.dataset.rows[0].model_copy(
        update={"row_id": "candidate_selected_contract", "source_contract_id": "contract:available"}
    )
    baseline = _rewrite_artifacts(
        baseline,
        baseline.dataset.model_copy(
            update={"rows": [baseline_missing, baseline_selected, *baseline.dataset.rows[1:]]}
        ),
    )
    candidate = _rewrite_artifacts(
        candidate,
        candidate.dataset.model_copy(
            update={"rows": [candidate_missing, candidate_selected, *candidate.dataset.rows[1:]]}
        ),
    )
    config = _config(baseline)
    config_path = tmp_path / "comparison_config.json"
    config_path.write_text(json.dumps(config.model_dump(mode="json")), encoding="utf-8")

    screening, _ = build_policy_comparison_reports(
        baseline=baseline,
        candidates={"candidate_exit": candidate},
        config=config,
        config_path=config_path,
        generated_at_utc=datetime(2026, 7, 4, tzinfo=UTC),
        cli_args=["test"],
    )

    assert screening.candidates[0].classification == "promising"


def test_registered_policy_digest_sets_match_exactly_for_multi_contract_artifacts(tmp_path: Path):
    baseline = _write_artifacts(tmp_path, "baseline")
    candidate = _write_artifacts(tmp_path, "candidate", candidate=True)
    baseline_rows = [
        row.model_copy(update={"policy_sha256": "sha256:" + ("c" if index % 2 else "d") * 64})
        for index, row in enumerate(baseline.dataset.rows)
    ]
    candidate_rows = [
        row.model_copy(update={"policy_sha256": "sha256:" + ("e" if index % 2 else "f") * 64})
        for index, row in enumerate(candidate.dataset.rows)
    ]
    baseline = _rewrite_artifacts(
        baseline, baseline.dataset.model_copy(update={"rows": baseline_rows})
    )
    candidate = _rewrite_artifacts(
        candidate, candidate.dataset.model_copy(update={"rows": candidate_rows})
    )
    config = _config(baseline)
    config = config.model_copy(
        update={
            "candidates": [
                config.candidates[0].model_copy(update={"policy_sha256s": ["sha256:" + "e" * 64, "sha256:" + "f" * 64]})
            ]
        }
    )
    config_path = tmp_path / "comparison_config.json"
    config_path.write_text(json.dumps(config.model_dump(mode="json")), encoding="utf-8")

    screening, _ = build_policy_comparison_reports(
        baseline=baseline,
        candidates={"candidate_exit": candidate},
        config=config,
        config_path=config_path,
        generated_at_utc=datetime(2026, 7, 4, tzinfo=UTC),
        cli_args=["test"],
    )

    assert screening.candidates[0].classification == "promising"
    wrong_config = config.model_copy(
        update={
            "candidates": [
                config.candidates[0].model_copy(
                    update={"policy_sha256s": ["sha256:" + "e" * 64]}
                )
            ]
        }
    )
    blocked, _ = build_policy_comparison_reports(
        baseline=baseline,
        candidates={"candidate_exit": candidate},
        config=wrong_config,
        config_path=config_path,
        generated_at_utc=datetime(2026, 7, 4, tzinfo=UTC),
        cli_args=["test"],
    )
    assert blocked.candidates[0].classification == "blocked"
    assert "policy identity" in blocked.candidates[0].classification_basis[0]


def test_cli_writes_hash_bound_typed_reports_without_pipeline_inputs(tmp_path: Path):
    baseline = _write_artifacts(tmp_path, "baseline")
    candidate = _write_artifacts(tmp_path, "candidate", candidate=True)
    config = _config(baseline)
    config_path = tmp_path / "comparison_config.json"
    config_path.write_text(json.dumps(config.model_dump(mode="json")), encoding="utf-8")
    screening = tmp_path / "screening.json"
    failures = tmp_path / "failures"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--baseline-dataset",
            str(baseline.dataset_path),
            "--baseline-aggregate",
            str(baseline.aggregate_path),
            "--comparison-config",
            str(config_path),
            "--candidate-input",
            "candidate_exit",
            str(candidate.dataset_path),
            str(candidate.aggregate_path),
            "--screening-out",
            str(screening),
            "--failure-report-dir",
            str(failures),
            "--generated-at-utc",
            "2026-07-04T00:00:00Z",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["screening_sha256"].startswith("sha256:")
    assert json.loads(screening.read_text(encoding="utf-8"))["candidates"][0]["classification"] == "promising"
    assert (failures / "candidate_exit_failure_mode_report.json").is_file()
