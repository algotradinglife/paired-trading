"""Deterministic read-only audit of Phase 1 candidate market-data interfaces."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


CONTRACT_SCHEMA_VERSION = "pa_feitian_phase1_candidate_interface_audit_contract_v1"
AUDIT_SCHEMA_VERSION = "pa_feitian_phase1_candidate_interface_audit_v1"
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
_EXPECTED_FILENAME_GRAMMAR = {
    "case_insensitive_family_prefix": True,
    "underlying_suffix_regex": "^[0-9]{3,4}$",
    "continuous_underlying_suffix": "0",
    "option_premium_suffix_regex": (
        "^[0-9]{3,4}(?:[CP][0-9]+(?:\\.[0-9]+)?|-[CP]-[0-9]+(?:\\.[0-9]+)?)$"
    ),
    "greeks_sidecar_suffix": ".greeks",
    "raw_contract_identifiers_in_output": False,
    "source_filenames_in_output": False,
}
_EXPECTED_AUDIT_FIELDS = {
    "timestamp_candidates": ["datetime", "timestamp", "date"],
    "ohlc": ["open", "high", "low", "close"],
    "activity": ["volume", "turnover", "open_interest"],
}
_EXPECTED_GUARDRAILS = {
    "explicit_runtime_root_required": True,
    "external_access_read_only": True,
    "source_refresh": False,
    "implicit_current_time": False,
    "deterministic_inventory_order": True,
    "filesystem_timestamps_as_freshness": False,
    "raw_rows_in_output": False,
    "source_filenames_in_output": False,
    "raw_contract_identifiers_in_output": False,
    "strategy_outcome_access": False,
    "performance_calculation": False,
    "instrument_ranking": False,
    "contract_selection": False,
    "cadence_resampling_or_substitution": False,
    "bid_ask_synthesis": False,
    "delta_synthesis": False,
    "m7": False,
    "m8": False,
    "execution": False,
}
_FORBIDDEN_EXACT_KEYS = {
    "entry",
    "exit",
    "fill",
    "pnl",
    "profit",
    "rank",
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


class CandidateInterfaceAuditError(ValueError):
    """Raised when the frozen candidate-interface audit boundary is violated."""


def pretty_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def load_contract(path: Path) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    validate_contract(contract)
    return contract


def validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        raise CandidateInterfaceAuditError("unexpected candidate audit contract schema")
    if contract.get("issue_number") != 43:
        raise CandidateInterfaceAuditError("issue binding drifted")
    if contract.get("audit_as_of_local_date") != AUDIT_AS_OF_LOCAL_DATE:
        raise CandidateInterfaceAuditError("fixed audit date drifted")
    families = [row.get("instrument_family") for row in contract.get("candidate_universe", [])]
    if families != _EXPECTED_FAMILIES:
        raise CandidateInterfaceAuditError("candidate universe or order drifted")
    if contract.get("cadences") != _EXPECTED_CADENCES:
        raise CandidateInterfaceAuditError("candidate audit cadences drifted")
    if contract.get("guardrails") != _EXPECTED_GUARDRAILS:
        raise CandidateInterfaceAuditError("candidate audit guardrails were weakened")
    runtime = contract.get("runtime_input", {})
    if runtime.get("binding") != "QUANT_DATA_ROOT":
        raise CandidateInterfaceAuditError("candidate audit runtime binding drifted")
    if runtime.get("allowed_relative_roots") != _EXPECTED_CADENCES:
        raise CandidateInterfaceAuditError("candidate audit roots drifted")
    if contract.get("filename_interface_grammar") != _EXPECTED_FILENAME_GRAMMAR:
        raise CandidateInterfaceAuditError("candidate filename grammar drifted")
    if contract.get("audit_fields") != _EXPECTED_AUDIT_FIELDS:
        raise CandidateInterfaceAuditError("candidate audit fields drifted")
    freshness = contract.get("freshness_policy", {})
    if freshness.get("fresh_max_calendar_lag_days") != 7:
        raise CandidateInterfaceAuditError("freshness threshold drifted")
    if freshness.get("implicit_current_time") is not False:
        raise CandidateInterfaceAuditError("freshness must not use current time")
    liquidity = contract.get("liquidity_proxy", {})
    if liquidity.get("minimum_pass_rate") is not None:
        raise CandidateInterfaceAuditError("liquidity proxy became a pass gate")
    if liquidity.get("ranking_allowed") is not False:
        raise CandidateInterfaceAuditError("instrument ranking is forbidden")


def _schema_signature(schema: pa.Schema) -> str:
    return ",".join(f"{field.name}:{field.type}" for field in schema)


def _scalar_int(value: pa.Scalar) -> int:
    result = value.as_py()
    return int(result) if result is not None else 0


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _classify_filename(name: str, candidate: dict[str, Any]) -> str | None:
    if not name.lower().endswith(".parquet"):
        return None
    stem = name[: -len(".parquet")]
    prefix = f"{candidate['exchange']}.{candidate['product']}"
    if not stem.lower().startswith(prefix.lower()):
        return None
    suffix = stem[len(prefix) :]
    greeks = suffix.endswith(".greeks")
    if greeks:
        suffix = suffix[: -len(".greeks")]
    grammar = {
        "underlying": re.fullmatch(r"[0-9]{3,4}", suffix),
        "continuous_underlying": suffix == "0",
        "option_premium": re.fullmatch(
            r"[0-9]{3,4}(?:[CP][0-9]+(?:\.[0-9]+)?|-[CP]-[0-9]+(?:\.[0-9]+)?)",
            suffix,
            flags=re.IGNORECASE,
        ),
    }
    if greeks:
        return "option_greeks_sidecar" if grammar["option_premium"] else "sidecar"
    for interface in ("option_premium", "underlying", "continuous_underlying"):
        if grammar[interface]:
            return interface
    return "unclassified"


def _count_true(value: pa.Array | pa.ChunkedArray) -> int:
    return _scalar_int(pc.sum(pc.cast(pc.fill_null(value, False), pa.int64())))


def _and_all(values: list[pa.Array | pa.ChunkedArray]) -> pa.Array | pa.ChunkedArray:
    result = values[0]
    for value in values[1:]:
        result = pc.and_kleene(result, value)
    return result


def _or_all(values: list[pa.Array | pa.ChunkedArray]) -> pa.Array | pa.ChunkedArray:
    result = values[0]
    for value in values[1:]:
        result = pc.or_kleene(result, value)
    return result


def _scan_file(
    task: tuple[Path, str, str, dict[str, Any]],
    *,
    timestamp_candidates: list[str],
    ohlc_fields: list[str],
    activity_fields: list[str],
) -> dict[str, Any]:
    path, cadence, interface, candidate = task
    path_identity = hashlib.sha256(f"{cadence}\0{path.name}".encode()).hexdigest()
    try:
        parquet = pq.ParquetFile(path)
        schema = parquet.schema_arrow
        timestamp_field = next(
            (field for field in timestamp_candidates if field in schema.names),
            None,
        )
        selected_fields = [
            field
            for field in [timestamp_field, *ohlc_fields, *activity_fields]
            if field is not None and field in schema.names
        ]
        table = pq.read_table(path, columns=list(dict.fromkeys(selected_fields)))
        row_count = parquet.metadata.num_rows

        minimum_timestamp = None
        maximum_timestamp = None
        null_timestamps = row_count
        duplicate_timestamps = 0
        if timestamp_field is not None:
            timestamps = table[timestamp_field]
            null_timestamps = timestamps.null_count
            non_null_timestamps = row_count - null_timestamps
            minimum_timestamp = _iso(pc.min(timestamps).as_py())
            maximum_timestamp = _iso(pc.max(timestamps).as_py())
            distinct_timestamps = _scalar_int(pc.count_distinct(timestamps))
            duplicate_timestamps = non_null_timestamps - distinct_timestamps

        ohlc_present = [field for field in ohlc_fields if field in schema.names]
        ohlc_rows_checked = 0
        ohlc_null_rows = row_count
        ohlc_violation_rows = 0
        if ohlc_present == ohlc_fields:
            non_null_masks = [pc.is_valid(table[field]) for field in ohlc_fields]
            valid_ohlc = _and_all(non_null_masks)
            ohlc_rows_checked = _count_true(valid_ohlc)
            ohlc_null_rows = row_count - ohlc_rows_checked
            violation = _or_all(
                [
                    pc.greater(table["low"], table["high"]),
                    pc.greater(table["open"], table["high"]),
                    pc.greater(table["close"], table["high"]),
                    pc.less(table["open"], table["low"]),
                    pc.less(table["close"], table["low"]),
                ]
            )
            ohlc_violation_rows = _count_true(pc.and_kleene(valid_ohlc, violation))

        activity: dict[str, dict[str, int | bool]] = {}
        nonzero_masks = []
        for field in activity_fields:
            present = field in schema.names
            nonzero_rows = 0
            non_null_rows = 0
            if present:
                values = table[field]
                non_null_rows = row_count - values.null_count
                nonzero = pc.not_equal(values, 0)
                nonzero_rows = _count_true(nonzero)
                nonzero_masks.append(nonzero)
            activity[field] = {
                "present": present,
                "non_null_rows": non_null_rows,
                "nonzero_rows": nonzero_rows,
            }
        rows_with_any_nonzero_activity = _count_true(_or_all(nonzero_masks)) if nonzero_masks else 0

        return {
            "path_identity_sha256": path_identity,
            "family": candidate["instrument_family"],
            "cadence": cadence,
            "interface": interface,
            "status": "scanned",
            "byte_size": path.stat().st_size,
            "row_count": row_count,
            "schema": _schema_signature(schema),
            "timestamp_field": timestamp_field,
            "minimum_observation_timestamp": minimum_timestamp,
            "maximum_observation_timestamp": maximum_timestamp,
            "null_timestamp_rows": null_timestamps,
            "duplicate_timestamp_rows": duplicate_timestamps,
            "ohlc_fields_present": ohlc_present,
            "ohlc_rows_checked": ohlc_rows_checked,
            "ohlc_null_rows": ohlc_null_rows,
            "ohlc_violation_rows": ohlc_violation_rows,
            "activity": activity,
            "rows_with_any_nonzero_activity": rows_with_any_nonzero_activity,
        }
    except Exception as exc:  # noqa: BLE001 - errors are aggregated without paths
        return {
            "path_identity_sha256": path_identity,
            "family": candidate["instrument_family"],
            "cadence": cadence,
            "interface": interface,
            "status": "read_error",
            "error_type": type(exc).__name__,
        }


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
        raise CandidateInterfaceAuditError("latest observation is after fixed audit date")
    return {
        "latest_observation": latest,
        "calendar_lag_days": lag,
        "status": "fresh" if lag <= fresh_max_days else "stale",
    }


def _field_coverage(
    records: list[dict[str, Any]],
    *,
    field: str,
    category: str,
) -> str:
    scanned = [record for record in records if record["status"] == "scanned"]
    if not scanned:
        return "unknown"
    if category == "schema":
        present_count = sum(
            any(part.startswith(f"{field}:") for part in record["schema"].split(","))
            for record in scanned
        )
    else:
        present_count = sum(record[category][field]["present"] for record in scanned)
    if present_count == len(scanned):
        return "present_in_all_scanned_files"
    if present_count:
        return "present_in_some_scanned_files"
    return "absent_from_all_scanned_files"


def _summarize_interface(
    records: list[dict[str, Any]],
    *,
    as_of: str,
    fresh_max_days: int,
    ohlc_fields: list[str],
    activity_fields: list[str],
) -> dict[str, Any]:
    scanned = [record for record in records if record["status"] == "scanned"]
    errors = [record for record in records if record["status"] == "read_error"]
    schemas = Counter(record["schema"] for record in scanned)
    latest = max(
        (
            record["maximum_observation_timestamp"]
            for record in scanned
            if record["maximum_observation_timestamp"] is not None
        ),
        default=None,
    )
    earliest = min(
        (
            record["minimum_observation_timestamp"]
            for record in scanned
            if record["minimum_observation_timestamp"] is not None
        ),
        default=None,
    )
    row_count = sum(record["row_count"] for record in scanned)
    activity = {
        field: {
            "availability": _field_coverage(
                scanned,
                field=field,
                category="activity",
            ),
            "non_null_rows": sum(record["activity"][field]["non_null_rows"] for record in scanned),
            "nonzero_rows": sum(record["activity"][field]["nonzero_rows"] for record in scanned),
        }
        for field in activity_fields
    }
    rows_with_activity = sum(record["rows_with_any_nonzero_activity"] for record in scanned)
    return {
        "matched_files": len(records),
        "scanned_files": len(scanned),
        "read_error_files": len(errors),
        "read_error_types": dict(
            sorted(Counter(record["error_type"] for record in errors).items())
        ),
        "byte_size": sum(record["byte_size"] for record in scanned),
        "rows": row_count,
        "coverage": {
            "minimum_observation_timestamp": earliest,
            "maximum_observation_timestamp": latest,
        },
        "freshness": _freshness(
            latest,
            as_of=as_of,
            fresh_max_days=fresh_max_days,
        ),
        "schema": {
            "variant_count": len(schemas),
            "consistent": len(schemas) == 1 and bool(scanned),
            "variants": [
                {"signature": signature, "file_count": count}
                for signature, count in sorted(schemas.items())
            ],
            "fields": {
                field: _field_coverage(scanned, field=field, category="schema")
                for field in [*ohlc_fields, *activity_fields]
            },
        },
        "timestamp_quality": {
            "null_rows": sum(record["null_timestamp_rows"] for record in scanned),
            "duplicate_rows": sum(record["duplicate_timestamp_rows"] for record in scanned),
        },
        "ohlc_quality": {
            "fields": {
                field: _field_coverage(scanned, field=field, category="schema")
                for field in ohlc_fields
            },
            "rows_checked": sum(record["ohlc_rows_checked"] for record in scanned),
            "null_rows": sum(record["ohlc_null_rows"] for record in scanned),
            "violation_rows": sum(record["ohlc_violation_rows"] for record in scanned),
        },
        "activity_fields": activity,
        "liquidity_proxy": {
            "name": "rows_with_any_observed_nonzero_activity_rate",
            "rows_with_any_nonzero_activity": rows_with_activity,
            "all_rows": row_count,
            "rate": round(rows_with_activity / row_count, 6) if row_count else None,
            "minimum_pass_rate": None,
            "ranking_or_outcomes_used": False,
        },
    }


def _inventory_tasks(
    *,
    contract: dict[str, Any],
    data_root: Path,
) -> tuple[list[tuple[Path, str, str, dict[str, Any]]], dict[str, int]]:
    tasks = []
    directory_entries: dict[str, int] = {}
    for cadence in contract["cadences"]:
        root = data_root / cadence
        if not root.is_dir():
            raise CandidateInterfaceAuditError(f"required cadence root is unavailable: {cadence}")
        paths = sorted(root.iterdir(), key=lambda path: path.name)
        directory_entries[cadence] = len(paths)
        for path in paths:
            for candidate in contract["candidate_universe"]:
                interface = _classify_filename(path.name, candidate)
                if interface is not None:
                    tasks.append((path, cadence, interface, candidate))
                    break
    tasks.sort(
        key=lambda item: (
            item[3]["instrument_family"],
            item[1],
            item[0].name,
        )
    )
    return tasks, directory_entries


def build_audit(
    *,
    contract: dict[str, Any],
    contract_path: Path,
    data_root: Path,
    workers: int = 8,
) -> dict[str, Any]:
    """Read the explicit candidate interfaces and return public-safe aggregates."""

    validate_contract(contract)
    if workers < 1:
        raise CandidateInterfaceAuditError("workers must be positive")
    resolved_root = data_root.resolve(strict=True)
    tasks, directory_entries = _inventory_tasks(
        contract=contract,
        data_root=resolved_root,
    )
    fields = contract["audit_fields"]

    def scan(task: tuple[Path, str, str, dict[str, Any]]) -> dict[str, Any]:
        return _scan_file(
            task,
            timestamp_candidates=fields["timestamp_candidates"],
            ohlc_fields=fields["ohlc"],
            activity_fields=fields["activity"],
        )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        records = list(executor.map(scan, tasks))

    as_of = contract["audit_as_of_local_date"]
    fresh_max_days = contract["freshness_policy"]["fresh_max_calendar_lag_days"]
    decision_surface = []
    for candidate in contract["candidate_universe"]:
        family = candidate["instrument_family"]
        cadences = []
        for cadence in contract["cadences"]:
            family_records = [
                record
                for record in records
                if record["family"] == family and record["cadence"] == cadence
            ]
            interfaces = {}
            for interface in (
                "underlying",
                "continuous_underlying",
                "option_premium",
                "option_greeks_sidecar",
                "sidecar",
                "unclassified",
            ):
                interface_records = [
                    record for record in family_records if record["interface"] == interface
                ]
                if interface_records:
                    interfaces[interface] = _summarize_interface(
                        interface_records,
                        as_of=as_of,
                        fresh_max_days=fresh_max_days,
                        ohlc_fields=fields["ohlc"],
                        activity_fields=fields["activity"],
                    )
            cadences.append(
                {
                    "cadence": cadence,
                    "matched_files": len(family_records),
                    "interfaces": interfaces,
                }
            )
        decision_surface.append(
            {
                "instrument_family": family,
                "role": candidate["role"],
                "cadences": cadences,
            }
        )

    inventory_records = [
        {key: value for key, value in record.items() if key not in {"family", "cadence"}}
        | {
            "family": record["family"],
            "cadence": record["cadence"],
        }
        for record in records
    ]
    inventory_sha = (
        "sha256:"
        + hashlib.sha256(
            b"".join(canonical_json_bytes(record) for record in inventory_records)
        ).hexdigest()
    )
    audit = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "audit_id": contract["contract_id"],
        "issue_number": 43,
        "audit_as_of_local_date": as_of,
        "timezone": contract["timezone"],
        "contract": {
            "alias": ("repository://paired-trading/phase1-candidate-interface-audit-contract-v1"),
            "schema_version": contract["schema_version"],
            "sha256": sha256_file(contract_path),
        },
        "source": {
            "alias": contract["runtime_input"]["public_alias"],
            "runtime_binding": contract["runtime_input"]["binding"],
            "access": "read_only",
            "source_refresh_performed": False,
            "filesystem_timestamps_used_as_freshness": False,
            "directory_entries_by_cadence": directory_entries,
            "matched_candidate_files": len(records),
            "inventory_sha256": inventory_sha,
        },
        "guardrails": contract["guardrails"],
        "decision_surface": decision_surface,
        "public_safety": {
            "local_paths": False,
            "local_usernames": False,
            "source_filenames": False,
            "raw_contract_identifiers": False,
            "raw_rows": False,
            "credentials": False,
            "strategy_outcomes": False,
            "instrument_ranking": False,
            "bid_ask_synthesis": False,
            "delta_synthesis": False,
        },
    }
    validate_audit(audit, contract=contract)
    return audit


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key).lower())
            keys.extend(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(_walk_keys(child))
    return keys


def validate_audit(audit: dict[str, Any], *, contract: dict[str, Any]) -> None:
    validate_contract(contract)
    if audit.get("schema_version") != AUDIT_SCHEMA_VERSION:
        raise CandidateInterfaceAuditError("unexpected candidate audit schema")
    if audit.get("audit_as_of_local_date") != AUDIT_AS_OF_LOCAL_DATE:
        raise CandidateInterfaceAuditError("candidate audit fixed date drifted")
    rows = audit.get("decision_surface", [])
    families = [row.get("instrument_family") for row in rows]
    if families != _EXPECTED_FAMILIES:
        raise CandidateInterfaceAuditError("candidate audit universe drifted")
    for row in rows:
        cadences = [cell.get("cadence") for cell in row.get("cadences", [])]
        if cadences != _EXPECTED_CADENCES:
            raise CandidateInterfaceAuditError("candidate audit cadence order drifted")
    source = audit.get("source", {})
    if source.get("runtime_binding") != "QUANT_DATA_ROOT":
        raise CandidateInterfaceAuditError("candidate audit source binding drifted")
    if source.get("access") != "read_only":
        raise CandidateInterfaceAuditError("candidate audit access is not read-only")
    if source.get("matched_candidate_files", 0) <= 0:
        raise CandidateInterfaceAuditError("candidate audit matched no interface files")

    forbidden_keys = sorted(set(_walk_keys(audit)) & _FORBIDDEN_EXACT_KEYS)
    if forbidden_keys:
        raise CandidateInterfaceAuditError(
            f"forbidden outcome or selection fields: {forbidden_keys}"
        )
    encoded = pretty_json_bytes(audit).decode("utf-8")
    for forbidden in _FORBIDDEN_TEXT:
        if forbidden in encoded:
            raise CandidateInterfaceAuditError("public-safety text boundary violated")
    if _RAW_CONTRACT_ID.search(encoded):
        raise CandidateInterfaceAuditError("raw contract identifier is forbidden")
