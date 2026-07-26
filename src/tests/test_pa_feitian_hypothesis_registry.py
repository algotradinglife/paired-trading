from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from engine.pa_feitian.hypothesis_registry import (
    HypothesisRegistryError,
    canonical_sha256,
    validate_registry_files,
    validate_registry_payload,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "docs/research/pa-feitian-phase1-hypothesis-registry-v1.json"
LOCK_PATH = REPO_ROOT / "docs/research/pa-feitian-phase1-hypothesis-registry-v1.lock.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_committed_registry_and_freeze_lock_validate() -> None:
    result = validate_registry_files(
        registry_path=REGISTRY_PATH,
        lock_path=LOCK_PATH,
        repo_root=REPO_ROOT,
    )

    assert result["registry_sha256"] == _sha256(REGISTRY_PATH)
    assert result["selected_experiment_design_sha256"] == canonical_sha256(
        _load(REGISTRY_PATH)["selection"]["selected_experiment"]["design"]
    )


def test_registry_rejects_missing_hypothesis_provenance() -> None:
    registry = _load(REGISTRY_PATH)
    registry["hypotheses"][0]["source_refs"] = []

    with pytest.raises(HypothesisRegistryError, match="source_refs"):
        validate_registry_payload(registry, repo_root=REPO_ROOT)


def test_registry_rejects_source_content_drift() -> None:
    registry = _load(REGISTRY_PATH)
    registry["source_catalog"][0]["sha256"] = "sha256:" + "0" * 64

    with pytest.raises(HypothesisRegistryError, match="source SHA-256 mismatch"):
        validate_registry_payload(registry, repo_root=REPO_ROOT)


def test_freeze_lock_rejects_after_the_fact_parameter_change(tmp_path: Path) -> None:
    registry = copy.deepcopy(_load(REGISTRY_PATH))
    for source in registry["source_catalog"]:
        target = tmp_path / source["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / source["path"], target)
    registry["selection"]["selected_experiment"]["design"]["iv_rank"]["rank_cutoff"] = 0.70
    changed_registry = tmp_path / REGISTRY_PATH.name
    _write_json(changed_registry, registry)

    lock = copy.deepcopy(_load(LOCK_PATH))
    lock["registry"]["path"] = changed_registry.relative_to(tmp_path).as_posix()
    lock["registry"]["sha256"] = _sha256(changed_registry)
    changed_lock = tmp_path / LOCK_PATH.name
    _write_json(changed_lock, lock)

    with pytest.raises(HypothesisRegistryError, match="rank_cutoff drifted"):
        validate_registry_files(
            registry_path=changed_registry,
            lock_path=changed_lock,
            repo_root=tmp_path,
        )


def test_freeze_lock_rejects_design_change_even_if_registry_hash_is_updated(
    tmp_path: Path,
) -> None:
    registry = copy.deepcopy(_load(REGISTRY_PATH))
    for source in registry["source_catalog"]:
        target = tmp_path / source["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / source["path"], target)
    changed_registry = tmp_path / REGISTRY_PATH.name
    _write_json(changed_registry, registry)

    lock = copy.deepcopy(_load(LOCK_PATH))
    lock["registry"]["path"] = changed_registry.relative_to(tmp_path).as_posix()
    lock["registry"]["sha256"] = _sha256(changed_registry)
    lock["selected_experiment"]["canonical_design_sha256"] = "sha256:" + "0" * 64
    changed_lock = tmp_path / LOCK_PATH.name
    _write_json(changed_lock, lock)

    with pytest.raises(HypothesisRegistryError, match="freeze lock design hash drifted"):
        validate_registry_files(
            registry_path=changed_registry,
            lock_path=changed_lock,
            repo_root=tmp_path,
        )


def test_registry_rejects_multiple_selected_hypotheses() -> None:
    registry = _load(REGISTRY_PATH)
    registry["hypotheses"][1]["selection_status"] = "selected"

    with pytest.raises(HypothesisRegistryError, match="exactly one hypothesis"):
        validate_registry_payload(registry, repo_root=REPO_ROOT)


@pytest.mark.parametrize(
    ("path", "replacement", "message"),
    [
        (
            ("event_source", "deduplication_key"),
            ["decision_intent_sha256", "snapshot_sha256", "signal_id"],
            "event source drifted",
        ),
        (
            ("event_source", "pre_ranking_conflict_pass"),
            "rank first and resolve conflicts later",
            "event source drifted",
        ),
        (
            ("iv_rank", "time_to_expiry", "day_count_convention"),
            "ACT/ACT",
            "iv_rank.time_to_expiry drifted",
        ),
        (
            ("timezone",),
            "UTC",
            "timezone drifted",
        ),
        (
            ("post_outcome_alternative",),
            True,
            "design fields drifted",
        ),
        (
            ("analysis", "primary_estimand", "product_weights", "ag"),
            0.75,
            "analysis definition drifted",
        ),
        (
            ("analysis", "bootstrap", "block_length_completed_trading_days"),
            1,
            "analysis definition drifted",
        ),
        (
            ("analysis", "classification", "inconclusive"),
            "sample gate fails or the interval contains zero",
            "analysis definition drifted",
        ),
    ],
)
def test_registry_rejects_reviewed_design_convention_drift(
    path: tuple[str, ...],
    replacement: object,
    message: str,
) -> None:
    registry = _load(REGISTRY_PATH)
    target = registry["selection"]["selected_experiment"]["design"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement

    with pytest.raises(HypothesisRegistryError, match=message):
        validate_registry_payload(registry, repo_root=REPO_ROOT)


def test_registry_rejects_post_enrollment_freeze_timestamp() -> None:
    registry = _load(REGISTRY_PATH)
    registry["frozen_at_utc"] = "2030-01-01T00:00:00Z"

    with pytest.raises(HypothesisRegistryError, match="freeze timestamp drifted"):
        validate_registry_payload(registry, repo_root=REPO_ROOT)


def test_registry_rejects_staged_window_role_drift() -> None:
    registry = _load(REGISTRY_PATH)
    registry["selection"]["selected_experiment"]["design"]["enrollment_windows"][2]["role"] = (
        "pooled_evaluation"
    )

    with pytest.raises(HypothesisRegistryError, match="enrollment windows drifted"):
        validate_registry_payload(registry, repo_root=REPO_ROOT)


def test_freeze_lock_rejects_coordinated_non_design_registry_rewrite(
    tmp_path: Path,
) -> None:
    registry = copy.deepcopy(_load(REGISTRY_PATH))
    for source in registry["source_catalog"]:
        target = tmp_path / source["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / source["path"], target)
    registry["hypotheses"][0]["statement"] = "post-outcome rewritten conclusion"
    changed_registry = tmp_path / REGISTRY_PATH.name
    _write_json(changed_registry, registry)

    lock = copy.deepcopy(_load(LOCK_PATH))
    lock["registry"]["path"] = changed_registry.relative_to(tmp_path).as_posix()
    lock["registry"]["sha256"] = _sha256(changed_registry)
    changed_lock = tmp_path / LOCK_PATH.name
    _write_json(changed_lock, lock)

    with pytest.raises(HypothesisRegistryError, match="freeze lock registry hash drifted"):
        validate_registry_files(
            registry_path=changed_registry,
            lock_path=changed_lock,
            repo_root=tmp_path,
        )


def test_validator_script_is_directly_importable() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "src/scripts/validate_pa_feitian_hypothesis_registry.py"),
            "--repo-root",
            str(REPO_ROOT),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "hypothesis registry verification passed" in completed.stdout
