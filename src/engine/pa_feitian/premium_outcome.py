"""PA / Feitian premium-space outcome sidecar contract."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PA_FEITIAN_PREMIUM_OUTCOME_SCHEMA_VERSION = "pa_feitian_premium_outcome_v1"
HASH_DIGEST_PATTERN = r"^sha256:[a-f0-9]{64}$"

PremiumOutcomeStatus = Literal["observed", "ambiguous", "data_blocked", "not_evaluable"]
PremiumPriceSourceType = Literal["observed", "model_derived", "unavailable"]
PremiumBarGranularity = Literal["daily", "intraday", "tick", "unknown"]
PremiumPolicyOrigin = Literal["decision_declared", "retrospective_fixed"]
PremiumPolicyLevelMode = Literal["absolute_premium", "entry_relative"]
PremiumExitReason = Literal[
    "premium_stop",
    "premium_target",
    "time_exit",
    "data_gap",
    "unresolved",
    "not_evaluable",
]
OptionRight = Literal["call", "put"]
FillRule = Literal["at_level", "next_open", "bar_close", "gap_open", "not_applicable"]
SameBarResolution = Literal[
    "ambiguous",
    "stop_first",
    "target_first",
    "conservative_stop_first",
    "not_applicable",
]
MissingBarPolicy = Literal["data_blocked", "skip_missing", "time_exit"]
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


class PremiumOutcomeNoLookaheadInputRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: NoLookaheadInputKind
    source: str
    record_index: int | None = Field(default=None, ge=0)
    asof_ts_utc: datetime
    digest: str | None = Field(default=None, pattern=HASH_DIGEST_PATTERN)

    @field_validator("id", "source")
    @classmethod
    def _validate_no_lookahead_label(cls, value: str) -> str:
        return _reject_lookahead_label(value)

    @field_validator("asof_ts_utc")
    @classmethod
    def _validate_asof_ts_utc(cls, value: datetime) -> datetime:
        return _utc_datetime(value)


class PremiumOutcomeProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["manifest_referenced_premium_outcome_sidecar"]
    source_manifest_path: str
    source_manifest_sha256: str = Field(pattern=HASH_DIGEST_PATTERN)
    source_manifest_schema_version: Literal["pa_feitian_run_manifest_v1"]
    snapshot_artifact_path: str
    snapshot_artifact_sha256: str = Field(pattern=HASH_DIGEST_PATTERN)
    snapshot_schema_version: Literal["pa_feitian_snapshot_v0", "pa_feitian_snapshot_v1"]
    decision_intent_artifact_path: str | None = None
    decision_intent_artifact_sha256: str | None = Field(default=None, pattern=HASH_DIGEST_PATTERN)
    decision_intent_schema_version: Literal["pa_feitian_decision_intent_v1"] | None = None
    producer: str
    cli_args: list[str] = Field(default_factory=list)
    input_hashes: dict[str, str] = Field(default_factory=dict)
    policy_hashes: dict[str, str] = Field(default_factory=dict)
    output_hashes: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    @field_validator("input_hashes", "policy_hashes", "output_hashes")
    @classmethod
    def _validate_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        pattern = re.compile(HASH_DIGEST_PATTERN)
        for label, digest in value.items():
            if not label:
                raise ValueError("hash labels must be non-empty")
            if pattern.fullmatch(digest) is None:
                raise ValueError("hash digests must use sha256:<hex>")
        return value

    @model_validator(mode="after")
    def _validate_artifact_hashes(self) -> PremiumOutcomeProvenance:
        decision_fields = (
            self.decision_intent_artifact_path,
            self.decision_intent_artifact_sha256,
            self.decision_intent_schema_version,
        )
        if any(field is not None for field in decision_fields) and not all(
            field is not None for field in decision_fields
        ):
            raise ValueError("decision intent provenance fields must be all present or all null")
        if self.input_hashes.get("source_manifest") != self.source_manifest_sha256:
            raise ValueError("input_hashes.source_manifest must match source_manifest_sha256")
        if self.input_hashes.get("snapshot_artifact") != self.snapshot_artifact_sha256:
            raise ValueError("input_hashes.snapshot_artifact must match snapshot_artifact_sha256")
        decision_hash = self.input_hashes.get("decision_intent_artifact")
        if self.decision_intent_artifact_sha256 is None:
            if decision_hash is not None:
                raise ValueError("decision_intent_artifact hash requires decision intent provenance")
        elif decision_hash != self.decision_intent_artifact_sha256:
            raise ValueError(
                "input_hashes.decision_intent_artifact must match "
                "decision_intent_artifact_sha256"
            )
        return self


class SelectedOptionContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_contract_id: str
    option_type: OptionRight
    exchange: str
    product: str
    contract_symbol: str
    strike: float = Field(gt=0)
    expiry: date
    dte_at_decision: int = Field(ge=0)
    contract_selection_asof_utc: datetime
    selection_source_ref: str

    @field_validator("contract_selection_asof_utc")
    @classmethod
    def _validate_contract_selection_asof_utc(cls, value: datetime) -> datetime:
        return _utc_datetime(value)


class PremiumOutcomePolicyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_rule: str
    price_level_mode: PremiumPolicyLevelMode
    stop_premium: float | None = Field(default=None, ge=0)
    target_premiums: list[float] = Field(default_factory=list)
    stop_fraction_of_entry: float | None = Field(default=None, gt=0, lt=1)
    target_multiples_of_entry: list[float] = Field(default_factory=list)
    max_holding_bars: int | None = Field(default=None, ge=1)
    max_holding_days: int | None = Field(default=None, ge=1)
    stop_fill_rule: FillRule
    target_fill_rule: FillRule
    time_exit_fill_rule: FillRule
    missing_bar_policy: MissingBarPolicy
    same_bar_resolution: SameBarResolution
    slippage_ticks: float = Field(ge=0)
    tick_size: float | None = Field(default=None, gt=0)

    @field_validator("target_premiums")
    @classmethod
    def _validate_target_premiums(cls, value: list[float]) -> list[float]:
        for premium in value:
            if premium < 0:
                raise ValueError("target premiums must be non-negative")
        return value

    @field_validator("target_multiples_of_entry")
    @classmethod
    def _validate_target_multiples(cls, value: list[float]) -> list[float]:
        for multiple in value:
            if multiple <= 1:
                raise ValueError("target multiples of entry must be greater than 1")
        return value

    @model_validator(mode="after")
    def _validate_price_level_spec(self) -> PremiumOutcomePolicyParams:
        if self.price_level_mode == "absolute_premium":
            if self.stop_premium is None or not self.target_premiums:
                raise ValueError("absolute_premium policy requires stop_premium and target_premiums")
            if self.stop_fraction_of_entry is not None or self.target_multiples_of_entry:
                raise ValueError("absolute_premium policy cannot mix entry-relative levels")
        else:
            if self.stop_fraction_of_entry is None or not self.target_multiples_of_entry:
                raise ValueError(
                    "entry_relative policy requires stop_fraction_of_entry and "
                    "target_multiples_of_entry"
                )
            if self.stop_premium is not None or self.target_premiums:
                raise ValueError("entry_relative policy cannot mix absolute premium levels")
        return self


class PremiumOutcomePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_id: str
    policy_version: str
    origin: PremiumPolicyOrigin
    declared_at_utc: datetime
    fixed_before_traversal: bool
    traversal_started_at_utc: datetime
    digest: str = Field(pattern=HASH_DIGEST_PATTERN)
    provenance_hash_key: str
    params: PremiumOutcomePolicyParams

    @field_validator("declared_at_utc", "traversal_started_at_utc")
    @classmethod
    def _validate_declared_at_utc(cls, value: datetime) -> datetime:
        return _utc_datetime(value)

    @model_validator(mode="after")
    def _validate_fixed_policy(self) -> PremiumOutcomePolicy:
        if not self.fixed_before_traversal:
            raise ValueError("outcome policy must be fixed before premium path traversal")
        if self.declared_at_utc > self.traversal_started_at_utc:
            raise ValueError("outcome policy declared_at_utc must not be after traversal start")
        return self


class PremiumOutcomeCostModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    currency: str
    commission_per_contract: float = Field(ge=0)
    fees_per_contract: float = Field(ge=0)
    slippage_ticks: float = Field(ge=0)
    tick_size: float | None = Field(default=None, gt=0)
    tick_value: float | None = Field(default=None, gt=0)
    entry_cost_premium: float = Field(ge=0)
    exit_cost_premium: float = Field(ge=0)
    notes: list[str] = Field(default_factory=list)


class PremiumFill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ts_utc: datetime
    fill_premium: float = Field(ge=0)
    fill_rule: FillRule
    slippage_premium: float = Field(ge=0)
    cost_premium: float = Field(ge=0)

    @field_validator("ts_utc")
    @classmethod
    def _validate_ts_utc(cls, value: datetime) -> datetime:
        return _utc_datetime(value)


class PremiumRiskBasis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_premium: float = Field(gt=0)
    stop_premium: float = Field(ge=0)
    entry_cost_premium: float = Field(ge=0)
    exit_cost_premium: float = Field(ge=0)
    declared_risk_premium: float = Field(gt=0)
    denominator_label: Literal["declared_premium_risk_after_costs"]

    @model_validator(mode="after")
    def _validate_declared_risk(self) -> PremiumRiskBasis:
        if self.stop_premium >= self.entry_premium:
            raise ValueError("premium risk basis requires stop_premium below entry_premium")
        return self


class PremiumOutcomeMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gross_premium_return: float
    net_premium_return: float
    premium_multiple: float = Field(ge=0)
    premium_r: float
    premium_mfe: float
    premium_mae: float
    risk: PremiumRiskBasis


class UnderlyingContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_source: Literal["observed_underlying", "model_derived", "unavailable"]
    entry_ts_utc: datetime | None = None
    exit_ts_utc: datetime | None = None
    entry_underlying: float | None = Field(default=None, ge=0)
    exit_underlying: float | None = Field(default=None, ge=0)
    underlying_return: float | None = None
    underlying_r: float | None = None
    underlying_r_denominator: str | None = None
    notes: list[str] = Field(default_factory=list)

    @field_validator("entry_ts_utc", "exit_ts_utc")
    @classmethod
    def _validate_ts_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _utc_datetime(value)

    @model_validator(mode="after")
    def _validate_underlying_window(self) -> UnderlyingContext:
        if (
            self.entry_ts_utc is not None
            and self.exit_ts_utc is not None
            and self.exit_ts_utc < self.entry_ts_utc
        ):
            raise ValueError("underlying exit_ts_utc must not be before entry_ts_utc")
        if self.underlying_r is not None and not self.underlying_r_denominator:
            raise ValueError("underlying_r requires underlying_r_denominator")
        return self


class PremiumOutcomeAmbiguity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["same_bar_stop_target", "missing_ordering", "daily_ohlc_limit", "other"]
    bar_ts_utc: datetime | None = None
    conservative_resolution: SameBarResolution | None = None
    description: str

    @field_validator("bar_ts_utc")
    @classmethod
    def _validate_bar_ts_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _utc_datetime(value)


class PremiumOutcomeDataGap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "missing_contract",
        "missing_bars",
        "early_termination",
        "missing_entry",
        "missing_exit",
        "other",
    ]
    start_ts_utc: datetime | None = None
    end_ts_utc: datetime | None = None
    description: str

    @field_validator("start_ts_utc", "end_ts_utc")
    @classmethod
    def _validate_ts_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _utc_datetime(value)

    @model_validator(mode="after")
    def _validate_gap_window(self) -> PremiumOutcomeDataGap:
        if (
            self.start_ts_utc is not None
            and self.end_ts_utc is not None
            and self.end_ts_utc < self.start_ts_utc
        ):
            raise ValueError("data gap end_ts_utc must not be before start_ts_utc")
        return self


class PremiumOutcomeDataQuality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    premium_price_source_type: PremiumPriceSourceType
    bar_granularity: PremiumBarGranularity
    required_premium_bars_available: bool
    first_premium_observation_ts_utc: datetime | None = None
    last_premium_observation_ts_utc: datetime | None = None
    ambiguity: PremiumOutcomeAmbiguity | None = None
    data_gap: PremiumOutcomeDataGap | None = None
    notes: list[str] = Field(default_factory=list)

    @field_validator("first_premium_observation_ts_utc", "last_premium_observation_ts_utc")
    @classmethod
    def _validate_ts_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _utc_datetime(value)

    @model_validator(mode="after")
    def _validate_observation_window(self) -> PremiumOutcomeDataQuality:
        if (
            self.first_premium_observation_ts_utc is not None
            and self.last_premium_observation_ts_utc is not None
            and self.last_premium_observation_ts_utc < self.first_premium_observation_ts_utc
        ):
            raise ValueError(
                "last_premium_observation_ts_utc must not be before "
                "first_premium_observation_ts_utc"
            )
        return self


class PremiumOutcomeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome_id: str = Field(pattern=r"^[a-z0-9_:-]+$")
    source_signal_id: str
    decision_intent_signal_id: str | None = None
    source_contract_id: str | None = None
    decision_ts_utc: datetime
    first_eligible_entry_ts_utc: datetime | None = None
    selected_contract: SelectedOptionContract | None = None
    policy: PremiumOutcomePolicy
    cost_model: PremiumOutcomeCostModel
    evaluation_status: PremiumOutcomeStatus
    exit_reason: PremiumExitReason
    entry_fill: PremiumFill | None = None
    exit_fill: PremiumFill | None = None
    premium_metrics: PremiumOutcomeMetrics | None = None
    underlying_context: UnderlyingContext | None = None
    data_quality: PremiumOutcomeDataQuality
    no_lookahead_inputs: list[PremiumOutcomeNoLookaheadInputRef] = Field(min_length=1)

    @field_validator("decision_ts_utc", "first_eligible_entry_ts_utc")
    @classmethod
    def _validate_ts_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _utc_datetime(value)

    @model_validator(mode="after")
    def _validate_outcome_semantics(self) -> PremiumOutcomeRecord:
        self._validate_no_lookahead_inputs()
        self._validate_observation_timing()
        self._validate_status_evidence()
        return self

    def _validate_no_lookahead_inputs(self) -> None:
        if (
            self.selected_contract is not None
            and self.selected_contract.contract_selection_asof_utc > self.decision_ts_utc
        ):
            raise ValueError("contract selection must be at or before decision_ts_utc")
        if (
            self.policy.origin == "decision_declared"
            and self.policy.declared_at_utc > self.decision_ts_utc
        ):
            raise ValueError("decision-declared policy must be declared at or before decision_ts_utc")

        seen: set[str] = set()
        for input_ref in self.no_lookahead_inputs:
            if input_ref.id in seen:
                raise ValueError("no_lookahead_inputs ids must be unique per outcome")
            seen.add(input_ref.id)
            if input_ref.asof_ts_utc > self.decision_ts_utc:
                raise ValueError("no_lookahead_inputs.asof_ts_utc must not be after decision_ts_utc")

    def _validate_observation_timing(self) -> None:
        if (
            self.first_eligible_entry_ts_utc is not None
            and self.first_eligible_entry_ts_utc <= self.decision_ts_utc
        ):
            raise ValueError("first eligible entry timestamp must be after decision_ts_utc")
        if self.entry_fill is not None:
            if self.entry_fill.ts_utc <= self.decision_ts_utc:
                raise ValueError("entry fill timestamp must be after decision_ts_utc")
            if (
                self.first_eligible_entry_ts_utc is not None
                and self.entry_fill.ts_utc < self.first_eligible_entry_ts_utc
            ):
                raise ValueError("entry fill timestamp must not be before first eligible entry")
        if self.entry_fill is not None and self.exit_fill is not None:
            if self.exit_fill.ts_utc < self.entry_fill.ts_utc:
                raise ValueError("exit fill timestamp must not be before entry fill timestamp")

        for ts in (
            self.data_quality.first_premium_observation_ts_utc,
            self.data_quality.last_premium_observation_ts_utc,
        ):
            if ts is not None and ts <= self.decision_ts_utc:
                raise ValueError("premium outcome observations must be after decision_ts_utc")

    def _validate_status_evidence(self) -> None:
        source_type = self.data_quality.premium_price_source_type
        if source_type == "model_derived" and self.evaluation_status == "observed":
            raise ValueError("model-derived premium data cannot be an observed outcome")

        if self.evaluation_status == "observed":
            if self.source_contract_id is None or self.selected_contract is None:
                raise ValueError("observed outcome requires selected contract identifiers")
            if source_type != "observed":
                raise ValueError("observed outcome requires observed premium data")
            if not self.data_quality.required_premium_bars_available:
                raise ValueError("observed outcome requires required premium bars")
            if self.data_quality.ambiguity is not None or self.data_quality.data_gap is not None:
                raise ValueError("observed outcome cannot carry ambiguity or data gaps")
            if self.exit_reason not in {"premium_stop", "premium_target", "time_exit"}:
                raise ValueError("observed outcome requires stop, target, or time exit reason")
            if self.entry_fill is None or self.exit_fill is None or self.premium_metrics is None:
                raise ValueError("observed outcome requires entry fill, exit fill, and metrics")
        else:
            if self.exit_fill is not None or self.premium_metrics is not None:
                raise ValueError("non-observed outcome cannot carry exit fill or premium metrics")

        if self.evaluation_status == "ambiguous":
            if source_type != "observed" or not self.data_quality.required_premium_bars_available:
                raise ValueError("ambiguous outcome requires observed premium bars")
            if self.data_quality.ambiguity is None:
                raise ValueError("ambiguous outcome requires ambiguity evidence")
        if self.evaluation_status == "data_blocked":
            blocked = (
                not self.data_quality.required_premium_bars_available
                or self.data_quality.data_gap is not None
                or source_type == "unavailable"
            )
            if not blocked:
                raise ValueError("data_blocked outcome requires missing or unavailable data evidence")
            if self.selected_contract is None and self.data_quality.data_gap is None:
                raise ValueError("missing-contract data_blocked outcome requires data gap evidence")
        if self.evaluation_status == "not_evaluable":
            if self.exit_reason != "not_evaluable":
                raise ValueError("not_evaluable outcome requires not_evaluable exit_reason")
            if self.entry_fill is not None:
                raise ValueError("not_evaluable outcome cannot carry entry fill")


class PaFeitianPremiumOutcomeSidecar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["pa_feitian_premium_outcome_v1"] = (
        PA_FEITIAN_PREMIUM_OUTCOME_SCHEMA_VERSION
    )
    generated_at_utc: datetime
    source_commit: str = Field(min_length=7, max_length=40)
    provenance: PremiumOutcomeProvenance
    outcomes: list[PremiumOutcomeRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("generated_at_utc")
    @classmethod
    def _validate_generated_at_utc(cls, value: datetime) -> datetime:
        return _utc_datetime(value)

    @model_validator(mode="after")
    def _validate_unique_outcomes(self) -> PaFeitianPremiumOutcomeSidecar:
        seen: set[str] = set()
        for outcome in self.outcomes:
            if outcome.outcome_id in seen:
                raise ValueError("premium outcome_id values must be unique")
            policy_hash = self.provenance.policy_hashes.get(outcome.policy.provenance_hash_key)
            if policy_hash != outcome.policy.digest:
                raise ValueError("premium outcome policy digest must match provenance.policy_hashes")
            seen.add(outcome.outcome_id)
        return self


def validate_premium_outcome(data: dict[str, Any]) -> PaFeitianPremiumOutcomeSidecar:
    return PaFeitianPremiumOutcomeSidecar.model_validate(data)


def premium_outcome_to_jsonable(sidecar: PaFeitianPremiumOutcomeSidecar) -> dict[str, Any]:
    return sidecar.model_dump(mode="json", exclude_none=False)


def load_premium_outcome(path: str | Path) -> PaFeitianPremiumOutcomeSidecar:
    with Path(path).open(encoding="utf-8") as f:
        return validate_premium_outcome(json.load(f))


def write_premium_outcome(sidecar: PaFeitianPremiumOutcomeSidecar, path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(premium_outcome_to_jsonable(sidecar), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
