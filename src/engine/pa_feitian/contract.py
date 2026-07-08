"""Shared PA / Feitian snapshot contract.

This module is intentionally small: strategy code produces the snapshot,
frontend code consumes it, and neither side should infer fields outside this
boundary.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION = "pa_feitian_snapshot_v0"
PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION = "pa_feitian_snapshot_v1"
DECISION_TRACE_V1_VERSION = "decision_trace_v1"
SIGNAL_STATUSES = ("keep", "drop", "advisory", "data_blocked", "model_dominated")

SignalStatus = Literal["keep", "drop", "advisory", "data_blocked", "model_dominated"]
DecisionAction = Literal["take", "skip", "watch"]
TraceInputKind = Literal[
    "scorecard_record",
    "option_chain_row",
    "iv_history",
    "policy_rule",
    "producer_config",
]
TraceNodeKind = Literal[
    "signal",
    "gate",
    "selection",
    "policy",
    "outcome_annotation",
]
TraceNodeStatus = Literal["pass", "fail", "blocked", "advisory", "not_applicable"]
TraceDecisionEffect = Literal["promote", "demote", "block", "annotate", "none"]
SnapshotContractVersion = Literal["pa_feitian_snapshot_v0", "pa_feitian_snapshot_v1"]


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware UTC")
    value = value.astimezone(UTC)
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must be UTC")
    return value


class IvRegimeAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iv_rank: float | None = None
    keep: bool
    reason: str | None = None


class OptionLegAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    side: Literal["call", "put", "none", "unknown"]
    strike: float | None = None
    dte: int | None = None
    otm_rank: int | None = None
    delta_estimate: float | None = None
    selection_status: SignalStatus


class ExitPolicyAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["runner", "fixed_tp", "tick_stop", "none", "unknown"]
    status: SignalStatus
    reason: str | None = None


class TraceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: Any
    source_ref: str | None


class TraceInputRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: TraceInputKind
    source: str
    record_index: int | None = Field(default=None, ge=0)
    asof_ts_utc: datetime | None = None
    digest: str | None = Field(default=None, pattern=r"^sha256:")

    @field_validator("asof_ts_utc")
    @classmethod
    def _validate_asof_ts_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _utc_datetime(value)


class TraceNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9_:-]+$")
    kind: TraceNodeKind
    label: str
    status: TraceNodeStatus
    decision_effect: TraceDecisionEffect
    reason: str | None
    evidence: list[TraceEvidence]


class DecisionTraceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str
    primary_blocker: str | None
    selected_option_contract: str | None
    confidence: float | None = Field(ge=0, le=1)


class DecisionTraceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_version: Literal["decision_trace_v1"]
    action: DecisionAction | None
    status: SignalStatus
    summary: DecisionTraceSummary
    input_refs: list[TraceInputRef]
    nodes: list[TraceNode] = Field(min_length=1)


class PaFeitianSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    instrument: str
    contract: str | None = None
    interval: str
    ts_utc: datetime
    underlying_signal: dict[str, Any] = Field(default_factory=dict)
    features_det: dict[str, Any] = Field(default_factory=dict)
    decision: str | None = None
    decision_trace: str | None = None
    option_leg: OptionLegAnnotation
    iv_regime: IvRegimeAnnotation
    exit_policy: ExitPolicyAnnotation
    underlying_r_outcome: dict[str, Any] | None = None
    premium_r_outcome: dict[str, Any] | None = None
    option_runner_outcome: dict[str, Any] | None = None
    proxy_outcome: dict[str, Any] | None = None
    status: SignalStatus
    caveats: list[str] = Field(default_factory=list)

    @field_validator("ts_utc")
    @classmethod
    def _validate_ts_utc(cls, value: datetime) -> datetime:
        return _utc_datetime(value)


class PaFeitianSignalV1(PaFeitianSignal):
    model_config = ConfigDict(extra="forbid")

    decision_trace_v1: DecisionTraceV1

    @model_validator(mode="after")
    def _validate_trace_matches_signal(self) -> PaFeitianSignalV1:
        if self.decision_trace_v1.status != self.status:
            raise ValueError("decision_trace_v1.status must equal signal status")
        if self.decision_trace_v1.action != self.decision:
            raise ValueError("decision_trace_v1.action must equal signal decision")
        return self


class PaFeitianSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["pa_feitian_snapshot_v0"] = PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION
    generated_at_utc: datetime
    source_commit: str
    run_config: dict[str, Any] = Field(default_factory=dict)
    data_quality: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    signals: list[PaFeitianSignal] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("generated_at_utc")
    @classmethod
    def _validate_generated_at_utc(cls, value: datetime) -> datetime:
        return _utc_datetime(value)


class PaFeitianSnapshotV1(PaFeitianSnapshot):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["pa_feitian_snapshot_v1"] = PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION
    signals: list[PaFeitianSignalV1] = Field(default_factory=list)


def validate_snapshot(data: dict[str, Any]) -> PaFeitianSnapshot | PaFeitianSnapshotV1:
    if data.get("schema_version") == PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION:
        return PaFeitianSnapshotV1.model_validate(data)
    return PaFeitianSnapshot.model_validate(data)


def validate_snapshot_v1(data: dict[str, Any]) -> PaFeitianSnapshotV1:
    return PaFeitianSnapshotV1.model_validate(data)


def snapshot_to_jsonable(snapshot: PaFeitianSnapshot | PaFeitianSnapshotV1) -> dict[str, Any]:
    return snapshot.model_dump(mode="json", exclude_none=False)


def load_snapshot(path: str | Path) -> PaFeitianSnapshot | PaFeitianSnapshotV1:
    with Path(path).open(encoding="utf-8") as f:
        return validate_snapshot(json.load(f))


def load_snapshot_v1(path: str | Path) -> PaFeitianSnapshotV1:
    with Path(path).open(encoding="utf-8") as f:
        return validate_snapshot_v1(json.load(f))


def write_snapshot(snapshot: PaFeitianSnapshot | PaFeitianSnapshotV1, path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(snapshot_to_jsonable(snapshot), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


_MOVED_PRODUCER_EXPORTS = {
    "example_snapshot",
    "snapshot_from_scorecard",
    "snapshot_from_scorecard_file",
}


def __getattr__(name: str) -> Any:
    """Resolve moved producer helpers for older direct imports."""
    if name in _MOVED_PRODUCER_EXPORTS:
        from engine.pa_feitian import scorecard_producer

        return getattr(scorecard_producer, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
