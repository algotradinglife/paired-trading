"""PA / Feitian run manifest contract and file helpers."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PA_FEITIAN_RUN_MANIFEST_SCHEMA_VERSION = "pa_feitian_run_manifest_v1"
HashDigest = str
ArtifactKind = Literal["scorecard", "snapshot", "decision_intent", "premium_outcome"]
ReviewStatus = Literal["pending", "approved", "changes_requested", "rejected"]
DataAccessStatus = Literal["real_data_available", "fixture_fallback", "data_blocked", "unknown"]
HASH_DIGEST_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware UTC")
    value = value.astimezone(UTC)
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must be UTC")
    return value


def _jsonable_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(dict(value), default=str, ensure_ascii=False))


def sha256_file(path: str | Path) -> HashDigest:
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _path_text(path: str | Path) -> str:
    if isinstance(path, Path):
        return path.as_posix()
    return str(path)


def _schema_version_from_json(path: str | Path, default: str | None = None) -> str | None:
    with Path(path).open(encoding="utf-8") as f:
        payload = json.load(f)
    if isinstance(payload, Mapping):
        schema_version = payload.get("schema_version")
        if isinstance(schema_version, str):
            return schema_version
    return default


class PaFeitianArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ArtifactKind
    path: str
    sha256: HashDigest = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    schema_version: str | None
    content_type: Literal["application/json"] = "application/json"


class PaFeitianReviewState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ReviewStatus = "pending"
    reviewer: str | None = None
    reviewed_at_utc: datetime | None = None
    notes: list[str] = Field(default_factory=list)

    @field_validator("reviewed_at_utc")
    @classmethod
    def _validate_reviewed_at_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _utc_datetime(value)


class PaFeitianDataAccess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: DataAccessStatus = "unknown"
    source: str | None = None
    notes: list[str] = Field(default_factory=list)


class PaFeitianRunManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["pa_feitian_run_manifest_v1"] = (
        PA_FEITIAN_RUN_MANIFEST_SCHEMA_VERSION
    )
    generated_at_utc: datetime
    source_commit: str = Field(min_length=7, max_length=40)
    scorecard_artifact: PaFeitianArtifactRef
    snapshot_artifact: PaFeitianArtifactRef
    decision_intent_artifact: PaFeitianArtifactRef | None = None
    premium_outcome_artifact: PaFeitianArtifactRef | None = None
    cli_args: list[str]
    run_config: dict[str, Any]
    data_access: PaFeitianDataAccess = Field(default_factory=PaFeitianDataAccess)
    input_hashes: dict[str, HashDigest] = Field(default_factory=dict)
    output_hashes: dict[str, HashDigest] = Field(default_factory=dict)
    frontend_copy_path: str | None
    review_state: PaFeitianReviewState = Field(default_factory=PaFeitianReviewState)

    @field_validator("generated_at_utc")
    @classmethod
    def _validate_generated_at_utc(cls, value: datetime) -> datetime:
        return _utc_datetime(value)

    @field_validator("input_hashes", "output_hashes")
    @classmethod
    def _validate_hashes(cls, value: dict[str, HashDigest]) -> dict[str, HashDigest]:
        for label, digest in value.items():
            if not label:
                raise ValueError("hash labels must be non-empty")
            if not isinstance(digest, str) or HASH_DIGEST_PATTERN.fullmatch(digest) is None:
                raise ValueError("hash digests must use sha256:<hex>")
        return value

    @model_validator(mode="after")
    def _validate_artifact_links(self) -> PaFeitianRunManifest:
        if self.scorecard_artifact.kind != "scorecard":
            raise ValueError("scorecard_artifact.kind must be scorecard")
        if self.snapshot_artifact.kind != "snapshot":
            raise ValueError("snapshot_artifact.kind must be snapshot")
        if (
            self.decision_intent_artifact is not None
            and self.decision_intent_artifact.kind != "decision_intent"
        ):
            raise ValueError("decision_intent_artifact.kind must be decision_intent")
        if (
            self.premium_outcome_artifact is not None
            and self.premium_outcome_artifact.kind != "premium_outcome"
        ):
            raise ValueError("premium_outcome_artifact.kind must be premium_outcome")
        if self.input_hashes.get("scorecard_artifact") != self.scorecard_artifact.sha256:
            raise ValueError("input_hashes.scorecard_artifact must match scorecard_artifact.sha256")
        if self.output_hashes.get("snapshot_artifact") != self.snapshot_artifact.sha256:
            raise ValueError("output_hashes.snapshot_artifact must match snapshot_artifact.sha256")
        decision_intent_hash = self.output_hashes.get("decision_intent_artifact")
        if self.decision_intent_artifact is None:
            if decision_intent_hash is not None:
                raise ValueError(
                    "decision_intent_artifact is required when output_hashes includes it"
                )
        elif decision_intent_hash != self.decision_intent_artifact.sha256:
            raise ValueError(
                "output_hashes.decision_intent_artifact must match "
                "decision_intent_artifact.sha256"
            )
        premium_outcome_hash = self.output_hashes.get("premium_outcome_artifact")
        if self.premium_outcome_artifact is None:
            if premium_outcome_hash is not None:
                raise ValueError(
                    "premium_outcome_artifact is required when output_hashes includes it"
                )
        elif premium_outcome_hash != self.premium_outcome_artifact.sha256:
            raise ValueError(
                "output_hashes.premium_outcome_artifact must match "
                "premium_outcome_artifact.sha256"
            )
        if self.frontend_copy_path is not None and "frontend_copy" not in self.output_hashes:
            raise ValueError("output_hashes.frontend_copy is required when frontend_copy_path is set")
        return self


def artifact_ref_from_file(
    path: str | Path,
    *,
    kind: ArtifactKind,
    schema_version: str | None = None,
) -> PaFeitianArtifactRef:
    return PaFeitianArtifactRef(
        kind=kind,
        path=_path_text(path),
        sha256=sha256_file(path),
        schema_version=schema_version,
    )


def build_run_manifest(
    *,
    scorecard_path: str | Path,
    snapshot_path: str | Path,
    source_commit: str,
    cli_args: Sequence[str],
    run_config: Mapping[str, Any],
    generated_at_utc: datetime | None = None,
    frontend_copy_path: str | Path | None = None,
    decision_intent_path: str | Path | None = None,
    premium_outcome_path: str | Path | None = None,
    review_state: PaFeitianReviewState | Mapping[str, Any] | None = None,
    data_access: PaFeitianDataAccess | Mapping[str, Any] | None = None,
    scorecard_schema_version: str = "score_today_json",
) -> PaFeitianRunManifest:
    scorecard_ref = artifact_ref_from_file(
        scorecard_path,
        kind="scorecard",
        schema_version=_schema_version_from_json(scorecard_path, scorecard_schema_version),
    )
    snapshot_ref = artifact_ref_from_file(
        snapshot_path,
        kind="snapshot",
        schema_version=_schema_version_from_json(snapshot_path),
    )
    output_hashes = {"snapshot_artifact": snapshot_ref.sha256}
    decision_intent_ref = None
    if decision_intent_path is not None:
        decision_intent_ref = artifact_ref_from_file(
            decision_intent_path,
            kind="decision_intent",
            schema_version=_schema_version_from_json(decision_intent_path),
        )
        output_hashes["decision_intent_artifact"] = decision_intent_ref.sha256
    premium_outcome_ref = None
    if premium_outcome_path is not None:
        premium_outcome_ref = artifact_ref_from_file(
            premium_outcome_path,
            kind="premium_outcome",
            schema_version=_schema_version_from_json(premium_outcome_path),
        )
        output_hashes["premium_outcome_artifact"] = premium_outcome_ref.sha256
    frontend_copy_text = None
    if frontend_copy_path is not None:
        frontend_copy_text = _path_text(frontend_copy_path)
        output_hashes["frontend_copy"] = sha256_file(frontend_copy_path)

    if review_state is None:
        review = PaFeitianReviewState()
    elif isinstance(review_state, PaFeitianReviewState):
        review = review_state
    else:
        review = PaFeitianReviewState.model_validate(review_state)

    if data_access is None:
        access = PaFeitianDataAccess()
    elif isinstance(data_access, PaFeitianDataAccess):
        access = data_access
    else:
        access = PaFeitianDataAccess.model_validate(data_access)

    return PaFeitianRunManifest(
        generated_at_utc=generated_at_utc or datetime.now(UTC),
        source_commit=source_commit,
        scorecard_artifact=scorecard_ref,
        snapshot_artifact=snapshot_ref,
        decision_intent_artifact=decision_intent_ref,
        premium_outcome_artifact=premium_outcome_ref,
        cli_args=list(cli_args),
        run_config=_jsonable_mapping(run_config),
        data_access=access,
        input_hashes={"scorecard_artifact": scorecard_ref.sha256},
        output_hashes=output_hashes,
        frontend_copy_path=frontend_copy_text,
        review_state=review,
    )


def validate_run_manifest(data: dict[str, Any]) -> PaFeitianRunManifest:
    return PaFeitianRunManifest.model_validate(data)


def run_manifest_to_jsonable(manifest: PaFeitianRunManifest) -> dict[str, Any]:
    payload = manifest.model_dump(mode="json", exclude_none=False)
    if manifest.decision_intent_artifact is None:
        payload.pop("decision_intent_artifact", None)
    if manifest.premium_outcome_artifact is None:
        payload.pop("premium_outcome_artifact", None)
    return payload


def load_run_manifest(path: str | Path) -> PaFeitianRunManifest:
    with Path(path).open(encoding="utf-8") as f:
        return validate_run_manifest(json.load(f))


def write_run_manifest(manifest: PaFeitianRunManifest, path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(run_manifest_to_jsonable(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
