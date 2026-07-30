"""Deterministic data gate for formal P1 historical replay requests."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

CONTRACT_SCHEMA_VERSION = "pa_feitian_m6_historical_backtest_data_gate_contract_v1"
PROFILE_SCHEMA_VERSION = "pa_feitian_m6_historical_backtest_data_gate_profile_v1"
REQUEST_SCHEMA_VERSION = "pa_feitian_m6_historical_backtest_gate_request_v1"
DECISION_SCHEMA_VERSION = "pa_feitian_m6_historical_backtest_gate_decision_v1"
SOURCE_VERSION_MANIFEST_SCHEMA_VERSION = "pa_feitian_m6_native_source_version_manifest_v1"
AUDIT_AS_OF_LOCAL_DATE = "2026-07-30"
CONTRACT_PUBLIC_PATH = "docs/research/pa-feitian-m6-historical-backtest-data-gate-contract-v1.json"
EXPECTED_FAMILIES = [
    "SHFE.au",
    "SHFE.ag",
    "CZCE.TA",
    "CZCE.MA",
    "SHFE.cu",
    "DCE.i",
]
EXPECTED_CADENCES = ["daily", "hour", "min15", "min5"]
REQUIRED_CADENCES = ["daily", "hour", "min15"]
EXPECTED_INTERFACES = {"underlying"}
EXPECTED_CAPABILITIES = {
    "underlying_ohlcv_oi",
    "exact_decision_close",
    "exchange_session_calendar",
    "causal_roll_ledger",
}
EXPECTED_CAPABILITY_ORDER = [
    "underlying_ohlcv_oi",
    "exact_decision_close",
    "exchange_session_calendar",
    "causal_roll_ledger",
]
EXPECTED_IDENTITY_KEY_FIELDS = ["contract_id", "datetime"]
REQUIRED_UNDERLYING_ROW_FIELDS = {
    "contract_id",
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "open_interest",
}
ALLOWED_UNDERLYING_ROW_FIELDS = REQUIRED_UNDERLYING_ROW_FIELDS | {
    "exchange_trading_date",
    "session_id",
}
EXPECTED_MODES = {"historical_replay", "prospective_shadow", "live"}
FROZEN_REGISTRY_SHA256 = "sha256:f2b77c11317c1f98fe6d4c95f47b2213243322f2f3d4ed6dd1ccbf92d972afa0"
FROZEN_REGISTRY_LOCK_SHA256 = (
    "sha256:d7e36900efb91807a0960922c5cdbc5241ec4ca1988eb477ac6bc5a32c940718"
)
FROZEN_DESIGN_SHA256 = "sha256:4d3026e5eb398752c3c8f207cb5e21d1b2706e7fb68d40ddf31b99132486cb65"
FROZEN_CONTRACT_SHA256 = "sha256:ce8508f1cb6f15d5030e6424404f07c7d2e346811ccbc1bad033f63d4bc3d351"
EXPECTED_REQUEST_FIELDS = {
    "schema_version",
    "request_id",
    "experiment_id",
    "mode",
    "required_capabilities",
    "frozen_design",
    "causal_support",
    "input_bindings",
    "controls",
    "operational_evidence",
}
EXPECTED_FROZEN_DESIGN_FIELDS = {
    "registry_sha256",
    "registry_lock_sha256",
    "canonical_design_sha256",
}
EXPECTED_CAUSAL_SUPPORT_FIELDS = {
    "native_source_version_manifest_sha256",
    "exchange_session_calendar_sha256",
    "causal_roll_ledger_sha256",
}
EXPECTED_BINDING_FIELDS = {
    "binding_id",
    "instrument_family",
    "interface",
    "cadence",
    "source_snapshot_sha256",
    "source_snapshot_binding_kind",
    "filtered_content_sha256",
    "filtered_content_binding_kind",
    "canonicalization_id",
    "identity_key_fields",
    "row_count",
    "decision_cutoff_utc",
    "required_through_utc",
    "minimum_observation_utc",
    "maximum_observation_utc",
    "timestamp_semantics",
    "source_timezone",
    "null_timestamp_rows",
    "duplicate_timestamp_rows",
    "ohlc_violation_rows",
    "nonfinite_or_negative_activity_rows",
    "post_cutoff_rows_in_bound_content",
    "close_timestamp_status",
    "raw_rows_published",
}
EXPECTED_CONTROL_FIELDS = {
    "filter_before_derivation",
    "outcomes_accessed",
    "instrument_selection_uses_outcomes",
    "option_inputs_accessed",
    "proxy_or_imputation",
    "bid_ask_synthesized",
    "delta_synthesized",
    "iv_synthesized",
    "source_refresh_performed",
}
EXPECTED_OPERATIONAL_FIELDS = {
    "append_only_acquisition_manifest_sha256",
    "point_in_time_observability_verified",
    "current_freshness_verified",
    "execution_authorized",
}
EXPECTED_DECISION_FIELDS = {
    "schema_version",
    "request_id",
    "request_sha256",
    "experiment_id",
    "mode",
    "decision",
    "reason_codes",
    "binding_count",
    "evaluated_bindings",
    "required_capabilities",
    "manifest_binding",
    "claim_boundary",
}
EXPECTED_MANIFEST_BINDING_FIELDS = {
    "registry_sha256",
    "registry_lock_sha256",
    "canonical_design_sha256",
    "approved_data_gate_sha256",
    "filtered_input_digest",
    "native_source_version_manifest_sha256",
    "exchange_session_calendar_sha256",
    "causal_roll_ledger_sha256",
}
EXPECTED_EVALUATED_BINDING_FIELDS = {
    "binding_id",
    "instrument_family",
    "interface",
    "cadence",
    "source_snapshot_sha256",
    "filtered_content_sha256",
    "row_count",
    "decision_cutoff_utc",
    "maximum_observation_utc",
    "coverage_lag_days",
    "freshness_status",
}
EXPECTED_CLAIM_BOUNDARY_FIELDS = {
    "finalized_vintage_historical_replay",
    "prospective_shadow_data_input",
    "point_in_time_vendor_observability_claim",
    "strategy_outcomes_authorized",
    "issue_51_unblocked",
    "execution_authorized",
}
CANONICALIZATION_ID = "pa_feitian_filtered_json_rows_v1"
TIMESTAMP_SEMANTICS = "exchange_observation_time_with_declared_timezone"
SOURCE_TIMEZONE = "Asia/Shanghai"
HISTORY_START_UTC = datetime(2021, 5, 31, 16, tzinfo=UTC)
FAMILY_CALENDAR = {
    "SHFE.au": "XSGE",
    "SHFE.ag": "XSGE",
    "SHFE.cu": "XSGE",
    "CZCE.TA": "XZCE",
    "CZCE.MA": "XZCE",
    "DCE.i": "XDCE",
}
EXPECTED_ROLES = {
    "SHFE.au": "continuity_candidate",
    "SHFE.ag": "continuity_candidate",
    "CZCE.TA": "mainstream_candidate",
    "CZCE.MA": "mainstream_candidate",
    "SHFE.cu": "non_czce_control",
    "DCE.i": "non_czce_control",
}
EXCHANGE_CALENDAR = {"SHFE": "XSGE", "CZCE": "XZCE", "DCE": "XDCE"}
EXPECTED_CALENDAR_VERSIONS = {
    "XSGE": "exchange_calendars==4.13.2+XSGE+cn_night_session_v1",
    "XZCE": "exchange_calendars==4.13.2+XZCE+cn_night_session_v1",
    "XDCE": "exchange_calendars==4.13.2+XDCE+cn_night_session_v1",
}
EXPECTED_EXPLORATION_LIMITATIONS = {
    "candidate_interface_evidence_is_stale",
    "historical_vendor_visibility_is_unproven",
    "exact_exchange_expiry_is_unavailable",
    "append_only_acquisition_lineage_is_unavailable",
    "daily_option_ohlc_coherence_violations_observed",
}
EXPECTED_PROFILE_LIMITATIONS = (
    "The profile maps audited capability; it is not a formal run request or an allow decision.",
    "The exploratory swing artifact supplies normalized descriptive views, not exact formal-run input bytes.",
    "A per-run source snapshot hash and exact causally filtered content hash remain mandatory.",
    "No formal allow is possible until a complete native source-version manifest is independently frozen into the contract.",
    "Every prefix is extracted from that approved full version from the frozen history start; genuine missing bars and late listings remain visible for downstream abstention.",
    "Calendar and cadence evidence are recomputed from exchange_calendars 4.13.2 plus the repository CN-futures session patch.",
    "P1-EXP-002 consumes exactly one underlying binding for every frozen family at daily, hour, and min15 cadence; option and min5 rows are excluded.",
    "Historical replay does not establish point-in-time vendor observability, shadow readiness, or live readiness.",
)
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
PUBLIC_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,95}$")
RAW_CONTRACT_ID = re.compile(r"\b(?:SHFE|CZCE|DCE)\.[A-Za-z]+\d", re.IGNORECASE)
TOKEN_PREFIX = re.compile(
    r"(?i)(?:\bgithub_pat_|\bgh[opusr]_|\bsk-(?:proj-)?|\bxox[baprs]-|"
    r"\bAKIA[0-9A-Z]{12,}|\bAIza[0-9A-Za-z_-]{20,}|\bya29\.)"
)
FORBIDDEN_TEXT = (
    "/home/",
    "/mnt/",
    "/var/",
    "/tmp/",
    "/root/",
    "\\Users\\",
    ".parquet",
    ".csv",
)
FORBIDDEN_PUBLIC_KEYS = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|secret|password|private[_-]?key|credential)"
)


class HistoricalBacktestGateError(ValueError):
    """Raised when a gate contract, request, or artifact fails closed."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, nested in pairs:
        if key in value:
            raise HistoricalBacktestGateError(f"duplicate JSON key: {key}")
        value[key] = nested
    return value


def strict_json_loads(value: str) -> Any:
    """Decode standards-compliant JSON while rejecting duplicate object keys."""

    try:
        return json.loads(
            value,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda constant: (_ for _ in ()).throw(
                HistoricalBacktestGateError(f"non-standard JSON constant: {constant}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise HistoricalBacktestGateError(f"invalid JSON: {exc}") from exc


def pretty_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return sha256_bytes(encoded)


def _parse_utc(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise HistoricalBacktestGateError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HistoricalBacktestGateError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise HistoricalBacktestGateError(
                "datetime values in filtered rows must be timezone-aware"
            )
        return _utc_text(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise HistoricalBacktestGateError("filtered row mapping keys must be strings")
        return {key: _json_safe(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(nested) for nested in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise HistoricalBacktestGateError("filtered rows cannot contain nonfinite values")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise HistoricalBacktestGateError(
        f"filtered rows contain unsupported value type {type(value).__name__}"
    )


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and HASH_PATTERN.fullmatch(value) is not None


def _assert_public_safe(value: Any) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if FORBIDDEN_PUBLIC_KEYS.search(str(key)) and nested is not False:
                raise HistoricalBacktestGateError("public output contains a credential field")
            _assert_public_safe(str(key))
            _assert_public_safe(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_public_safe(nested)
    elif isinstance(value, str):
        lowered = value.lower()
        if any(token.lower() in lowered for token in FORBIDDEN_TEXT):
            raise HistoricalBacktestGateError("public output contains local source text")
        if RAW_CONTRACT_ID.search(value):
            raise HistoricalBacktestGateError("public output contains a raw contract identifier")
        if TOKEN_PREFIX.search(value):
            raise HistoricalBacktestGateError("public output contains a token prefix")


def _bound_evidence_by_alias(contract: dict[str, Any]) -> dict[str, dict[str, str]]:
    rows = contract.get("bound_evidence")
    if not isinstance(rows, list) or not rows:
        raise HistoricalBacktestGateError("bound evidence is invalid")
    expected_fields = {"alias", "path", "schema_version", "sha256"}
    if any(not isinstance(row, dict) or set(row) != expected_fields for row in rows):
        raise HistoricalBacktestGateError("bound evidence fields differ from exact allowlist")
    aliases = [row["alias"] for row in rows]
    if len(aliases) != len(set(aliases)):
        raise HistoricalBacktestGateError("bound evidence aliases are duplicated")
    return {row["alias"]: row for row in rows}


def validate_contract(contract: dict[str, Any]) -> None:
    if canonical_hash(contract) != FROZEN_CONTRACT_SHA256:
        raise HistoricalBacktestGateError("approved data-gate contract digest drifted")
    if contract.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        raise HistoricalBacktestGateError("unexpected historical data-gate schema")
    if contract.get("issue_number") != 50:
        raise HistoricalBacktestGateError("issue binding drifted")
    if contract.get("audit_as_of_local_date") != AUDIT_AS_OF_LOCAL_DATE:
        raise HistoricalBacktestGateError("audit date drifted")
    if contract.get("timezone") != SOURCE_TIMEZONE:
        raise HistoricalBacktestGateError("source timezone drifted")
    families = [row.get("instrument_family") for row in contract.get("candidate_universe", [])]
    if families != EXPECTED_FAMILIES:
        raise HistoricalBacktestGateError("candidate universe or order drifted")
    evidence = _bound_evidence_by_alias(contract)
    if set(evidence) != {
        "candidate_interface_audit",
        "candidate_capability_inventory",
        "exploratory_swing_views",
        "epistemic_replay_contract",
        "retrospective_replay_evidence",
        "hypothesis_registry_v2",
        "hypothesis_registry_v2_lock",
    }:
        raise HistoricalBacktestGateError("bound evidence set drifted")
    for row in evidence.values():
        if not _is_sha256(row.get("sha256")) or str(row.get("path", "")).startswith("/"):
            raise HistoricalBacktestGateError("bound evidence identity is invalid")

    modes = contract.get("mode_policy", {})
    historical = modes.get("historical_replay", {})
    shadow = modes.get("prospective_shadow", {})
    live = modes.get("live", {})
    if (
        historical.get("append_only_acquisition_manifest_required") is not False
        or historical.get("finalized_immutable_snapshot_required") is not True
        or historical.get("independently_approved_native_source_version_required") is not True
        or historical.get("exact_filtered_content_binding_required") is not True
        or historical.get("decision_timestamp_cutoff_required") is not True
        or historical.get("point_in_time_vendor_observability_claim_allowed") is not False
    ):
        raise HistoricalBacktestGateError("historical replay boundary was weakened")
    if (
        shadow.get("append_only_acquisition_manifest_required") is not True
        or shadow.get("exact_filtered_content_binding_required") is not True
        or shadow.get("current_freshness_required") is not True
        or shadow.get("point_in_time_vendor_observability_required") is not True
    ):
        raise HistoricalBacktestGateError("shadow boundary was weakened")
    if (
        live.get("authorized_by_this_gate") is not False
        or live.get("status") != "deny_execution_outside_data_gate"
    ):
        raise HistoricalBacktestGateError("live boundary was weakened")

    binding = contract.get("binding_policy", {})
    if (
        binding.get("canonicalization_id") != CANONICALIZATION_ID
        or binding.get("manifest_membership_hash_is_sufficient") is not False
        or binding.get("source_snapshot_binding_kind")
        != "immutable_snapshot_or_acquisition_version"
        or binding.get("filtered_content_binding_kind") != "exact_causally_filtered_row_content"
        or binding.get("source_snapshot_sha256_required") is not True
        or binding.get("filtered_content_sha256_required") is not True
        or binding.get("filter_before_derivation") is not True
        or binding.get("future_rows_in_bound_content") != 0
        or binding.get("maximum_coverage_lag_days") != 7
        or binding.get("timestamp_semantics") != TIMESTAMP_SEMANTICS
        or binding.get("source_timezone") != SOURCE_TIMEZONE
        or binding.get("approved_data_gate_sha256_kind") != "canonical_json_sha256"
        or binding.get("source_snapshot_schema_version")
        != "pa_feitian_causal_underlying_snapshot_v1"
        or binding.get("source_snapshot_scope_fields")
        != ["schema_version", "instrument_family", "cadence", "records"]
        or (
            binding.get("approved_native_source_version_manifest_sha256") is not None
            and not _is_sha256(binding.get("approved_native_source_version_manifest_sha256"))
        )
        or binding.get("native_source_version_manifest_schema_version")
        != SOURCE_VERSION_MANIFEST_SCHEMA_VERSION
        or binding.get("complete_prefix_extraction")
        != "all_approved_native_rows_from_history_start_through_decision_cutoff"
        or binding.get("calendar_versions") != EXPECTED_CALENDAR_VERSIONS
        or binding.get("session_slot_policy")
        != "frozen_exchange_sessions_and_family_night_segments"
        or binding.get("causal_support_artifact_schemas")
        != {
            "native_source_version_manifest": SOURCE_VERSION_MANIFEST_SCHEMA_VERSION,
            "exchange_session_calendar": "pa_feitian_exchange_session_calendar_binding_v2",
            "causal_roll_ledger": "pa_feitian_causal_roll_ledger_binding_v1",
        }
        or binding.get("duplicate_identity") != "composite_identity_key_fields_not_timestamp_alone"
        or binding.get("required_underlying_fields")
        != ["open", "high", "low", "close", "volume", "open_interest"]
    ):
        raise HistoricalBacktestGateError("filtered-content binding policy drifted")
    fail_closed = contract.get("fail_closed_policy", {})
    expected_zero = (
        "null_timestamp_rows",
        "duplicate_timestamp_rows",
        "ohlc_violation_rows",
        "nonfinite_or_negative_activity_rows",
        "post_cutoff_rows_in_bound_content",
    )
    if any(fail_closed.get(field) != 0 for field in expected_zero):
        raise HistoricalBacktestGateError("quality fail-closed policy drifted")
    if (
        fail_closed.get("close_timestamp") != "verified"
        or fail_closed.get("exchange_session_calendar_binding") != "verified"
        or fail_closed.get("causal_roll_ledger_binding") != "verified"
        or fail_closed.get("option_inputs") != "forbidden"
        or fail_closed.get("synthesis_of_iv_bid_ask_or_delta") is not False
        or fail_closed.get("outcome_access_or_selection") is not False
        or fail_closed.get("source_refresh_or_mutation") is not False
    ):
        raise HistoricalBacktestGateError("capability fail-closed policy drifted")
    if set(contract.get("capabilities", [])) != EXPECTED_CAPABILITIES:
        raise HistoricalBacktestGateError("capability vocabulary drifted")
    policy = contract.get("p1_exp_002_input_policy", {})
    if (
        policy.get("experiment_id") != "P1-EXP-002"
        or policy.get("registry_sha256") != FROZEN_REGISTRY_SHA256
        or policy.get("registry_lock_sha256") != FROZEN_REGISTRY_LOCK_SHA256
        or policy.get("canonical_design_sha256") != FROZEN_DESIGN_SHA256
        or policy.get("allowed_mode") != "historical_replay"
        or policy.get("request_scope") != "one_decision_timestamp"
        or policy.get("formal_run_coverage")
        != "exactly_one_allow_decision_per_materialized_decision_timestamp"
        or policy.get("required_families") != EXPECTED_FAMILIES
        or policy.get("required_underlying_cadences") != REQUIRED_CADENCES
        or policy.get("required_binding_matrix")
        != "exactly_one_underlying_binding_per_family_and_required_cadence"
        or policy.get("decision_local_time") != "15:00:00"
        or policy.get("history_start_inclusive") != "2021-06-01T00:00:00+08:00"
        or policy.get("option_inputs_allowed") is not False
        or policy.get("min5_input_allowed") is not False
        or set(policy.get("unavailable_option_capabilities", {}))
        != {"bid_ask", "contract_delta", "exact_exchange_expiry", "iv_history", "option_premium"}
    ):
        raise HistoricalBacktestGateError("P1-EXP-002 frozen input policy drifted")
    request = contract.get("request_schema", {})
    if (
        request.get("schema_version") != REQUEST_SCHEMA_VERSION
        or set(request.get("exact_top_level_fields", [])) != EXPECTED_REQUEST_FIELDS
        or len(request.get("exact_top_level_fields", [])) != len(EXPECTED_REQUEST_FIELDS)
        or set(request.get("exact_binding_fields", [])) != EXPECTED_BINDING_FIELDS
        or len(request.get("exact_binding_fields", [])) != len(EXPECTED_BINDING_FIELDS)
        or set(request.get("exact_frozen_design_fields", [])) != EXPECTED_FROZEN_DESIGN_FIELDS
        or len(request.get("exact_frozen_design_fields", [])) != len(EXPECTED_FROZEN_DESIGN_FIELDS)
        or set(request.get("exact_causal_support_fields", [])) != EXPECTED_CAUSAL_SUPPORT_FIELDS
        or len(request.get("exact_causal_support_fields", []))
        != len(EXPECTED_CAUSAL_SUPPORT_FIELDS)
        or set(request.get("exact_control_fields", [])) != EXPECTED_CONTROL_FIELDS
        or len(request.get("exact_control_fields", [])) != len(EXPECTED_CONTROL_FIELDS)
        or set(request.get("exact_operational_evidence_fields", [])) != EXPECTED_OPERATIONAL_FIELDS
        or len(request.get("exact_operational_evidence_fields", []))
        != len(EXPECTED_OPERATIONAL_FIELDS)
    ):
        raise HistoricalBacktestGateError("request schema drifted")
    decision = contract.get("decision_schema", {})
    if (
        decision.get("schema_version") != DECISION_SCHEMA_VERSION
        or set(decision.get("exact_top_level_fields", [])) != EXPECTED_DECISION_FIELDS
        or len(decision.get("exact_top_level_fields", [])) != len(EXPECTED_DECISION_FIELDS)
        or set(decision.get("exact_evaluated_binding_fields", []))
        != EXPECTED_EVALUATED_BINDING_FIELDS
        or len(decision.get("exact_evaluated_binding_fields", []))
        != len(EXPECTED_EVALUATED_BINDING_FIELDS)
        or set(decision.get("exact_manifest_binding_fields", []))
        != EXPECTED_MANIFEST_BINDING_FIELDS
        or len(decision.get("exact_manifest_binding_fields", []))
        != len(EXPECTED_MANIFEST_BINDING_FIELDS)
        or set(decision.get("exact_claim_boundary_fields", [])) != EXPECTED_CLAIM_BOUNDARY_FIELDS
        or len(decision.get("exact_claim_boundary_fields", []))
        != len(EXPECTED_CLAIM_BOUNDARY_FIELDS)
    ):
        raise HistoricalBacktestGateError("decision schema drifted")
    boundary = contract.get("research_boundary", {})
    if (
        boundary.get("p1_exp_002_implementation_may_consume_gate") is not True
        or boundary.get("p1_exp_002_outcome_work_authorized") is not False
        or boundary.get("issue_51_unblocked") is not False
        or boundary.get("registry_mutation_authorized") is not False
        or boundary.get("causal_roll_rule_recomputation_authorized") is not False
        or boundary.get("causal_roll_semantic_validation_owner")
        != "issue_51_strategy_implementation"
        or boundary.get("execution_authorized") is not False
    ):
        raise HistoricalBacktestGateError("research boundary was weakened")
    _assert_public_safe(contract)


def load_contract(path: Path) -> dict[str, Any]:
    contract = strict_json_loads(path.read_text(encoding="utf-8"))
    if not isinstance(contract, dict):
        raise HistoricalBacktestGateError("contract must be a JSON object")
    validate_contract(contract)
    return contract


def _source_manifest_cells(
    manifest: Mapping[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    expected_top = {
        "schema_version",
        "source_version_id",
        "immutability_status",
        "finalized_at_utc",
        "history_start_utc",
        "cells",
    }
    expected_cell = {
        "instrument_family",
        "cadence",
        "source_snapshot_sha256",
        "record_count",
        "minimum_observation_utc",
        "maximum_observation_utc",
    }
    if (
        set(manifest) != expected_top
        or manifest.get("schema_version") != SOURCE_VERSION_MANIFEST_SCHEMA_VERSION
        or not isinstance(manifest.get("source_version_id"), str)
        or PUBLIC_ID_PATTERN.fullmatch(manifest["source_version_id"]) is None
        or manifest.get("immutability_status") != "finalized_immutable"
        or manifest.get("history_start_utc") != _utc_text(HISTORY_START_UTC)
        or not isinstance(manifest.get("cells"), list)
    ):
        raise HistoricalBacktestGateError("native source version manifest is invalid")
    finalized_at = _parse_utc(manifest.get("finalized_at_utc"), "finalized_at_utc")
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    for cell in manifest["cells"]:
        if not isinstance(cell, dict) or set(cell) != expected_cell:
            raise HistoricalBacktestGateError("native source version cell fields drifted")
        key = (cell.get("instrument_family"), cell.get("cadence"))
        if (
            key in cells
            or key[0] not in EXPECTED_FAMILIES
            or key[1] not in REQUIRED_CADENCES
            or not _is_sha256(cell.get("source_snapshot_sha256"))
            or not isinstance(cell.get("record_count"), int)
            or isinstance(cell.get("record_count"), bool)
            or cell["record_count"] <= 0
        ):
            raise HistoricalBacktestGateError("native source version cell is invalid")
        minimum = _parse_utc(cell.get("minimum_observation_utc"), "minimum_observation_utc")
        maximum = _parse_utc(cell.get("maximum_observation_utc"), "maximum_observation_utc")
        if minimum > maximum:
            raise HistoricalBacktestGateError("native source version range is inverted")
        cells[key] = cell
    required = {(family, cadence) for family in EXPECTED_FAMILIES for cadence in REQUIRED_CADENCES}
    if set(cells) != required:
        raise HistoricalBacktestGateError("native source version matrix is incomplete")
    if any(
        _parse_utc(cell["maximum_observation_utc"], "maximum_observation_utc") > finalized_at
        for cell in cells.values()
    ):
        raise HistoricalBacktestGateError(
            "native source version was finalized before its last observation"
        )
    _assert_public_safe(manifest)
    return cells


def _manifest_payload(value: bytes | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, Mapping):
        payload = dict(value)
    else:
        content = _artifact_bytes(value)
        try:
            payload = strict_json_loads(content.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise HistoricalBacktestGateError(
                "native source version manifest must be UTF-8 JSON"
            ) from exc
    if not isinstance(payload, dict):
        raise HistoricalBacktestGateError("native source version manifest must be an object")
    _source_manifest_cells(payload)
    return payload


def _snapshot_payload(
    *,
    source_snapshot_bytes: bytes,
    instrument_family: str,
    cadence: str,
) -> dict[str, Any]:
    if not isinstance(source_snapshot_bytes, bytes) or not source_snapshot_bytes:
        raise HistoricalBacktestGateError("source snapshot bytes must be nonempty")
    try:
        snapshot = strict_json_loads(source_snapshot_bytes.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise HistoricalBacktestGateError("source snapshot must be UTF-8 JSON") from exc
    if (
        not isinstance(snapshot, dict)
        or set(snapshot) != {"schema_version", "instrument_family", "cadence", "records"}
        or snapshot.get("schema_version") != "pa_feitian_causal_underlying_snapshot_v1"
        or snapshot.get("instrument_family") != instrument_family
        or snapshot.get("cadence") != cadence
        or not isinstance(snapshot.get("records"), list)
        or not snapshot["records"]
    ):
        raise HistoricalBacktestGateError("source snapshot schema is invalid")
    return snapshot


def _complete_snapshot_records(
    *,
    source_snapshot_bytes: bytes,
    instrument_family: str,
    cadence: str,
    source_version_manifest: bytes | Path | Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    snapshot = _snapshot_payload(
        source_snapshot_bytes=source_snapshot_bytes,
        instrument_family=instrument_family,
        cadence=cadence,
    )
    manifest = _manifest_payload(source_version_manifest)
    cell = _source_manifest_cells(manifest)[(instrument_family, cadence)]
    records = snapshot["records"]
    timestamps: list[datetime] = []
    for record in records:
        if not isinstance(record, Mapping) or "datetime" not in record:
            raise HistoricalBacktestGateError("source row is missing its native timestamp")
        timestamps.append(_parse_utc(record["datetime"], "datetime"))
    if (
        sha256_bytes(source_snapshot_bytes) != cell["source_snapshot_sha256"]
        or len(records) != cell["record_count"]
        or _utc_text(min(timestamps)) != cell["minimum_observation_utc"]
        or _utc_text(max(timestamps)) != cell["maximum_observation_utc"]
    ):
        raise HistoricalBacktestGateError(
            "source snapshot is not the complete approved native source version"
        )
    return records


def build_native_source_version_manifest(
    *,
    source_version_id: str,
    finalized_at_utc: str,
    source_snapshots: Mapping[tuple[str, str], bytes | Path],
) -> dict[str, Any]:
    """Build a separately frozen completeness registry from full native archives."""

    required = {(family, cadence) for family in EXPECTED_FAMILIES for cadence in REQUIRED_CADENCES}
    if set(source_snapshots) != required:
        raise HistoricalBacktestGateError("native source snapshot matrix is incomplete")
    cells: list[dict[str, Any]] = []
    for family, cadence in sorted(required):
        supplied = source_snapshots[(family, cadence)]
        content = supplied.read_bytes() if isinstance(supplied, Path) else supplied
        snapshot = _snapshot_payload(
            source_snapshot_bytes=content,
            instrument_family=family,
            cadence=cadence,
        )
        timestamps = [_parse_utc(record["datetime"], "datetime") for record in snapshot["records"]]
        cells.append(
            {
                "instrument_family": family,
                "cadence": cadence,
                "source_snapshot_sha256": sha256_bytes(content),
                "record_count": len(snapshot["records"]),
                "minimum_observation_utc": _utc_text(min(timestamps)),
                "maximum_observation_utc": _utc_text(max(timestamps)),
            }
        )
    manifest = {
        "schema_version": SOURCE_VERSION_MANIFEST_SCHEMA_VERSION,
        "source_version_id": source_version_id,
        "immutability_status": "finalized_immutable",
        "finalized_at_utc": _utc_text(_parse_utc(finalized_at_utc, "finalized_at_utc")),
        "history_start_utc": _utc_text(HISTORY_START_UTC),
        "cells": cells,
    }
    _source_manifest_cells(manifest)
    return manifest


def _filtered_snapshot_records(
    *,
    records: Iterable[Mapping[str, Any]],
    instrument_family: str,
    timestamp_field: str,
    identity_fields: list[str],
    cutoff: datetime,
) -> list[tuple[datetime, dict[str, Any]]]:
    normalized: list[tuple[datetime, dict[str, Any]]] = []
    for record in records:
        if (
            not isinstance(record, Mapping)
            or not REQUIRED_UNDERLYING_ROW_FIELDS <= set(record)
            or not set(record) <= ALLOWED_UNDERLYING_ROW_FIELDS
        ):
            raise HistoricalBacktestGateError("source row fields violate the causal allowlist")
        contract_id = record["contract_id"]
        if (
            not isinstance(contract_id, str)
            or re.fullmatch(rf"{re.escape(instrument_family)}[0-9A-Za-z._-]+", contract_id) is None
        ):
            raise HistoricalBacktestGateError("source contract identity does not match family")
        if timestamp_field not in record or record[timestamp_field] is None:
            raise HistoricalBacktestGateError("filtered source contains a null timestamp")
        observed = _parse_utc(record[timestamp_field], timestamp_field)
        if observed < HISTORY_START_UTC or observed > cutoff:
            continue
        safe_record = _json_safe(dict(record))
        safe_record[timestamp_field] = _utc_text(observed)
        if any(field not in safe_record or safe_record[field] is None for field in identity_fields):
            raise HistoricalBacktestGateError("filtered source contains a null identity key")
        normalized.append((observed, safe_record))
    if not normalized:
        raise HistoricalBacktestGateError("causally filtered content is empty")
    return normalized


def build_filtered_content_binding(
    *,
    binding_id: str,
    instrument_family: str,
    interface: str,
    cadence: str,
    source_snapshot_bytes: bytes,
    timestamp_field: str,
    identity_key_fields: Iterable[str],
    decision_cutoff_utc: str,
    source_version_manifest: bytes | Path | Mapping[str, Any],
) -> dict[str, Any]:
    """Hash every field of the causally filtered rows without publishing them."""

    if PUBLIC_ID_PATTERN.fullmatch(binding_id) is None:
        raise HistoricalBacktestGateError("binding_id is not public-safe")
    if instrument_family not in EXPECTED_FAMILIES:
        raise HistoricalBacktestGateError("binding family is outside the candidate universe")
    if interface not in EXPECTED_INTERFACES or cadence not in EXPECTED_CADENCES:
        raise HistoricalBacktestGateError("binding interface or cadence is invalid")
    identity_fields = list(identity_key_fields)
    if (
        not identity_fields
        or len(identity_fields) != len(set(identity_fields))
        or any(
            not isinstance(field, str) or PUBLIC_ID_PATTERN.fullmatch(field) is None
            for field in identity_fields
        )
        or identity_fields != EXPECTED_IDENTITY_KEY_FIELDS
        or timestamp_field != "datetime"
    ):
        raise HistoricalBacktestGateError(
            "identity_key_fields must be unique public field names including timestamp_field"
        )
    cutoff = _parse_utc(decision_cutoff_utc, "decision_cutoff_utc")
    records = _complete_snapshot_records(
        source_snapshot_bytes=source_snapshot_bytes,
        instrument_family=instrument_family,
        cadence=cadence,
        source_version_manifest=source_version_manifest,
    )
    normalized = _filtered_snapshot_records(
        records=records,
        instrument_family=instrument_family,
        timestamp_field=timestamp_field,
        identity_fields=identity_fields,
        cutoff=cutoff,
    )
    if not _native_cutoff_contracts(
        records=[row for _, row in normalized],
        instrument_family=instrument_family,
        cadence=cadence,
        cutoff=cutoff,
        require_cutoff=False,
    ):
        raise HistoricalBacktestGateError("source timestamps do not prove native cadence")

    canonical_rows = sorted(
        json.dumps(
            row,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        for _, row in normalized
    )
    content_bytes = b"".join(row + b"\n" for row in canonical_rows)
    timestamps = [observed for observed, _ in normalized]
    identity_keys = [
        tuple(
            json.dumps(
                row[field],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            for field in identity_fields
        )
        for _, row in normalized
    ]
    duplicate_timestamps = len(identity_keys) - len(set(identity_keys))
    ohlc_violations = 0
    activity_violations = 0
    for _, row in normalized:
        values = [row.get(field) for field in ("open", "high", "low", "close")]
        numeric = all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value > 0
            for value in values
        )
        if not numeric:
            ohlc_violations += 1
            continue
        open_, high, low, close = values
        if high < low or high < open_ or high < close or low > open_ or low > close:
            ohlc_violations += 1
        activity = [row.get(field) for field in ("volume", "open_interest")]
        if not all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value >= 0
            for value in activity
        ):
            activity_violations += 1

    binding = {
        "binding_id": binding_id,
        "instrument_family": instrument_family,
        "interface": interface,
        "cadence": cadence,
        "source_snapshot_sha256": sha256_bytes(source_snapshot_bytes),
        "source_snapshot_binding_kind": "immutable_snapshot_or_acquisition_version",
        "filtered_content_sha256": sha256_bytes(content_bytes),
        "filtered_content_binding_kind": "exact_causally_filtered_row_content",
        "canonicalization_id": CANONICALIZATION_ID,
        "identity_key_fields": identity_fields,
        "row_count": len(normalized),
        "decision_cutoff_utc": _utc_text(cutoff),
        "required_through_utc": _utc_text(cutoff),
        "minimum_observation_utc": _utc_text(min(timestamps)),
        "maximum_observation_utc": _utc_text(max(timestamps)),
        "timestamp_semantics": TIMESTAMP_SEMANTICS,
        "source_timezone": SOURCE_TIMEZONE,
        "null_timestamp_rows": 0,
        "duplicate_timestamp_rows": duplicate_timestamps,
        "ohlc_violation_rows": ohlc_violations,
        "nonfinite_or_negative_activity_rows": activity_violations,
        "post_cutoff_rows_in_bound_content": 0,
        "close_timestamp_status": "verified" if cutoff in timestamps else "unavailable",
        "raw_rows_published": False,
    }
    _assert_public_safe(binding)
    return binding


def _validate_gate_request(contract: dict[str, Any], request: dict[str, Any]) -> None:
    validate_contract(contract)
    schema = contract["request_schema"]
    if set(request) != set(schema["exact_top_level_fields"]):
        raise HistoricalBacktestGateError("request fields differ from exact allowlist")
    if request.get("schema_version") != REQUEST_SCHEMA_VERSION:
        raise HistoricalBacktestGateError("unexpected gate request schema")
    if (
        not isinstance(request.get("request_id"), str)
        or PUBLIC_ID_PATTERN.fullmatch(request["request_id"]) is None
    ):
        raise HistoricalBacktestGateError("request_id is not public-safe")
    if request.get("experiment_id") != "P1-EXP-002":
        raise HistoricalBacktestGateError("gate request must target P1-EXP-002")
    if request.get("mode") not in EXPECTED_MODES:
        raise HistoricalBacktestGateError("gate request mode is invalid")
    capabilities = request.get("required_capabilities")
    if not isinstance(capabilities, list) or capabilities != EXPECTED_CAPABILITY_ORDER:
        raise HistoricalBacktestGateError(
            "required capabilities must equal the frozen P1-EXP-002 capability plan"
        )
    frozen_design = request.get("frozen_design")
    if (
        not isinstance(frozen_design, dict)
        or set(frozen_design) != set(schema["exact_frozen_design_fields"])
        or any(not _is_sha256(value) for value in frozen_design.values())
    ):
        raise HistoricalBacktestGateError("frozen design binding is invalid")
    causal_support = request.get("causal_support")
    if (
        not isinstance(causal_support, dict)
        or set(causal_support) != set(schema["exact_causal_support_fields"])
        or not _is_sha256(causal_support.get("native_source_version_manifest_sha256"))
        or not _is_sha256(causal_support.get("exchange_session_calendar_sha256"))
        or not _is_sha256(causal_support.get("causal_roll_ledger_sha256"))
    ):
        raise HistoricalBacktestGateError("causal support binding is invalid")
    bindings = request.get("input_bindings")
    if not isinstance(bindings, list) or not bindings:
        raise HistoricalBacktestGateError("gate request has no input bindings")
    seen_bindings: set[str] = set()
    for binding in bindings:
        if not isinstance(binding, dict) or set(binding) != set(schema["exact_binding_fields"]):
            raise HistoricalBacktestGateError("binding fields differ from exact allowlist")
        binding_id = binding.get("binding_id")
        if (
            not isinstance(binding_id, str)
            or PUBLIC_ID_PATTERN.fullmatch(binding_id) is None
            or binding_id in seen_bindings
        ):
            raise HistoricalBacktestGateError("binding_id is invalid or duplicated")
        seen_bindings.add(binding_id)
        if binding.get("instrument_family") not in EXPECTED_FAMILIES:
            raise HistoricalBacktestGateError("binding family is outside the universe")
        if (
            binding.get("interface") not in EXPECTED_INTERFACES
            or binding.get("cadence") not in EXPECTED_CADENCES
        ):
            raise HistoricalBacktestGateError("binding interface or cadence is invalid")
        if not _is_sha256(binding.get("source_snapshot_sha256")) or not _is_sha256(
            binding.get("filtered_content_sha256")
        ):
            raise HistoricalBacktestGateError("binding digest is invalid")
        if binding.get("source_snapshot_binding_kind") not in {
            "immutable_snapshot_or_acquisition_version",
            "inventory_membership_only",
        }:
            raise HistoricalBacktestGateError("source_snapshot_binding_kind is invalid")
        if binding.get("filtered_content_binding_kind") not in {
            "exact_causally_filtered_row_content",
            "inventory_membership_only",
        }:
            raise HistoricalBacktestGateError("filtered_content_binding_kind is invalid")
        identity_key_fields = binding.get("identity_key_fields")
        if (
            not isinstance(identity_key_fields, list)
            or identity_key_fields != EXPECTED_IDENTITY_KEY_FIELDS
        ):
            raise HistoricalBacktestGateError("identity_key_fields are invalid")
        if not isinstance(binding.get("row_count"), int) or isinstance(
            binding.get("row_count"), bool
        ):
            raise HistoricalBacktestGateError("binding row_count is invalid")
        for field in (
            "null_timestamp_rows",
            "duplicate_timestamp_rows",
            "ohlc_violation_rows",
            "nonfinite_or_negative_activity_rows",
            "post_cutoff_rows_in_bound_content",
        ):
            if (
                not isinstance(binding.get(field), int)
                or isinstance(binding.get(field), bool)
                or binding[field] < 0
            ):
                raise HistoricalBacktestGateError(f"{field} is invalid")
        for field in ("close_timestamp_status",):
            if binding.get(field) not in {"verified", "unavailable", "not_applicable"}:
                raise HistoricalBacktestGateError(f"{field} is invalid")
        if not isinstance(binding.get("raw_rows_published"), bool):
            raise HistoricalBacktestGateError("raw_rows_published is invalid")

    controls = request.get("controls")
    if not isinstance(controls, dict) or set(controls) != set(schema["exact_control_fields"]):
        raise HistoricalBacktestGateError("control fields differ from exact allowlist")
    if any(not isinstance(value, bool) for value in controls.values()):
        raise HistoricalBacktestGateError("gate controls must be booleans")
    operational = request.get("operational_evidence")
    if not isinstance(operational, dict) or set(operational) != set(
        schema["exact_operational_evidence_fields"]
    ):
        raise HistoricalBacktestGateError("operational evidence fields differ from exact allowlist")
    manifest = operational["append_only_acquisition_manifest_sha256"]
    if manifest is not None and not _is_sha256(manifest):
        raise HistoricalBacktestGateError("append-only manifest digest is invalid")
    for field in (
        "point_in_time_observability_verified",
        "current_freshness_verified",
        "execution_authorized",
    ):
        if not isinstance(operational[field], bool):
            raise HistoricalBacktestGateError(f"{field} must be boolean")
    _assert_public_safe(request)


def _artifact_bytes(value: bytes | Path) -> bytes:
    if isinstance(value, Path):
        return value.read_bytes()
    if isinstance(value, bytes):
        return value
    raise HistoricalBacktestGateError("causal support artifact must be bytes or a path")


def _calendar_api() -> tuple[Any, Any, Any, Any]:
    try:
        from data.calendars import (
            calendar_version_for,
            is_session,
            session_close,
            session_open,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        raise HistoricalBacktestGateError(
            "authoritative exchange calendar dependency is unavailable"
        ) from exc
    return calendar_version_for, is_session, session_open, session_close


def build_authoritative_calendar_binding(*, decision_cutoff_utc: str) -> bytes:
    """Render the only accepted calendar artifact from the frozen calendar implementation."""

    cutoff = _parse_utc(decision_cutoff_utc, "decision_cutoff_utc")
    session_date = cutoff.astimezone(ZoneInfo(SOURCE_TIMEZONE)).date()
    calendar_version_for, is_session, session_open, session_close = _calendar_api()
    records: list[dict[str, str]] = []
    for exchange, calendar_id in EXCHANGE_CALENDAR.items():
        if not is_session(calendar_id, session_date):
            raise HistoricalBacktestGateError("decision cutoff is not an exchange session")
        version = str(calendar_version_for(calendar_id))
        if version != EXPECTED_CALENDAR_VERSIONS[calendar_id]:
            raise HistoricalBacktestGateError("authoritative exchange calendar version drifted")
        open_utc = session_open(calendar_id, session_date)
        close_utc = session_close(calendar_id, session_date)
        if close_utc != cutoff:
            raise HistoricalBacktestGateError(
                "decision cutoff is not the authoritative session close"
            )
        records.append(
            {
                "exchange": exchange,
                "calendar_id": calendar_id,
                "calendar_version": version,
                "session_date": session_date.isoformat(),
                "open_utc": _utc_text(open_utc),
                "close_utc": _utc_text(close_utc),
            }
        )
    return pretty_json_bytes(
        {
            "schema_version": "pa_feitian_exchange_session_calendar_binding_v2",
            "decision_cutoff_utc": _utc_text(cutoff),
            "records": records,
        }
    )


def _previous_session_date(calendar_id: str, session_date: date) -> date:
    _, is_session, _, _ = _calendar_api()
    candidate = session_date - timedelta(days=1)
    for _ in range(16):
        if is_session(calendar_id, candidate):
            return candidate
        candidate -= timedelta(days=1)
    raise HistoricalBacktestGateError("previous exchange session is unavailable")


def authoritative_session_slots(
    *,
    instrument_family: str,
    cadence: str,
    session_date: date,
) -> set[datetime]:
    """Return canonical completed-bar endpoints on the frozen session-minute grid."""

    if instrument_family not in FAMILY_CALENDAR or cadence not in EXPECTED_CADENCES:
        raise HistoricalBacktestGateError("session-slot family or cadence is invalid")
    calendar_id = FAMILY_CALENDAR[instrument_family]
    _, is_session, _, session_close = _calendar_api()
    if not is_session(calendar_id, session_date):
        return set()
    if cadence == "daily":
        return {session_close(calendar_id, session_date)}

    local = ZoneInfo(SOURCE_TIMEZONE)
    previous = _previous_session_date(calendar_id, session_date)
    night_end = {
        "SHFE.au": time(2, 30),
        "SHFE.ag": time(2, 30),
        "SHFE.cu": time(1, 0),
        "CZCE.TA": time(23, 0),
        "CZCE.MA": time(23, 0),
        "DCE.i": time(23, 0),
    }[instrument_family]
    periods = []
    # A Friday night may belong to Monday's trading date, but a closed weekend
    # or exchange holiday is never itself a continuous trading interval. The
    # repository calendar does not authoritatively publish post-holiday night
    # reopenings, so only consecutive sessions and an ordinary Friday-to-Monday
    # weekend receive inferred night slots; every holiday gap is day-only.
    gap_days = (session_date - previous).days
    ordinary_weekend = gap_days == 3 and previous.weekday() == 4 and session_date.weekday() == 0
    if gap_days == 1 or ordinary_weekend:
        night_start = datetime.combine(previous, time(21, 0), tzinfo=local)
        night_end_date = previous + timedelta(days=1) if night_end < time(21, 0) else previous
        periods.append((night_start, datetime.combine(night_end_date, night_end, tzinfo=local)))
    periods.extend(
        [
            (
                datetime.combine(session_date, time(9, 0), tzinfo=local),
                datetime.combine(session_date, time(10, 15), tzinfo=local),
            ),
            (
                datetime.combine(session_date, time(10, 30), tzinfo=local),
                datetime.combine(session_date, time(11, 30), tzinfo=local),
            ),
            (
                datetime.combine(session_date, time(13, 30), tzinfo=local),
                datetime.combine(session_date, time(15, 0), tzinfo=local),
            ),
        ]
    )
    step = {"hour": 60, "min15": 15, "min5": 5}[cadence]
    target = step
    elapsed = 0
    slots: set[datetime] = set()
    for start, end in periods:
        duration = int((end - start).total_seconds() // 60)
        while target <= elapsed + duration:
            slots.add((start + timedelta(minutes=target - elapsed)).astimezone(UTC))
            target += step
        elapsed += duration
    slots.add(session_close(calendar_id, session_date))
    return slots


def _native_cutoff_contracts(
    *,
    records: Iterable[Mapping[str, Any]],
    instrument_family: str,
    cadence: str,
    cutoff: datetime,
    require_cutoff: bool = True,
) -> set[str]:
    by_contract: dict[str, set[datetime]] = {}
    all_observations: set[datetime] = set()
    for record in records:
        observed = _parse_utc(record["datetime"], "datetime")
        if HISTORY_START_UTC <= observed <= cutoff:
            by_contract.setdefault(record["contract_id"], set()).add(observed)
            all_observations.add(observed)
    if not all_observations:
        return set()
    local_dates = [row.astimezone(ZoneInfo(SOURCE_TIMEZONE)).date() for row in all_observations]
    first = min(local_dates) - timedelta(days=8)
    last = max(local_dates) + timedelta(days=8)
    legal_slots: set[datetime] = set()
    candidate = first
    while candidate <= last:
        legal_slots.update(
            authoritative_session_slots(
                instrument_family=instrument_family,
                cadence=cadence,
                session_date=candidate,
            )
        )
        candidate += timedelta(days=1)
    if not all_observations <= legal_slots:
        return set()
    ordered_slots = sorted(legal_slots)
    slot_position = {observed: index for index, observed in enumerate(ordered_slots)}

    def has_native_neighbor(observations: set[datetime]) -> bool:
        positions = sorted(slot_position[observed] for observed in observations)
        return any(current == previous + 1 for previous, current in pairwise(positions))

    return {
        contract_id
        for contract_id, observations in by_contract.items()
        if has_native_neighbor(observations) and (not require_cutoff or cutoff in observations)
    }


def _verify_causal_support_artifacts(
    *,
    contract: dict[str, Any],
    request: dict[str, Any],
    artifacts: Mapping[str, bytes | Path],
    verified_native_cutoff_contracts: Mapping[tuple[str, str], set[str]],
) -> set[str]:
    reasons: set[str] = set()
    expected_names = {
        "native_source_version_manifest",
        "exchange_session_calendar",
        "causal_roll_ledger",
    }
    if set(artifacts) - expected_names:
        raise HistoricalBacktestGateError("unknown causal support artifact supplied")
    cutoffs = {binding["decision_cutoff_utc"] for binding in request["input_bindings"]}
    if len(cutoffs) != 1:
        return {"causal_support_cutoff_is_ambiguous"}
    cutoff_text = next(iter(cutoffs))
    try:
        cutoff = _parse_utc(cutoff_text, "decision_cutoff_utc")
    except HistoricalBacktestGateError:
        return {"causal_support_cutoff_is_invalid"}
    for name in sorted(expected_names):
        supplied = artifacts.get(name)
        if supplied is None:
            reasons.add(f"{name}_artifact_missing")
            continue
        try:
            content = _artifact_bytes(supplied)
            payload = strict_json_loads(content.decode("utf-8"))
        except (OSError, UnicodeDecodeError, HistoricalBacktestGateError):
            reasons.add(f"{name}_artifact_invalid")
            continue
        observed_digest = sha256_bytes(content)
        if observed_digest != request["causal_support"][f"{name}_sha256"]:
            reasons.add(f"{name}_artifact_digest_mismatch")
            continue
        if not isinstance(payload, dict):
            reasons.add(f"{name}_artifact_invalid")
            continue
        try:
            if name == "native_source_version_manifest":
                _source_manifest_cells(payload)
                approved = contract["binding_policy"][
                    "approved_native_source_version_manifest_sha256"
                ]
                if approved is None or observed_digest != approved:
                    raise HistoricalBacktestGateError(
                        "native source version is not independently approved"
                    )
            elif name == "exchange_session_calendar":
                authoritative = build_authoritative_calendar_binding(
                    decision_cutoff_utc=cutoff_text
                )
                if content != authoritative:
                    raise HistoricalBacktestGateError(
                        "calendar differs from authoritative frozen sessions"
                    )
            else:
                records = payload.get("records")
                expected_session_date = (
                    cutoff.astimezone(ZoneInfo(SOURCE_TIMEZONE)).date().isoformat()
                )
                if (
                    set(payload) != {"schema_version", "decision_cutoff_utc", "records"}
                    or payload.get("decision_cutoff_utc") != cutoff_text
                    or not isinstance(records, list)
                    or not records
                ):
                    raise HistoricalBacktestGateError("roll-ledger envelope drifted")
                if payload["schema_version"] != "pa_feitian_causal_roll_ledger_binding_v1":
                    raise HistoricalBacktestGateError("roll-ledger schema drifted")
                families: set[str] = set()
                for record in records:
                    if not isinstance(record, dict) or set(record) != {
                        "instrument_family",
                        "effective_session",
                        "selected_contract_id",
                        "as_of_utc",
                    }:
                        raise HistoricalBacktestGateError("roll-ledger record fields drifted")
                    family = record["instrument_family"]
                    families.add(family)
                    if (
                        family not in EXPECTED_FAMILIES
                        or record["effective_session"] != expected_session_date
                        or not isinstance(record["selected_contract_id"], str)
                        or re.fullmatch(
                            rf"{re.escape(family)}[0-9A-Za-z._-]+",
                            record["selected_contract_id"],
                        )
                        is None
                        or _parse_utc(record["as_of_utc"], "as_of_utc") > cutoff
                        or any(
                            record["selected_contract_id"]
                            not in verified_native_cutoff_contracts.get((family, cadence), set())
                            for cadence in REQUIRED_CADENCES
                        )
                    ):
                        raise HistoricalBacktestGateError("roll-ledger record is invalid")
                if families != set(EXPECTED_FAMILIES) or len(records) != len(EXPECTED_FAMILIES):
                    raise HistoricalBacktestGateError("roll-ledger family coverage is incomplete")
        except HistoricalBacktestGateError:
            reasons.add(f"{name}_artifact_invalid")
    return reasons


def evaluate_gate_request(
    *,
    contract: dict[str, Any],
    request: dict[str, Any],
    source_snapshots: Mapping[str, bytes | Path] | None = None,
    causal_support_artifacts: Mapping[str, bytes | Path] | None = None,
) -> dict[str, Any]:
    """Return a deterministic allow/deny decision for a schema-valid request."""

    _validate_gate_request(contract, request)
    reasons: set[str] = set()
    evaluated_bindings: list[dict[str, Any]] = []
    bindings = request["input_bindings"]
    max_lag_days = contract["binding_policy"]["maximum_coverage_lag_days"]
    supplied_snapshots = {} if source_snapshots is None else source_snapshots
    supplied_support = {} if causal_support_artifacts is None else causal_support_artifacts
    # Capture every filesystem input once. All hashes, parsing, filtering,
    # quality checks, cadence checks, and roll linkage consume these immutable
    # bytes so a concurrent replacement cannot create a split-view allow.
    source_snapshots = {
        binding_id: _artifact_bytes(value) for binding_id, value in supplied_snapshots.items()
    }
    causal_support_artifacts = {
        name: _artifact_bytes(value) for name, value in supplied_support.items()
    }
    source_version_manifest = causal_support_artifacts.get("native_source_version_manifest")
    if set(source_snapshots) - {row["binding_id"] for row in bindings}:
        raise HistoricalBacktestGateError("source snapshot supplied for an unknown binding")

    required_matrix = {
        (family, cadence) for family in EXPECTED_FAMILIES for cadence in REQUIRED_CADENCES
    }
    policy = contract["p1_exp_002_input_policy"]
    observed_matrix = [(row["instrument_family"], row["cadence"]) for row in bindings]
    if set(observed_matrix) != required_matrix or len(observed_matrix) != len(required_matrix):
        reasons.add("p1_exp_002_binding_matrix_mismatch")
    if any(row["interface"] != "underlying" for row in bindings):
        reasons.add("p1_exp_002_option_or_unknown_interface_forbidden")
    if any(row["cadence"] == "min5" for row in bindings):
        reasons.add("p1_exp_002_min5_input_forbidden")
    source_hashes = [row["source_snapshot_sha256"] for row in bindings]
    if len(source_hashes) != len(set(source_hashes)):
        reasons.add("source_snapshot_reused_across_binding_matrix")
    cutoffs = {row["decision_cutoff_utc"] for row in bindings}
    if len(cutoffs) != 1:
        reasons.add("inconsistent_binding_decision_cutoffs")
    else:
        try:
            only_cutoff = _parse_utc(next(iter(cutoffs)), "decision_cutoff_utc")
        except HistoricalBacktestGateError:
            pass
        else:
            if (
                only_cutoff.astimezone(ZoneInfo(SOURCE_TIMEZONE)).strftime("%H:%M:%S")
                != policy["decision_local_time"]
            ):
                reasons.add("decision_cutoff_not_exact_15_00_asia_shanghai")

    frozen_design = request["frozen_design"]
    if frozen_design["registry_sha256"] != policy["registry_sha256"]:
        reasons.add("frozen_registry_binding_mismatch")
    if frozen_design["registry_lock_sha256"] != policy["registry_lock_sha256"]:
        reasons.add("frozen_registry_lock_binding_mismatch")
    if frozen_design["canonical_design_sha256"] != policy["canonical_design_sha256"]:
        reasons.add("frozen_design_binding_mismatch")
    causal_support = request["causal_support"]
    verified_native_cutoff_contracts: dict[tuple[str, str], set[str]] = {}
    for binding in bindings:
        prefix = binding["binding_id"]
        snapshot_bytes = source_snapshots.get(prefix)
        if snapshot_bytes is None:
            reasons.add(f"{prefix}:source_snapshot_not_independently_verified")
        else:
            try:
                rebuilt = build_filtered_content_binding(
                    binding_id=prefix,
                    instrument_family=binding["instrument_family"],
                    interface=binding["interface"],
                    cadence=binding["cadence"],
                    source_snapshot_bytes=snapshot_bytes,
                    timestamp_field="datetime",
                    identity_key_fields=binding["identity_key_fields"],
                    decision_cutoff_utc=binding["decision_cutoff_utc"],
                    source_version_manifest=source_version_manifest,
                )
            except HistoricalBacktestGateError:
                reasons.add(f"{prefix}:source_snapshot_verification_failed")
            else:
                if rebuilt != binding:
                    reasons.add(f"{prefix}:source_snapshot_evidence_mismatch")
                cutoff = _parse_utc(binding["decision_cutoff_utc"], "decision_cutoff_utc")
                complete_records = _complete_snapshot_records(
                    source_snapshot_bytes=snapshot_bytes,
                    instrument_family=binding["instrument_family"],
                    cadence=binding["cadence"],
                    source_version_manifest=source_version_manifest,
                )
                filtered_records = _filtered_snapshot_records(
                    records=complete_records,
                    instrument_family=binding["instrument_family"],
                    timestamp_field="datetime",
                    identity_fields=binding["identity_key_fields"],
                    cutoff=cutoff,
                )
                verified_native_cutoff_contracts[
                    (binding["instrument_family"], binding["cadence"])
                ] = _native_cutoff_contracts(
                    records=[row for _, row in filtered_records],
                    instrument_family=binding["instrument_family"],
                    cadence=binding["cadence"],
                    cutoff=cutoff,
                )
        coverage_lag_days: float | None = None
        freshness_status = "invalid_timestamp"
        if binding["canonicalization_id"] != CANONICALIZATION_ID:
            reasons.add(f"{prefix}:canonicalization_mismatch")
        if binding["source_snapshot_binding_kind"] != "immutable_snapshot_or_acquisition_version":
            reasons.add(f"{prefix}:source_snapshot_not_immutable_version")
        if binding["filtered_content_binding_kind"] != "exact_causally_filtered_row_content":
            reasons.add(f"{prefix}:missing_exact_filtered_content_binding")
        if binding["row_count"] <= 0:
            reasons.add(f"{prefix}:empty_filtered_content")
        try:
            cutoff = _parse_utc(binding["decision_cutoff_utc"], "decision_cutoff_utc")
            required_through = _parse_utc(binding["required_through_utc"], "required_through_utc")
            minimum = _parse_utc(binding["minimum_observation_utc"], "minimum_observation_utc")
            maximum = _parse_utc(binding["maximum_observation_utc"], "maximum_observation_utc")
        except HistoricalBacktestGateError:
            reasons.add(f"{prefix}:invalid_timestamp")
        else:
            if required_through != cutoff:
                reasons.add(f"{prefix}:required_through_must_equal_cutoff")
            if minimum > maximum:
                reasons.add(f"{prefix}:observation_range_inverted")
            if maximum > cutoff:
                reasons.add(f"{prefix}:post_cutoff_observation")
            if maximum > cutoff:
                coverage_lag_days = -((maximum - cutoff).total_seconds() / 86400)
                reasons.add(f"{prefix}:negative_coverage_lag")
                freshness_status = "future_observation"
            else:
                coverage_lag_days = (
                    cutoff.astimezone(ZoneInfo(SOURCE_TIMEZONE)).date()
                    - maximum.astimezone(ZoneInfo(SOURCE_TIMEZONE)).date()
                ).days
            if maximum <= cutoff and coverage_lag_days > max_lag_days:
                reasons.add(f"{prefix}:stale_required_coverage")
                freshness_status = "stale_for_declared_cutoff"
            elif maximum <= cutoff:
                freshness_status = "current_for_declared_cutoff"
        if binding["timestamp_semantics"] != TIMESTAMP_SEMANTICS:
            reasons.add(f"{prefix}:timestamp_semantics_unverified")
        if binding["source_timezone"] != SOURCE_TIMEZONE:
            reasons.add(f"{prefix}:source_timezone_unverified")
        for field in (
            "null_timestamp_rows",
            "duplicate_timestamp_rows",
            "ohlc_violation_rows",
            "nonfinite_or_negative_activity_rows",
            "post_cutoff_rows_in_bound_content",
        ):
            if binding[field] != 0:
                reasons.add(f"{prefix}:{field}")
        if binding["close_timestamp_status"] != "verified":
            reasons.add(f"{prefix}:close_timestamp_unavailable")
        if binding["raw_rows_published"]:
            reasons.add(f"{prefix}:raw_rows_published")
        evaluated_bindings.append(
            {
                "binding_id": binding["binding_id"],
                "instrument_family": binding["instrument_family"],
                "interface": binding["interface"],
                "cadence": binding["cadence"],
                "source_snapshot_sha256": binding["source_snapshot_sha256"],
                "filtered_content_sha256": binding["filtered_content_sha256"],
                "row_count": binding["row_count"],
                "decision_cutoff_utc": binding["decision_cutoff_utc"],
                "maximum_observation_utc": binding["maximum_observation_utc"],
                "coverage_lag_days": coverage_lag_days,
                "freshness_status": freshness_status,
            }
        )

    reasons.update(
        _verify_causal_support_artifacts(
            contract=contract,
            request=request,
            artifacts=causal_support_artifacts,
            verified_native_cutoff_contracts=verified_native_cutoff_contracts,
        )
    )

    controls = request["controls"]
    expected_controls = {
        "filter_before_derivation": True,
        "outcomes_accessed": False,
        "instrument_selection_uses_outcomes": False,
        "option_inputs_accessed": False,
        "proxy_or_imputation": False,
        "bid_ask_synthesized": False,
        "delta_synthesized": False,
        "iv_synthesized": False,
        "source_refresh_performed": False,
    }
    for field, expected in expected_controls.items():
        if controls[field] is not expected:
            reasons.add(f"control:{field}")

    operational = request["operational_evidence"]
    mode = request["mode"]
    if mode != policy["allowed_mode"]:
        reasons.add("p1_exp_002_historical_replay_only")
    if mode == "prospective_shadow":
        if operational["append_only_acquisition_manifest_sha256"] is None:
            reasons.add("shadow_append_only_acquisition_manifest_missing")
        if not operational["point_in_time_observability_verified"]:
            reasons.add("shadow_point_in_time_observability_unverified")
        if not operational["current_freshness_verified"]:
            reasons.add("shadow_current_freshness_unverified")
    if mode == "live":
        reasons.add("live_execution_outside_data_gate")
    if operational["execution_authorized"]:
        reasons.add("execution_authorization_forbidden")

    filtered_input_digest = canonical_hash(
        {
            "bindings": [
                {
                    "binding_id": binding["binding_id"],
                    "source_snapshot_sha256": binding["source_snapshot_sha256"],
                    "filtered_content_sha256": binding["filtered_content_sha256"],
                }
                for binding in sorted(bindings, key=lambda row: row["binding_id"])
            ],
            "native_source_version_manifest_sha256": causal_support[
                "native_source_version_manifest_sha256"
            ],
            "exchange_session_calendar_sha256": causal_support["exchange_session_calendar_sha256"],
            "causal_roll_ledger_sha256": causal_support["causal_roll_ledger_sha256"],
        }
    )
    decision = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "request_id": request["request_id"],
        "request_sha256": canonical_hash(request),
        "experiment_id": request["experiment_id"],
        "mode": mode,
        "decision": "allow" if not reasons else "deny",
        "reason_codes": sorted(reasons),
        "binding_count": len(bindings),
        "evaluated_bindings": evaluated_bindings,
        "required_capabilities": request["required_capabilities"],
        "manifest_binding": {
            "registry_sha256": frozen_design["registry_sha256"],
            "registry_lock_sha256": frozen_design["registry_lock_sha256"],
            "canonical_design_sha256": frozen_design["canonical_design_sha256"],
            "approved_data_gate_sha256": canonical_hash(contract),
            "filtered_input_digest": filtered_input_digest,
            "native_source_version_manifest_sha256": causal_support[
                "native_source_version_manifest_sha256"
            ],
            "exchange_session_calendar_sha256": causal_support["exchange_session_calendar_sha256"],
            "causal_roll_ledger_sha256": causal_support["causal_roll_ledger_sha256"],
        },
        "claim_boundary": {
            "finalized_vintage_historical_replay": (mode == "historical_replay" and not reasons),
            "prospective_shadow_data_input": False,
            "point_in_time_vendor_observability_claim": False,
            "strategy_outcomes_authorized": False,
            "issue_51_unblocked": False,
            "execution_authorized": False,
        },
    }
    validate_gate_decision_envelope(decision, contract=contract)
    return decision


def validate_gate_decision_envelope(decision: dict[str, Any], *, contract: dict[str, Any]) -> None:
    """Validate shape and internal formulas only; this is not an attestation check."""

    validate_contract(contract)
    if set(decision) != EXPECTED_DECISION_FIELDS:
        raise HistoricalBacktestGateError("decision fields differ from exact allowlist")
    if decision.get("schema_version") != DECISION_SCHEMA_VERSION:
        raise HistoricalBacktestGateError("unexpected gate decision schema")
    if (
        not isinstance(decision.get("request_id"), str)
        or PUBLIC_ID_PATTERN.fullmatch(decision["request_id"]) is None
        or decision.get("experiment_id") != "P1-EXP-002"
        or decision.get("mode") not in EXPECTED_MODES
    ):
        raise HistoricalBacktestGateError("decision identity is invalid")
    if decision.get("decision") not in {"allow", "deny"}:
        raise HistoricalBacktestGateError("gate decision is invalid")
    if not _is_sha256(decision.get("request_sha256")):
        raise HistoricalBacktestGateError("decision request digest is invalid")
    reasons = decision.get("reason_codes")
    if (
        not isinstance(reasons, list)
        or any(
            not isinstance(reason, str)
            or not reason
            or PUBLIC_ID_PATTERN.fullmatch(reason.replace(":", "-")) is None
            for reason in reasons
        )
        or reasons != sorted(set(reasons))
        or (decision["decision"] == "allow") == bool(reasons)
    ):
        raise HistoricalBacktestGateError("gate reasons do not reconcile")
    binding_count = decision.get("binding_count")
    evaluated = decision.get("evaluated_bindings")
    if (
        not isinstance(binding_count, int)
        or isinstance(binding_count, bool)
        or binding_count <= 0
        or not isinstance(evaluated, list)
        or len(evaluated) != binding_count
        or len({row.get("binding_id") for row in evaluated if isinstance(row, dict)})
        != len(evaluated)
    ):
        raise HistoricalBacktestGateError("decision binding evidence is invalid")
    for binding in evaluated:
        if (
            not isinstance(binding, dict)
            or set(binding) != EXPECTED_EVALUATED_BINDING_FIELDS
            or not _is_sha256(binding.get("source_snapshot_sha256"))
            or not _is_sha256(binding.get("filtered_content_sha256"))
            or not isinstance(binding.get("binding_id"), str)
            or PUBLIC_ID_PATTERN.fullmatch(binding["binding_id"]) is None
            or binding.get("instrument_family") not in EXPECTED_FAMILIES
            or binding.get("interface") not in EXPECTED_INTERFACES
            or binding.get("cadence") not in EXPECTED_CADENCES
            or not isinstance(binding.get("row_count"), int)
            or isinstance(binding.get("row_count"), bool)
            or binding["row_count"] <= 0
            or binding.get("freshness_status")
            not in {
                "current_for_declared_cutoff",
                "stale_for_declared_cutoff",
                "future_observation",
                "invalid_timestamp",
            }
            or (
                binding.get("coverage_lag_days") is not None
                and (
                    not isinstance(binding["coverage_lag_days"], (int, float))
                    or isinstance(binding["coverage_lag_days"], bool)
                    or not math.isfinite(binding["coverage_lag_days"])
                )
            )
        ):
            raise HistoricalBacktestGateError("decision binding evidence is invalid")
        lag = binding["coverage_lag_days"]
        status = binding["freshness_status"]
        if (
            (status == "invalid_timestamp") != (lag is None)
            or (status == "current_for_declared_cutoff" and not 0 <= lag <= 7)
            or (status == "stale_for_declared_cutoff" and not lag > 7)
            or (status == "future_observation" and not lag < 0)
        ):
            raise HistoricalBacktestGateError("decision freshness classification is invalid")
        _parse_utc(binding.get("decision_cutoff_utc"), "decision_cutoff_utc")
        _parse_utc(binding.get("maximum_observation_utc"), "maximum_observation_utc")
    capabilities = decision.get("required_capabilities")
    if capabilities != EXPECTED_CAPABILITY_ORDER:
        raise HistoricalBacktestGateError("decision capabilities are invalid")
    manifest = decision.get("manifest_binding")
    if (
        not isinstance(manifest, dict)
        or set(manifest) != EXPECTED_MANIFEST_BINDING_FIELDS
        or any(not _is_sha256(value) for value in manifest.values())
    ):
        raise HistoricalBacktestGateError("decision manifest binding is invalid")
    expected_filtered_input_digest = canonical_hash(
        {
            "bindings": [
                {
                    "binding_id": binding["binding_id"],
                    "source_snapshot_sha256": binding["source_snapshot_sha256"],
                    "filtered_content_sha256": binding["filtered_content_sha256"],
                }
                for binding in sorted(evaluated, key=lambda row: row["binding_id"])
            ],
            "native_source_version_manifest_sha256": manifest[
                "native_source_version_manifest_sha256"
            ],
            "exchange_session_calendar_sha256": manifest["exchange_session_calendar_sha256"],
            "causal_roll_ledger_sha256": manifest["causal_roll_ledger_sha256"],
        }
    )
    if (
        manifest["approved_data_gate_sha256"] != canonical_hash(contract)
        or manifest["filtered_input_digest"] != expected_filtered_input_digest
    ):
        raise HistoricalBacktestGateError("decision manifest digest does not reconcile")
    boundary = decision.get("claim_boundary", {})
    if set(boundary) != EXPECTED_CLAIM_BOUNDARY_FIELDS:
        raise HistoricalBacktestGateError("decision claim boundary drifted")
    if any(type(value) is not bool for value in boundary.values()):
        raise HistoricalBacktestGateError("decision claim boundary values must be booleans")
    if (
        boundary["strategy_outcomes_authorized"]
        or boundary["issue_51_unblocked"]
        or boundary["execution_authorized"]
    ):
        raise HistoricalBacktestGateError("decision widened downstream authority")
    allowed_historical = decision["decision"] == "allow" and decision["mode"] == "historical_replay"
    if decision["decision"] == "allow":
        observed_matrix = {(row["instrument_family"], row["cadence"]) for row in evaluated}
        expected_matrix = {
            (family, cadence) for family in EXPECTED_FAMILIES for cadence in REQUIRED_CADENCES
        }
        cutoffs = {
            _parse_utc(row["decision_cutoff_utc"], "decision_cutoff_utc") for row in evaluated
        }
        if (
            decision["mode"] != "historical_replay"
            or binding_count != len(expected_matrix)
            or observed_matrix != expected_matrix
            or any(row["interface"] != "underlying" for row in evaluated)
            or len({row["source_snapshot_sha256"] for row in evaluated}) != binding_count
            or len(cutoffs) != 1
            or next(iter(cutoffs)).astimezone(ZoneInfo(SOURCE_TIMEZONE)).strftime("%H:%M:%S")
            != "15:00:00"
            or manifest["registry_sha256"] != FROZEN_REGISTRY_SHA256
            or manifest["registry_lock_sha256"] != FROZEN_REGISTRY_LOCK_SHA256
            or manifest["canonical_design_sha256"] != FROZEN_DESIGN_SHA256
        ):
            raise HistoricalBacktestGateError("allowed decision violates frozen input matrix")
    if (
        boundary["finalized_vintage_historical_replay"] is not allowed_historical
        or boundary["prospective_shadow_data_input"] is not False
        or boundary["point_in_time_vendor_observability_claim"] is not False
    ):
        raise HistoricalBacktestGateError("decision claim boundary does not match mode")
    _assert_public_safe(decision)


def validate_gate_decision(
    decision: dict[str, Any],
    *,
    contract: dict[str, Any],
    request: dict[str, Any],
    source_snapshots: Mapping[str, bytes | Path],
    causal_support_artifacts: Mapping[str, bytes | Path],
) -> None:
    """Re-evaluate every bound artifact and require byte-equivalent decision evidence."""

    validate_gate_decision_envelope(decision, contract=contract)
    rebuilt = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=source_snapshots,
        causal_support_artifacts=causal_support_artifacts,
    )
    if rebuilt != decision:
        raise HistoricalBacktestGateError(
            "decision does not attest to the supplied request and artifacts"
        )


def _verify_bound_evidence(
    *,
    contract: dict[str, Any],
    paths: Mapping[str, Path],
) -> tuple[list[dict[str, str]], dict[str, dict[str, Any]]]:
    expected = _bound_evidence_by_alias(contract)
    if set(paths) != set(expected):
        raise HistoricalBacktestGateError("supplied evidence set drifted")
    verified: list[dict[str, str]] = []
    payloads: dict[str, dict[str, Any]] = {}
    for alias in expected:
        row = expected[alias]
        path = paths[alias]
        try:
            content = path.read_bytes()
            payload = strict_json_loads(content.decode("utf-8"))
        except (OSError, UnicodeDecodeError, HistoricalBacktestGateError) as exc:
            raise HistoricalBacktestGateError(f"{alias} cannot be read unambiguously") from exc
        if not isinstance(payload, dict):
            raise HistoricalBacktestGateError(f"{alias} must be a JSON object")
        if payload.get("schema_version") != row["schema_version"]:
            raise HistoricalBacktestGateError(f"{alias} schema drifted")
        normalized = path.resolve().as_posix()
        if not normalized.endswith(f"/{row['path']}") or sha256_bytes(content) != row["sha256"]:
            raise HistoricalBacktestGateError(f"{alias} hash or path drifted")
        verified.append(dict(row))
        payloads[alias] = payload
    return verified, payloads


def build_gate_profile(
    *,
    contract: dict[str, Any],
    paths: Mapping[str, Path],
) -> dict[str, Any]:
    """Build the public #48/#53 capability map without reading raw market rows."""

    validate_contract(contract)
    verified, payloads = _verify_bound_evidence(
        contract=contract,
        paths=paths,
    )
    audit = payloads["candidate_interface_audit"]
    inventory = payloads["candidate_capability_inventory"]
    swings = payloads["exploratory_swing_views"]
    replay_contract = payloads["epistemic_replay_contract"]
    replay = payloads["retrospective_replay_evidence"]
    registry = payloads["hypothesis_registry_v2"]
    registry_lock = payloads["hypothesis_registry_v2_lock"]
    if (
        audit.get("audit_as_of_local_date") != AUDIT_AS_OF_LOCAL_DATE
        or inventory.get("audit_as_of_local_date") != AUDIT_AS_OF_LOCAL_DATE
        or swings.get("audit_as_of_local_date") != AUDIT_AS_OF_LOCAL_DATE
    ):
        raise HistoricalBacktestGateError("bound evidence audit date drifted")
    if (
        replay_contract.get("claim_modes", {})
        .get("retrospective_finalized", {})
        .get("missing_acquisition_metadata_blocks_claim")
        is not False
        or replay.get("mode_results", {}).get("retrospective_finalized", {}).get("status")
        != "enabled_with_explicit_limitations"
    ):
        raise HistoricalBacktestGateError("retrospective replay precedent drifted")
    if (
        registry.get("selection", {}).get("selected_experiment", {}).get("experiment_id")
        != "P1-EXP-002"
        or registry_lock.get("registry", {}).get("sha256") != FROZEN_REGISTRY_SHA256
        or registry_lock.get("selected_experiment", {}).get("canonical_design_sha256")
        != FROZEN_DESIGN_SHA256
        or registry_lock.get("freeze", {}).get("data_gate_issue") != 50
    ):
        raise HistoricalBacktestGateError("frozen P1-EXP-002 registry binding drifted")
    source_version_registered = (
        contract["binding_policy"]["approved_native_source_version_manifest_sha256"] is not None
    )
    baseline_gate_status = (
        "not_evaluated_no_formal_run_request"
        if source_version_registered
        else "blocked_no_approved_native_source_version"
    )

    audited = {row["instrument_family"]: row for row in audit["decision_surface"]}
    inventory_rows = {row["instrument_family"]: row for row in inventory["decision_surface"]}
    swing_summaries = {row["instrument_family"]: row for row in swings["family_window_summaries"]}
    swing_views = swings["representative_swing_views"]
    if (
        list(audited) != EXPECTED_FAMILIES
        or list(inventory_rows) != EXPECTED_FAMILIES
        or list(swing_summaries) != EXPECTED_FAMILIES
    ):
        raise HistoricalBacktestGateError("bound candidate universe drifted")

    families = []
    roles = {row["instrument_family"]: row["role"] for row in contract["candidate_universe"]}
    for family in EXPECTED_FAMILIES:
        cadence_rows = []
        for cadence in audited[family]["cadences"]:
            if cadence["cadence"] not in EXPECTED_CADENCES:
                raise HistoricalBacktestGateError("candidate cadence drifted")
            interfaces = {}
            for interface in ("underlying", "option_premium"):
                source = cadence["interfaces"][interface]
                interfaces[interface] = {
                    "available": source["scanned_files"] > 0,
                    "file_count": source["scanned_files"],
                    "row_count": source["rows"],
                    "coverage": {
                        "minimum_observation_timestamp": source["coverage"][
                            "minimum_observation_timestamp"
                        ],
                        "maximum_observation_timestamp": source["coverage"][
                            "maximum_observation_timestamp"
                        ],
                    },
                    "audit_freshness": {
                        "calendar_lag_days": source["freshness"]["calendar_lag_days"],
                        "status": source["freshness"]["status"],
                    },
                    "timestamp_quality": {
                        "null_rows": source["timestamp_quality"]["null_rows"],
                        "duplicate_rows": source["timestamp_quality"]["duplicate_rows"],
                    },
                    "ohlc_quality": {
                        "rows_checked": source["ohlc_quality"]["rows_checked"],
                        "null_rows": source["ohlc_quality"]["null_rows"],
                        "violation_rows": source["ohlc_quality"]["violation_rows"],
                    },
                    "required_activity_fields": (
                        {
                            field: {
                                "availability": source["activity_fields"][field]["availability"],
                                "non_null_rows": source["activity_fields"][field]["non_null_rows"],
                            }
                            for field in ("volume", "open_interest")
                        }
                        if interface == "underlying"
                        else {}
                    ),
                    "formal_historical_use": (
                        "conditional_exact_run_binding_required"
                        if interface == "underlying" and cadence["cadence"] in REQUIRED_CADENCES
                        else "not_consumed_by_p1_exp_002"
                    ),
                }
            cadence_rows.append(
                {
                    "cadence": cadence["cadence"],
                    "interfaces": interfaces,
                }
            )
        summary = swing_summaries[family]
        views = [row for row in swing_views if row["instrument_family"] == family]
        inventory_limitations = inventory_rows[family]["historical_research_usability"][
            "limitations"
        ]
        families.append(
            {
                "instrument_family": family,
                "role": roles[family],
                "cadences": cadence_rows,
                "exploratory_swing_evidence": {
                    "all_complete_windows": summary["all_complete_windows"]["window_count"],
                    "representative_eligible_clean_windows": summary[
                        "representative_eligible_clean_windows"
                    ]["window_count"],
                    "representative_view_count": len(views),
                    "invalid_option_overlay_count": sum(
                        row["option_premium_overlay"]["quality_status"] == "invalid"
                        for row in views
                    ),
                    "formal_run_input_binding": "not_produced_by_exploration",
                },
                "known_unavailable_capabilities": {
                    "exact_exchange_expiry": "unavailable_in_bound_audit",
                    "historical_bid_ask": "unavailable_not_synthesized",
                    "contract_delta": "unavailable_not_synthesized",
                    "causal_iv_history": "unavailable_not_synthesized",
                },
                "accepted_exploration_limitations": inventory_limitations,
            }
        )

    profile = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "issue_number": 50,
        "audit_as_of_local_date": AUDIT_AS_OF_LOCAL_DATE,
        "contract": {
            "path": CONTRACT_PUBLIC_PATH,
            "sha256": canonical_hash(contract),
            "sha256_kind": "canonical_json_sha256",
        },
        "bound_evidence": verified,
        "mode_surface": {
            "historical_replay": {
                "status": baseline_gate_status,
                "append_only_acquisition_manifest_required": False,
                "approved_native_source_version_required": True,
                "exact_filtered_content_binding_required": True,
                "current_audit_staleness_interpretation": (
                    "does not by itself reject an older declared historical window; "
                    "per-run coverage freshness is measured against each decision cutoff"
                ),
                "point_in_time_vendor_observability_claim": False,
            },
            "prospective_shadow": {
                "status": "blocked_by_stale_interfaces_and_missing_acquisition_lineage",
                "append_only_acquisition_manifest_required": True,
                "current_freshness_required": True,
                "point_in_time_vendor_observability_required": True,
            },
            "live": {
                "status": "deny_execution_outside_data_gate",
                "authorized_by_this_gate": False,
            },
        },
        "candidate_interface_mapping": families,
        "engineer_surface": {
            "request_schema_version": REQUEST_SCHEMA_VERSION,
            "decision_schema_version": DECISION_SCHEMA_VERSION,
            "allow_requires_zero_reason_codes": True,
            "malformed_request_action": "fail_closed_error",
            "membership_only_hash_action": "deny_missing_exact_filtered_content_binding",
            "p1_exp_002_required_binding_count": len(EXPECTED_FAMILIES) * len(REQUIRED_CADENCES),
            "p1_exp_002_required_underlying_cadences": REQUIRED_CADENCES,
            "p1_exp_002_option_inputs_allowed": False,
            "source_snapshot_verification_required": True,
            "approved_native_source_version_registered": source_version_registered,
            "complete_prefix_extraction": contract["binding_policy"]["complete_prefix_extraction"],
            "calendar_versions": contract["binding_policy"]["calendar_versions"],
            "request_scope": "one_decision_timestamp",
            "formal_run_coverage": (
                "exactly_one_allow_decision_per_materialized_decision_timestamp"
            ),
        },
        "baseline": {
            "p1_exp_002_gate_status": baseline_gate_status,
            "p1_exp_002_implementation_may_integrate_gate": True,
            "p1_exp_002_outcome_work_authorized": False,
            "issue_51_unblocked": False,
            "registry_mutation_authorized": False,
            "causal_roll_semantic_validation": "deferred_to_issue_51_strategy_implementation",
            "execution_authorized": False,
        },
        "public_safety": contract["public_safety"],
        "limitations": list(EXPECTED_PROFILE_LIMITATIONS),
    }
    validate_gate_profile(profile, contract=contract)
    return profile


def _expect_exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise HistoricalBacktestGateError(f"{label} fields differ from exact allowlist")
    return value


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_profile_shape(profile: dict[str, Any], contract: dict[str, Any]) -> None:
    _expect_exact_keys(
        profile,
        {
            "schema_version",
            "issue_number",
            "audit_as_of_local_date",
            "contract",
            "bound_evidence",
            "mode_surface",
            "candidate_interface_mapping",
            "engineer_surface",
            "baseline",
            "public_safety",
            "limitations",
        },
        "profile",
    )
    _expect_exact_keys(profile["contract"], {"path", "sha256", "sha256_kind"}, "profile contract")
    if not isinstance(profile["bound_evidence"], list):
        raise HistoricalBacktestGateError("profile evidence must be a list")
    for row in profile["bound_evidence"]:
        _expect_exact_keys(row, {"alias", "path", "schema_version", "sha256"}, "profile evidence")
    modes = _expect_exact_keys(
        profile["mode_surface"],
        {"historical_replay", "prospective_shadow", "live"},
        "profile mode surface",
    )
    _expect_exact_keys(
        modes["historical_replay"],
        {
            "status",
            "append_only_acquisition_manifest_required",
            "approved_native_source_version_required",
            "exact_filtered_content_binding_required",
            "current_audit_staleness_interpretation",
            "point_in_time_vendor_observability_claim",
        },
        "historical replay profile",
    )
    _expect_exact_keys(
        modes["prospective_shadow"],
        {
            "status",
            "append_only_acquisition_manifest_required",
            "current_freshness_required",
            "point_in_time_vendor_observability_required",
        },
        "prospective shadow profile",
    )
    _expect_exact_keys(modes["live"], {"status", "authorized_by_this_gate"}, "live profile")
    engineer = _expect_exact_keys(
        profile["engineer_surface"],
        {
            "request_schema_version",
            "decision_schema_version",
            "allow_requires_zero_reason_codes",
            "malformed_request_action",
            "membership_only_hash_action",
            "p1_exp_002_required_binding_count",
            "p1_exp_002_required_underlying_cadences",
            "p1_exp_002_option_inputs_allowed",
            "source_snapshot_verification_required",
            "approved_native_source_version_registered",
            "complete_prefix_extraction",
            "calendar_versions",
            "request_scope",
            "formal_run_coverage",
        },
        "profile engineer surface",
    )
    _expect_exact_keys(
        engineer["calendar_versions"],
        set(EXPECTED_CALENDAR_VERSIONS),
        "profile calendar versions",
    )
    _expect_exact_keys(
        profile["baseline"],
        {
            "p1_exp_002_gate_status",
            "p1_exp_002_implementation_may_integrate_gate",
            "p1_exp_002_outcome_work_authorized",
            "issue_51_unblocked",
            "registry_mutation_authorized",
            "causal_roll_semantic_validation",
            "execution_authorized",
        },
        "profile baseline",
    )
    _expect_exact_keys(
        profile["public_safety"], set(contract["public_safety"]), "profile public safety"
    )
    if profile["limitations"] != list(EXPECTED_PROFILE_LIMITATIONS):
        raise HistoricalBacktestGateError("profile limitations differ from exact allowlist")
    if not isinstance(profile["candidate_interface_mapping"], list):
        raise HistoricalBacktestGateError("profile candidate mapping must be a list")
    for family in profile["candidate_interface_mapping"]:
        _expect_exact_keys(
            family,
            {
                "instrument_family",
                "role",
                "cadences",
                "exploratory_swing_evidence",
                "known_unavailable_capabilities",
                "accepted_exploration_limitations",
            },
            "profile family",
        )
        if family.get("instrument_family") not in EXPECTED_FAMILIES or family.get(
            "role"
        ) != EXPECTED_ROLES.get(family.get("instrument_family")):
            raise HistoricalBacktestGateError("profile family identity or role drifted")
        _expect_exact_keys(
            family["exploratory_swing_evidence"],
            {
                "all_complete_windows",
                "formal_run_input_binding",
                "invalid_option_overlay_count",
                "representative_eligible_clean_windows",
                "representative_view_count",
            },
            "profile swing evidence",
        )
        _expect_exact_keys(
            family["known_unavailable_capabilities"],
            {
                "causal_iv_history",
                "contract_delta",
                "exact_exchange_expiry",
                "historical_bid_ask",
            },
            "profile unavailable capabilities",
        )
        if not isinstance(family["accepted_exploration_limitations"], list) or any(
            not isinstance(row, str) for row in family["accepted_exploration_limitations"]
        ):
            raise HistoricalBacktestGateError(
                "profile exploration limitations must be public strings"
            )
        if (
            len(family["accepted_exploration_limitations"])
            != len(set(family["accepted_exploration_limitations"]))
            or not set(family["accepted_exploration_limitations"])
            <= EXPECTED_EXPLORATION_LIMITATIONS
        ):
            raise HistoricalBacktestGateError(
                "profile exploration limitations differ from exact vocabulary"
            )
        if not isinstance(family["cadences"], list):
            raise HistoricalBacktestGateError("profile cadences must be a list")
        for cadence in family["cadences"]:
            _expect_exact_keys(cadence, {"cadence", "interfaces"}, "profile cadence")
            interfaces = _expect_exact_keys(
                cadence["interfaces"], {"underlying", "option_premium"}, "profile interfaces"
            )
            for interface_name, interface in interfaces.items():
                _expect_exact_keys(
                    interface,
                    {
                        "available",
                        "file_count",
                        "row_count",
                        "coverage",
                        "audit_freshness",
                        "timestamp_quality",
                        "ohlc_quality",
                        "required_activity_fields",
                        "formal_historical_use",
                    },
                    "profile interface",
                )
                _expect_exact_keys(
                    interface["coverage"],
                    {"minimum_observation_timestamp", "maximum_observation_timestamp"},
                    "profile coverage",
                )
                _expect_exact_keys(
                    interface["audit_freshness"],
                    {"calendar_lag_days", "status"},
                    "profile freshness",
                )
                _expect_exact_keys(
                    interface["timestamp_quality"],
                    {"null_rows", "duplicate_rows"},
                    "profile timestamp quality",
                )
                _expect_exact_keys(
                    interface["ohlc_quality"],
                    {"rows_checked", "null_rows", "violation_rows"},
                    "profile OHLC quality",
                )
                if (
                    type(interface["available"]) is not bool
                    or not _is_nonnegative_int(interface["file_count"])
                    or not _is_nonnegative_int(interface["row_count"])
                    or interface["available"] is not (interface["file_count"] > 0)
                    or interface["audit_freshness"]["status"] not in {"current", "stale"}
                    or not _is_nonnegative_int(interface["audit_freshness"]["calendar_lag_days"])
                    or any(
                        not _is_nonnegative_int(interface["timestamp_quality"][field])
                        for field in ("null_rows", "duplicate_rows")
                    )
                    or any(
                        not _is_nonnegative_int(interface["ohlc_quality"][field])
                        for field in ("rows_checked", "null_rows", "violation_rows")
                    )
                ):
                    raise HistoricalBacktestGateError(
                        "profile interface value types or ranges drifted"
                    )
                try:
                    coverage_minimum = datetime.fromisoformat(
                        interface["coverage"]["minimum_observation_timestamp"]
                    )
                    coverage_maximum = datetime.fromisoformat(
                        interface["coverage"]["maximum_observation_timestamp"]
                    )
                except (TypeError, ValueError) as exc:
                    raise HistoricalBacktestGateError(
                        "profile coverage timestamps are invalid"
                    ) from exc
                if coverage_minimum > coverage_maximum:
                    raise HistoricalBacktestGateError("profile coverage range is inverted")
                expected_activity = (
                    {"volume", "open_interest"} if interface_name == "underlying" else set()
                )
                activity = _expect_exact_keys(
                    interface["required_activity_fields"],
                    expected_activity,
                    "profile activity fields",
                )
                for row in activity.values():
                    _expect_exact_keys(
                        row, {"availability", "non_null_rows"}, "profile activity evidence"
                    )
                    if row["availability"] not in {
                        "present_in_all_scanned_files",
                        "present_in_some_scanned_files",
                        "absent_in_scanned_files",
                    } or not _is_nonnegative_int(row["non_null_rows"]):
                        raise HistoricalBacktestGateError(
                            "profile activity evidence values drifted"
                        )


def validate_gate_profile(profile: dict[str, Any], *, contract: dict[str, Any]) -> None:
    validate_contract(contract)
    _validate_profile_shape(profile, contract)
    if profile.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise HistoricalBacktestGateError("unexpected gate profile schema")
    if profile.get("issue_number") != 50:
        raise HistoricalBacktestGateError("profile issue binding drifted")
    if profile.get("contract") != {
        "path": CONTRACT_PUBLIC_PATH,
        "sha256": canonical_hash(contract),
        "sha256_kind": "canonical_json_sha256",
    }:
        raise HistoricalBacktestGateError("profile contract binding drifted")
    aliases = [row.get("alias") for row in profile.get("bound_evidence", [])]
    if aliases != [row["alias"] for row in contract["bound_evidence"]]:
        raise HistoricalBacktestGateError("profile evidence order drifted")
    for observed, expected in zip(
        profile["bound_evidence"],
        contract["bound_evidence"],
        strict=True,
    ):
        if observed != expected:
            raise HistoricalBacktestGateError("profile evidence identity drifted")
    families = [
        row.get("instrument_family") for row in profile.get("candidate_interface_mapping", [])
    ]
    if families != EXPECTED_FAMILIES:
        raise HistoricalBacktestGateError("profile candidate universe drifted")
    for family in profile["candidate_interface_mapping"]:
        if [row.get("cadence") for row in family.get("cadences", [])] != (EXPECTED_CADENCES):
            raise HistoricalBacktestGateError("profile cadence order drifted")
        if family["exploratory_swing_evidence"]["representative_view_count"] != 3:
            raise HistoricalBacktestGateError("profile representative evidence drifted")
        if set(family["known_unavailable_capabilities"]) != {
            "exact_exchange_expiry",
            "historical_bid_ask",
            "contract_delta",
            "causal_iv_history",
        }:
            raise HistoricalBacktestGateError("profile unavailable-capability map drifted")
        for cadence in family["cadences"]:
            expected_use = (
                "conditional_exact_run_binding_required"
                if cadence["cadence"] in REQUIRED_CADENCES
                else "not_consumed_by_p1_exp_002"
            )
            if (
                cadence["interfaces"]["underlying"]["formal_historical_use"] != expected_use
                or cadence["interfaces"]["option_premium"]["formal_historical_use"]
                != "not_consumed_by_p1_exp_002"
                or set(cadence["interfaces"]["underlying"]["required_activity_fields"])
                != {"volume", "open_interest"}
                or cadence["interfaces"]["option_premium"]["required_activity_fields"] != {}
            ):
                raise HistoricalBacktestGateError("profile P1 input projection drifted")
    modes = profile.get("mode_surface", {})
    if (
        modes.get("historical_replay", {}).get("append_only_acquisition_manifest_required")
        is not False
        or modes.get("historical_replay", {}).get("approved_native_source_version_required")
        is not True
        or modes.get("historical_replay", {}).get("exact_filtered_content_binding_required")
        is not True
        or modes.get("prospective_shadow", {}).get("append_only_acquisition_manifest_required")
        is not True
        or modes.get("live", {}).get("authorized_by_this_gate") is not False
    ):
        raise HistoricalBacktestGateError("profile mode boundary drifted")
    baseline = profile.get("baseline", {})
    engineer = profile.get("engineer_surface", {})
    source_version_registered = (
        contract["binding_policy"]["approved_native_source_version_manifest_sha256"] is not None
    )
    expected_baseline_status = (
        "not_evaluated_no_formal_run_request"
        if source_version_registered
        else "blocked_no_approved_native_source_version"
    )
    if (
        baseline.get("p1_exp_002_gate_status") != expected_baseline_status
        or baseline.get("p1_exp_002_outcome_work_authorized") is not False
        or baseline.get("issue_51_unblocked") is not False
        or baseline.get("registry_mutation_authorized") is not False
        or baseline.get("causal_roll_semantic_validation")
        != "deferred_to_issue_51_strategy_implementation"
        or baseline.get("execution_authorized") is not False
        or engineer.get("approved_native_source_version_registered")
        is not source_version_registered
        or engineer.get("complete_prefix_extraction")
        != "all_approved_native_rows_from_history_start_through_decision_cutoff"
        or engineer.get("calendar_versions") != EXPECTED_CALENDAR_VERSIONS
    ):
        raise HistoricalBacktestGateError("profile baseline boundary drifted")
    _assert_public_safe(profile)
