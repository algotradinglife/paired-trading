from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from engine.pa_feitian.baseline_evaluator import (
    BaselineEvaluationConfig,
    build_aggregate_result,
    build_evaluation_dataset,
    build_walk_forward_folds,
    verify_artifact_links,
    verify_no_lookahead,
)
from engine.pa_feitian.contract import load_decision_intent
from engine.pa_feitian.evaluation import write_evaluation_dataset
from engine.pa_feitian.manifest import load_run_manifest
from engine.pa_feitian.premium_outcome import load_premium_outcome


SRC_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC_ROOT.parent
FIXTURE_DIR = SRC_ROOT / "tests" / "fixtures"
SCRIPT = SRC_ROOT / "scripts" / "evaluate_pa_feitian_m6_baseline.py"
MANIFEST = FIXTURE_DIR / "pa_feitian_run_manifest_with_premium_outcome_v1.json"
PREMIUM = FIXTURE_DIR / "pa_feitian_premium_outcome_v1.json"
INTENT = FIXTURE_DIR / "pa_feitian_decision_intent_v1.json"


def _inputs():
    return load_run_manifest(MANIFEST), load_premium_outcome(PREMIUM), load_decision_intent(INTENT)


def _dataset(config: BaselineEvaluationConfig | None = None):
    manifest, premium, intent = _inputs()
    return build_evaluation_dataset(
        manifest=manifest,
        manifest_path=MANIFEST,
        premium_outcome=premium,
        premium_outcome_path=PREMIUM,
        decision_intent=intent,
        decision_intent_path=INTENT,
        config=config or BaselineEvaluationConfig(folds=2),
        generated_at_utc=premium.generated_at_utc,
        cli_args=["test"],
    )


def test_dataset_preserves_m5_statuses_and_unknown_dimensions():
    dataset = _dataset()

    assert [row.evaluation_status for row in dataset.rows] == [
        "data_blocked",
        "ambiguous",
        "observed",
        "not_evaluable",
    ]
    assert {row.iv_gate_status for row in dataset.rows} == {"unknown"}
    assert all(row.decision_trace_node_ids == [] for row in dataset.rows)
    assert dataset.time_boundary.split_method == "walk_forward"


def test_no_lookahead_verifier_rejects_future_decision_input():
    _, premium, intent = _inputs()
    broken = intent.model_copy(deep=True)
    broken.intents[0].no_lookahead_inputs[0].asof_ts_utc = (
        broken.intents[0].decision_ts_utc + timedelta(seconds=1)
    )

    with pytest.raises(ValueError, match="future decision-intent input"):
        verify_no_lookahead(premium, broken)


def test_artifact_link_verifier_rejects_manifest_hash_drift():
    manifest, premium, intent = _inputs()
    broken = manifest.model_copy(deep=True)
    assert broken.premium_outcome_artifact is not None
    broken.premium_outcome_artifact.sha256 = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="manifest premium outcome hash"):
        verify_artifact_links(
            manifest=broken,
            manifest_path=MANIFEST,
            premium_outcome=premium,
            premium_outcome_path=PREMIUM,
            decision_intent=intent,
            decision_intent_path=INTENT,
        )


def test_walk_forward_keeps_events_with_the_same_timestamp_on_one_side():
    dataset = _dataset()
    sibling = dataset.rows[0].model_copy(
        update={"row_id": "m6:same-time-sibling", "event_id": "event:same-time-sibling"}
    )
    folds = build_walk_forward_folds([*dataset.rows, sibling], BaselineEvaluationConfig(folds=2))
    assert all(
        {dataset.rows[0].event_id, sibling.event_id}.issubset(set(fold.train_event_ids))
        or {dataset.rows[0].event_id, sibling.event_id}.issubset(set(fold.test_event_ids))
        for fold in folds
    )


def test_effective_sample_threshold_counts_distinct_events_not_repeated_legs(tmp_path):
    config = BaselineEvaluationConfig(folds=2, minimum_effective_samples=2)
    dataset = _dataset(config)
    observed = next(row for row in dataset.rows if row.evaluation_status == "observed")
    repeated_leg = observed.model_copy(
        update={
            "row_id": "m6:repeated-leg",
            "outcome_id": "repeated-leg",
            "premium_r": 1.0,
        }
    )
    dataset = dataset.model_copy(update={"rows": [*dataset.rows, repeated_leg]})
    dataset_path = tmp_path / "dataset.json"
    write_evaluation_dataset(dataset, dataset_path)
    aggregate = build_aggregate_result(
        dataset=dataset,
        dataset_path=dataset_path,
        config=config,
        generated_at_utc=dataset.generated_at_utc,
    )
    pooled = aggregate.groups[0]
    assert pooled.status_counts.observed == 2
    assert pooled.sample_count == 5
    assert pooled.effective_sample_count == 1
    assert pooled.result_status == "insufficient_sample"
    assert pooled.premium_r is not None
    assert pooled.premium_r.mean == pytest.approx((5.016949153 + 1.0) / 2)


def test_time_windows_use_declared_iana_timezone_and_invalid_timezone_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="valid IANA timezone"):
        BaselineEvaluationConfig(timezone="Mars/Olympus")

    config = BaselineEvaluationConfig(folds=2, timezone="America/Los_Angeles")
    dataset = _dataset(config)
    boundary = datetime(2026, 7, 1, 0, 30, tzinfo=UTC)
    shifted_rows = [
        row.model_copy(update={"decision_ts_utc": boundary})
        if row.event_id == "event:paft_scorecard_0002_kq_m_shfe_au_20260629000000"
        else row
        for row in dataset.rows
    ]
    dataset = dataset.model_copy(
        update={
            "rows": shifted_rows,
            "time_boundary": dataset.time_boundary.model_copy(
                update={"decision_end_utc": boundary}
            ),
        }
    )
    dataset_path = tmp_path / "dataset.json"
    write_evaluation_dataset(dataset, dataset_path)
    aggregate = build_aggregate_result(
        dataset=dataset,
        dataset_path=dataset_path,
        config=config,
        generated_at_utc=dataset.generated_at_utc,
    )
    time_windows = [group.value for group in aggregate.groups if group.dimension == "time_window"]
    assert time_windows == ["2026-06"]


def test_cli_emits_deterministic_hash_bound_dataset_aggregate_and_walk_forward(tmp_path):
    dataset = tmp_path / "evaluation_dataset.json"
    aggregate = tmp_path / "evaluation_aggregate.json"
    output_manifest = tmp_path / "evaluation_manifest.json"
    args = [
        sys.executable,
        str(SCRIPT),
        "--m5-manifest",
        str(MANIFEST),
        "--premium-outcome",
        str(PREMIUM),
        "--decision-intent",
        str(INTENT),
        "--dataset-out",
        str(dataset),
        "--aggregate-out",
        str(aggregate),
        "--manifest-out",
        str(output_manifest),
        "--generated-at-utc",
        "2026-07-11T00:00:00Z",
        "--bootstrap-replicates",
        "50",
        "--folds",
        "2",
        "--trading-calendar",
        "XSGE",
    ]
    first = subprocess.run(args, cwd=REPO_ROOT, check=True, capture_output=True, text=True)
    first_dataset = dataset.read_bytes()
    first_aggregate = aggregate.read_bytes()
    second = subprocess.run(args, cwd=REPO_ROOT, check=True, capture_output=True, text=True)

    assert first.stdout == second.stdout
    assert dataset.read_bytes() == first_dataset
    assert aggregate.read_bytes() == first_aggregate
    aggregate_payload = json.loads(aggregate.read_text(encoding="utf-8"))
    pooled = next(group for group in aggregate_payload["groups"] if group["dimension"] == "pooled")
    assert pooled["status_counts"] == {
        "observed": 1,
        "ambiguous": 1,
        "data_blocked": 1,
        "not_evaluable": 1,
    }
    assert pooled["premium_r"]["win_definition"] == "premium_r_gt_zero"
    assert pooled["premium_r"]["bootstrap_95_ci"]["method"] == "seeded_cluster_bootstrap_mean_v1"
    assert {group["dimension"] for group in aggregate_payload["groups"]} == {
        "pooled",
        "pool",
        "underlying",
        "time_window",
    }
    folds = aggregate_payload["walk_forward_folds"]
    assert len(folds) == 2
    assert all(fold["no_lookahead_verified"] for fold in folds)
    assert all(
        set(fold["train_event_ids"]).isdisjoint(fold["test_event_ids"]) for fold in folds
    )
    assert folds[0]["train_result"]["effective_sample_count"] == 0
    assert folds[0]["test_result"]["effective_sample_count"] == 1
    manifest_payload = json.loads(output_manifest.read_text(encoding="utf-8"))
    assert manifest_payload["evaluation_dataset_artifact"]["sha256"]
    assert manifest_payload["evaluation_aggregate_result_artifact"]["sha256"]


def test_cli_rejects_resolved_input_output_path_collision_before_write():
    premium_before = PREMIUM.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--m5-manifest",
            str(MANIFEST),
            "--premium-outcome",
            str(PREMIUM),
            "--decision-intent",
            str(INTENT),
            "--dataset-out",
            str(PREMIUM),
            "--aggregate-out",
            "/tmp/m6-aggregate-unused.json",
            "--manifest-out",
            "/tmp/m6-manifest-unused.json",
            "--generated-at-utc",
            "2026-07-11T00:00:00Z",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "must not collide" in result.stderr
    assert PREMIUM.read_bytes() == premium_before
