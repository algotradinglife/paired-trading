"""Artifact-only, pre-registered M6-C policy comparisons.

This module deliberately works only with already-written M6 evaluation datasets
and aggregates.  It does not import the scoring, market-data, option-selection,
or execution layers.  A missing or incompatible candidate is a reportable
blocked result, never a reason to reconstruct an input or infer an outcome.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import statistics
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .evaluation import (
    ComparisonOosWindow,
    EvaluationArtifactProvenance,
    EvaluationArtifactRef,
    EvaluationConfidenceInterval,
    EvaluationDatasetRow,
    FailureModeRecord,
    MultipleComparisonAccounting,
    PaFeitianEvaluationAggregateResult,
    PaFeitianEvaluationDataset,
    PaFeitianEvaluationFailureModeReport,
    PaFeitianEvaluationScreeningReport,
    PolicyComparisonEvidence,
    ScreeningCandidate,
)
from .manifest import sha256_file


POLICY_COMPARISON_CONFIG_SCHEMA_VERSION = "pa_feitian_m6_policy_comparison_config_v1"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class RegisteredPolicy(BaseModel):
    """An immutable policy identity named before its outcomes are compared."""

    model_config = ConfigDict(extra="forbid")

    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_sha256s: list[str] = Field(min_length=1)

    @field_validator("policy_sha256s")
    @classmethod
    def _digest_set(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("policy_sha256s must not contain duplicate digests")
        for digest in values:
            if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
                raise ValueError("policy_sha256s must use sha256:<hex> digests")
        return sorted(values)


class RegisteredCandidate(RegisteredPolicy):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(pattern=r"^[a-z0-9_:-]+$")
    dimensions: list[str] = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)


_VALID_DIMENSIONS = {"exit_policy", "iv_gate", "option_leg"}


class PolicyComparisonConfig(BaseModel):
    """The checked-in/pre-run candidate family and fixed screening discipline."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["pa_feitian_m6_policy_comparison_config_v1"] = (
        POLICY_COMPARISON_CONFIG_SCHEMA_VERSION
    )
    registration_id: str = Field(min_length=1)
    registered_at_utc: datetime
    baseline: RegisteredPolicy
    candidates: list[RegisteredCandidate] = Field(min_length=1)
    minimum_effective_events: int = Field(ge=1)
    minimum_comparable_oos_windows: int = Field(ge=2)
    alpha: float = Field(default=0.05, gt=0, lt=1)
    bootstrap_replicates: int = Field(default=1_000, ge=1)
    random_seed: int = 7
    notes: list[str] = Field(default_factory=list)

    @field_validator("registered_at_utc")
    @classmethod
    def _registered_at_utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @field_validator("candidates")
    @classmethod
    def _candidate_dimensions(cls, values: list[RegisteredCandidate]) -> list[RegisteredCandidate]:
        for candidate in values:
            invalid = set(candidate.dimensions) - _VALID_DIMENSIONS
            if invalid:
                raise ValueError(f"unsupported comparison dimensions: {sorted(invalid)}")
        return values

    @model_validator(mode="after")
    def _unique_candidates(self) -> PolicyComparisonConfig:
        ids = [candidate.candidate_id for candidate in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("registered candidate_id values must be unique")
        policy_identities = [
            (candidate.policy_id, candidate.policy_version, tuple(candidate.policy_sha256s))
            for candidate in self.candidates
        ]
        if len(policy_identities) != len(set(policy_identities)):
            raise ValueError("each registered candidate policy identity must be unique")
        return self

    def canonical_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json")


def canonical_config_sha256(config: PolicyComparisonConfig) -> str:
    encoded = json.dumps(config.canonical_payload(), sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def load_policy_comparison_config(path: str | Path) -> PolicyComparisonConfig:
    with Path(path).open(encoding="utf-8") as handle:
        return PolicyComparisonConfig.model_validate(json.load(handle))


class CandidateArtifacts(BaseModel):
    """Explicit paths make a missing candidate input observable to the caller."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    dataset_path: Path
    aggregate_path: Path
    dataset: PaFeitianEvaluationDataset
    aggregate: PaFeitianEvaluationAggregateResult


def _artifact_ref(kind: str, path: Path, schema_version: str) -> EvaluationArtifactRef:
    return EvaluationArtifactRef(kind=kind, path=str(path), sha256=sha256_file(path), schema_version=schema_version)


def _verify_dataset_aggregate(
    dataset: PaFeitianEvaluationDataset,
    dataset_path: Path,
    aggregate: PaFeitianEvaluationAggregateResult,
) -> None:
    dataset_hash = sha256_file(dataset_path)
    if aggregate.evaluation_dataset.sha256 != dataset_hash:
        raise ValueError("aggregate evaluation_dataset hash does not match explicit dataset")
    if aggregate.provenance.input_hashes.get("evaluation_dataset") != dataset_hash:
        raise ValueError("aggregate provenance does not bind explicit dataset")
    event_times: dict[str, datetime] = {}
    # Dataset construction should make event timestamps consistent. Recheck it here
    # because comparison inputs may be produced by another M6-compatible writer.
    for row in dataset.rows:
        prior = event_times.setdefault(row.event_id, row.decision_ts_utc)
        if prior != row.decision_ts_utc:
            raise ValueError(f"event {row.event_id} has multiple decision timestamps")
    known_events = set(event_times)
    tested: set[str] = set()
    for fold in aggregate.walk_forward_folds:
        if not fold.no_lookahead_verified:
            raise ValueError(f"{fold.fold_id}: aggregate did not verify no-lookahead")
        if not set(fold.train_event_ids).issubset(known_events) or not set(fold.test_event_ids).issubset(known_events):
            raise ValueError(f"{fold.fold_id}: aggregate fold contains an unknown event")
        if tested & set(fold.test_event_ids):
            raise ValueError(f"{fold.fold_id}: OOS event appears in more than one fold")
        tested.update(fold.test_event_ids)
        if any(event_times[event_id] > fold.test_end_utc for event_id in fold.test_event_ids):
            raise ValueError(f"{fold.fold_id}: OOS event is after its declared test window")


def _policy_identity(dataset: PaFeitianEvaluationDataset) -> tuple[str, str, frozenset[str]]:
    policy_ids = {row.policy_id for row in dataset.rows}
    policy_versions = {row.policy_version for row in dataset.rows}
    if len(policy_ids) != 1 or len(policy_versions) != 1:
        raise ValueError("comparison datasets must contain exactly one policy_id and policy_version")
    return policy_ids.pop(), policy_versions.pop(), frozenset(row.policy_sha256 for row in dataset.rows)


def _event_values(rows: list[EvaluationDatasetRow]) -> dict[str, float]:
    values: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row.evaluation_status == "observed" and row.premium_r is not None:
            values[row.event_id].append(row.premium_r)
    return {event_id: statistics.fmean(per_leg) for event_id, per_leg in values.items()}


def _decision_input_projection(
    rows: list[EvaluationDatasetRow],
) -> list[tuple[str, datetime, str, str, str, str, str, tuple[str, ...]]]:
    """Normalize the decision-time event/leg evidence shared by both policies."""

    return sorted(
        (
            row.event_id,
            row.decision_ts_utc,
            row.source_signal_id,
            row.source_contract_id or "",
            row.option_type,
            row.contract_family,
            row.moneyness_bucket,
            tuple(sorted(set(row.input_refs))),
        )
        for row in rows
    )


def _quantile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    pos = (len(ordered) - 1) * quantile
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def _difference_ci(
    differences: dict[str, float], *, config: PolicyComparisonConfig
) -> EvaluationConfidenceInterval | None:
    if not differences:
        return None
    values = [differences[event_id] for event_id in sorted(differences)]
    seed = config.random_seed + int(hashlib.sha256(config.registration_id.encode()).hexdigest()[:8], 16)
    generator = random.Random(seed)
    estimates = [
        statistics.fmean(values[generator.randrange(len(values))] for _ in values)
        for _ in range(config.bootstrap_replicates)
    ]
    adjusted_level = 1 - config.alpha / len(config.candidates)
    tail = (1 - adjusted_level) / 2
    return EvaluationConfidenceInterval(
        confidence_level=adjusted_level,
        lower=_quantile(estimates, tail),
        upper=_quantile(estimates, 1 - tail),
        method="seeded_event_paired_bootstrap_bonferroni_v1",
        cluster_unit="event",
    )


def _comparison_error(
    baseline: CandidateArtifacts,
    candidate: CandidateArtifacts,
    config: PolicyComparisonConfig,
) -> str | None:
    _verify_dataset_aggregate(baseline.dataset, baseline.dataset_path, baseline.aggregate)
    _verify_dataset_aggregate(candidate.dataset, candidate.dataset_path, candidate.aggregate)
    if baseline.dataset.time_boundary != candidate.dataset.time_boundary:
        return "candidate time boundary/split provenance differs from baseline"
    if baseline.dataset.provenance.data_access_status != candidate.dataset.provenance.data_access_status:
        return "candidate data-access provenance differs from baseline"
    baseline_intent_hash = baseline.dataset.provenance.input_hashes.get(
        "decision_intent_artifact"
    )
    candidate_intent_hash = candidate.dataset.provenance.input_hashes.get(
        "decision_intent_artifact"
    )
    if baseline_intent_hash is None or candidate_intent_hash is None:
        return "comparison inputs lack a decision_intent_artifact hash"
    if baseline_intent_hash != candidate_intent_hash:
        return "candidate decision-intent artifact hash differs from baseline"
    baseline_events = {row.event_id: row.decision_ts_utc for row in baseline.dataset.rows}
    candidate_events = {row.event_id: row.decision_ts_utc for row in candidate.dataset.rows}
    if baseline_events != candidate_events:
        return "candidate event set or decision timestamps differ from baseline"
    if _decision_input_projection(baseline.dataset.rows) != _decision_input_projection(
        candidate.dataset.rows
    ):
        return "candidate decision-time event/leg/input-ref mapping differs from baseline"
    if set(_event_values(baseline.dataset.rows)) != set(_event_values(candidate.dataset.rows)):
        return (
            "candidate observed event-id set differs from baseline; "
            "paired comparison would select outcomes"
        )
    baseline_folds = {fold.fold_id: fold for fold in baseline.aggregate.walk_forward_folds}
    candidate_folds = {fold.fold_id: fold for fold in candidate.aggregate.walk_forward_folds}
    if set(baseline_folds) != set(candidate_folds):
        return "candidate OOS fold identifiers differ from baseline"
    for fold_id in sorted(baseline_folds):
        left, right = baseline_folds[fold_id], candidate_folds[fold_id]
        if (
            left.test_start_utc != right.test_start_utc
            or left.test_end_utc != right.test_end_utc
            or set(left.test_event_ids) != set(right.test_event_ids)
        ):
            return f"{fold_id}: candidate OOS event window differs from baseline"
    if config.registered_at_utc > baseline.dataset.time_boundary.decision_start_utc:
        return "candidate configuration was registered after the evaluation decision window began"
    return None


def _report_provenance(
    *,
    role: str,
    baseline: CandidateArtifacts,
    config: PolicyComparisonConfig,
    config_path: Path,
    cli_args: list[str],
    candidate: CandidateArtifacts | None = None,
) -> EvaluationArtifactProvenance:
    base = baseline.dataset.provenance
    config_hash = canonical_config_sha256(config)
    report_dataset = candidate if candidate is not None else baseline
    hashes = {
        **base.input_hashes,
        "evaluation_dataset": sha256_file(report_dataset.dataset_path),
        "aggregate_result": sha256_file(baseline.aggregate_path),
        "policy_config": config_hash,
        "policy_comparison_config": config_hash,
        "policy_comparison_config_file": sha256_file(config_path),
    }
    if candidate is not None:
        hashes["candidate_evaluation_dataset"] = sha256_file(candidate.dataset_path)
        hashes["candidate_aggregate_result"] = sha256_file(candidate.aggregate_path)
    payload = base.model_dump()
    payload.update(
        {
            "role": role,
            "producer": "engine.pa_feitian.policy_comparison.v1",
            "cli_args": cli_args,
            "policy_config_sha256": config_hash,
            "random_seed": config.random_seed,
            "input_hashes": hashes,
            "notes": [
                "M6-C consumed explicit baseline/candidate M6 artifacts only",
                "no score_today rerun, market scan, contract reselection, live trading, or execution occurred",
            ],
        }
    )
    return EvaluationArtifactProvenance.model_validate(payload)


def _failure_records(rows: list[EvaluationDatasetRow], candidate_id: str) -> list[FailureModeRecord]:
    groups: list[tuple[str, str, str, str, list[EvaluationDatasetRow], str]] = []
    for status, severity in (("data_blocked", "blocking"), ("ambiguous", "warning"), ("not_evaluable", "warning")):
        groups.append((f"{candidate_id}:status:{status}", "data_quality", status, severity, [r for r in rows if r.evaluation_status == status], "outcome status retained; not imputed"))
    for exit_reason in ("premium_stop", "time_exit", "data_gap"):
        groups.append((f"{candidate_id}:exit:{exit_reason}", "exit_reason", exit_reason, "warning", [r for r in rows if r.exit_reason == exit_reason], "exit outcome is retained for reviewer drill-down"))
    for gate in ("unknown", "not_evaluable", "fail"):
        groups.append((f"{candidate_id}:iv:{gate}", "iv_gate", f"IV gate {gate}", "warning", [r for r in rows if r.iv_gate_status == gate], "IV status is not treated as pass"))
    groups.append((f"{candidate_id}:leg:unknown", "option_leg", "unknown option-leg dimension", "warning", [r for r in rows if r.option_type == "unknown" or r.moneyness_bucket == "unknown"], "missing leg labels are retained"))
    groups.append((f"{candidate_id}:premium_underlying:positive_underlying_negative_premium", "premium_underlying_divergence", "positive underlying R with negative premium R", "warning", [r for r in rows if r.premium_r is not None and r.underlying_r is not None and r.premium_r < 0 < r.underlying_r], "underlying R is retained only as a diagnostic"))
    groups.append((f"{candidate_id}:premium_underlying:negative_underlying_positive_premium", "premium_underlying_divergence", "negative underlying R with positive premium R", "warning", [r for r in rows if r.premium_r is not None and r.underlying_r is not None and r.underlying_r < 0 < r.premium_r], "underlying R is retained only as a diagnostic"))
    for state in sorted({row.decision_state for row in rows if row.decision_state != "trade_ready"}):
        groups.append((f"{candidate_id}:decision_state:{state}", "decision_trace", f"decision state {state}", "info", [row for row in rows if row.decision_state == state], "decision-state cohort retained for trace review"))
    for trace_node in sorted({node for row in rows for node in row.decision_trace_node_ids}):
        affected = [row for row in rows if trace_node in row.decision_trace_node_ids and row.premium_r is not None and row.premium_r <= 0]
        groups.append((f"{candidate_id}:trace:{trace_node}", "decision_trace", f"non-positive premium R at trace node {trace_node}", "warning", affected, "trace-node cohort is descriptive and not a post-hoc gate"))
    observed = [row for row in rows if row.evaluation_status == "observed" and row.premium_r is not None]
    for dimension, label, key in (("pool", "pool", lambda row: row.pool), ("contract_family", "contract family", lambda row: row.contract_family), ("time", "time window", lambda row: row.decision_ts_utc.strftime("%Y-%m"))):
        buckets: dict[str, list[EvaluationDatasetRow]] = defaultdict(list)
        for row in observed:
            buckets[key(row)].append(row)
        means = {value: statistics.fmean(row.premium_r for row in bucket if row.premium_r is not None) for value, bucket in buckets.items()}
        if any(value > 0 for value in means.values()) and any(value < 0 for value in means.values()):
            groups.append((f"{candidate_id}:instability:{dimension}", "policy_instability", f"policy direction changes across {label}", "warning", observed, "mixed-sign observed premium-R group means; no subgroup was selected for promotion"))
    output: list[FailureModeRecord] = []
    for failure_id, category, label, severity, affected, note in groups:
        if not affected:
            continue
        output.append(FailureModeRecord(
            failure_mode_id=failure_id,
            category=category,  # type: ignore[arg-type]
            label=label,
            affected_row_count=len(affected),
            outcome_ids=sorted({row.outcome_id for row in affected}),
            source_signal_ids=sorted({row.source_signal_id for row in affected}),
            input_refs=sorted({ref for row in affected for ref in row.input_refs}),
            severity=severity,  # type: ignore[arg-type]
            notes=[note],
        ))
    return output


def _blocked_evidence(
    baseline: CandidateArtifacts, candidate: CandidateArtifacts | None, reason: str
) -> PolicyComparisonEvidence:
    return PolicyComparisonEvidence(
        comparability_status="blocked",
        baseline_dataset_sha256=sha256_file(baseline.dataset_path),
        candidate_dataset_sha256=sha256_file(candidate.dataset_path) if candidate else None,
        baseline_aggregate_sha256=sha256_file(baseline.aggregate_path),
        candidate_aggregate_sha256=sha256_file(candidate.aggregate_path) if candidate else None,
        paired_effective_event_count=0,
        limitations=[reason],
    )


def build_policy_comparison_reports(
    *,
    baseline: CandidateArtifacts,
    candidates: dict[str, CandidateArtifacts],
    config: PolicyComparisonConfig,
    config_path: str | Path,
    generated_at_utc: datetime,
    cli_args: list[str],
) -> tuple[PaFeitianEvaluationScreeningReport, dict[str, PaFeitianEvaluationFailureModeReport]]:
    """Build one screening report and one typed failure report per registered candidate."""

    config_path = Path(config_path)
    generated_at_utc = _utc(generated_at_utc)
    extra = set(candidates) - {candidate.candidate_id for candidate in config.candidates}
    if extra:
        raise ValueError(f"candidate inputs are not pre-registered: {sorted(extra)}")
    _verify_dataset_aggregate(baseline.dataset, baseline.dataset_path, baseline.aggregate)
    baseline_identity = _policy_identity(baseline.dataset)
    expected_baseline = (
        config.baseline.policy_id,
        config.baseline.policy_version,
        frozenset(config.baseline.policy_sha256s),
    )
    if baseline_identity != expected_baseline:
        raise ValueError("explicit baseline dataset policy does not match pre-registered baseline")
    screening_candidates: list[ScreeningCandidate] = []
    failures: dict[str, PaFeitianEvaluationFailureModeReport] = {}
    tested = 0
    for registered in config.candidates:
        candidate = candidates.get(registered.candidate_id)
        limitation: str | None = None
        if candidate is None:
            evidence = _blocked_evidence(baseline, None, "no explicit candidate dataset+aggregate input was supplied")
            classification = "blocked"
            basis = ["blocked: registered candidate has no explicit comparable artifact input"]
            report_rows = baseline.dataset.rows
        else:
            candidate_identity = _policy_identity(candidate.dataset)
            expected = (
                registered.policy_id,
                registered.policy_version,
                frozenset(registered.policy_sha256s),
            )
            if candidate_identity != expected:
                limitation = "candidate policy identity does not match its pre-registered configuration"
            else:
                try:
                    limitation = _comparison_error(baseline, candidate, config)
                except ValueError as exc:
                    limitation = f"candidate artifact validation failed: {exc}"
            if limitation:
                evidence = _blocked_evidence(baseline, candidate, limitation)
                classification, basis = "blocked", [f"blocked: {limitation}"]
            else:
                baseline_values = _event_values(baseline.dataset.rows)
                candidate_values = _event_values(candidate.dataset.rows)
                paired_ids = sorted(set(baseline_values) & set(candidate_values))
                differences = {event_id: candidate_values[event_id] - baseline_values[event_id] for event_id in paired_ids}
                oos: list[ComparisonOosWindow] = []
                for fold in baseline.aggregate.walk_forward_folds:
                    fold_diffs = [differences[event_id] for event_id in fold.test_event_ids if event_id in differences]
                    status = "generated" if fold_diffs else "insufficient_sample"
                    oos.append(ComparisonOosWindow(fold_id=fold.fold_id, effective_event_count=len(fold_diffs), mean_premium_r_difference=statistics.fmean(fold_diffs) if fold_diffs else None, result_status=status, notes=["paired observed events only; dependent legs were averaged within event"]))
                comparable_oos = [window for window in oos if window.effective_event_count]
                enough = len(paired_ids) >= config.minimum_effective_events and len(comparable_oos) >= config.minimum_comparable_oos_windows
                status = "comparable" if enough else "insufficient_sample"
                ci = _difference_ci(differences, config=config)
                evidence = PolicyComparisonEvidence(
                    comparability_status=status,
                    baseline_dataset_sha256=sha256_file(baseline.dataset_path),
                    candidate_dataset_sha256=sha256_file(candidate.dataset_path),
                    baseline_aggregate_sha256=sha256_file(baseline.aggregate_path),
                    candidate_aggregate_sha256=sha256_file(candidate.aggregate_path),
                    paired_effective_event_count=len(paired_ids),
                    baseline_mean_premium_r=statistics.fmean(baseline_values[event_id] for event_id in paired_ids) if paired_ids else None,
                    candidate_mean_premium_r=statistics.fmean(candidate_values[event_id] for event_id in paired_ids) if paired_ids else None,
                    mean_premium_r_difference=statistics.fmean(differences.values()) if differences else None,
                    median_premium_r_difference=statistics.median(differences.values()) if differences else None,
                    adjusted_bootstrap_ci=ci,
                    comparable_oos_windows=oos,
                    limitations=[] if enough else ["insufficient paired event-level/OOS evidence; no promotion inference"],
                )
                tested += 1
                if not enough:
                    classification, basis = "inconclusive", ["inconclusive: pre-registered effective-event or OOS-window minimum not met"]
                elif ci is not None and ci.lower is not None and ci.lower > 0:
                    classification, basis = "promising", ["paired premium-R difference has positive Bonferroni-adjusted bootstrap lower bound; reviewer approval remains required"]
                elif ci is not None and ci.upper is not None and ci.upper < 0:
                    classification, basis = "negative", ["paired premium-R difference has negative Bonferroni-adjusted bootstrap upper bound"]
                else:
                    classification, basis = "inconclusive", ["paired Bonferroni-adjusted confidence interval crosses zero"]
            report_rows = candidate.dataset.rows
        screening_candidates.append(ScreeningCandidate(
            candidate_id=registered.candidate_id,
            policy_id=registered.policy_id,
            policy_version=registered.policy_version,
            classification=classification,  # type: ignore[arg-type]
            classification_basis=basis,
            comparable_oos_window_count=len(evidence.comparable_oos_windows),
            effective_event_count=evidence.paired_effective_event_count,
            baseline_policy_id=config.baseline.policy_id,
            limitations=evidence.limitations,
            comparison=evidence,
        ))
        failure_records = _failure_records(report_rows, registered.candidate_id)
        if classification == "blocked":
            failure_records.insert(0, FailureModeRecord(failure_mode_id=f"{registered.candidate_id}:comparison_blocked", category="policy_instability", label="controlled comparison blocked", affected_row_count=0, severity="blocking", notes=evidence.limitations))
        report_dataset = candidate if candidate is not None else baseline
        failures[registered.candidate_id] = PaFeitianEvaluationFailureModeReport(
            generated_at_utc=generated_at_utc,
            provenance=_report_provenance(role="m6_failure_mode_report", baseline=baseline, candidate=candidate, config=config, config_path=config_path, cli_args=cli_args),
            evaluation_dataset=_artifact_ref("evaluation_dataset", report_dataset.dataset_path, report_dataset.dataset.schema_version),
            failure_modes=failure_records,
            warnings=["failure modes are descriptive artifact evidence, not execution instructions"],
        )
    accounting = MultipleComparisonAccounting(configuration_sha256=canonical_config_sha256(config), method="bonferroni", family_size=len(config.candidates), alpha=config.alpha, adjusted_confidence_level=1 - config.alpha / len(config.candidates), tested_candidate_count=tested, unavailable_candidate_count=len(config.candidates) - tested)
    screening = PaFeitianEvaluationScreeningReport(
        generated_at_utc=generated_at_utc,
        provenance=_report_provenance(role="m6_screening_report", baseline=baseline, config=config, config_path=config_path, cli_args=cli_args),
        evaluation_dataset=_artifact_ref("evaluation_dataset", baseline.dataset_path, baseline.dataset.schema_version),
        aggregate_result=_artifact_ref("evaluation_aggregate_result", baseline.aggregate_path, baseline.aggregate.schema_version),
        candidates=screening_candidates,
        multiple_comparison=accounting,
        warnings=["M6-C comparison is an audit shortlist only; no candidate is approved for execution"],
    )
    return screening, failures
