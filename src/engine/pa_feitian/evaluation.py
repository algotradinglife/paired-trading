"""Immutable PA / Feitian M6 evaluation artifact contracts.

This module deliberately contains no evaluator or policy-selection logic.  It
only describes the reproducible inputs and reports that a future evaluator may
write after consuming M5 premium-outcome sidecars.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PA_FEITIAN_EVALUATION_DATASET_SCHEMA_VERSION = "pa_feitian_evaluation_dataset_v1"
PA_FEITIAN_EVALUATION_AGGREGATE_RESULT_SCHEMA_VERSION = (
    "pa_feitian_evaluation_aggregate_result_v1"
)
PA_FEITIAN_EVALUATION_FAILURE_MODE_REPORT_SCHEMA_VERSION = (
    "pa_feitian_evaluation_failure_mode_report_v1"
)
PA_FEITIAN_EVALUATION_SCREENING_REPORT_SCHEMA_VERSION = (
    "pa_feitian_evaluation_screening_report_v1"
)

HASH_DIGEST_PATTERN = r"^sha256:[a-f0-9]{64}$"
EvaluationStatus = Literal["observed", "ambiguous", "data_blocked", "not_evaluable"]
EvaluationArtifactRole = Literal[
    "m6_evaluation_dataset",
    "m6_aggregate_result",
    "m6_failure_mode_report",
    "m6_screening_report",
]
EvaluationArtifactKind = Literal[
    "evaluation_dataset",
    "evaluation_aggregate_result",
    "evaluation_failure_mode_report",
    "evaluation_screening_report",
]
DecisionState = Literal["reject", "watch", "armed_watch", "trade_ready", "observation_runner"]
ExitReason = Literal[
    "premium_stop",
    "premium_target",
    "time_exit",
    "data_gap",
    "unresolved",
    "not_evaluable",
]


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware UTC")
    value = value.astimezone(UTC)
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must be UTC")
    return value


def _validate_hash_map(value: dict[str, str]) -> dict[str, str]:
    pattern = re.compile(HASH_DIGEST_PATTERN)
    for label, digest in value.items():
        if not label:
            raise ValueError("hash labels must be non-empty")
        if pattern.fullmatch(digest) is None:
            raise ValueError("hash digests must use sha256:<hex>")
    return value


class EvaluationArtifactRef(BaseModel):
    """A typed, content-addressed M6 artifact reference."""

    model_config = ConfigDict(extra="forbid")

    kind: EvaluationArtifactKind
    path: str
    sha256: str = Field(pattern=HASH_DIGEST_PATTERN)
    schema_version: str
    content_type: Literal["application/json"] = "application/json"


class EvaluationArtifactProvenance(BaseModel):
    """Common, replayable provenance retained by every M6 artifact."""

    model_config = ConfigDict(extra="forbid")

    role: EvaluationArtifactRole
    source_manifest_path: str
    source_manifest_sha256: str = Field(pattern=HASH_DIGEST_PATTERN)
    source_manifest_schema_version: Literal["pa_feitian_run_manifest_v1"]
    premium_outcome_artifact_path: str
    premium_outcome_artifact_sha256: str = Field(pattern=HASH_DIGEST_PATTERN)
    premium_outcome_schema_version: Literal["pa_feitian_premium_outcome_v1"]
    source_commit: str = Field(min_length=7, max_length=40)
    producer: str
    cli_args: list[str] = Field(default_factory=list)
    policy_config_sha256: str = Field(pattern=HASH_DIGEST_PATTERN)
    data_access_status: Literal[
        "real_data_available", "fixture_fallback", "data_blocked", "unknown"
    ]
    fixture_fallback: bool
    random_seed: int | None = None
    input_hashes: dict[str, str] = Field(default_factory=dict)
    output_hashes: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    @field_validator("input_hashes", "output_hashes")
    @classmethod
    def _validate_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_hash_map(value)

    @model_validator(mode="after")
    def _validate_input_hashes(self) -> EvaluationArtifactProvenance:
        if self.fixture_fallback != (self.data_access_status == "fixture_fallback"):
            raise ValueError("fixture_fallback must match data_access_status")
        if self.input_hashes.get("source_manifest") != self.source_manifest_sha256:
            raise ValueError("input_hashes.source_manifest must match source_manifest_sha256")
        if (
            self.input_hashes.get("premium_outcome_artifact")
            != self.premium_outcome_artifact_sha256
        ):
            raise ValueError(
                "input_hashes.premium_outcome_artifact must match "
                "premium_outcome_artifact_sha256"
            )
        if self.input_hashes.get("policy_config") != self.policy_config_sha256:
            raise ValueError("input_hashes.policy_config must match policy_config_sha256")
        return self


class EvaluationTimeBoundary(BaseModel):
    """Declared time discipline for a dataset or report, not a split algorithm."""

    model_config = ConfigDict(extra="forbid")

    timezone: str = Field(min_length=1)
    trading_calendar: str = Field(min_length=1)
    decision_start_utc: datetime
    decision_end_utc: datetime
    split_method: Literal["walk_forward", "fixed_time_holdout", "not_applicable"]
    folds_declared: int = Field(ge=0)

    @field_validator("decision_start_utc", "decision_end_utc")
    @classmethod
    def _validate_ts(cls, value: datetime) -> datetime:
        return _utc_datetime(value)

    @model_validator(mode="after")
    def _validate_window(self) -> EvaluationTimeBoundary:
        if self.decision_end_utc < self.decision_start_utc:
            raise ValueError("decision_end_utc must not be before decision_start_utc")
        if self.split_method == "walk_forward" and self.folds_declared < 1:
            raise ValueError("walk_forward requires at least one declared fold")
        return self


class EvaluationDatasetRow(BaseModel):
    """One immutable event/leg/policy observation derived from M5 output."""

    model_config = ConfigDict(extra="forbid")

    row_id: str = Field(pattern=r"^[a-z0-9_:-]+$")
    event_id: str
    outcome_id: str
    source_signal_id: str
    source_contract_id: str | None = None
    decision_ts_utc: datetime
    pool: str = "unknown"
    underlying: str = "unknown"
    decision_state: DecisionState
    decision_trace_node_ids: list[str] = Field(default_factory=list)
    iv_gate_status: Literal["pass", "fail", "unknown", "not_evaluable"] = "unknown"
    option_type: Literal["call", "put", "unknown"] = "unknown"
    contract_family: str = "unknown"
    moneyness_bucket: str = "unknown"
    policy_id: str
    policy_version: str
    policy_sha256: str = Field(pattern=HASH_DIGEST_PATTERN)
    evaluation_status: EvaluationStatus
    exit_reason: ExitReason
    premium_r: float | None = None
    underlying_r: float | None = None
    premium_mfe: float | None = None
    premium_mae: float | None = None
    input_refs: list[str] = Field(min_length=1)

    @field_validator("decision_ts_utc")
    @classmethod
    def _validate_decision_ts(cls, value: datetime) -> datetime:
        return _utc_datetime(value)

    @model_validator(mode="after")
    def _validate_outcome_projection(self) -> EvaluationDatasetRow:
        if self.evaluation_status == "observed":
            if self.premium_r is None or self.premium_mfe is None or self.premium_mae is None:
                raise ValueError("observed rows require premium_r, premium_mfe, and premium_mae")
            if self.exit_reason not in {"premium_stop", "premium_target", "time_exit"}:
                raise ValueError("observed rows require a resolved premium exit reason")
        elif any(
            value is not None for value in (self.premium_r, self.premium_mfe, self.premium_mae)
        ):
            raise ValueError("non-observed rows cannot carry premium outcome metrics")
        if self.evaluation_status == "not_evaluable" and self.exit_reason != "not_evaluable":
            raise ValueError("not_evaluable rows require not_evaluable exit_reason")
        return self


class PaFeitianEvaluationDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["pa_feitian_evaluation_dataset_v1"] = (
        PA_FEITIAN_EVALUATION_DATASET_SCHEMA_VERSION
    )
    generated_at_utc: datetime
    provenance: EvaluationArtifactProvenance
    time_boundary: EvaluationTimeBoundary
    rows: list[EvaluationDatasetRow] = Field(default_factory=list)
    filter_reason_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("generated_at_utc")
    @classmethod
    def _validate_generated_at(cls, value: datetime) -> datetime:
        return _utc_datetime(value)

    @field_validator("filter_reason_counts")
    @classmethod
    def _validate_filter_counts(cls, value: dict[str, int]) -> dict[str, int]:
        for label, count in value.items():
            if not label or count < 0:
                raise ValueError("filter reason counts require non-empty labels and non-negative values")
        return value

    @model_validator(mode="after")
    def _validate_dataset(self) -> PaFeitianEvaluationDataset:
        if self.provenance.role != "m6_evaluation_dataset":
            raise ValueError("dataset provenance.role must be m6_evaluation_dataset")
        seen: set[str] = set()
        for row in self.rows:
            if row.row_id in seen:
                raise ValueError("evaluation dataset row_id values must be unique")
            if not (
                self.time_boundary.decision_start_utc
                <= row.decision_ts_utc
                <= self.time_boundary.decision_end_utc
            ):
                raise ValueError("row decision_ts_utc must be inside the declared time boundary")
            seen.add(row.row_id)
        return self


class EvaluationStatusCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed: int = Field(ge=0)
    ambiguous: int = Field(ge=0)
    data_blocked: int = Field(ge=0)
    not_evaluable: int = Field(ge=0)

    @property
    def total(self) -> int:
        return self.observed + self.ambiguous + self.data_blocked + self.not_evaluable


class EvaluationConfidenceInterval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confidence_level: float = Field(gt=0, lt=1)
    lower: float | None = None
    upper: float | None = None
    method: str = Field(min_length=1)
    cluster_unit: Literal["event", "date", "none"]

    @model_validator(mode="after")
    def _validate_interval(self) -> EvaluationConfidenceInterval:
        if (self.lower is None) != (self.upper is None):
            raise ValueError("confidence interval bounds must be both present or both null")
        if self.lower is not None and self.upper is not None and self.upper < self.lower:
            raise ValueError("confidence interval upper must not be below lower")
        return self


class EvaluationRStatistics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mean: float | None = None
    median: float | None = None
    standard_deviation: float | None = Field(default=None, ge=0)
    median_absolute_deviation: float | None = Field(default=None, ge=0)
    lower_quantile: float | None = None
    worst_case: float | None = None
    win_rate: float | None = Field(default=None, ge=0, le=1)
    win_definition: Literal["premium_r_gt_zero"] = "premium_r_gt_zero"
    bootstrap_95_ci: EvaluationConfidenceInterval | None = None


class EvaluationAggregateGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: str
    dimension: Literal["pooled", "pool", "underlying", "time_window", "trace_node", "policy"]
    value: str
    result_status: Literal["generated", "insufficient_sample", "data_blocked", "not_evaluable"]
    sample_count: int = Field(ge=0)
    effective_sample_count: int = Field(
        ge=0,
        description="Distinct observed event_id count; rows may contain dependent option legs.",
    )
    status_counts: EvaluationStatusCounts
    premium_r: EvaluationRStatistics | None = None
    underlying_r_correlation: float | None = Field(default=None, ge=-1, le=1)
    underlying_r_difference_mean: float | None = None
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_counts(self) -> EvaluationAggregateGroup:
        if self.status_counts.total != self.sample_count:
            raise ValueError("status_counts must sum to sample_count")
        if self.effective_sample_count > self.status_counts.observed:
            raise ValueError("effective_sample_count cannot exceed observed status count")
        if self.effective_sample_count == 0 and self.premium_r is not None:
            raise ValueError("premium_r statistics require at least one effective sample")
        return self


class EvaluationWalkForwardFold(BaseModel):
    """A fixed, event-grouped chronological out-of-sample fold."""

    model_config = ConfigDict(extra="forbid")

    fold_id: str = Field(pattern=r"^wf_[0-9]+$")
    train_start_utc: datetime
    train_end_utc: datetime
    test_start_utc: datetime
    test_end_utc: datetime
    train_event_ids: list[str] = Field(min_length=1)
    test_event_ids: list[str] = Field(min_length=1)
    train_result: EvaluationAggregateGroup
    test_result: EvaluationAggregateGroup
    no_lookahead_verified: bool
    notes: list[str] = Field(default_factory=list)

    @field_validator("train_start_utc", "train_end_utc", "test_start_utc", "test_end_utc")
    @classmethod
    def _validate_timestamps(cls, value: datetime) -> datetime:
        return _utc_datetime(value)

    @model_validator(mode="after")
    def _validate_chronology(self) -> EvaluationWalkForwardFold:
        if self.train_end_utc >= self.test_start_utc:
            raise ValueError("walk-forward training window must end before test window")
        if self.train_end_utc < self.train_start_utc or self.test_end_utc < self.test_start_utc:
            raise ValueError("walk-forward windows must be ordered")
        if set(self.train_event_ids) & set(self.test_event_ids):
            raise ValueError("walk-forward folds must not split an event across train and test")
        if self.train_result.dimension != "pooled" or self.test_result.dimension != "pooled":
            raise ValueError("walk-forward train and test results must be pooled aggregates")
        return self


class PaFeitianEvaluationAggregateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["pa_feitian_evaluation_aggregate_result_v1"] = (
        PA_FEITIAN_EVALUATION_AGGREGATE_RESULT_SCHEMA_VERSION
    )
    generated_at_utc: datetime
    provenance: EvaluationArtifactProvenance
    evaluation_dataset: EvaluationArtifactRef
    groups: list[EvaluationAggregateGroup] = Field(default_factory=list)
    walk_forward_folds: list[EvaluationWalkForwardFold] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("generated_at_utc")
    @classmethod
    def _validate_generated_at(cls, value: datetime) -> datetime:
        return _utc_datetime(value)

    @model_validator(mode="after")
    def _validate_aggregate(self) -> PaFeitianEvaluationAggregateResult:
        if self.provenance.role != "m6_aggregate_result":
            raise ValueError("aggregate provenance.role must be m6_aggregate_result")
        if self.evaluation_dataset.kind != "evaluation_dataset":
            raise ValueError("evaluation_dataset.kind must be evaluation_dataset")
        if self.evaluation_dataset.schema_version != PA_FEITIAN_EVALUATION_DATASET_SCHEMA_VERSION:
            raise ValueError(
                "evaluation_dataset.schema_version must be "
                "pa_feitian_evaluation_dataset_v1"
            )
        if self.provenance.input_hashes.get("evaluation_dataset") != self.evaluation_dataset.sha256:
            raise ValueError("input_hashes.evaluation_dataset must match evaluation_dataset.sha256")
        return self


class FailureModeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_mode_id: str
    category: Literal[
        "decision_trace",
        "iv_gate",
        "option_leg",
        "data_quality",
        "exit_reason",
        "premium_underlying_divergence",
        "policy_instability",
        "other",
    ]
    label: str
    affected_row_count: int = Field(ge=0)
    outcome_ids: list[str] = Field(default_factory=list)
    source_signal_ids: list[str] = Field(default_factory=list)
    input_refs: list[str] = Field(default_factory=list)
    severity: Literal["info", "warning", "blocking"]
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_traceability(self) -> FailureModeRecord:
        if self.affected_row_count and not (self.outcome_ids or self.source_signal_ids):
            raise ValueError("non-empty failure modes require outcome_ids or source_signal_ids")
        return self


class PaFeitianEvaluationFailureModeReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["pa_feitian_evaluation_failure_mode_report_v1"] = (
        PA_FEITIAN_EVALUATION_FAILURE_MODE_REPORT_SCHEMA_VERSION
    )
    generated_at_utc: datetime
    provenance: EvaluationArtifactProvenance
    evaluation_dataset: EvaluationArtifactRef
    failure_modes: list[FailureModeRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("generated_at_utc")
    @classmethod
    def _validate_generated_at(cls, value: datetime) -> datetime:
        return _utc_datetime(value)

    @model_validator(mode="after")
    def _validate_report(self) -> PaFeitianEvaluationFailureModeReport:
        if self.provenance.role != "m6_failure_mode_report":
            raise ValueError("failure report provenance.role must be m6_failure_mode_report")
        if self.evaluation_dataset.kind != "evaluation_dataset":
            raise ValueError("evaluation_dataset.kind must be evaluation_dataset")
        if self.evaluation_dataset.schema_version != PA_FEITIAN_EVALUATION_DATASET_SCHEMA_VERSION:
            raise ValueError(
                "evaluation_dataset.schema_version must be "
                "pa_feitian_evaluation_dataset_v1"
            )
        if self.provenance.input_hashes.get("evaluation_dataset") != self.evaluation_dataset.sha256:
            raise ValueError("input_hashes.evaluation_dataset must match evaluation_dataset.sha256")
        return self


class ScreeningCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    policy_id: str
    policy_version: str
    classification: Literal["promising", "inconclusive", "negative", "blocked"]
    classification_basis: list[str] = Field(min_length=1)
    comparable_oos_window_count: int = Field(ge=0)
    effective_event_count: int = Field(ge=0)
    baseline_policy_id: str
    reviewer_status: Literal["pending", "approved", "changes_requested", "rejected"] = "pending"
    limitations: list[str] = Field(default_factory=list)


class PaFeitianEvaluationScreeningReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["pa_feitian_evaluation_screening_report_v1"] = (
        PA_FEITIAN_EVALUATION_SCREENING_REPORT_SCHEMA_VERSION
    )
    generated_at_utc: datetime
    provenance: EvaluationArtifactProvenance
    evaluation_dataset: EvaluationArtifactRef
    aggregate_result: EvaluationArtifactRef
    candidates: list[ScreeningCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("generated_at_utc")
    @classmethod
    def _validate_generated_at(cls, value: datetime) -> datetime:
        return _utc_datetime(value)

    @model_validator(mode="after")
    def _validate_screening(self) -> PaFeitianEvaluationScreeningReport:
        if self.provenance.role != "m6_screening_report":
            raise ValueError("screening provenance.role must be m6_screening_report")
        if self.evaluation_dataset.kind != "evaluation_dataset":
            raise ValueError("evaluation_dataset.kind must be evaluation_dataset")
        if self.evaluation_dataset.schema_version != PA_FEITIAN_EVALUATION_DATASET_SCHEMA_VERSION:
            raise ValueError(
                "evaluation_dataset.schema_version must be "
                "pa_feitian_evaluation_dataset_v1"
            )
        if self.aggregate_result.kind != "evaluation_aggregate_result":
            raise ValueError("aggregate_result.kind must be evaluation_aggregate_result")
        if (
            self.aggregate_result.schema_version
            != PA_FEITIAN_EVALUATION_AGGREGATE_RESULT_SCHEMA_VERSION
        ):
            raise ValueError(
                "aggregate_result.schema_version must be "
                "pa_feitian_evaluation_aggregate_result_v1"
            )
        if self.provenance.input_hashes.get("evaluation_dataset") != self.evaluation_dataset.sha256:
            raise ValueError("input_hashes.evaluation_dataset must match evaluation_dataset.sha256")
        if self.provenance.input_hashes.get("aggregate_result") != self.aggregate_result.sha256:
            raise ValueError("input_hashes.aggregate_result must match aggregate_result.sha256")
        return self


def _load(path: str | Path, validator: Any) -> Any:
    with Path(path).open(encoding="utf-8") as f:
        return validator(json.load(f))


def _write(model: BaseModel, path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(model.model_dump(mode="json", exclude_none=False), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


def validate_evaluation_dataset(data: dict[str, Any]) -> PaFeitianEvaluationDataset:
    return PaFeitianEvaluationDataset.model_validate(data)


def evaluation_dataset_to_jsonable(dataset: PaFeitianEvaluationDataset) -> dict[str, Any]:
    return dataset.model_dump(mode="json", exclude_none=False)


def load_evaluation_dataset(path: str | Path) -> PaFeitianEvaluationDataset:
    return _load(path, validate_evaluation_dataset)


def write_evaluation_dataset(dataset: PaFeitianEvaluationDataset, path: str | Path) -> None:
    _write(dataset, path)


def validate_evaluation_aggregate_result(data: dict[str, Any]) -> PaFeitianEvaluationAggregateResult:
    return PaFeitianEvaluationAggregateResult.model_validate(data)


def evaluation_aggregate_result_to_jsonable(
    result: PaFeitianEvaluationAggregateResult,
) -> dict[str, Any]:
    return result.model_dump(mode="json", exclude_none=False)


def load_evaluation_aggregate_result(path: str | Path) -> PaFeitianEvaluationAggregateResult:
    return _load(path, validate_evaluation_aggregate_result)


def write_evaluation_aggregate_result(
    result: PaFeitianEvaluationAggregateResult, path: str | Path
) -> None:
    _write(result, path)


def validate_evaluation_failure_mode_report(
    data: dict[str, Any],
) -> PaFeitianEvaluationFailureModeReport:
    return PaFeitianEvaluationFailureModeReport.model_validate(data)


def evaluation_failure_mode_report_to_jsonable(
    report: PaFeitianEvaluationFailureModeReport,
) -> dict[str, Any]:
    return report.model_dump(mode="json", exclude_none=False)


def load_evaluation_failure_mode_report(path: str | Path) -> PaFeitianEvaluationFailureModeReport:
    return _load(path, validate_evaluation_failure_mode_report)


def write_evaluation_failure_mode_report(
    report: PaFeitianEvaluationFailureModeReport, path: str | Path
) -> None:
    _write(report, path)

def validate_evaluation_screening_report(
    data: dict[str, Any],
) -> PaFeitianEvaluationScreeningReport:
    return PaFeitianEvaluationScreeningReport.model_validate(data)


def evaluation_screening_report_to_jsonable(
    report: PaFeitianEvaluationScreeningReport,
) -> dict[str, Any]:
    return report.model_dump(mode="json", exclude_none=False)


def load_evaluation_screening_report(path: str | Path) -> PaFeitianEvaluationScreeningReport:
    return _load(path, validate_evaluation_screening_report)


def write_evaluation_screening_report(
    report: PaFeitianEvaluationScreeningReport, path: str | Path
) -> None:
    _write(report, path)
