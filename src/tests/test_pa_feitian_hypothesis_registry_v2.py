from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from engine.pa_feitian.hypothesis_registry_v2 import (
    HypothesisRegistryV2Error,
    splitmix64_indices,
    validate_registry_v2_files,
    validate_registry_v2_payload,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "docs/research/pa-feitian-phase1-hypothesis-registry-v2.json"
LOCK_PATH = REPO_ROOT / "docs/research/pa-feitian-phase1-hypothesis-registry-v2.lock.json"


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def test_frozen_registry_v2_validates() -> None:
    result = validate_registry_v2_files(
        registry_path=REGISTRY_PATH,
        lock_path=LOCK_PATH,
        repo_root=REPO_ROOT,
    )

    assert result == {
        "registry_sha256": (
            "sha256:f2b77c11317c1f98fe6d4c95f47b2213243322f2f3d4ed6dd1ccbf92d972afa0"
        ),
        "selected_experiment_design_sha256": (
            "sha256:4d3026e5eb398752c3c8f207cb5e21d1b2706e7fb68d40ddf31b99132486cb65"
        ),
    }


def test_registry_v2_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text(
        '{"schema_version":"first","schema_version":"second"}\n',
        encoding="utf-8",
    )

    with pytest.raises(HypothesisRegistryV2Error, match="duplicate JSON key"):
        validate_registry_v2_files(
            registry_path=registry,
            lock_path=LOCK_PATH,
            repo_root=REPO_ROOT,
        )


def test_registry_v2_rejects_source_hash_drift(tmp_path: Path) -> None:
    registry = copy.deepcopy(_load(REGISTRY_PATH))
    first_source = registry["source_catalog"][0]
    assert isinstance(first_source, dict)
    first_source["sha256"] = "sha256:" + "0" * 64

    with pytest.raises(HypothesisRegistryV2Error, match="source hash mismatch"):
        validate_registry_v2_payload(registry, repo_root=REPO_ROOT)


def test_registry_v2_reports_missing_source_as_domain_error(tmp_path: Path) -> None:
    registry = copy.deepcopy(_load(REGISTRY_PATH))

    with pytest.raises(HypothesisRegistryV2Error, match="source file unavailable"):
        validate_registry_v2_payload(registry, repo_root=tmp_path)


def test_registry_v2_rejects_candidate_reselection() -> None:
    registry = copy.deepcopy(_load(REGISTRY_PATH))
    selection = registry["selection"]
    assert isinstance(selection, dict)
    selection["selected_candidate_id"] = "SR-02"

    with pytest.raises(
        HypothesisRegistryV2Error,
        match="selected candidate must be SR-01",
    ):
        validate_registry_v2_payload(registry, repo_root=REPO_ROOT)


def test_registry_v2_rejects_family_removal() -> None:
    registry = copy.deepcopy(_load(REGISTRY_PATH))
    design = registry["selection"]["selected_experiment"]["design"]
    design["universe"].pop()

    with pytest.raises(
        HypothesisRegistryV2Error,
        match="six-family universe or roles drifted",
    ):
        validate_registry_v2_payload(registry, repo_root=REPO_ROOT)


@pytest.mark.parametrize(
    ("path", "replacement", "message"),
    [
        (
            ("decision_event", "decision_local_time"),
            "14:59:00",
            "decision event decision_local_time drifted",
        ),
        (
            ("causal_roll_policy", "confirmation_sessions"),
            2,
            "causal roll policy drifted",
        ),
        (
            ("outcome", "horizon_completed_daily_bars"),
            10,
            "outcome definition drifted",
        ),
        (
            ("sample_gate", "minimum_events_per_family_direction_cell_per_stage"),
            1,
            "sample gate drifted",
        ),
        (
            (
                "sample_gate",
                "maximum_single_decision_date_share_of_effective_events",
            ),
            0.5,
            "sample gate drifted",
        ),
        (
            ("analysis", "bootstrap", "seed"),
            7,
            "bootstrap seed drifted",
        ),
        (
            (
                "analysis",
                "bootstrap",
                "prng",
                "golden_first_12_indices_when_n_10",
            ),
            [0] * 12,
            "bootstrap PRNG protocol drifted",
        ),
    ],
)
def test_registry_v2_rejects_design_drift(
    path: tuple[str, ...],
    replacement: object,
    message: str,
) -> None:
    registry = copy.deepcopy(_load(REGISTRY_PATH))
    target = registry["selection"]["selected_experiment"]["design"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement

    with pytest.raises(HypothesisRegistryV2Error, match=message):
        validate_registry_v2_payload(registry, repo_root=REPO_ROOT)


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (
            ("decision_event", "weekly_aggregation"),
            "calendar week using all rows",
        ),
        (
            ("analysis", "primary_estimand", "within_family"),
            "event-count weighting",
        ),
        (
            ("analysis", "classification", "inconclusive"),
            "interval strictly straddles zero",
        ),
    ],
)
def test_registry_v2_rejects_any_canonical_design_drift(
    path: tuple[str, ...],
    replacement: object,
) -> None:
    registry = copy.deepcopy(_load(REGISTRY_PATH))
    target = registry["selection"]["selected_experiment"]["design"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement

    with pytest.raises(
        HypothesisRegistryV2Error,
        match="P1-EXP-002 canonical design drifted",
    ):
        validate_registry_v2_payload(registry, repo_root=REPO_ROOT)


def test_registry_v2_splitmix64_golden_vector() -> None:
    assert splitmix64_indices(seed=49002, population=10, count=12) == [
        8,
        1,
        0,
        3,
        9,
        3,
        2,
        6,
        9,
        2,
        9,
        4,
    ]


def test_registry_v2_splitmix64_rejects_uint64_overflow_population() -> None:
    with pytest.raises(HypothesisRegistryV2Error, match="exceeds uint64"):
        splitmix64_indices(seed=49002, population=(1 << 64) + 1, count=1)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda value: value.__setitem__("unbound", True), "top-level fields"),
        (
            lambda value: value["selection"].__setitem__("unbound", True),
            "selection fields",
        ),
        (
            lambda value: value["selection"]["selected_experiment"].__setitem__("unbound", True),
            "selected experiment fields",
        ),
        (
            lambda value: value["candidate_decisions"][0].__setitem__("unbound", True),
            r"candidate_decisions\[0\] fields",
        ),
        (
            lambda value: value["source_catalog"][0].__setitem__("unbound", True),
            r"source_catalog\[0\] fields",
        ),
        (
            lambda value: value["selection"]["selected_experiment"]["design"][
                "outcome"
            ].__setitem__("forward_close", 1),
            "posterior outcome field forbidden",
        ),
    ],
)
def test_registry_v2_payload_rejects_semantic_api_bypass(mutator, message) -> None:
    registry = copy.deepcopy(_load(REGISTRY_PATH))
    mutator(registry)

    with pytest.raises(HypothesisRegistryV2Error, match=message):
        validate_registry_v2_payload(registry, repo_root=REPO_ROOT)


def test_registry_v2_lock_rejects_coordinated_registry_rewrite(
    tmp_path: Path,
) -> None:
    registry = copy.deepcopy(_load(REGISTRY_PATH))
    for source in registry["source_catalog"]:
        target = tmp_path / source["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / source["path"], target)

    registry["selection"]["selected_experiment"]["statement"] = "post-outcome rewritten conclusion"
    changed_registry = tmp_path / REGISTRY_PATH.relative_to(REPO_ROOT)
    changed_registry.parent.mkdir(parents=True, exist_ok=True)
    _write_json(changed_registry, registry)

    lock = copy.deepcopy(_load(LOCK_PATH))
    lock["registry"]["path"] = changed_registry.relative_to(tmp_path).as_posix()
    lock["registry"]["sha256"] = _sha256(changed_registry)
    changed_lock = tmp_path / LOCK_PATH.relative_to(REPO_ROOT)
    changed_lock.parent.mkdir(parents=True, exist_ok=True)
    _write_json(changed_lock, lock)

    with pytest.raises(
        HypothesisRegistryV2Error,
        match="registry-v2 lock hash drifted",
    ):
        validate_registry_v2_files(
            registry_path=changed_registry,
            lock_path=changed_lock,
            repo_root=tmp_path,
        )


def test_registry_v2_rejects_alternate_lock_path(tmp_path: Path) -> None:
    alternate = tmp_path / "alternate-lock.json"
    shutil.copyfile(LOCK_PATH, alternate)

    with pytest.raises(
        HypothesisRegistryV2Error,
        match="registry or lock path escapes repository",
    ):
        validate_registry_v2_files(
            registry_path=REGISTRY_PATH,
            lock_path=alternate,
            repo_root=REPO_ROOT,
        )


def test_registry_v2_lock_rejects_unknown_fields(tmp_path: Path) -> None:
    lock = copy.deepcopy(_load(LOCK_PATH))
    lock["unbound_annotation"] = "must not bypass validation"
    changed_lock = tmp_path / LOCK_PATH.name
    _write_json(changed_lock, lock)

    with pytest.raises(
        HypothesisRegistryV2Error,
        match="registry-v2 lock fields drifted",
    ):
        validate_registry_v2_files(
            registry_path=REGISTRY_PATH,
            lock_path=changed_lock,
            repo_root=REPO_ROOT,
        )


def test_registry_v2_validator_script_is_directly_importable() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "src/scripts/validate_pa_feitian_hypothesis_registry_v2.py"),
            "--repo-root",
            str(REPO_ROOT),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "hypothesis registry v2 verification passed" in completed.stdout
