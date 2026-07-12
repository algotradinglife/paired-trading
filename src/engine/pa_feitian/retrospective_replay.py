"""Epistemic gate for finalized-vintage M6 historical replay.

This module separates a retrospective research reconstruction from an
operational claim that data was observable at the historical decision time.
Append-only acquisition lineage is an M8 requirement.  Its absence is an
explicit limitation of retrospective replay and a hard blocker for operational
observability; it is not a blocker for a hash-pinned, decision-time-truncated
replay of finalized data.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from engine.pa_feitian.manifest import sha256_file
from engine.pa_feitian.raw_availability import EVIDENCE_FIELDS


CONTRACT_VERSION = "pa_feitian_m6_epistemic_replay_contract_v1"
ARTIFACT_VERSION = "pa_feitian_m6_retrospective_replay_evidence_v1"
TASK_ID = "t_23c01908"
RETROSPECTIVE_MODE = "retrospective_finalized"
OPERATIONAL_MODE = "operational_observability"
EXCLUDED_CAPABILITIES = {
    "date_only_iv_or_regime",
    "options_or_option_premiums",
    "delta_or_dte",
    "dd_line",
    "bid_or_ask",
    "performance_or_strategy_screening",
    "m7",
    "execution",
}


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _utc(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def truncate_finalized_at_decision(
    frame: pd.DataFrame,
    *,
    decision_ts_utc: str,
    timestamp_column: str = "datetime",
    source_timezone: str = "Asia/Shanghai",
) -> pd.DataFrame:
    """Filter finalized data at the decision instant before any derivation.

    Naive timestamps are interpreted only through the declared source timezone.
    The function does not discover, select, or reselect contracts.
    """

    if timestamp_column not in frame:
        raise ValueError(f"missing timestamp column {timestamp_column!r}")
    timestamps = pd.to_datetime(frame[timestamp_column])
    if timestamps.isna().any():
        raise ValueError("timestamps must be complete")
    if timestamps.dt.tz is None:
        comparable = timestamps.dt.tz_localize(
            source_timezone, ambiguous="raise", nonexistent="raise"
        ).dt.tz_convert("UTC")
    else:
        comparable = timestamps.dt.tz_convert("UTC")
    cutoff = pd.Timestamp(_utc(decision_ts_utc, "decision_ts_utc"))
    return frame.loc[comparable <= cutoff].copy().reset_index(drop=True)


def validate_contract(contract: dict[str, Any]) -> None:
    """Reject widened modes, scope, rules, or milestone ownership."""

    if contract.get("schema_version") != CONTRACT_VERSION:
        raise ValueError("unsupported epistemic replay contract schema")
    if contract.get("hermes_task") != TASK_ID:
        raise ValueError("wrong Hermes task")
    modes = contract.get("claim_modes", {})
    retrospective = modes.get(RETROSPECTIVE_MODE, {})
    operational = modes.get(OPERATIONAL_MODE, {})
    if (
        retrospective.get("missing_acquisition_metadata_blocks_claim") is not False
        or retrospective.get("finalized_vintage_required") is not True
        or retrospective.get("decision_timestamp_truncation_required") is not True
        or retrospective.get("causal_roll_schedule_allowed") is not True
    ):
        raise ValueError("retrospective finalized gate was weakened")
    if (
        operational.get("missing_acquisition_metadata_blocks_claim") is not True
        or operational.get("append_only_acquisition_manifest_required") is not True
        or operational.get("requirement_owner") != "M8"
        or operational.get("status") != "blocked_in_m6"
        or operational.get("causal_roll_schedule_allowed") is not False
    ):
        raise ValueError("operational observability boundary was weakened")
    rules = contract.get("replay_rules", {})
    required_rules = {
        "filter_before_calendar_or_resample": True,
        "future_rows_allowed": False,
        "explicit_hash_pinned_sources_only": True,
        "declared_roll_rule_only": True,
        "contract_selection": "none",
        "contract_reselection": False,
        "directory_discovery": False,
        "proxy_or_imputation": False,
    }
    if rules != required_rules:
        raise ValueError("retrospective replay rules drifted")
    scope = contract.get("scope", {})
    if scope.get("source_ids") != [
        "shfe_au0_underlying_5min",
        "shfe_ag0_underlying_5min",
    ] or scope.get("decision_ids") != [
        "paft_scorecard_0001_kq_m_shfe_au_20260313000000",
        "paft_scorecard_0002_kq_m_shfe_au_20260318000000",
        "paft_scorecard_0003_kq_m_shfe_ag_20260515000000",
        "paft_scorecard_0004_kq_m_shfe_ag_20260602000000",
    ]:
        raise ValueError("retrospective replay scope must remain frozen")
    if set(contract.get("excluded_capabilities", [])) != EXCLUDED_CAPABILITIES:
        raise ValueError("excluded capability boundary drifted")


def _source_ref(contract: dict[str, Any], name: str) -> dict[str, str]:
    try:
        return next(row for row in contract["source_artifacts"] if row["name"] == name)
    except StopIteration as exc:
        raise ValueError(f"missing source artifact {name!r}") from exc


def build_replay_evidence(
    *,
    contract: dict[str, Any],
    contract_path: Path,
    protocol: dict[str, Any],
    protocol_path: Path,
    historical_audit: dict[str, Any],
    historical_audit_path: Path,
    provenance: dict[str, Any],
    provenance_path: Path,
    availability: dict[str, Any],
    availability_path: Path,
) -> dict[str, Any]:
    """Build the mode-separated evidence artifact from merged, pinned evidence."""

    validate_contract(contract)
    supplied = {
        "historical_asof_protocol": (protocol, protocol_path),
        "historical_asof_source_audit": (historical_audit, historical_audit_path),
        "continuous_provenance": (provenance, provenance_path),
        "raw_availability_audit": (availability, availability_path),
    }
    sources: list[dict[str, str]] = []
    for name, (_payload, path) in supplied.items():
        declared = _source_ref(contract, name)
        observed = sha256_file(path)
        if declared["path"] != str(path) or declared["sha256"] != observed:
            raise ValueError(f"source artifact drift for {name}")
        sources.append({"name": name, "path": str(path), "sha256": observed})

    bound = {row["source_id"]: row for row in provenance["bound_candidates"]}
    decisions = {row["id"]: row for row in protocol["decisions"]}
    universe = {row["id"]: row for row in protocol["universe"]}
    missing_counts = availability["gap_summary"]["gap_counts"]
    if any(missing_counts.get(f"missing_{field}") != 210 for field in EVIDENCE_FIELDS):
        raise ValueError("raw acquisition gap evidence drifted")
    aggregation_rows = historical_audit.get("aggregation_audit", [])
    if (
        len(aggregation_rows) != 16
        or {row.get("decision_id") for row in aggregation_rows}
        != set(contract["scope"]["decision_ids"])
        or {row.get("level") for row in aggregation_rows}
        != set(contract["scope"]["derived_levels"])
        or any(
            row.get("strict_asof_passed") is not True
            or row.get("minimum_rows_met") is not True
            for row in aggregation_rows
        )
    ):
        raise ValueError("historical strict-as-of aggregation evidence drifted")

    decision_gates: list[dict[str, Any]] = []
    for decision_id in contract["scope"]["decision_ids"]:
        decision = decisions[decision_id]
        product = universe[decision["universe_id"]]["product"]
        candidate = bound[f"shfe_{product}0_underlying_5min"]
        decision_gates.append(
            {
                "decision_id": decision_id,
                "decision_ts_utc": decision["decision_ts_utc"],
                "source_id": candidate["source_id"],
                "source_sha256": candidate["sha256"],
                "raw_input_set_sha256": candidate["raw_input_set_sha256"],
                "causal_roll_records_sha256": candidate["causal_roll_schedule"][
                    "records_sha256"
                ],
                "cutoff_rule": "timestamp <= decision_ts_utc before calendar assignment or resampling",
                "contract_selection": "none",
                "contract_reselection": False,
                "retrospective_finalized_claim": "allowed_with_limitations",
                "operational_observability_claim": "blocked_missing_acquisition_metadata",
                "limitations": [
                    "finalized current-vintage bytes may contain later vendor corrections or revisions",
                    "historical acquisition time and point-in-time vendor visibility are unproven",
                    "survivorship and deletion history of the vendor dataset are unobservable",
                    "embedded calendar-date main_month/is_roll annotations are not consumed",
                ],
            }
        )

    artifact = {
        "schema_version": ARTIFACT_VERSION,
        "hermes_task": TASK_ID,
        "contract": {"path": str(contract_path), "sha256": sha256_file(contract_path)},
        "source_artifacts": sources,
        "evidence_identity_sha256": _canonical_hash(sources),
        "acquisition_metadata": {
            "complete_inputs": 0,
            "inputs_with_gaps": 210,
            "required_for_retrospective_finalized": False,
            "required_for_operational_observability": True,
            "append_only_manifest_milestone": "M8",
        },
        "decision_gates": decision_gates,
        "mode_results": {
            RETROSPECTIVE_MODE: {
                "status": "enabled_with_explicit_limitations",
                "causal_roll_schedule_reuse": True,
                "missing_acquisition_metadata_is_blocker": False,
            },
            OPERATIONAL_MODE: {
                "status": "blocked",
                "causal_roll_schedule_reuse": False,
                "missing_acquisition_metadata_is_blocker": True,
            },
        },
        "narrowest_enabled_capability": (
            "finalized-vintage, decision-time-truncated descriptive D/W/60/15 "
            "underlying replay for the four frozen au/ag decisions using only the "
            "hash-pinned continuous reconstruction and declared causal roll schedule"
        ),
        "excluded_capabilities": contract["excluded_capabilities"],
        "promotion": {
            "score_today": False,
            "performance_or_strategy_screening": False,
            "m7": False,
            "execution": False,
        },
    }
    validate_replay_evidence(artifact)
    return artifact


def validate_replay_evidence(artifact: dict[str, Any]) -> None:
    """Enforce the asymmetric retrospective/operational claim gate."""

    if artifact.get("schema_version") != ARTIFACT_VERSION:
        raise ValueError("unsupported retrospective replay evidence schema")
    if artifact.get("hermes_task") != TASK_ID:
        raise ValueError("wrong Hermes task")
    if set(artifact.get("excluded_capabilities", [])) != EXCLUDED_CAPABILITIES:
        raise ValueError("excluded capability boundary drifted")
    metadata = artifact.get("acquisition_metadata", {})
    if (
        metadata.get("complete_inputs") != 0
        or metadata.get("inputs_with_gaps") != 210
        or metadata.get("required_for_retrospective_finalized") is not False
        or metadata.get("required_for_operational_observability") is not True
        or metadata.get("append_only_manifest_milestone") != "M8"
    ):
        raise ValueError("acquisition metadata boundary drifted")
    modes = artifact.get("mode_results", {})
    if modes.get(RETROSPECTIVE_MODE) != {
        "status": "enabled_with_explicit_limitations",
        "causal_roll_schedule_reuse": True,
        "missing_acquisition_metadata_is_blocker": False,
    }:
        raise ValueError("retrospective finalized mode must remain limited and enabled")
    if modes.get(OPERATIONAL_MODE) != {
        "status": "blocked",
        "causal_roll_schedule_reuse": False,
        "missing_acquisition_metadata_is_blocker": True,
    }:
        raise ValueError("operational observability must remain blocked")
    gates = artifact.get("decision_gates", [])
    if len(gates) != 4 or len({row.get("decision_id") for row in gates}) != 4:
        raise ValueError("evidence must cover exactly four frozen decisions")
    for row in gates:
        _utc(row.get("decision_ts_utc"), "decision_ts_utc")
        if (
            row.get("cutoff_rule")
            != "timestamp <= decision_ts_utc before calendar assignment or resampling"
            or row.get("contract_selection") != "none"
            or row.get("contract_reselection") is not False
            or row.get("retrospective_finalized_claim") != "allowed_with_limitations"
            or row.get("operational_observability_claim")
            != "blocked_missing_acquisition_metadata"
            or len(row.get("limitations", [])) != 4
        ):
            raise ValueError("decision replay gate drifted")
        for field in ("source_sha256", "raw_input_set_sha256", "causal_roll_records_sha256"):
            if not str(row.get(field, "")).startswith("sha256:"):
                raise ValueError(f"decision gate must pin {field}")
    if any(artifact.get("promotion", {}).values()):
        raise ValueError("retrospective replay cannot promote downstream capability")


def verify_replay_evidence(
    artifact: dict[str, Any],
    *,
    contract: dict[str, Any],
    contract_path: Path,
    protocol: dict[str, Any],
    protocol_path: Path,
    historical_audit: dict[str, Any],
    historical_audit_path: Path,
    provenance: dict[str, Any],
    provenance_path: Path,
    availability: dict[str, Any],
    availability_path: Path,
) -> dict[str, Any]:
    validate_replay_evidence(artifact)
    rebuilt = build_replay_evidence(
        contract=contract,
        contract_path=contract_path,
        protocol=protocol,
        protocol_path=protocol_path,
        historical_audit=historical_audit,
        historical_audit_path=historical_audit_path,
        provenance=provenance,
        provenance_path=provenance_path,
        availability=availability,
        availability_path=availability_path,
    )
    if rebuilt != artifact:
        raise ValueError("retrospective replay evidence is not reproducible")
    return {
        "ok": True,
        "task": TASK_ID,
        "retrospective_finalized": "enabled_with_explicit_limitations",
        "operational_observability": "blocked",
        "decisions": 4,
        "acquisition_manifest_milestone": "M8",
        "advance_m7": False,
    }
