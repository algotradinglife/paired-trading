"""Shared PA / Feitian snapshot contract.

This module is intentionally small: strategy code produces the snapshot,
frontend code consumes it, and neither side should infer fields outside this
boundary.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION = "pa_feitian_snapshot_v0"
PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION = "pa_feitian_snapshot_v1"
PA_FEITIAN_DECISION_INTENT_SCHEMA_VERSION = "pa_feitian_decision_intent_v1"
DECISION_TRACE_V1_VERSION = "decision_trace_v1"
SIGNAL_STATUSES = ("keep", "drop", "advisory", "data_blocked", "model_dominated")
DECISION_INTENT_STATES = ("reject", "watch", "armed_watch", "trade_ready", "observation_runner")
PRODUCT_DIRECTION_TIERS = (
    "aligned_trade_candidate",
    "conditional_watch",
    "observation_only",
    "direction_blocked",
    "unknown",
)
PREMIUM_STOP_STATUSES = ("clear", "unclear", "blocked", "not_applicable")
PREMIUM_STOP_SOURCES = (
    "swing_low_premium",
    "recent_36bar_low",
    "half_loss_fixed",
    "manual",
    "unavailable",
    "not_applicable",
)
CONFIRMATION_STATUSES = ("confirmed", "pending", "failed", "not_applicable")
CONFIRMATION_SOURCES = (
    "premium_macd",
    "premium_breakout",
    "underlying_only",
    "manual",
    "unavailable",
    "not_applicable",
)
LIQUIDITY_STATUSES = ("adequate", "thin", "stale", "thin_and_stale", "unknown", "not_applicable")

SignalStatus = Literal["keep", "drop", "advisory", "data_blocked", "model_dominated"]
DecisionAction = Literal["take", "skip", "watch"]
DecisionIntentState = Literal["reject", "watch", "armed_watch", "trade_ready", "observation_runner"]
ProductDirectionTier = Literal[
    "aligned_trade_candidate",
    "conditional_watch",
    "observation_only",
    "direction_blocked",
    "unknown",
]
PremiumStopStatus = Literal["clear", "unclear", "blocked", "not_applicable"]
PremiumStopSource = Literal[
    "swing_low_premium",
    "recent_36bar_low",
    "half_loss_fixed",
    "manual",
    "unavailable",
    "not_applicable",
]
ConfirmationStatus = Literal["confirmed", "pending", "failed", "not_applicable"]
ConfirmationSource = Literal[
    "premium_macd",
    "premium_breakout",
    "underlying_only",
    "manual",
    "unavailable",
    "not_applicable",
]
LiquidityStatus = Literal["adequate", "thin", "stale", "thin_and_stale", "unknown", "not_applicable"]
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
NoLookaheadInputKind = Literal[
    "scorecard_record",
    "snapshot_signal",
    "decision_context",
    "event",
    "option_match",
    "premium_bars",
    "underlying_bars",
    "policy_rule",
    "producer_config",
    "run_manifest",
]

_REASON_CODE_PATTERN = re.compile(r"^[A-Z0-9_]+$")
_FORBIDDEN_NO_LOOKAHEAD_TOKENS = (
    "posterior",
    "outcome",
    "label",
    "mfe",
    "mae",
    "hit_marker",
    "stop_first",
)


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware UTC")
    value = value.astimezone(UTC)
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must be UTC")
    return value


def _reject_lookahead_label(value: str) -> str:
    folded = value.lower()
    for token in _FORBIDDEN_NO_LOOKAHEAD_TOKENS:
        if token in folded:
            raise ValueError(f"no-lookahead input must not reference {token!r}")
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


class DecisionIntentProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["manifest_referenced_decision_intent_sidecar"]
    source_manifest_path: str
    source_manifest_schema_version: Literal["pa_feitian_run_manifest_v1"]
    source_manifest_generated_at_utc: datetime | None = None
    snapshot_artifact_path: str
    snapshot_artifact_sha256: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    snapshot_schema_version: SnapshotContractVersion
    producer: str
    notes: list[str] = Field(default_factory=list)

    @field_validator("source_manifest_generated_at_utc")
    @classmethod
    def _validate_source_manifest_generated_at_utc(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None
        return _utc_datetime(value)


class PremiumStopIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: PremiumStopStatus
    source: PremiumStopSource
    entry_premium: float | None = Field(default=None, gt=0)
    stop_premium: float | None = Field(default=None, ge=0)
    stop_distance_pct: float | None = Field(default=None, ge=0)
    soft_gate_min_pct: float | None = Field(default=None, ge=0)
    soft_gate_max_pct: float | None = Field(default=None, ge=0)
    asof_ts_utc: datetime | None = None
    evidence_ref: str | None = None

    @field_validator("asof_ts_utc")
    @classmethod
    def _validate_asof_ts_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _utc_datetime(value)

    @model_validator(mode="after")
    def _validate_clear_stop(self) -> PremiumStopIntent:
        if self.status != "clear":
            return self
        if self.source in {"half_loss_fixed", "unavailable", "not_applicable"}:
            raise ValueError("clear premium_stop cannot use proxy or unavailable stop source")
        if (
            self.entry_premium is None
            or self.stop_premium is None
            or self.stop_distance_pct is None
        ):
            raise ValueError("clear premium_stop requires entry, stop, and distance")
        return self


class ConfirmationIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ConfirmationStatus
    source: ConfirmationSource
    confirmed_at_utc: datetime | None = None
    evidence_ref: str | None = None

    @field_validator("confirmed_at_utc")
    @classmethod
    def _validate_confirmed_at_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _utc_datetime(value)

    @model_validator(mode="after")
    def _validate_confirmed_source(self) -> ConfirmationIntent:
        if self.status != "confirmed":
            return self
        if self.source in {"underlying_only", "unavailable", "not_applicable"}:
            raise ValueError("confirmed readiness requires premium confirmation evidence")
        if self.confirmed_at_utc is None:
            raise ValueError("confirmed readiness requires confirmed_at_utc")
        return self


class LiquidityIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: LiquidityStatus
    quote_count: int | None = Field(default=None, ge=0)
    last_quote_age_seconds: int | None = Field(default=None, ge=0)
    recovery_required: bool
    evidence_ref: str | None = None


class NoLookaheadInputRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: NoLookaheadInputKind
    source: str
    record_index: int | None = Field(default=None, ge=0)
    asof_ts_utc: datetime
    digest: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")

    @field_validator("id", "source")
    @classmethod
    def _validate_no_lookahead_label(cls, value: str) -> str:
        return _reject_lookahead_label(value)

    @field_validator("asof_ts_utc")
    @classmethod
    def _validate_asof_ts_utc(cls, value: datetime) -> datetime:
        return _utc_datetime(value)


class DecisionIntentSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: str
    instrument: str
    contract: str | None = None
    interval: str
    decision_ts_utc: datetime
    decision_state: DecisionIntentState
    execution_allowed: bool
    product_direction_tier: ProductDirectionTier
    premium_stop: PremiumStopIntent
    confirmation: ConfirmationIntent
    liquidity: LiquidityIntent
    reason_codes: list[str] = Field(min_length=1)
    no_lookahead_inputs: list[NoLookaheadInputRef] = Field(min_length=1)

    @field_validator("decision_ts_utc")
    @classmethod
    def _validate_decision_ts_utc(cls, value: datetime) -> datetime:
        return _utc_datetime(value)

    @field_validator("reason_codes")
    @classmethod
    def _validate_reason_codes(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        for code in value:
            if _REASON_CODE_PATTERN.fullmatch(code) is None:
                raise ValueError("reason_codes must use uppercase snake-case tokens")
            if code in seen:
                raise ValueError("reason_codes must be unique per signal")
            seen.add(code)
        return value

    @model_validator(mode="after")
    def _validate_execution_contract(self) -> DecisionIntentSignal:
        trade_ready = self.decision_state == "trade_ready"
        if self.execution_allowed != trade_ready:
            raise ValueError("execution_allowed must be true if and only if decision_state is trade_ready")
        if self.execution_allowed:
            if self.product_direction_tier != "aligned_trade_candidate":
                raise ValueError("execution_allowed requires aligned_trade_candidate direction tier")
            if self.premium_stop.status != "clear":
                raise ValueError("execution_allowed requires clear premium_stop")
            if self.confirmation.status != "confirmed":
                raise ValueError("execution_allowed requires confirmed premium confirmation")
            if self.liquidity.status != "adequate" or self.liquidity.recovery_required:
                raise ValueError("execution_allowed requires adequate recovered liquidity")
        if self.product_direction_tier == "observation_only" and self.execution_allowed:
            raise ValueError("observation_only product direction cannot allow execution")
        for input_ref in self.no_lookahead_inputs:
            if input_ref.asof_ts_utc > self.decision_ts_utc:
                raise ValueError("no_lookahead_inputs.asof_ts_utc must not be after decision_ts_utc")
        return self


class PaFeitianDecisionIntentSidecar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["pa_feitian_decision_intent_v1"] = (
        PA_FEITIAN_DECISION_INTENT_SCHEMA_VERSION
    )
    generated_at_utc: datetime
    source_commit: str = Field(min_length=7, max_length=40)
    provenance: DecisionIntentProvenance
    intents: list[DecisionIntentSignal] = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("generated_at_utc")
    @classmethod
    def _validate_generated_at_utc(cls, value: datetime) -> datetime:
        return _utc_datetime(value)

    @model_validator(mode="after")
    def _validate_unique_signal_ids(self) -> PaFeitianDecisionIntentSidecar:
        seen: set[str] = set()
        for intent in self.intents:
            if intent.signal_id in seen:
                raise ValueError("decision intent signal_id values must be unique")
            seen.add(intent.signal_id)
        return self


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


def validate_decision_intent(data: dict[str, Any]) -> PaFeitianDecisionIntentSidecar:
    return PaFeitianDecisionIntentSidecar.model_validate(data)


def snapshot_to_jsonable(snapshot: PaFeitianSnapshot | PaFeitianSnapshotV1) -> dict[str, Any]:
    return snapshot.model_dump(mode="json", exclude_none=False)


def decision_intent_to_jsonable(sidecar: PaFeitianDecisionIntentSidecar) -> dict[str, Any]:
    return sidecar.model_dump(mode="json", exclude_none=False)


def load_snapshot(path: str | Path) -> PaFeitianSnapshot | PaFeitianSnapshotV1:
    with Path(path).open(encoding="utf-8") as f:
        return validate_snapshot(json.load(f))


def load_snapshot_v1(path: str | Path) -> PaFeitianSnapshotV1:
    with Path(path).open(encoding="utf-8") as f:
        return validate_snapshot_v1(json.load(f))


def load_decision_intent(path: str | Path) -> PaFeitianDecisionIntentSidecar:
    with Path(path).open(encoding="utf-8") as f:
        return validate_decision_intent(json.load(f))


def write_snapshot(snapshot: PaFeitianSnapshot | PaFeitianSnapshotV1, path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(snapshot_to_jsonable(snapshot), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_decision_intent(sidecar: PaFeitianDecisionIntentSidecar, path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(decision_intent_to_jsonable(sidecar), ensure_ascii=False, indent=2) + "\n",
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
