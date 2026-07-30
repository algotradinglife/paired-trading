"""Deterministic public-safe Phase 1 data capability inventory.

The inventory consumes the committed aggregate produced by the explicit,
read-only six-family candidate-interface audit. It never serializes source
filenames, raw contract identifiers, raw rows, local paths, or outcomes.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from engine.pa_feitian.candidate_interface_audit import (
    validate_audit as validate_candidate_interface_audit,
)
from engine.pa_feitian.hypothesis_registry import validate_registry_files


CONTRACT_SCHEMA_VERSION = "pa_feitian_phase1_data_capability_contract_v1"
INVENTORY_SCHEMA_VERSION = "pa_feitian_phase1_data_capability_inventory_v1"
AUDIT_AS_OF_LOCAL_DATE = "2026-07-30"

_EXPECTED_FAMILIES = [
    "SHFE.au",
    "SHFE.ag",
    "CZCE.TA",
    "CZCE.MA",
    "SHFE.cu",
    "DCE.i",
]
_EXPECTED_CADENCES = ["daily", "hour", "min15", "min5"]
_EXPECTED_P1_UNIVERSE = ["SHFE.ag", "SHFE.au"]
_EXPECTED_GUARDRAILS = {
    "candidate_interface_audit_required": True,
    "candidate_interface_external_access_read_only": True,
    "inventory_builder_bound_aggregate_only": True,
    "external_source_refresh": False,
    "raw_market_data_mutation": False,
    "implicit_current_time": False,
    "cadence_resampling_or_substitution": False,
    "strategy_outcome_access": False,
    "performance_calculation": False,
    "instrument_ranking": False,
    "contract_selection": False,
    "future_result_membership_change": False,
    "bid_ask_synthesis": False,
    "delta_synthesis": False,
    "m7": False,
    "m8": False,
    "execution": False,
}

_REGISTRY_ALIAS = "repository://paired-trading/phase1-hypothesis-registry-v1"
_REGISTRY_LOCK_ALIAS = "repository://paired-trading/phase1-hypothesis-registry-lock-v1"
_CANDIDATE_CONTRACT_ALIAS = (
    "repository://paired-trading/phase1-candidate-interface-audit-contract-v1"
)
_CANDIDATE_AUDIT_ALIAS = (
    "repository://paired-trading/phase1-candidate-interface-audit-v1"
)
_OPTION_AUDIT_ALIAS = "repository://paired-trading/m6-option-input-capability-audit-v1"
_LIQUID_PREMIUM_ALIAS = "repository://paired-trading/m6-liquid-premium-evidence-v1"
_CONTINUOUS_ALIAS = "repository://paired-trading/m6-continuous-provenance-v1"
_UNDERLYING_CORPUS_ALIAS = "repository://paired-trading/m6-underlying-signal-corpus-v1"
_RETROSPECTIVE_ALIAS = "repository://paired-trading/m6-retrospective-replay-evidence-v1"
_RAW_AVAILABILITY_ALIAS = "repository://paired-trading/m6-raw-availability-blocker-v1"

_FORBIDDEN_EXACT_KEYS = {
    "entry",
    "exit",
    "fill",
    "pnl",
    "profit",
    "recommendation",
    "return",
    "selected_contract",
    "selection",
    "signal_outcome",
    "trade",
    "win_rate",
}
_FORBIDDEN_TEXT = (
    "/home/",
    "/mnt/",
    "\\Users\\",
    ".parquet",
    ".csv",
    "drwho1985",
    "hhusl",
)
_RAW_CONTRACT_ID = re.compile(r"\b(?:SHFE|CZCE|DCE)\.[A-Za-z]+\d")


class DataCapabilityInventoryError(ValueError):
    """Raised when the frozen inventory boundary is violated."""


def pretty_json_bytes(value: Any) -> bytes:
    """Return the sole byte representation used by builders and verifiers."""

    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def load_contract(path: Path) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    validate_contract(contract)
    return contract


def validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        raise DataCapabilityInventoryError("unexpected data capability contract schema")
    if contract.get("issue_number") != 43:
        raise DataCapabilityInventoryError("issue binding drifted")
    if contract.get("audit_as_of_local_date") != AUDIT_AS_OF_LOCAL_DATE:
        raise DataCapabilityInventoryError("fixed audit date drifted")
    families = [
        row.get("instrument_family") for row in contract.get("candidate_universe", [])
    ]
    if families != _EXPECTED_FAMILIES:
        raise DataCapabilityInventoryError("candidate universe or order drifted")
    if contract.get("audit_cadences") != _EXPECTED_CADENCES:
        raise DataCapabilityInventoryError("audit cadence surface drifted")
    if contract.get("p1_exp_001", {}).get("required_universe") != _EXPECTED_P1_UNIVERSE:
        raise DataCapabilityInventoryError("frozen P1-EXP-001 universe drifted")
    if contract.get("guardrails") != _EXPECTED_GUARDRAILS:
        raise DataCapabilityInventoryError("data capability guardrails were weakened")
    freshness = contract.get("freshness_policy", {})
    if freshness.get("fresh_max_calendar_lag_days") != 7:
        raise DataCapabilityInventoryError("freshness threshold drifted")
    if freshness.get("implicit_current_time") is not False:
        raise DataCapabilityInventoryError("freshness must not use current time")
    liquidity = contract.get("liquidity_proxy", {})
    if liquidity.get("minimum_pass_rate") is not None:
        raise DataCapabilityInventoryError("liquidity proxy must not create a gate")
    if liquidity.get("ranking_allowed") is not False:
        raise DataCapabilityInventoryError("instrument ranking is forbidden")

    aliases = [row.get("alias") for row in contract.get("bound_inputs", [])]
    expected_aliases = [
        _REGISTRY_ALIAS,
        _REGISTRY_LOCK_ALIAS,
        _CANDIDATE_CONTRACT_ALIAS,
        _CANDIDATE_AUDIT_ALIAS,
        _OPTION_AUDIT_ALIAS,
        _LIQUID_PREMIUM_ALIAS,
        _CONTINUOUS_ALIAS,
        _UNDERLYING_CORPUS_ALIAS,
        _RETROSPECTIVE_ALIAS,
        _RAW_AVAILABILITY_ALIAS,
    ]
    if aliases != expected_aliases:
        raise DataCapabilityInventoryError("bound input set or order drifted")
    if len(set(aliases)) != len(aliases):
        raise DataCapabilityInventoryError("bound input aliases must be unique")


def _load_bound_inputs(
    *,
    contract: dict[str, Any],
    repo_root: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    resolved_repo = repo_root.resolve(strict=True)
    payloads: dict[str, dict[str, Any]] = {}
    metadata: dict[str, dict[str, Any]] = {}
    for binding in contract["bound_inputs"]:
        relative = Path(binding["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise DataCapabilityInventoryError("bound input path escapes repository")
        target = (resolved_repo / relative).resolve(strict=True)
        if not target.is_relative_to(resolved_repo):
            raise DataCapabilityInventoryError("bound input path escapes repository")
        observed_sha = sha256_file(target)
        if observed_sha != binding["sha256"]:
            raise DataCapabilityInventoryError(
                f"bound input SHA-256 mismatch for {binding['alias']}"
            )
        payload = json.loads(target.read_text(encoding="utf-8"))
        if payload.get("schema_version") != binding["schema_version"]:
            raise DataCapabilityInventoryError(
                f"bound input schema mismatch for {binding['alias']}"
            )
        payloads[binding["alias"]] = payload
        metadata[binding["alias"]] = {
            "alias": binding["alias"],
            "schema_version": binding["schema_version"],
            "sha256": observed_sha,
        }

    registry_binding = next(
        row for row in contract["bound_inputs"] if row["alias"] == _REGISTRY_ALIAS
    )
    lock_binding = next(
        row for row in contract["bound_inputs"] if row["alias"] == _REGISTRY_LOCK_ALIAS
    )
    validate_registry_files(
        registry_path=resolved_repo / registry_binding["path"],
        lock_path=resolved_repo / lock_binding["path"],
        repo_root=resolved_repo,
    )
    validate_candidate_interface_audit(
        payloads[_CANDIDATE_AUDIT_ALIAS],
        contract=payloads[_CANDIDATE_CONTRACT_ALIAS],
    )
    return payloads, metadata


def _freshness(
    latest: str | None,
    *,
    as_of: str,
    fresh_max_days: int,
) -> dict[str, Any]:
    if latest is None:
        return {
            "latest_observation": None,
            "calendar_lag_days": None,
            "status": "unknown",
        }
    latest_day = date.fromisoformat(latest[:10])
    audit_day = date.fromisoformat(as_of)
    lag = (audit_day - latest_day).days
    if lag < 0:
        raise DataCapabilityInventoryError("latest observation is after fixed audit date")
    return {
        "latest_observation": latest,
        "calendar_lag_days": lag,
        "status": "fresh" if lag <= fresh_max_days else "stale",
    }


def _coverage_status(summary: dict[str, Any] | None) -> str:
    if summary is None or summary["matched_files"] == 0:
        return "unavailable"
    if summary["read_error_files"]:
        return "incomplete_read_errors"
    return f"present_{summary['freshness']['status']}"


def _cadence_coverage(
    cell: dict[str, Any],
    *,
    interface: str,
) -> dict[str, Any]:
    summary = cell["interfaces"].get(interface)
    if summary is None:
        return {
            "cadence": cell["cadence"],
            "status": "unavailable",
            "matched_files": 0,
        }
    return {
        "cadence": cell["cadence"],
        "status": _coverage_status(summary),
        **summary,
    }


def _audited_family(
    *,
    candidate: dict[str, Any],
    audited: dict[str, Any],
    as_of: str,
    fresh_max_days: int,
) -> dict[str, Any]:
    underlying = [
        _cadence_coverage(cell, interface="underlying")
        for cell in audited["cadences"]
    ]
    option = [
        _cadence_coverage(cell, interface="option_premium")
        for cell in audited["cadences"]
    ]
    supporting_latest = [
        row["coverage"]["maximum_observation_timestamp"]
        for row in [*underlying, *option]
        if row["status"] != "unavailable"
        and row["coverage"]["maximum_observation_timestamp"] is not None
    ]
    overall_freshness = _freshness(
        min(supporting_latest) if supporting_latest else None,
        as_of=as_of,
        fresh_max_days=fresh_max_days,
    )
    all_interfaces_present = all(
        row["matched_files"] > 0 and row["read_error_files"] == 0
        for row in [*underlying, *option]
    )
    daily_option = next(row for row in option if row["cadence"] == "daily")
    daily_ohlc_violations = daily_option.get("ohlc_quality", {}).get(
        "violation_rows",
        0,
    )
    in_frozen_universe = candidate["instrument_family"] in _EXPECTED_P1_UNIVERSE
    limitations = [
        "candidate_interface_evidence_is_stale",
        "historical_vendor_visibility_is_unproven",
        "exact_exchange_expiry_is_unavailable",
        "append_only_acquisition_lineage_is_unavailable",
    ]
    if daily_ohlc_violations:
        limitations.append("daily_option_ohlc_coherence_violations_observed")

    if in_frozen_universe:
        causal_status = "data_blocked"
        fail_closed_reason = [
            "stale_explicit_candidate_interface_evidence",
            "exact_exchange_expiry_unavailable",
            "decision_time_availability_unproven",
            "causal_signal_day_iv_history_with_availability_unavailable",
            "selected_option_leg_not_bound_to_enrollment_artifacts",
            "immutable_daily_enrollment_ledger_not_evidenced",
        ]
        if daily_ohlc_violations:
            fail_closed_reason.append(
                "daily_option_ohlc_coherence_violations_observed"
            )
    else:
        causal_status = "not_permitted_outside_frozen_universe"
        fail_closed_reason = [
            "outside_frozen_p1_exp_001_universe",
            "stale_explicit_candidate_interface_evidence",
            "decision_time_availability_unproven",
            "exact_exchange_expiry_unavailable",
        ]

    return {
        "instrument_family": candidate["instrument_family"],
        "role": candidate["role"],
        "underlying_coverage": {
            "status": (
                "present_all_declared_cadences"
                if all(row["matched_files"] > 0 for row in underlying)
                else "incomplete"
            ),
            "cadences": underlying,
        },
        "option_premium_coverage": {
            "status": (
                "present_all_declared_cadences"
                if all(row["matched_files"] > 0 for row in option)
                else "incomplete"
            ),
            "cadences": option,
            "premium_ohlc": (
                "present_with_daily_quality_findings"
                if daily_ohlc_violations
                else "present"
            ),
            "exact_exchange_expiry": "unavailable",
            "historical_bid_ask": "unavailable_not_synthesized",
            "contract_delta": "unavailable_not_synthesized",
            "decision_time_availability": "unproven",
        },
        "liquidity_proxy": {
            "status": "observed_public_safe_aggregate",
            "cadences": [
                {
                    "cadence": row["cadence"],
                    **row["liquidity_proxy"],
                }
                for row in option
                if row["status"] != "unavailable"
            ],
            "ranking_or_performance_used": False,
        },
        "freshness": overall_freshness,
        "historical_research_usability": {
            "retrospective_finalized_bare_k_premium_ohlc": (
                "usable_with_limitations"
                if all_interfaces_present
                else "data_blocked"
            ),
            "causal_p1_iv_experiment": causal_status,
            "operational_observability": "data_blocked",
            "limitations": limitations,
        },
        "usable_for_p1_exp_001": False,
        "fail_closed_reason": fail_closed_reason,
    }


def build_inventory(
    *,
    contract: dict[str, Any],
    contract_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    validate_contract(contract)
    payloads, metadata = _load_bound_inputs(contract=contract, repo_root=repo_root)

    registry = payloads[_REGISTRY_ALIAS]
    experiment = registry["selection"]["selected_experiment"]
    design = experiment["design"]
    registry_universe = sorted(
        f"{row['exchange']}.{row['product']}" for row in design["universe"]
    )
    if experiment["experiment_id"] != "P1-EXP-001":
        raise DataCapabilityInventoryError("selected experiment drifted")
    if registry_universe != sorted(_EXPECTED_P1_UNIVERSE):
        raise DataCapabilityInventoryError("registry experiment universe drifted")

    candidate_audit = payloads[_CANDIDATE_AUDIT_ALIAS]
    audit_rows = {
        row["instrument_family"]: row
        for row in candidate_audit["decision_surface"]
    }
    as_of = contract["audit_as_of_local_date"]
    fresh_max_days = contract["freshness_policy"]["fresh_max_calendar_lag_days"]
    families = [
        _audited_family(
            candidate=candidate,
            audited=audit_rows[candidate["instrument_family"]],
            as_of=as_of,
            fresh_max_days=fresh_max_days,
        )
        for candidate in contract["candidate_universe"]
    ]

    inventory = {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "inventory_id": contract["contract_id"],
        "issue_number": 43,
        "audit_as_of_local_date": as_of,
        "timezone": contract["timezone"],
        "research_boundary": {
            "evidence_mode": (
                "explicit_read_only_candidate_interface_audit_plus_"
                "hash_bound_repository_aggregates"
            ),
            "explicit_candidate_interface_audited": True,
            "candidate_interface_access": "read_only",
            "inventory_builder_bound_aggregate_only": True,
            "source_refresh_performed": False,
            "strategy_outcomes_accessed": False,
            "candidate_universe_predeclared_before_capability_classification": True,
        },
        "contract": {
            "alias": "repository://paired-trading/phase1-data-capability-contract-v1",
            "schema_version": contract["schema_version"],
            "sha256": sha256_file(contract_path),
        },
        "candidate_interface_evidence": {
            "alias": _CANDIDATE_AUDIT_ALIAS,
            "schema_version": candidate_audit["schema_version"],
            "sha256": metadata[_CANDIDATE_AUDIT_ALIAS]["sha256"],
            "source_inventory_sha256": candidate_audit["source"]["inventory_sha256"],
            "matched_candidate_files": candidate_audit["source"][
                "matched_candidate_files"
            ],
            "runtime_binding": "QUANT_DATA_ROOT",
            "access": "read_only",
        },
        "frozen_experiment": {
            "experiment_id": experiment["experiment_id"],
            "registry_alias": _REGISTRY_ALIAS,
            "registry_sha256": metadata[_REGISTRY_ALIAS]["sha256"],
            "design_sha256": payloads[_REGISTRY_LOCK_ALIAS]["selected_experiment"][
                "canonical_design_sha256"
            ],
            "universe": _EXPECTED_P1_UNIVERSE,
            "universe_changes_require_new_registry_version_and_experiment_id": True,
        },
        "status_definitions": contract["status_definitions"],
        "evidence_relationships": [
            {
                "alias": _CANDIDATE_AUDIT_ALIAS,
                "sha256": metadata[_CANDIDATE_AUDIT_ALIAS]["sha256"],
                "role": (
                    "primary_six_family_per_cadence_interface_capability_"
                    "freshness_and_quality_evidence"
                ),
            },
            {
                "alias": _OPTION_AUDIT_ALIAS,
                "sha256": metadata[_OPTION_AUDIT_ALIAS]["sha256"],
                "role": "prior_au_ag_option_audit_continuity_reference",
            },
            {
                "alias": _LIQUID_PREMIUM_ALIAS,
                "sha256": metadata[_LIQUID_PREMIUM_ALIAS]["sha256"],
                "role": "prior_au_ag_predeclared_liquidity_reference",
            },
            {
                "alias": _CONTINUOUS_ALIAS,
                "sha256": metadata[_CONTINUOUS_ALIAS]["sha256"],
                "role": "prior_au_ag_causal_roll_provenance_boundary",
            },
            {
                "alias": _UNDERLYING_CORPUS_ALIAS,
                "sha256": metadata[_UNDERLYING_CORPUS_ALIAS]["sha256"],
                "role": "prior_au_ag_retrospective_corpus_boundary",
            },
            {
                "alias": _RETROSPECTIVE_ALIAS,
                "sha256": metadata[_RETROSPECTIVE_ALIAS]["sha256"],
                "role": "retrospective_usability_and_observability_boundary",
            },
            {
                "alias": _RAW_AVAILABILITY_ALIAS,
                "sha256": metadata[_RAW_AVAILABILITY_ALIAS]["sha256"],
                "role": "acquisition_lineage_and_historical_availability_boundary",
            },
        ],
        "decision_surface": families,
        "decision": {
            "status": "data_blocked",
            "usable_family_count": sum(
                row["usable_for_p1_exp_001"] for row in families
            ),
            "usable_families": [
                row["instrument_family"]
                for row in families
                if row["usable_for_p1_exp_001"]
            ],
            "p1_exp_001_action": "stop_as_data_blocked",
            "issue_45_may_start_outcome_work": False,
            "next_data_gate": [
                "bind fresh decision-time underlying and selected-option closes",
                "resolve observed daily option OHLC coherence findings",
                "bind exact exchange expiry and observed close timestamps",
                "seal append-only enrollment ledgers with acquisition availability",
                "establish causal same-product signal-day IV history",
                "retain the frozen SHFE.ag and SHFE.au experiment universe",
            ],
        },
        "public_safety": {
            "local_paths": False,
            "local_usernames": False,
            "source_filenames": False,
            "contract_identifiers": False,
            "raw_market_rows": False,
            "credentials": False,
            "strategy_outcomes": False,
            "instrument_performance_ranking": False,
            "bid_ask_synthesis": False,
            "delta_synthesis": False,
        },
    }
    validate_inventory(inventory, contract=contract)
    return inventory


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(key.lower())
            keys.extend(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(_walk_keys(child))
    return keys


def validate_inventory(inventory: dict[str, Any], *, contract: dict[str, Any]) -> None:
    validate_contract(contract)
    if inventory.get("schema_version") != INVENTORY_SCHEMA_VERSION:
        raise DataCapabilityInventoryError("unexpected inventory schema")
    if inventory.get("audit_as_of_local_date") != AUDIT_AS_OF_LOCAL_DATE:
        raise DataCapabilityInventoryError("inventory fixed audit date drifted")
    rows = inventory.get("decision_surface", [])
    families = [row.get("instrument_family") for row in rows]
    if families != _EXPECTED_FAMILIES:
        raise DataCapabilityInventoryError("inventory candidate universe drifted")
    if inventory.get("frozen_experiment", {}).get("universe") != _EXPECTED_P1_UNIVERSE:
        raise DataCapabilityInventoryError("inventory experiment universe drifted")
    evidence = inventory.get("candidate_interface_evidence", {})
    if evidence.get("matched_candidate_files", 0) <= 0:
        raise DataCapabilityInventoryError("candidate interface evidence is absent")
    if evidence.get("access") != "read_only":
        raise DataCapabilityInventoryError("candidate interface access drifted")

    for row in rows:
        usable = row.get("usable_for_p1_exp_001")
        if not isinstance(usable, bool):
            raise DataCapabilityInventoryError("P1 usability must be boolean")
        if not usable and not row.get("fail_closed_reason"):
            raise DataCapabilityInventoryError("blocked family lacks fail-closed reason")
        if len(row["underlying_coverage"]["cadences"]) != len(_EXPECTED_CADENCES):
            raise DataCapabilityInventoryError("underlying cadence surface drifted")
        if len(row["option_premium_coverage"]["cadences"]) != len(
            _EXPECTED_CADENCES
        ):
            raise DataCapabilityInventoryError("option cadence surface drifted")
        if (
            row["instrument_family"] not in _EXPECTED_P1_UNIVERSE
            and "outside_frozen_p1_exp_001_universe" not in row["fail_closed_reason"]
        ):
            raise DataCapabilityInventoryError("non-registry family was not blocked")

    usable = [row["instrument_family"] for row in rows if row["usable_for_p1_exp_001"]]
    decision = inventory.get("decision", {})
    if decision.get("usable_family_count") != len(usable):
        raise DataCapabilityInventoryError("usable family count does not reconcile")
    if decision.get("usable_families") != usable:
        raise DataCapabilityInventoryError("usable family list does not reconcile")
    if not usable:
        if decision.get("status") != "data_blocked":
            raise DataCapabilityInventoryError("empty usable universe must fail closed")
        if decision.get("p1_exp_001_action") != "stop_as_data_blocked":
            raise DataCapabilityInventoryError("empty usable universe must stop #45")
        if decision.get("issue_45_may_start_outcome_work") is not False:
            raise DataCapabilityInventoryError("issue #45 must remain blocked")

    forbidden_keys = sorted(set(_walk_keys(inventory)) & _FORBIDDEN_EXACT_KEYS)
    if forbidden_keys:
        raise DataCapabilityInventoryError(
            f"forbidden outcome or selection fields: {forbidden_keys}"
        )
    encoded = pretty_json_bytes(inventory).decode("utf-8")
    for forbidden in _FORBIDDEN_TEXT:
        if forbidden in encoded:
            raise DataCapabilityInventoryError("public-safety text boundary violated")
    if _RAW_CONTRACT_ID.search(encoded):
        raise DataCapabilityInventoryError("raw contract identifier is forbidden")
