"""Deterministic validation for the frozen PA/Feitian Phase 1 v2 registry."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "pa_feitian_phase1_hypothesis_registry_v2"
LOCK_SCHEMA_VERSION = "pa_feitian_phase1_hypothesis_registry_lock_v2"
FROZEN_REGISTRY_SHA256 = "sha256:f2b77c11317c1f98fe6d4c95f47b2213243322f2f3d4ed6dd1ccbf92d972afa0"
FROZEN_DESIGN_SHA256 = "sha256:4d3026e5eb398752c3c8f207cb5e21d1b2706e7fb68d40ddf31b99132486cb65"
FROZEN_LOCK_SHA256 = "sha256:d7e36900efb91807a0960922c5cdbc5241ec4ca1988eb477ac6bc5a32c940718"
REGISTRY_RELATIVE_PATH = "docs/research/pa-feitian-phase1-hypothesis-registry-v2.json"
LOCK_RELATIVE_PATH = "docs/research/pa-feitian-phase1-hypothesis-registry-v2.lock.json"
SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")

EXPECTED_SOURCES = {
    "docs/research/pa-feitian-phase1-hypothesis-registry-v1.json",
    "docs/research/pa-feitian-phase1-hypothesis-registry-v1.lock.json",
    "docs/research/pa-feitian-phase1-data-capability-contract-v1.json",
    (
        "doc/repro/pa-feitian-phase1-data-capability-2026-07-30/"
        "candidate_capability_inventory_v1.json"
    ),
    ("doc/repro/pa-feitian-phase1-data-capability-2026-07-30/candidate_interface_audit_v1.json"),
    ("doc/repro/pa-feitian-phase1-swing-regime-exploration-2026-07-30/README.md"),
    "docs/research/pa-feitian-m6-exploratory-swing-views-contract-v1.json",
    ("doc/repro/pa-feitian-m6-exploratory-swing-views-2026-07-30/exploratory_swing_views_v1.json"),
    "docs/research/pa-feitian-m6-underlying-corpus-contract-v1.json",
    "doc/repro/pa-feitian-m6-premium-k-response-2026-07-13/README.md",
}

EXPECTED_UNIVERSE = [
    {
        "instrument_family": "SHFE.au",
        "role": "continuity_candidate",
        "fixed_weight": "1/6",
    },
    {
        "instrument_family": "SHFE.ag",
        "role": "continuity_candidate",
        "fixed_weight": "1/6",
    },
    {
        "instrument_family": "CZCE.TA",
        "role": "mainstream_candidate",
        "fixed_weight": "1/6",
    },
    {
        "instrument_family": "CZCE.MA",
        "role": "mainstream_candidate",
        "fixed_weight": "1/6",
    },
    {
        "instrument_family": "SHFE.cu",
        "role": "non_czce_control",
        "fixed_weight": "1/6",
    },
    {
        "instrument_family": "DCE.i",
        "role": "non_czce_control",
        "fixed_weight": "1/6",
    },
]

EXPECTED_WINDOWS = [
    {
        "window_id": "P1-EXP-002-TRAIN",
        "role": "training_gate",
        "decision_date_start": "2021-11-01",
        "decision_date_end": "2023-06-30",
        "outcome_observation_cutoff": "2023-07-07",
    },
    {
        "window_id": "P1-EXP-002-VALIDATE",
        "role": "validation_gate",
        "decision_date_start": "2023-07-08",
        "decision_date_end": "2024-12-31",
        "outcome_observation_cutoff": "2025-01-10",
    },
    {
        "window_id": "P1-EXP-002-HOLDOUT",
        "role": "single_use_holdout",
        "decision_date_start": "2025-01-11",
        "decision_date_end": "2026-04-30",
        "outcome_observation_cutoff": "2026-05-15",
    },
]


class HypothesisRegistryV2Error(ValueError):
    """Raised when registry-v2 provenance or its frozen design drifts."""


EXPECTED_REGISTRY_KEYS = {
    "schema_version",
    "version",
    "registry_id",
    "issue_number",
    "status",
    "frozen_at_utc",
    "baseline",
    "scope",
    "source_catalog",
    "prior_registry_decision",
    "candidate_decisions",
    "selection",
    "amendment_policy",
}
EXPECTED_SELECTION_KEYS = {"selected_candidate_id", "selected_experiment"}
EXPECTED_EXPERIMENT_KEYS = {
    "experiment_id",
    "hypothesis_id",
    "status",
    "outcome_inspection_at_freeze",
    "research_label",
    "statement",
    "selection_reasoning_fixed_pre_outcome",
    "design",
    "material_distinction_from_p1_exp_001",
    "material_distinction_from_m6_exp_013",
}
EXPECTED_CANDIDATE_KEYS = {"candidate_id", "source_status", "decision", "reason"}
FORBIDDEN_POSTERIOR_KEYS = {
    "forward_close",
    "outcome_value",
    "pnl",
    "ev",
    "win_rate",
    "profitability",
    "realized_return",
    "t_plus_5_close",
}


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HypothesisRegistryV2Error(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise HypothesisRegistryV2Error(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise HypothesisRegistryV2Error(f"{path} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def canonical_sha256(value: Any) -> str:
    """Hash JSON with stable key ordering and no insignificant whitespace."""

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def splitmix64_indices(*, seed: int, population: int, count: int) -> list[int]:
    """Return unbiased SplitMix64 indices under the frozen v2 stream rules."""

    if population <= 0:
        raise HypothesisRegistryV2Error("PRNG population must be positive")
    if population > (1 << 64):
        raise HypothesisRegistryV2Error("PRNG population exceeds uint64 range")
    if count < 0:
        raise HypothesisRegistryV2Error("PRNG count must be non-negative")

    mask = (1 << 64) - 1
    limit = ((1 << 64) // population) * population
    state = seed & mask
    indices: list[int] = []
    while len(indices) < count:
        state = (state + 0x9E3779B97F4A7C15) & mask
        output = state
        output = ((output ^ (output >> 30)) * 0xBF58476D1CE4E5B9) & mask
        output = ((output ^ (output >> 27)) * 0x94D049BB133111EB) & mask
        output ^= output >> 31
        if output < limit:
            indices.append(output % population)
    return indices


def _require_dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HypothesisRegistryV2Error(f"{field} must be an object")
    return value


def _require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise HypothesisRegistryV2Error(f"{field} must be a non-empty list")
    return value


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HypothesisRegistryV2Error(f"{field} must be a non-empty string")
    return value


def _reject_forbidden_posterior_keys(value: Any, field: str = "registry") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in FORBIDDEN_POSTERIOR_KEYS:
                raise HypothesisRegistryV2Error(f"posterior outcome field forbidden: {field}.{key}")
            _reject_forbidden_posterior_keys(nested, f"{field}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_forbidden_posterior_keys(nested, f"{field}[{index}]")


def _validate_sources(registry: dict[str, Any], repo_root: Path) -> None:
    root = repo_root.resolve()
    paths: set[str] = set()
    source_ids: set[str] = set()

    for index, source in enumerate(_require_list(registry.get("source_catalog"), "source_catalog")):
        source = _require_dict(source, f"source_catalog[{index}]")
        if set(source) != {"source_id", "path", "sha256", "role"}:
            raise HypothesisRegistryV2Error(f"source_catalog[{index}] fields drifted")
        source_id = _require_string(source.get("source_id"), f"source_catalog[{index}].source_id")
        if source_id in source_ids:
            raise HypothesisRegistryV2Error(f"duplicate source id: {source_id}")
        source_ids.add(source_id)

        relative = _require_string(source.get("path"), f"source_catalog[{index}].path")
        if relative.startswith("/") or ".." in Path(relative).parts:
            raise HypothesisRegistryV2Error("source path must be repository-relative")
        if relative in paths:
            raise HypothesisRegistryV2Error(f"duplicate source path: {relative}")
        paths.add(relative)

        expected_hash = _require_string(source.get("sha256"), f"source_catalog[{index}].sha256")
        if not SHA256_PATTERN.fullmatch(expected_hash):
            raise HypothesisRegistryV2Error(f"invalid source hash: {relative}")
        source_path = (root / relative).resolve()
        try:
            source_path.relative_to(root)
        except ValueError as exc:
            raise HypothesisRegistryV2Error("source path escapes repository") from exc
        if not source_path.is_file():
            raise HypothesisRegistryV2Error(f"source file unavailable: {relative}")
        try:
            actual_hash = _sha256(source_path)
        except OSError as exc:
            raise HypothesisRegistryV2Error(f"source file unavailable: {relative}") from exc
        if actual_hash != expected_hash:
            raise HypothesisRegistryV2Error(f"source hash mismatch: {relative}")
        _require_string(source.get("role"), f"source_catalog[{index}].role")

    if paths != EXPECTED_SOURCES:
        raise HypothesisRegistryV2Error("source catalog path set drifted")


def _validate_candidate_decisions(registry: dict[str, Any]) -> None:
    expected = [
        ("SR-01", "derived_proxy", "selected"),
        ("SR-02", "proxy", "rejected_for_reuse"),
        ("SR-03", "too_subjective", "excluded"),
    ]
    decisions = _require_list(registry.get("candidate_decisions"), "candidate_decisions")
    actual: list[tuple[Any, Any, Any]] = []
    for index, decision in enumerate(decisions):
        decision = _require_dict(decision, f"candidate_decisions[{index}]")
        if set(decision) != EXPECTED_CANDIDATE_KEYS:
            raise HypothesisRegistryV2Error(f"candidate_decisions[{index}] fields drifted")
        actual.append(
            (
                decision.get("candidate_id"),
                decision.get("source_status"),
                decision.get("decision"),
            )
        )
        _require_string(decision.get("reason"), f"candidate_decisions[{index}].reason")
    if actual != expected:
        raise HypothesisRegistryV2Error("candidate decision set drifted")


def _validate_event(design: dict[str, Any]) -> None:
    event = _require_dict(design.get("decision_event"), "design.decision_event")
    fixed_values = {
        "decision_local_time": "15:00:00",
        "exact_close_required": True,
        "source_timestamp_cutoff": (
            "timestamp <= decision timestamp before session mapping or aggregation"
        ),
        "levels_in_fixed_order": ["D", "W", "60min", "15min"],
        "prior_20_high": (
            "maximum high of the 20 completed D bars strictly before the current D bar"
        ),
        "prior_20_low": (
            "minimum low of the 20 completed D bars strictly before the current D bar"
        ),
        "ema_5": (
            "causal close EWM with span 5 and adjust=false through the current completed bar"
        ),
        "ema_20": (
            "causal close EWM with span 20 and adjust=false through the current completed bar"
        ),
        "up_event": ("D close > strict-prior-20 D high and EMA5 > EMA20 on D, W, 60min, and 15min"),
        "down_event": (
            "D close < strict-prior-20 D low and EMA5 < EMA20 on D, W, 60min, and 15min"
        ),
        "otherwise": "abstain",
        "event_key": [
            "instrument_family",
            "selected_contract_identifier",
            "exchange_trading_date",
        ],
    }
    for key, expected in fixed_values.items():
        if event.get(key) != expected:
            raise HypothesisRegistryV2Error(f"decision event {key} drifted")

    abstain_text = " ".join(
        str(item)
        for item in _require_list(
            event.get("abstain_conditions"),
            "design.decision_event.abstain_conditions",
        )
    ).lower()
    for term in (
        "scheduled close",
        "20 completed prior",
        "ohlc coherence",
        "roll ambiguity",
        "disagreement",
        "filtered input",
    ):
        if term not in abstain_text:
            raise HypothesisRegistryV2Error(f"decision event lacks fail-closed {term} condition")


def _validate_design(design: dict[str, Any]) -> None:
    if design.get("timezone") != "Asia/Shanghai":
        raise HypothesisRegistryV2Error("design timezone drifted")
    if design.get("universe") != EXPECTED_UNIVERSE:
        raise HypothesisRegistryV2Error("six-family universe or roles drifted")
    if design.get("staged_windows") != EXPECTED_WINDOWS:
        raise HypothesisRegistryV2Error("staged windows drifted")

    roll = _require_dict(design.get("causal_roll_policy"), "design.causal_roll_policy")
    expected_roll = {
        "selection": "prior_session_OI_when_all_active_positive_else_volume",
        "active_contract_eligibility": "A contract is eligible on a session only when its prior-session row exists, is causally available before the session decision, has finite nonnegative open_interest and volume, and passes timestamp, duplicate, and OHLC coherence checks.",
        "candidate_enumeration": "Enumerate exactly the frozen family contract universe observed in the causally filtered prior-session snapshot; never infer candidates from posterior rows or embedded calendar annotations.",
        "prior_session_requirements": "Require one and only one causally filtered prior-session row per candidate contract with finite nonnegative volume and finite open_interest; missing, duplicate, nonfinite, or incoherent rows make that candidate ineligible.",
        "zero_and_missing_handling": "Zero or missing open_interest makes a contract ineligible for OI leadership; zero or missing volume makes it ineligible for volume leadership. If no eligible leader remains, preserve the incumbent only when its own causal row remains valid; otherwise emit no selected contract and abstain.",
        "leader_rule": "If every active candidate has strictly positive open_interest, choose the maximum prior-session open_interest; otherwise choose the maximum prior-session volume among candidates with strictly positive finite volume.",
        "confirmation_sessions": 3,
        "confirmation_rule": "The proposed leader must win on three consecutive exchange trading sessions; a missing session, ineligible proposed leader, or different leader resets the streak to zero.",
        "streak_reset": "Reset confirmation to zero whenever the proposed leader changes, any required prior-session row is invalid, or the exchange session is absent from the bound calendar.",
        "effective_session": "next_session_after_third_confirmation",
        "incumbent_expiry": "An incumbent expires immediately when its next causal prior-session row is missing, invalid, or outside the frozen candidate universe; no forced roll or posterior repair is permitted.",
        "date_semantics": "exchange_trading_date",
        "embedded_calendar_date_annotations_consumed": False,
        "selected_contract_fixed_through_outcome": True,
        "tie_rule": "Resolve equal leadership values by bytewise ascending contract identifier.",
        "initial_state": (
            "no incumbent contract at history_start_inclusive; the first selection "
            "becomes effective only on the session after one leader satisfies all "
            "three confirmation sessions"
        ),
    }
    if roll != expected_roll:
        raise HypothesisRegistryV2Error("causal roll policy drifted")

    history = _require_dict(
        design.get("history_initialization"),
        "design.history_initialization",
    )
    expected_history = {
        "history_start_inclusive": "2021-06-01T00:00:00+08:00",
        "rows_before_history_start": "forbidden",
        "roll_state": "empty_no_incumbent",
        "indicator_history_membership": "For every frozen-family contract and required level, use all causally valid contract-local completed bars at or after history_start_inclusive, regardless of whether that contract is selected at the bar timestamp; never splice bars from different contracts into one indicator series.",
        "roll_away_behavior": "Retain each contract's causal D/W/60min/15min indicator state while it is not selected; do not update it with another contract's bars.",
        "roll_back_behavior": "When a contract becomes selected again, resume its retained contract-local state through the current completed bar; no reset or reuse of another contract's state is permitted.",
        "ema_rule": (
            "For each selected contract and level independently, initialize EMA5 "
            "and EMA20 to the first finite completed close at or after "
            "history_start_inclusive, then apply adjust=false recurrences "
            "alpha=2/(span+1) in completed-bar order."
        ),
        "minimum_prior_completed_bars_per_level_before_event": 20,
        "missing_or_insufficient_history_action": "abstain_event",
    }
    if history != expected_history:
        raise HypothesisRegistryV2Error("history initialization drifted")
    _validate_event(design)

    outcome = _require_dict(design.get("outcome"), "design.outcome")
    expected_outcome = {
        "name": "five_completed_daily_bar_signal_signed_underlying_close_return",
        "formula": (
            "direction_multiplier * (same_contract_close_on_5th_subsequent_"
            "completed_daily_bar / decision_close - 1), where up=+1 and down=-1"
        ),
        "horizon_completed_daily_bars": 5,
        "same_contract_required": True,
        "roll_during_outcome": False,
        "option_outcome": False,
        "pnl_or_execution_semantics": False,
        "availability_rule": "The estimand is conditional on same-contract fifth-close availability. Admit an effective observation only when the decision close and fifth subsequent completed daily close are finite and strictly positive; otherwise apply EX-03.",
        "outcome_access_boundary": "Only the separate event-keyed same-contract T+5 availability/value join may read later rows, after causal membership is sealed; later decision construction may read only rows timestamp-truncated to that later decision.",
        "posterior_fields_forbidden": ["forward_close", "outcome_value", "pnl", "ev", "win_rate"],
    }
    if outcome != expected_outcome:
        raise HypothesisRegistryV2Error("outcome definition drifted")

    sample_gate = _require_dict(design.get("sample_gate"), "design.sample_gate")
    expected_gate = {
        "effective_event_definition": (
            "A sealed causal event that remains after the current unlocked stage "
            "applies P1-EXP-002-EX-03 without changing causal membership."
        ),
        "minimum_effective_events_per_stage": 60,
        "minimum_distinct_decision_dates_per_stage": 20,
        "minimum_events_per_family_direction_cell_per_stage": 5,
        "required_family_direction_cells": 12,
        "maximum_single_decision_date_share_of_effective_events": 0.2,
        "maximum_ex03_attrition_share_per_stage": 0.5,
        "maximum_ex03_attrition_share_per_family_direction_cell": 0.5,
        "ex03_attrition_measure": "For each stage and family-direction cell, EX-03 attrition is unavailable-T+5 events divided by all causal event-membership rows in that cell; if either maximum is exceeded, classify the stage as insufficient_sample.",
        "ex03_excess_action": "insufficient_sample_no_strategy_inference_and_later_stages_remain_sealed",
        "unmet_action": (
            "insufficient_sample_no_strategy_inference_and_later_stages_remain_sealed"
        ),
    }
    if sample_gate != expected_gate:
        raise HypothesisRegistryV2Error("sample gate drifted")

    materialization = _require_dict(
        design.get("pre_outcome_materialization"),
        "design.pre_outcome_materialization",
    )
    if (
        materialization.get("all_stage_membership_rule")
        != (
            "Materialize and hash the causal event, abstain, conflict, decision-time "
            "exclusion, family, direction, selected-contract, and decision-date "
            "fields for all three stages before reading or joining any forward close. "
            "P1-EXP-002-EX-03 is not a causal-membership exclusion and is applied "
            "only after its stage unlocks."
        )
        or materialization.get("outcome_join_rule")
        != (
            "After the all-stage membership manifest is immutable, the outcome "
            "loader may join only the sealed event keys for the currently unlocked "
            "stage. It records P1-EXP-002-EX-03 outcome availability without "
            "changing causal event membership, then computes values only for the "
            "remaining effective events."
        )
        or materialization.get("chronology_anchor_requirement")
        != (
            "Use the protected merged Git commit containing the exact registry and "
            "lock as the external anchor. The first-access attestation must record "
            "that commit, prove it is an ancestor of the builder source commit, and "
            "predate all event materialization and forward-outcome reads."
        )
        or materialization.get("membership_recomputation_after_outcome_access") != "forbidden"
        or materialization.get("missing_action") != "block_outcome_access"
    ):
        raise HypothesisRegistryV2Error("pre-outcome stage membership freeze drifted")
    required_bindings = {
        "registry_sha256",
        "canonical_design_sha256",
        "approved_data_gate_sha256",
        "filtered_input_digest",
        "source_commit",
        "builder_version",
        "arguments",
        "stage_membership_hashes",
    }
    if set(materialization.get("manifest_bindings", [])) != required_bindings:
        raise HypothesisRegistryV2Error("pre-outcome manifest bindings drifted")

    data_gate = _require_dict(design.get("data_gate_dependency"), "design.data_gate_dependency")
    if (
        data_gate.get("issue_number") != 50
        or data_gate.get("required_before_event_materialization") is not True
        or data_gate.get("required_before_outcome_access") is not True
        or data_gate.get("missing_action") != "keep_issue_51_blocked"
    ):
        raise HypothesisRegistryV2Error("historical data-gate dependency drifted")

    analysis = _require_dict(design.get("analysis"), "design.analysis")
    bootstrap = _require_dict(analysis.get("bootstrap"), "design.analysis.bootstrap")
    for key, value in {
        "algorithm_version": "cross_family_date_block_percentile_v1",
        "block_length_dates": 5,
        "replicates": 2000,
        "maximum_attempts": 20000,
        "seed": 49002,
        "confidence_level": 0.95,
    }.items():
        if bootstrap.get(key) != value:
            raise HypothesisRegistryV2Error(f"bootstrap {key} drifted")
    prng = _require_dict(bootstrap.get("prng"), "design.analysis.bootstrap.prng")
    expected_prng = {
        "algorithm": "splitmix64_v1",
        "unsigned_integer_width": 64,
        "arithmetic": "all additions and multiplications modulo 2^64",
        "state_transition": (
            "state=(state+0x9E3779B97F4A7C15) mod 2^64; z=state; "
            "z=((z xor (z>>30))*0xBF58476D1CE4E5B9) mod 2^64; "
            "z=((z xor (z>>27))*0x94D049BB133111EB) mod 2^64; "
            "output=z xor (z>>31)"
        ),
        "uniform_index_mapping": (
            "For N possible block starts, limit=floor(2^64/N)*N; reject outputs "
            ">= limit; accepted index=output mod N."
        ),
        "stream_rule": (
            "Use one continuous stream for the stage. Every attempted block start "
            "and every discarded replicate consumes draws; never reset between "
            "replicates or attempts."
        ),
        "golden_first_12_indices_when_n_10": splitmix64_indices(
            seed=49002,
            population=10,
            count=12,
        ),
    }
    if prng != expected_prng:
        raise HypothesisRegistryV2Error("bootstrap PRNG protocol drifted")

    sequential = _require_dict(
        analysis.get("sequential_evaluation"),
        "design.analysis.sequential_evaluation",
    )
    if sequential.get("window_order") != [
        "P1-EXP-002-TRAIN",
        "P1-EXP-002-VALIDATE",
        "P1-EXP-002-HOLDOUT",
    ]:
        raise HypothesisRegistryV2Error("sequential window order drifted")
    if sequential.get("window_pooling") != "forbidden":
        raise HypothesisRegistryV2Error("window pooling must remain forbidden")
    if sequential.get("adaptation_between_windows") != "forbidden":
        raise HypothesisRegistryV2Error("adaptation between windows must remain forbidden")

    prohibited = " ".join(
        str(item)
        for item in _require_list(
            design.get("prohibited_adaptations"),
            "design.prohibited_adaptations",
        )
    ).lower()
    for term in (
        "family",
        "causal roll",
        "15:00",
        "strict-prior-20",
        "ema5",
        "five-completed-daily-bar",
        "single-use holdout",
        "bootstrap",
        "sealed outcomes",
        "option",
        "sr-02",
        "filtered-input binding",
    ):
        if term not in prohibited:
            raise HypothesisRegistryV2Error(f"prohibited adaptations omit {term}")


def validate_registry_v2_payload(
    registry: dict[str, Any],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    """Validate v2 semantic completeness and source provenance."""

    if set(registry) != EXPECTED_REGISTRY_KEYS:
        raise HypothesisRegistryV2Error("registry top-level fields drifted")
    _reject_forbidden_posterior_keys(registry)

    if registry.get("schema_version") != SCHEMA_VERSION:
        raise HypothesisRegistryV2Error("unsupported registry-v2 schema")
    if registry.get("version") != 2:
        raise HypothesisRegistryV2Error("registry version must be 2")
    if registry.get("registry_id") != "pa_feitian_phase1_2026_07_30":
        raise HypothesisRegistryV2Error("registry id drifted")
    if registry.get("issue_number") != 49:
        raise HypothesisRegistryV2Error("registry issue binding drifted")
    if registry.get("status") != "frozen_before_p1_exp_002_outcome_access":
        raise HypothesisRegistryV2Error("registry-v2 freeze status drifted")
    if registry.get("frozen_at_utc") != "2026-07-30T13:37:34Z":
        raise HypothesisRegistryV2Error("registry-v2 freeze timestamp drifted")
    expected_baseline = {
        "commit": "2fc557bf55984b83781c9ebe76e558e7896b8296",
        "workspace": "PT-Strategy",
        "parent_bookmark": "strategy/active",
        "pull_request_base": "develop",
        "parent_registry": "docs/research/pa-feitian-phase1-hypothesis-registry-v1.json",
    }
    if registry.get("baseline") != expected_baseline:
        raise HypothesisRegistryV2Error("registry-v2 baseline drifted")

    _validate_sources(registry, repo_root)
    _validate_candidate_decisions(registry)

    selection = _require_dict(registry.get("selection"), "selection")
    if set(selection) != EXPECTED_SELECTION_KEYS:
        raise HypothesisRegistryV2Error("selection fields drifted")
    if selection.get("selected_candidate_id") != "SR-01":
        raise HypothesisRegistryV2Error("selected candidate must be SR-01")
    experiment = _require_dict(
        selection.get("selected_experiment"),
        "selection.selected_experiment",
    )
    if set(experiment) != EXPECTED_EXPERIMENT_KEYS:
        raise HypothesisRegistryV2Error("selected experiment fields drifted")
    if experiment.get("experiment_id") != "P1-EXP-002":
        raise HypothesisRegistryV2Error("selected experiment id drifted")
    if experiment.get("hypothesis_id") != "P1-HYP-SR-01":
        raise HypothesisRegistryV2Error("selected hypothesis id drifted")
    if experiment.get("status") != "frozen_before_event_materialization_and_outcome_access":
        raise HypothesisRegistryV2Error("selected experiment status drifted")
    if experiment.get("outcome_inspection_at_freeze") != "not_started":
        raise HypothesisRegistryV2Error("registry was not frozen before outcome inspection")

    design = _require_dict(
        experiment.get("design"),
        "selection.selected_experiment.design",
    )
    _validate_design(design)
    if canonical_sha256(design) != FROZEN_DESIGN_SHA256:
        raise HypothesisRegistryV2Error("P1-EXP-002 canonical design drifted")
    return design


def validate_registry_v2_files(
    *,
    registry_path: Path,
    lock_path: Path,
    repo_root: Path,
) -> dict[str, str]:
    """Validate v2 sources, immutable registry bytes, and design hash."""

    registry = _load_json(registry_path)
    lock = _load_json(lock_path)
    design = validate_registry_v2_payload(registry, repo_root=repo_root)

    if lock.get("schema_version") != LOCK_SCHEMA_VERSION:
        raise HypothesisRegistryV2Error("unsupported registry-v2 lock schema")
    if set(lock) != {
        "schema_version",
        "registry",
        "selected_experiment",
        "freeze",
    }:
        raise HypothesisRegistryV2Error("registry-v2 lock fields drifted")
    registry_binding = _require_dict(lock.get("registry"), "lock.registry")
    if set(registry_binding) != {"path", "sha256"}:
        raise HypothesisRegistryV2Error("registry-v2 lock registry fields drifted")
    root = repo_root.resolve()
    try:
        relative = registry_path.resolve().relative_to(root).as_posix()
        lock_relative = lock_path.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise HypothesisRegistryV2Error("registry or lock path escapes repository") from exc
    if relative != REGISTRY_RELATIVE_PATH:
        raise HypothesisRegistryV2Error("registry-v2 path is not canonical")
    if lock_relative != LOCK_RELATIVE_PATH:
        raise HypothesisRegistryV2Error("registry-v2 lock path is not canonical")
    if registry_binding.get("path") != relative:
        raise HypothesisRegistryV2Error("registry-v2 lock path mismatch")

    actual_registry_hash = _sha256(registry_path)
    if registry_binding.get("sha256") != FROZEN_REGISTRY_SHA256:
        raise HypothesisRegistryV2Error("registry-v2 lock hash drifted")
    if actual_registry_hash != FROZEN_REGISTRY_SHA256:
        raise HypothesisRegistryV2Error(
            "registry-v2 hash mismatch: possible after-the-fact rewrite"
        )
    if _sha256(lock_path) != FROZEN_LOCK_SHA256:
        raise HypothesisRegistryV2Error("registry-v2 lock hash mismatch")

    experiment_binding = _require_dict(
        lock.get("selected_experiment"),
        "lock.selected_experiment",
    )
    if set(experiment_binding) != {
        "experiment_id",
        "canonical_design_sha256",
    }:
        raise HypothesisRegistryV2Error("registry-v2 lock experiment fields drifted")
    if experiment_binding.get("experiment_id") != "P1-EXP-002":
        raise HypothesisRegistryV2Error("registry-v2 lock experiment id drifted")
    actual_design_hash = canonical_sha256(design)
    if experiment_binding.get("canonical_design_sha256") != FROZEN_DESIGN_SHA256:
        raise HypothesisRegistryV2Error("registry-v2 design anchor drifted")
    if actual_design_hash != FROZEN_DESIGN_SHA256:
        raise HypothesisRegistryV2Error(
            "P1-EXP-002 design hash mismatch: after-the-fact parameter change"
        )

    freeze = _require_dict(lock.get("freeze"), "lock.freeze")
    expected_freeze = {
        "frozen_at_utc": registry["frozen_at_utc"],
        "outcome_inspection_status": "not_started",
        "event_materialization_status": "not_started",
        "data_gate_issue": 50,
        "data_gate_status": "required_before_event_materialization",
        "chronology_anchor_status": ("protected_merged_commit_required_before_first_access"),
        "amendment_policy": "new_registry_version_and_experiment_id_required",
    }
    if freeze != expected_freeze:
        raise HypothesisRegistryV2Error("registry-v2 freeze metadata drifted")

    return {
        "registry_sha256": actual_registry_hash,
        "selected_experiment_design_sha256": actual_design_hash,
    }
