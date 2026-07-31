"""Deterministic validation for the frozen PA/Feitian Phase 1 hypothesis registry."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "pa_feitian_phase1_hypothesis_registry_v1"
LOCK_SCHEMA_VERSION = "pa_feitian_phase1_hypothesis_registry_lock_v1"
FROZEN_REGISTRY_SHA256 = "sha256:8658189af71f58e665d09af6c84ee49558b41ff33b79d4aafbcc0479c5eaab57"
FROZEN_DESIGN_SHA256 = "sha256:ef4d64e30684c7febf50be69ff75732c01d091bbdf853a15f5ee0c6c69206907"
SOURCE_STATUSES = frozenset({"authentic", "derived", "proxy"})
SELECTION_STATUSES = frozenset({"selected", "parked", "blocked"})
REQUIRED_SOURCE_PATHS = frozenset(
    {
        "doc/repro/pa-feitian-m6-premium-k-response-2026-07-13/README.md",
        "doc/feitian-deployable-rules-2026-06-16.md",
        "doc/xiao-feitian-options-timing-system-2026-06-16.md",
        "doc/design/pa-feitian-m6-strategy-evaluation-scope-2026-07-11.md",
    }
)
SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


class HypothesisRegistryError(ValueError):
    """Raised when registry provenance or its frozen design drifts."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HypothesisRegistryError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise HypothesisRegistryError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise HypothesisRegistryError(f"{path} must contain a JSON object")
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


def _require_nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HypothesisRegistryError(f"{field} must be a non-empty string")
    return value


def _require_nonempty_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise HypothesisRegistryError(f"{field} must be a non-empty list")
    return value


def _validate_source_refs(
    refs: Any,
    *,
    field: str,
    source_locators: dict[str, set[str]],
) -> None:
    for index, ref in enumerate(_require_nonempty_list(refs, field)):
        if not isinstance(ref, dict):
            raise HypothesisRegistryError(f"{field}[{index}] must be an object")
        source_id = _require_nonempty_string(ref.get("source_id"), f"{field}[{index}].source_id")
        if source_id not in source_locators:
            raise HypothesisRegistryError(f"{field}[{index}] references unknown source {source_id}")
        locator = _require_nonempty_string(ref.get("locator"), f"{field}[{index}].locator")
        if locator not in source_locators[source_id]:
            raise HypothesisRegistryError(
                f"{field}[{index}] references unbound locator {locator!r} in {source_id}"
            )
        _require_nonempty_string(ref.get("claim"), f"{field}[{index}].claim")


def _validate_source_catalog(registry: dict[str, Any], repo_root: Path) -> dict[str, set[str]]:
    sources = _require_nonempty_list(registry.get("source_catalog"), "source_catalog")
    source_locators: dict[str, set[str]] = {}
    paths: set[str] = set()
    root = repo_root.resolve()

    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise HypothesisRegistryError(f"source_catalog[{index}] must be an object")
        source_id = _require_nonempty_string(
            source.get("source_id"), f"source_catalog[{index}].source_id"
        )
        if source_id in source_locators:
            raise HypothesisRegistryError(f"duplicate source_id: {source_id}")

        relative_path = _require_nonempty_string(
            source.get("path"), f"source_catalog[{index}].path"
        )
        if Path(relative_path).is_absolute():
            raise HypothesisRegistryError(
                f"source path must be repository-relative: {relative_path}"
            )
        resolved = (root / relative_path).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise HypothesisRegistryError(
                f"source path escapes repository root: {relative_path}"
            ) from exc
        paths.add(relative_path)

        expected = _require_nonempty_string(source.get("sha256"), f"source_catalog[{index}].sha256")
        if not SHA256_PATTERN.fullmatch(expected):
            raise HypothesisRegistryError(f"invalid source SHA-256: {expected}")
        if not resolved.is_file():
            raise HypothesisRegistryError(f"source file is missing: {relative_path}")
        actual = _sha256(resolved)
        if actual != expected:
            raise HypothesisRegistryError(
                f"source SHA-256 mismatch for {relative_path}: expected {expected}, got {actual}"
            )
        locators = _require_nonempty_list(
            source.get("locators"), f"source_catalog[{index}].locators"
        )
        if not all(isinstance(locator, str) and locator.strip() for locator in locators):
            raise HypothesisRegistryError(
                f"source_catalog[{index}].locators must contain non-empty strings"
            )
        if len(set(locators)) != len(locators):
            raise HypothesisRegistryError(f"source_catalog[{index}].locators contains duplicates")
        source_text = resolved.read_text(encoding="utf-8")
        for locator in locators:
            if locator not in source_text:
                raise HypothesisRegistryError(
                    f"source locator {locator!r} is absent from {relative_path}"
                )
        source_locators[source_id] = set(locators)
        _require_nonempty_string(source.get("role"), f"source_catalog[{index}].role")

    if paths != REQUIRED_SOURCE_PATHS:
        raise HypothesisRegistryError(
            "source_catalog must bind exactly the four issue-mandated source documents"
        )
    return source_locators


def _validate_minimum_sample_gate(gate: Any, field: str) -> None:
    if not isinstance(gate, dict):
        raise HypothesisRegistryError(f"{field} must be an object")
    for name in (
        "minimum_effective_events",
        "minimum_non_overlapping_time_windows",
        "minimum_effective_events_per_window",
        "minimum_effective_events_per_comparison_cell",
    ):
        value = gate.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise HypothesisRegistryError(f"{field}.{name} must be a positive integer")
    _require_nonempty_string(gate.get("unmet_action"), f"{field}.unmet_action")


def _validate_hypotheses(
    registry: dict[str, Any],
    *,
    source_locators: dict[str, set[str]],
) -> tuple[set[str], str]:
    hypotheses = registry.get("hypotheses")
    if not isinstance(hypotheses, list) or not 2 <= len(hypotheses) <= 3:
        raise HypothesisRegistryError("hypotheses must contain two or three entries")

    hypothesis_ids: set[str] = set()
    selected_ids: list[str] = []
    for index, hypothesis in enumerate(hypotheses):
        field = f"hypotheses[{index}]"
        if not isinstance(hypothesis, dict):
            raise HypothesisRegistryError(f"{field} must be an object")
        hypothesis_id = _require_nonempty_string(
            hypothesis.get("hypothesis_id"), f"{field}.hypothesis_id"
        )
        if hypothesis_id in hypothesis_ids:
            raise HypothesisRegistryError(f"duplicate hypothesis_id: {hypothesis_id}")
        hypothesis_ids.add(hypothesis_id)
        _require_nonempty_string(hypothesis.get("title"), f"{field}.title")
        _require_nonempty_string(hypothesis.get("statement"), f"{field}.statement")

        source_status = hypothesis.get("source_status")
        if source_status not in SOURCE_STATUSES:
            raise HypothesisRegistryError(
                f"{field}.source_status must be one of {sorted(SOURCE_STATUSES)}"
            )
        selection_status = hypothesis.get("selection_status")
        if selection_status not in SELECTION_STATUSES:
            raise HypothesisRegistryError(
                f"{field}.selection_status must be one of {sorted(SELECTION_STATUSES)}"
            )
        if selection_status == "selected":
            selected_ids.append(hypothesis_id)

        _validate_source_refs(
            hypothesis.get("source_refs"),
            field=f"{field}.source_refs",
            source_locators=source_locators,
        )
        inputs = _require_nonempty_list(
            hypothesis.get("causal_decision_time_inputs"),
            f"{field}.causal_decision_time_inputs",
        )
        for entry_index, entry in enumerate(inputs):
            if not isinstance(entry, dict):
                raise HypothesisRegistryError(
                    f"{field}.causal_decision_time_inputs[{entry_index}] must be an object"
                )
            for name in ("name", "available_by", "rule", "missing_action"):
                _require_nonempty_string(
                    entry.get(name),
                    f"{field}.causal_decision_time_inputs[{entry_index}].{name}",
                )

        exclusions = _require_nonempty_list(hypothesis.get("exclusions"), f"{field}.exclusions")
        exclusion_ids: set[str] = set()
        for entry_index, entry in enumerate(exclusions):
            if not isinstance(entry, dict):
                raise HypothesisRegistryError(
                    f"{field}.exclusions[{entry_index}] must be an object"
                )
            exclusion_id = _require_nonempty_string(
                entry.get("exclusion_id"), f"{field}.exclusions[{entry_index}].exclusion_id"
            )
            if exclusion_id in exclusion_ids:
                raise HypothesisRegistryError(f"duplicate exclusion_id: {exclusion_id}")
            exclusion_ids.add(exclusion_id)
            for name in ("rule", "reason"):
                _require_nonempty_string(
                    entry.get(name), f"{field}.exclusions[{entry_index}].{name}"
                )

        capabilities = _require_nonempty_list(
            hypothesis.get("required_data_capabilities"),
            f"{field}.required_data_capabilities",
        )
        for entry_index, entry in enumerate(capabilities):
            if not isinstance(entry, dict):
                raise HypothesisRegistryError(
                    f"{field}.required_data_capabilities[{entry_index}] must be an object"
                )
            for name in ("capability", "status", "missing_action"):
                _require_nonempty_string(
                    entry.get(name),
                    f"{field}.required_data_capabilities[{entry_index}].{name}",
                )

        falsification = hypothesis.get("falsification")
        if not isinstance(falsification, dict):
            raise HypothesisRegistryError(f"{field}.falsification must be an object")
        for name in (
            "primary_estimand",
            "uncertainty",
            "supported_when",
            "falsified_when",
            "inconclusive_when",
        ):
            _require_nonempty_string(falsification.get(name), f"{field}.falsification.{name}")
        _validate_minimum_sample_gate(
            hypothesis.get("minimum_sample_gate"), f"{field}.minimum_sample_gate"
        )

    if len(selected_ids) != 1:
        raise HypothesisRegistryError("exactly one hypothesis must be selected")
    return hypothesis_ids, selected_ids[0]


def _validate_negative_gate(registry: dict[str, Any], source_locators: dict[str, set[str]]) -> None:
    gate = registry.get("prior_negative_gate")
    if not isinstance(gate, dict):
        raise HypothesisRegistryError("prior_negative_gate must be an object")
    expected = {
        "experiment_id": "M6-EXP-013",
        "classification": "negative_or_inconclusive",
        "eligible_training_candidate_count": 0,
        "holdout_application": "not_applied_no_training_candidates",
        "rejection_is_frozen": True,
    }
    for key, value in expected.items():
        if gate.get(key) != value:
            raise HypothesisRegistryError(f"prior_negative_gate.{key} drifted")
    _validate_source_refs(
        gate.get("source_refs"),
        field="prior_negative_gate.source_refs",
        source_locators=source_locators,
    )
    prohibited = " ".join(
        str(item)
        for item in _require_nonempty_list(
            gate.get("prohibited_reinterpretations"),
            "prior_negative_gate.prohibited_reinterpretations",
        )
    ).lower()
    for term in ("label", "mapping", "horizon", "observation", "bootstrap", "corpus", "holdout"):
        if term not in prohibited:
            raise HypothesisRegistryError(
                f"prior_negative_gate does not preserve the frozen {term} boundary"
            )


def _validate_selection(
    registry: dict[str, Any],
    *,
    hypothesis_ids: set[str],
    selected_hypothesis_id: str,
) -> dict[str, Any]:
    selection = registry.get("selection")
    if not isinstance(selection, dict):
        raise HypothesisRegistryError("selection must be an object")
    if selection.get("selected_hypothesis_id") != selected_hypothesis_id:
        raise HypothesisRegistryError("selection does not match the one selected hypothesis")
    _require_nonempty_list(
        selection.get("selection_reasoning_fixed_pre_outcome"),
        "selection.selection_reasoning_fixed_pre_outcome",
    )

    experiment = selection.get("selected_experiment")
    if not isinstance(experiment, dict):
        raise HypothesisRegistryError("selection.selected_experiment must be an object")
    exact_experiment_fields = {
        "experiment_id",
        "hypothesis_id",
        "status",
        "outcome_inspection_at_freeze",
        "research_label",
        "design",
        "material_distinction_from_m6_exp_013",
    }
    if set(experiment) != exact_experiment_fields:
        raise HypothesisRegistryError("selected experiment fields drifted")
    if experiment.get("hypothesis_id") not in hypothesis_ids:
        raise HypothesisRegistryError("selected experiment references an unknown hypothesis")
    if experiment.get("hypothesis_id") != selected_hypothesis_id:
        raise HypothesisRegistryError("selected experiment must implement the selected hypothesis")
    if experiment.get("experiment_id") != "P1-EXP-001":
        raise HypothesisRegistryError("selected experiment id drifted")
    if experiment.get("status") != "frozen_before_enrollment_and_outcome_inspection":
        raise HypothesisRegistryError("selected experiment is not frozen pre-outcome")
    if experiment.get("outcome_inspection_at_freeze") != "not_started":
        raise HypothesisRegistryError(
            "selected experiment was not frozen before outcome inspection"
        )
    if experiment.get("research_label") != ("prospective_descriptive_non_authentic_non_executable"):
        raise HypothesisRegistryError("selected experiment research label drifted")

    design = experiment.get("design")
    if not isinstance(design, dict):
        raise HypothesisRegistryError("selected experiment design must be an object")
    exact_design_fields = {
        "timezone",
        "enrollment_windows",
        "outcome_observation_cutoff",
        "universe",
        "event_source",
        "ordered_eligibility",
        "iv_rank",
        "outcome",
        "sample_gate",
        "analysis",
        "prohibited_adaptations",
    }
    if set(design) != exact_design_fields:
        raise HypothesisRegistryError("selected experiment design fields drifted")
    if design.get("timezone") != "Asia/Shanghai":
        raise HypothesisRegistryError("selected experiment timezone drifted")
    iv_rank = design.get("iv_rank")
    if not isinstance(iv_rank, dict):
        raise HypothesisRegistryError("selected experiment iv_rank must be an object")
    frozen_iv_parameters = {
        "implementation": "engine.options.iv_regime.causal_iv_rank",
        "iv_inversion": "engine.options.black76.implied_vol",
        "risk_free_rate": 0.02,
        "time_to_expiry": {
            "day_count_convention": "ACT/365F",
            "expiry_timestamp_rule": ("15:00:00 Asia/Shanghai on the exact recorded expiry date"),
            "decision_timestamp_rule": "timestamp of the observed decision-time option close",
            "formula": (
                "max((expiry_timestamp_utc - "
                "decision_time_option_close_timestamp_utc).total_seconds() / "
                "31536000, 0)"
            ),
        },
        "warmup": 40,
        "history_scope": "same_product_prior_rankable_signals_only",
        "history_initialization": "empty_at_2026-07-27T00:00:00+08:00",
        "history_update_eligibility": (
            "Append every unique in-window same-product decision with a finite "
            "decision-time IV after ranking it, including warmup events and events "
            "later excluded for a missing 17-bar outcome."
        ),
        "same_timestamp_batch_rule": (
            "Rank every same-product event sharing a decision timestamp against "
            "history from strictly earlier timestamps, then append the batch in "
            "deduplication-key bytewise order."
        ),
        "tie_rule": "strictly_lower_prior_iv_count_divided_by_all_finite_prior_ivs",
        "current_event_in_history": False,
        "rank_cutoff": 0.66,
        "kept_cell": "rank<=0.66",
        "rejected_cell": "rank>0.66",
        "warmup_fallback": "none",
    }
    for key, value in frozen_iv_parameters.items():
        if iv_rank.get(key) != value:
            raise HypothesisRegistryError(f"selected experiment iv_rank.{key} drifted")
    if set(iv_rank) != set(frozen_iv_parameters):
        raise HypothesisRegistryError("selected experiment iv_rank fields drifted")

    exact_windows = [
        {
            "window_id": "P1-W1",
            "role": "training_gate",
            "decision_date_start": "2026-07-27",
            "decision_date_end": "2026-10-31",
        },
        {
            "window_id": "P1-W2",
            "role": "validation_gate",
            "decision_date_start": "2026-11-01",
            "decision_date_end": "2027-02-28",
        },
        {
            "window_id": "P1-W3",
            "role": "single_use_holdout",
            "decision_date_start": "2027-03-01",
            "decision_date_end": "2027-06-30",
        },
    ]
    if design.get("enrollment_windows") != exact_windows:
        raise HypothesisRegistryError("selected experiment enrollment windows drifted")
    if design.get("outcome_observation_cutoff") != "2027-07-31":
        raise HypothesisRegistryError("selected experiment outcome cutoff drifted")
    exact_universe = [
        {"exchange": "SHFE", "product": "ag", "option_type": "call"},
        {"exchange": "SHFE", "product": "au", "option_type": "call"},
    ]
    if design.get("universe") != exact_universe:
        raise HypothesisRegistryError("selected experiment universe drifted")
    exact_event_source = {
        "decision_intent_schema_version": "pa_feitian_decision_intent_v1",
        "snapshot_schema_version": "pa_feitian_snapshot_v1",
        "join_key": "signal_id",
        "selection_rule": (
            "Retain every finalized in-window decision intent that joins one-to-one "
            "to a snapshot signal with an already-selected long-call contract and all "
            "frozen eligibility inputs hash-bound; use only snapshot "
            "selected_option_contract plus its matching options_calls metadata and do "
            "not rerun score_today, scan contracts, or reselect a leg."
        ),
        "deduplication_key": [
            "signal_id",
            "selected_contract_symbol",
        ],
        "provenance_fields": [
            "decision_intent_sha256",
            "snapshot_sha256",
        ],
        "admission_deadline": (
            "12:00:00 Asia/Shanghai on the calendar day after the decision date"
        ),
        "admission_ledger_rule": (
            "Before the deadline, append candidate artifact-pair hashes and "
            "decision-time fields to an immutable per-decision-date enrollment "
            "ledger; artifacts first seen after the sealed deadline are audit-only "
            "late revisions and cannot enter or alter rank history."
        ),
        "pre_ranking_conflict_pass": (
            "Before computing any rank for a staged window, scan all sealed "
            "enrollment-ledger entries from history initialization through that "
            "window end by stable deduplication key."
        ),
        "duplicate_resolution_rule": (
            "Within the sealed ledgers, retain one observation only when every copy "
            "has identical provenance hashes and decision-time fields; otherwise "
            "mark the stable key conflicted and exclude every copy before constructing "
            "IV history. Late audit-only revisions never trigger rollback or "
            "recomputation."
        ),
    }
    if design.get("event_source") != exact_event_source:
        raise HypothesisRegistryError("selected experiment event source drifted")
    exact_ordered_eligibility = [
        "decision date is inside exactly one frozen enrollment window",
        "exchange, product, and option type are in the frozen universe",
        "snapshot and decision intent are immutable and hash-bound",
        (
            "the artifact pair was admitted by its deadline and the global pre-ranking "
            "conflict pass retained exactly one conflict-free stable key"
        ),
        (
            "the selected contract, strike, exact expiry, option close, underlying "
            "futures close, and timestamps were available at the finalized decision-day close"
        ),
        "Black-76 implied volatility with r=0.02 and option_type C is finite",
        (
            "at least 40 finite same-product signal-day IV observations exist strictly "
            "before the current event"
        ),
        ("the seventeenth subsequent completed daily option close exists by the outcome cutoff"),
    ]
    if design.get("ordered_eligibility") != exact_ordered_eligibility:
        raise HypothesisRegistryError("selected experiment eligibility order drifted")

    exact_outcome = {
        "name": "seventeen_completed_daily_bar_premium_close_return",
        "formula": (
            "option_close_on_17th_subsequent_completed_daily_bar / decision_time_option_close - 1"
        ),
        "stop": "none",
        "profit_target": "none",
        "position_sizing": "none",
        "cost_model": "none_descriptive_response_only",
        "underlying_return_as_option_outcome": False,
        "execution_claim": False,
    }
    if design.get("outcome") != exact_outcome:
        raise HypothesisRegistryError("selected experiment outcome definition drifted")

    experiment_gate = design.get("sample_gate")
    if not isinstance(experiment_gate, dict):
        raise HypothesisRegistryError("selected experiment sample_gate must be an object")
    exact_gate = {
        "minimum_effective_events_across_three_windows": 60,
        "minimum_effective_events_per_window": 20,
        "minimum_effective_events_per_rank_cell_across_three_windows": 30,
        "minimum_effective_events_per_rank_cell_per_window": 10,
        "minimum_effective_events_per_product_rank_cell_across_three_windows": 15,
        "minimum_effective_events_per_product_rank_cell_per_window": 5,
        "stage_rule": (
            "Apply every per-window threshold independently before advancing to the "
            "next sealed window."
        ),
        "unmet_action": "insufficient_sample_no_strategy_inference",
    }
    if experiment_gate != exact_gate:
        raise HypothesisRegistryError("selected experiment sample gate drifted")

    exact_analysis = {
        "primary_estimand": {
            "name": "equal_weighted_within_product_rank_cell_mean_return_difference",
            "product_contrasts": {
                "ag": "mean_return_ag_rank_lte_0_66_minus_mean_return_ag_rank_gt_0_66",
                "au": "mean_return_au_rank_lte_0_66_minus_mean_return_au_rank_gt_0_66",
            },
            "aggregation": "arithmetic_mean_of_ag_and_au_product_contrasts",
            "product_weights": {"ag": 0.5, "au": 0.5},
            "rank_assignments": (
                "frozen_from_original_enrollment_and_not_recomputed_during_resampling"
            ),
        },
        "sequential_evaluation": {
            "window_order": ["P1-W1", "P1-W2", "P1-W3"],
            "training_gate": (
                "Evaluate P1-W1 only. Advance without parameter changes only when "
                "its sample and valid-replicate gates pass and its 95% interval lower "
                "bound is strictly greater than zero; otherwise terminate as "
                "falsified when the upper bound is less than or equal to zero, or "
                "inconclusive when the gate fails or the interval strictly straddles zero."
            ),
            "validation_gate": (
                "Keep P1-W2 sealed until an immutable hash-bound P1-W1 result "
                "manifest records a passing training gate. Evaluate P1-W2 once under "
                "the identical design and advance only under the identical "
                "positive-lower-bound rule; otherwise terminate and keep P1-W3 sealed."
            ),
            "single_use_holdout": (
                "Keep P1-W3 sealed until immutable hash-bound P1-W1 and P1-W2 result "
                "manifests both record passing gates. Evaluate P1-W3 exactly once "
                "under the identical design; its interval and sample gate alone "
                "determine the final supported, falsified, or inconclusive classification."
            ),
            "window_pooling": "forbidden",
            "adaptation_between_windows": "forbidden",
            "result_manifest_binding": (
                "Each stage manifest binds the registry SHA-256, canonical design "
                "SHA-256, admitted enrollment-ledger hashes, source artifact hashes, "
                "stage id, bootstrap algorithm version, seed, and result hash before "
                "the next stage is unsealed."
            ),
        },
        "secondary_diagnostics": [
            "ag and au within-product rank-cell mean-return contrasts",
            "median return by rank cell",
            "positive-return rate by rank cell",
            "event counts and exclusions by product and window",
        ],
        "bootstrap": {
            "algorithm_version": "stratified_circular_moving_block_percentile_v1",
            "calendar": (
                "Every completed SHFE trading date in the one currently evaluated "
                "frozen window, including dates with zero eligible events."
            ),
            "application": (
                "Run separately for P1-W1, then P1-W2 only if unlocked, then P1-W3 "
                "only if unlocked; never combine observations or replicate estimates "
                "across windows."
            ),
            "date_bin": ("All eligible ag and au events sharing a decision date move together."),
            "block_length_completed_trading_days": 17,
            "block_start_rule": (
                "Sample start indices uniformly with replacement from all completed "
                "trading dates in the window; each block wraps within that same window."
            ),
            "sample_length_rule": (
                "Concatenate blocks until the original window calendar length is "
                "reached and truncate excess dates."
            ),
            "rank_recomputation": False,
            "replicate_estimand": (
                "Recompute the ag and au within-product rank-cell mean differences "
                "and their fixed 0.5/0.5 arithmetic mean."
            ),
            "invalid_replicate_rule": (
                "Discard a replicate if any ag or au rank cell is empty; draw a "
                "replacement until 2000 valid replicates or 20000 total attempts."
            ),
            "insufficient_valid_replicates_action": (
                "If fewer than 2000 valid replicates are produced in 20000 attempts, "
                "classify the result inconclusive."
            ),
            "interval": (
                "Two-sided percentile interval over sorted valid replicate estimates "
                "with linear interpolation at p*(n-1) for p=0.025 and p=0.975."
            ),
            "replicates": 2000,
            "maximum_attempts": 20000,
            "seed": 42001,
            "confidence_level": 0.95,
        },
        "classification": {
            "evaluation_order": [
                "current_stage_sample_and_valid_replicate_gate",
                "interval_upper_bound_lte_zero",
                "interval_lower_bound_gt_zero",
                "interval_strictly_straddles_zero",
            ],
            "supported": (
                "P1-W1 and P1-W2 passed without adaptation, and the single-use P1-W3 "
                "sample gate passes with its 95% interval lower bound greater than zero"
            ),
            "falsified": (
                "the current stage sample gate passes and its 95% interval upper bound "
                "is less than or equal to zero; later stages remain sealed"
            ),
            "inconclusive": (
                "the current stage sample gate fails, fewer than 2000 valid replicates "
                "are produced, or its 95% interval lower bound is less than or equal "
                "to zero and its upper bound is strictly greater than zero; later "
                "stages remain sealed"
            ),
        },
    }
    if design.get("analysis") != exact_analysis:
        raise HypothesisRegistryError("selected experiment analysis definition drifted")

    distinctions = _require_nonempty_list(
        experiment.get("material_distinction_from_m6_exp_013"),
        "selection.selected_experiment.material_distinction_from_m6_exp_013",
    )
    if len(distinctions) < 3:
        raise HypothesisRegistryError("material distinction from M6-EXP-013 is incomplete")
    prohibited = " ".join(
        str(item)
        for item in _require_nonempty_list(
            design.get("prohibited_adaptations"),
            "selection.selected_experiment.design.prohibited_adaptations",
        )
    ).lower()
    for term in (
        "warmup",
        "rank cutoff",
        "deduplication",
        "admission",
        "act/365f",
        "products",
        "17-bar",
        "validation",
        "holdout",
        "sealed",
        "product weights",
        "moving-block",
        "modeled",
        "reselect",
        "m6-exp-013",
    ):
        if term not in prohibited:
            raise HypothesisRegistryError(
                f"selected experiment does not prohibit after-the-fact {term} changes"
            )
    return design


def validate_registry_payload(registry: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    """Validate semantic completeness and source provenance, without a freeze lock."""

    if registry.get("schema_version") != SCHEMA_VERSION:
        raise HypothesisRegistryError("unsupported hypothesis registry schema")
    if registry.get("version") != 1:
        raise HypothesisRegistryError("registry version must be 1")
    if registry.get("status") != "frozen_before_phase1_outcome_inspection":
        raise HypothesisRegistryError("registry must be frozen before outcome inspection")
    if registry.get("frozen_at_utc") != "2026-07-26T09:45:21Z":
        raise HypothesisRegistryError("registry freeze timestamp drifted")
    expected_baseline = {
        "commit": "6242a8a2d6562829a997dd925daf233684162cc5",
        "workspace": "PT-Strategy",
        "bookmark": "strategy/active",
        "pull_request_base": "develop",
    }
    if registry.get("baseline") != expected_baseline:
        raise HypothesisRegistryError("registry baseline or Jujutsu workspace binding drifted")

    contract_preservation = registry.get("scope", {}).get("contract_preservation", {})
    expected_contracts = {
        "pa_feitian_snapshot_v1": "read_only",
        "pa_feitian_decision_intent_v1": "read_only",
        "posterior_outcome_fields_as_decision_inputs": "forbidden",
    }
    if contract_preservation != expected_contracts:
        raise HypothesisRegistryError("snapshot or decision-intent contract boundary drifted")
    source_status_definitions = registry.get("source_status_definitions", {})
    if set(source_status_definitions) != SOURCE_STATUSES:
        raise HypothesisRegistryError(
            "source status definitions must cover authentic, derived, proxy"
        )
    for status, definition in source_status_definitions.items():
        _require_nonempty_string(definition, f"source_status_definitions.{status}")

    source_locators = _validate_source_catalog(registry, repo_root)
    _validate_negative_gate(registry, source_locators)
    hypothesis_ids, selected_hypothesis_id = _validate_hypotheses(
        registry,
        source_locators=source_locators,
    )
    return _validate_selection(
        registry,
        hypothesis_ids=hypothesis_ids,
        selected_hypothesis_id=selected_hypothesis_id,
    )


def validate_registry_files(
    *,
    registry_path: Path,
    lock_path: Path,
    repo_root: Path,
) -> dict[str, str]:
    """Validate the registry, source hashes, and immutable freeze-lock bindings."""

    registry = _load_json(registry_path)
    lock = _load_json(lock_path)
    design = validate_registry_payload(registry, repo_root=repo_root)

    if lock.get("schema_version") != LOCK_SCHEMA_VERSION:
        raise HypothesisRegistryError("unsupported hypothesis registry lock schema")
    registry_binding = lock.get("registry")
    if not isinstance(registry_binding, dict):
        raise HypothesisRegistryError("freeze lock registry binding must be an object")
    try:
        registry_relative = registry_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise HypothesisRegistryError("registry path must be inside the repository") from exc
    if registry_binding.get("path") != registry_relative:
        raise HypothesisRegistryError("freeze lock registry path mismatch")

    expected_registry_sha256 = registry_binding.get("sha256")
    actual_registry_sha256 = _sha256(registry_path)
    if expected_registry_sha256 != FROZEN_REGISTRY_SHA256:
        raise HypothesisRegistryError("freeze lock registry hash drifted from the v1 anchor")
    if actual_registry_sha256 != FROZEN_REGISTRY_SHA256:
        raise HypothesisRegistryError(
            "registry hash mismatch: possible after-the-fact registry change"
        )

    experiment_binding = lock.get("selected_experiment")
    if not isinstance(experiment_binding, dict):
        raise HypothesisRegistryError("freeze lock selected_experiment must be an object")
    if experiment_binding.get("experiment_id") != "P1-EXP-001":
        raise HypothesisRegistryError("freeze lock experiment id mismatch")
    expected_design_sha256 = experiment_binding.get("canonical_design_sha256")
    actual_design_sha256 = canonical_sha256(design)
    if expected_design_sha256 != FROZEN_DESIGN_SHA256:
        raise HypothesisRegistryError("freeze lock design hash drifted from the v1 anchor")
    if actual_design_sha256 != FROZEN_DESIGN_SHA256:
        raise HypothesisRegistryError(
            "selected experiment design hash mismatch: after-the-fact parameter change"
        )

    freeze = lock.get("freeze")
    if not isinstance(freeze, dict):
        raise HypothesisRegistryError("freeze lock metadata must be an object")
    if freeze.get("outcome_inspection_status") != "not_started":
        raise HypothesisRegistryError("freeze lock was not created before outcome inspection")
    if freeze.get("frozen_at_utc") != registry.get("frozen_at_utc"):
        raise HypothesisRegistryError("freeze lock timestamp does not match the registry")
    if freeze.get("amendment_policy") != "new_registry_version_and_experiment_id_required":
        raise HypothesisRegistryError("freeze lock amendment policy drifted")

    return {
        "registry_sha256": actual_registry_sha256,
        "selected_experiment_design_sha256": actual_design_sha256,
    }
