"""Deterministic, artifact-only M6-B baseline evaluation.

This module consumes the M5 sidecar exactly as written.  It neither imports
the scoring pipeline nor touches an option store, so evaluation cannot cause a
market scan, contract reselection, execution, or a ``score_today`` rerun.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .contract import PaFeitianDecisionIntentSidecar
from .evaluation import (
    EvaluationAggregateGroup,
    EvaluationArtifactProvenance,
    EvaluationArtifactRef,
    EvaluationConfidenceInterval,
    EvaluationDatasetRow,
    EvaluationRStatistics,
    EvaluationStatusCounts,
    EvaluationTimeBoundary,
    EvaluationWalkForwardFold,
    PaFeitianEvaluationAggregateResult,
    PaFeitianEvaluationDataset,
)
from .manifest import PaFeitianRunManifest, sha256_file
from .premium_outcome import PaFeitianPremiumOutcomeSidecar


@dataclass(frozen=True)
class BaselineEvaluationConfig:
    """Predeclared statistics and chronological split settings for M6-B."""

    random_seed: int = 7
    bootstrap_replicates: int = 1_000
    lower_quantile: float = 0.05
    minimum_effective_samples: int = 3
    folds: int = 2
    minimum_train_events: int = 1
    timezone: str = "UTC"
    trading_calendar: str = "unknown"

    def __post_init__(self) -> None:
        if self.bootstrap_replicates < 1:
            raise ValueError("bootstrap_replicates must be at least one")
        if not 0 < self.lower_quantile < 1:
            raise ValueError("lower_quantile must be between zero and one")
        if self.minimum_effective_samples < 1 or self.minimum_train_events < 1:
            raise ValueError("minimum sample and train event counts must be positive")
        if self.folds < 1:
            raise ValueError("folds must be at least one")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc

    def canonical_payload(self) -> dict[str, object]:
        return {
            "baseline": "m5_premium_outcome_fixed_policy_only",
            "bootstrap_replicates": self.bootstrap_replicates,
            "cluster_unit": "event",
            "folds": self.folds,
            "lower_quantile": self.lower_quantile,
            "minimum_effective_samples": self.minimum_effective_samples,
            "minimum_train_events": self.minimum_train_events,
            "random_seed": self.random_seed,
            "split_method": "fixed_time_series_walk_forward_event_grouped",
            "timezone": self.timezone,
            "trading_calendar": self.trading_calendar,
        }


def canonical_config_sha256(config: BaselineEvaluationConfig) -> str:
    encoded = json.dumps(config.canonical_payload(), sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def verify_artifact_links(
    *,
    manifest: PaFeitianRunManifest,
    manifest_path: str | Path,
    premium_outcome: PaFeitianPremiumOutcomeSidecar,
    premium_outcome_path: str | Path,
    decision_intent: PaFeitianDecisionIntentSidecar,
    decision_intent_path: str | Path,
) -> None:
    """Reject inputs whose typed manifest links or hashes do not match the files."""

    if manifest.premium_outcome_artifact is None or manifest.decision_intent_artifact is None:
        raise ValueError("M6-B requires manifest premium_outcome_artifact and decision_intent_artifact")
    if manifest.premium_outcome_artifact.schema_version != premium_outcome.schema_version:
        raise ValueError("manifest premium outcome schema version does not match explicit sidecar")
    if manifest.decision_intent_artifact.schema_version != decision_intent.schema_version:
        raise ValueError("manifest decision intent schema version does not match explicit sidecar")
    if manifest.premium_outcome_artifact.sha256 != sha256_file(premium_outcome_path):
        raise ValueError("manifest premium outcome hash does not match explicit sidecar")
    if manifest.decision_intent_artifact.sha256 != sha256_file(decision_intent_path):
        raise ValueError("manifest decision intent hash does not match explicit sidecar")
    if premium_outcome.provenance.decision_intent_artifact_sha256 != sha256_file(
        decision_intent_path
    ):
        raise ValueError("M5 premium outcome provenance does not bind the explicit decision intent")
    if premium_outcome.provenance.decision_intent_artifact_path is None:
        raise ValueError("M5 premium outcome must name its decision intent sidecar")
    if not Path(manifest_path).is_file():
        raise ValueError("explicit manifest path does not exist")


def verify_no_lookahead(
    outcomes: PaFeitianPremiumOutcomeSidecar,
    intents: PaFeitianDecisionIntentSidecar,
) -> None:
    """Verify decision-side evidence and M5 inputs precede every decision.

    Outcomes remain posterior measurements and are never copied into decision
    inputs.  Multiple M5 records from one signal deliberately share an event,
    which the fold builder keeps intact.
    """

    intent_by_signal = {intent.signal_id: intent for intent in intents.intents}
    for outcome in outcomes.outcomes:
        if outcome.decision_intent_signal_id != outcome.source_signal_id:
            raise ValueError(f"{outcome.outcome_id}: decision intent link is not the source signal")
        intent = intent_by_signal.get(outcome.source_signal_id)
        if intent is None:
            raise ValueError(f"{outcome.outcome_id}: no matching decision intent signal")
        if intent.decision_ts_utc != outcome.decision_ts_utc:
            raise ValueError(f"{outcome.outcome_id}: decision timestamp differs from decision intent")
        for ref in intent.no_lookahead_inputs:
            if ref.asof_ts_utc > outcome.decision_ts_utc:
                raise ValueError(f"{outcome.outcome_id}: future decision-intent input {ref.id}")
        for ref in outcome.no_lookahead_inputs:
            if ref.asof_ts_utc > outcome.decision_ts_utc:
                raise ValueError(f"{outcome.outcome_id}: future M5 input {ref.id}")
        if outcome.selected_contract is not None and (
            outcome.selected_contract.contract_selection_asof_utc > outcome.decision_ts_utc
        ):
            raise ValueError(f"{outcome.outcome_id}: contract selection is after decision")


def _provenance(
    *,
    role: str,
    manifest: PaFeitianRunManifest,
    manifest_path: str | Path,
    premium_path: str | Path,
    decision_path: str | Path,
    config: BaselineEvaluationConfig,
    generated_args: list[str],
) -> EvaluationArtifactProvenance:
    policy_hash = canonical_config_sha256(config)
    manifest_hash = sha256_file(manifest_path)
    premium_hash = sha256_file(premium_path)
    return EvaluationArtifactProvenance(
        role=role,
        source_manifest_path=str(manifest_path),
        source_manifest_sha256=manifest_hash,
        source_manifest_schema_version=manifest.schema_version,
        premium_outcome_artifact_path=str(premium_path),
        premium_outcome_artifact_sha256=premium_hash,
        premium_outcome_schema_version="pa_feitian_premium_outcome_v1",
        source_commit=manifest.source_commit,
        producer="engine.pa_feitian.baseline_evaluator.v1",
        cli_args=generated_args,
        policy_config_sha256=policy_hash,
        data_access_status=manifest.data_access.status,
        fixture_fallback=manifest.data_access.status == "fixture_fallback",
        random_seed=config.random_seed,
        input_hashes={
            "source_manifest": manifest_hash,
            "premium_outcome_artifact": premium_hash,
            "decision_intent_artifact": sha256_file(decision_path),
            "policy_config": policy_hash,
        },
        output_hashes={},
        notes=[
            "M6-B consumed explicit M5 manifest, premium-outcome, and decision-intent artifacts only",
            "no score_today rerun, market scan, contract reselection, live trading, or execution occurred",
        ],
    )


def build_evaluation_dataset(
    *,
    manifest: PaFeitianRunManifest,
    manifest_path: str | Path,
    premium_outcome: PaFeitianPremiumOutcomeSidecar,
    premium_outcome_path: str | Path,
    decision_intent: PaFeitianDecisionIntentSidecar,
    decision_intent_path: str | Path,
    config: BaselineEvaluationConfig,
    generated_at_utc: datetime,
    cli_args: list[str],
) -> PaFeitianEvaluationDataset:
    verify_artifact_links(
        manifest=manifest,
        manifest_path=manifest_path,
        premium_outcome=premium_outcome,
        premium_outcome_path=premium_outcome_path,
        decision_intent=decision_intent,
        decision_intent_path=decision_intent_path,
    )
    verify_no_lookahead(premium_outcome, decision_intent)
    intents = {intent.signal_id: intent for intent in decision_intent.intents}
    pool = manifest.run_config.get("pool")
    pool_label = str(pool) if isinstance(pool, str) else "unknown"
    rows: list[EvaluationDatasetRow] = []
    for outcome in sorted(premium_outcome.outcomes, key=lambda item: item.outcome_id):
        intent = intents[outcome.source_signal_id]
        selected = outcome.selected_contract
        option_type = selected.option_type if selected is not None else "unknown"
        underlying = (
            f"{selected.exchange}.{selected.product}" if selected is not None else intent.instrument
        )
        family = (
            f"{selected.product}_monthly_{selected.option_type}" if selected is not None else "unknown"
        )
        metrics = outcome.premium_metrics
        refs = sorted(
            {ref.id for ref in intent.no_lookahead_inputs}
            | {ref.id for ref in outcome.no_lookahead_inputs}
        )
        rows.append(
            EvaluationDatasetRow(
                row_id=f"m6:{outcome.outcome_id}",
                event_id=f"event:{outcome.source_signal_id}",
                outcome_id=outcome.outcome_id,
                source_signal_id=outcome.source_signal_id,
                source_contract_id=outcome.source_contract_id,
                decision_ts_utc=outcome.decision_ts_utc,
                pool=pool_label,
                underlying=underlying,
                decision_state=intent.decision_state,
                decision_trace_node_ids=[],
                iv_gate_status="unknown",
                option_type=option_type,
                contract_family=family,
                moneyness_bucket="unknown",
                policy_id=outcome.policy.policy_id,
                policy_version=outcome.policy.policy_version,
                policy_sha256=outcome.policy.digest,
                evaluation_status=outcome.evaluation_status,
                exit_reason=outcome.exit_reason,
                premium_r=metrics.premium_r if metrics is not None else None,
                underlying_r=(
                    outcome.underlying_context.underlying_r
                    if outcome.underlying_context is not None
                    else None
                ),
                premium_mfe=metrics.premium_mfe if metrics is not None else None,
                premium_mae=metrics.premium_mae if metrics is not None else None,
                input_refs=refs,
            )
        )
    if not rows:
        raise ValueError("M5 premium outcome sidecar contains no outcomes")
    timestamps = [row.decision_ts_utc for row in rows]
    return PaFeitianEvaluationDataset(
        generated_at_utc=generated_at_utc.astimezone(UTC),
        provenance=_provenance(
            role="m6_evaluation_dataset",
            manifest=manifest,
            manifest_path=manifest_path,
            premium_path=premium_outcome_path,
            decision_path=decision_intent_path,
            config=config,
            generated_args=cli_args,
        ),
        time_boundary=EvaluationTimeBoundary(
            timezone=config.timezone,
            trading_calendar=config.trading_calendar,
            decision_start_utc=min(timestamps),
            decision_end_utc=max(timestamps),
            split_method="walk_forward",
            folds_declared=config.folds,
        ),
        rows=rows,
        filter_reason_counts={},
        warnings=[
            "IV gate and decision-trace nodes are unknown because the explicit M5 inputs do not carry M6 labels",
            "non-observed M5 statuses are retained and excluded from premium-R statistics",
        ],
    )


def _quantile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _bootstrap_ci(rows: list[EvaluationDatasetRow], config: BaselineEvaluationConfig, salt: str):
    by_event: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row.evaluation_status == "observed" and row.premium_r is not None:
            by_event[row.event_id].append(row.premium_r)
    event_values = [by_event[event_id] for event_id in sorted(by_event)]
    if not event_values:
        return None
    seed = config.random_seed + int(hashlib.sha256(salt.encode()).hexdigest()[:8], 16)
    generator = random.Random(seed)
    estimates: list[float] = []
    for _ in range(config.bootstrap_replicates):
        sampled = [event_values[generator.randrange(len(event_values))] for _ in event_values]
        flat = [value for event in sampled for value in event]
        estimates.append(statistics.fmean(flat))
    return EvaluationConfidenceInterval(
        confidence_level=0.95,
        lower=_quantile(estimates, 0.025),
        upper=_quantile(estimates, 0.975),
        method="seeded_cluster_bootstrap_mean_v1",
        cluster_unit="event",
    )


def _correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2:
        return None
    left_delta = [value - statistics.fmean(left) for value in left]
    right_delta = [value - statistics.fmean(right) for value in right]
    denominator = math.sqrt(sum(value * value for value in left_delta) * sum(value * value for value in right_delta))
    return None if denominator == 0 else sum(a * b for a, b in zip(left_delta, right_delta)) / denominator


def _group(
    *, dimension: str,
    value: str,
    rows: list[EvaluationDatasetRow],
    config: BaselineEvaluationConfig,
) -> EvaluationAggregateGroup:
    counts = Counter(row.evaluation_status for row in rows)
    status_counts = EvaluationStatusCounts(
        observed=counts["observed"],
        ambiguous=counts["ambiguous"],
        data_blocked=counts["data_blocked"],
        not_evaluable=counts["not_evaluable"],
    )
    observed = [
        row for row in rows if row.evaluation_status == "observed" and row.premium_r is not None
    ]
    premium_values = [row.premium_r for row in observed if row.premium_r is not None]
    effective_event_count = len({row.event_id for row in observed})
    if not premium_values:
        result_status = "data_blocked" if status_counts.data_blocked else "not_evaluable"
        stats = None
    else:
        result_status = (
            "generated"
            if effective_event_count >= config.minimum_effective_samples
            else "insufficient_sample"
        )
        median = statistics.median(premium_values)
        stats = EvaluationRStatistics(
            mean=statistics.fmean(premium_values),
            median=median,
            standard_deviation=statistics.stdev(premium_values) if len(premium_values) > 1 else 0.0,
            median_absolute_deviation=statistics.median([abs(value - median) for value in premium_values]),
            lower_quantile=_quantile(premium_values, config.lower_quantile),
            worst_case=min(premium_values),
            win_rate=sum(value > 0 for value in premium_values) / len(premium_values),
            bootstrap_95_ci=_bootstrap_ci(rows, config, f"{dimension}:{value}"),
        )
    paired = [row for row in observed if row.underlying_r is not None]
    return EvaluationAggregateGroup(
        group_id="pooled" if dimension == "pooled" else f"{dimension}:{value}",
        dimension=dimension,  # type: ignore[arg-type]
        value=value,
        result_status=result_status,
        sample_count=len(rows),
        effective_sample_count=effective_event_count,
        status_counts=status_counts,
        premium_r=stats,
        underlying_r_correlation=_correlation(
            [row.premium_r for row in paired if row.premium_r is not None],
            [row.underlying_r for row in paired if row.underlying_r is not None],
        ),
        underlying_r_difference_mean=(
            statistics.fmean(row.premium_r - row.underlying_r for row in paired if row.premium_r is not None and row.underlying_r is not None)
            if paired
            else None
        ),
        notes=[
            "premium-R metrics retain observed rows; effective samples and thresholds count distinct event_id values",
            "bootstrap confidence intervals cluster dependent rows by event_id",
            *(
                []
                if result_status == "generated"
                else ["insufficient or non-evaluable evidence is retained, not imputed"]
            ),
        ],
    )


def build_walk_forward_folds(
    rows: Iterable[EvaluationDatasetRow], config: BaselineEvaluationConfig
) -> list[EvaluationWalkForwardFold]:
    row_list = list(rows)
    events: dict[str, list[EvaluationDatasetRow]] = defaultdict(list)
    for row in row_list:
        events[row.event_id].append(row)
    events_by_time: dict[datetime, list[str]] = defaultdict(list)
    for event_id, event_rows in events.items():
        timestamps = {row.decision_ts_utc for row in event_rows}
        if len(timestamps) != 1:
            raise ValueError(f"event {event_id} has multiple decision timestamps")
        events_by_time[timestamps.pop()].append(event_id)
    time_groups = [(timestamp, sorted(event_ids)) for timestamp, event_ids in sorted(events_by_time.items())]
    train_group_count = 0
    train_event_count = 0
    while train_group_count < len(time_groups) and train_event_count < config.minimum_train_events:
        train_event_count += len(time_groups[train_group_count][1])
        train_group_count += 1
    remaining_groups = time_groups[train_group_count:]
    if len(remaining_groups) < config.folds:
        raise ValueError("not enough chronological event groups for requested fixed walk-forward folds")
    test_chunks = [
        remaining_groups[index * len(remaining_groups) // config.folds : (index + 1)
        * len(remaining_groups)
        // config.folds]
        for index in range(config.folds)
    ]
    folds: list[EvaluationWalkForwardFold] = []
    previous = list(time_groups[:train_group_count])
    for index, test in enumerate(test_chunks, start=1):
        test_event_ids = [event_id for _, event_ids in test for event_id in event_ids]
        train_event_ids = [event_id for _, event_ids in previous for event_id in event_ids]
        train_rows = [row for row in row_list if row.event_id in train_event_ids]
        test_rows = [row for row in row_list if row.event_id in test_event_ids]
        fold_id = f"wf_{index}"
        train_result = _group(
            dimension="pooled", value=f"{fold_id}:train", rows=train_rows, config=config
        ).model_copy(update={"group_id": f"fold:{fold_id}:train"})
        test_result = _group(
            dimension="pooled", value=f"{fold_id}:test", rows=test_rows, config=config
        ).model_copy(update={"group_id": f"fold:{fold_id}:test"})
        folds.append(
            EvaluationWalkForwardFold(
                fold_id=fold_id,
                train_start_utc=previous[0][0],
                train_end_utc=previous[-1][0],
                test_start_utc=test[0][0],
                test_end_utc=test[-1][0],
                train_event_ids=train_event_ids,
                test_event_ids=test_event_ids,
                train_result=train_result,
                test_result=test_result,
                no_lookahead_verified=True,
                notes=["event IDs are assigned wholly to one chronological side of the fold"],
            )
        )
        previous.extend(test)
    return folds


def build_aggregate_result(
    *,
    dataset: PaFeitianEvaluationDataset,
    dataset_path: str | Path,
    config: BaselineEvaluationConfig,
    generated_at_utc: datetime,
) -> PaFeitianEvaluationAggregateResult:
    rows = dataset.rows
    groups = [_group(dimension="pooled", value="all", rows=rows, config=config)]
    time_zone = ZoneInfo(config.timezone)
    for dimension, selector in (
        ("pool", lambda row: row.pool),
        ("underlying", lambda row: row.underlying),
        ("time_window", lambda row: row.decision_ts_utc.astimezone(time_zone).strftime("%Y-%m")),
    ):
        buckets: dict[str, list[EvaluationDatasetRow]] = defaultdict(list)
        for row in rows:
            buckets[selector(row)].append(row)
        groups.extend(
            _group(dimension=dimension, value=value, rows=buckets[value], config=config)
            for value in sorted(buckets)
        )
    provenance_payload = dataset.provenance.model_dump()
    provenance_payload["role"] = "m6_aggregate_result"
    provenance_payload["input_hashes"] = {
        **dataset.provenance.input_hashes,
        "evaluation_dataset": sha256_file(dataset_path),
    }
    return PaFeitianEvaluationAggregateResult(
        generated_at_utc=generated_at_utc.astimezone(UTC),
        provenance=EvaluationArtifactProvenance.model_validate(provenance_payload),
        evaluation_dataset=EvaluationArtifactRef(
            kind="evaluation_dataset",
            path=str(dataset_path),
            sha256=sha256_file(dataset_path),
            schema_version=dataset.schema_version,
        ),
        groups=groups,
        walk_forward_folds=build_walk_forward_folds(rows, config),
        warnings=[
            "baseline-only M6-B: no policy comparison, screening, failure-mode report, frontend, or execution is emitted",
        ],
    )
