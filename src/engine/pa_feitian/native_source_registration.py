"""Fail-closed real-source audit for Issue #58 native-version registration."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pyarrow as pa
import pyarrow.parquet as pq

from engine.pa_feitian.historical_backtest_gate import (
    EXPECTED_CALENDAR_VERSIONS,
    EXPECTED_FAMILIES,
    FROZEN_CONTRACT_SHA256,
    HISTORY_START_UTC,
    REQUIRED_CADENCES,
    authoritative_session_slots,
)

CONTRACT_SCHEMA_VERSION = "pa_feitian_m6_native_source_registration_contract_v1"
AUDIT_SCHEMA_VERSION = "pa_feitian_m6_native_source_registration_audit_v1"
CONTRACT_ID = "pa_feitian_m6_native_source_registration_2026_07_30"
AUDIT_ID = "pa-feitian-m6-native-source-registration-2026-07-30"
AUDIT_AS_OF_UTC = "2026-07-30T15:45:00Z"
SOURCE_TIMEZONE = "Asia/Shanghai"
FROZEN_REGISTRATION_CONTRACT_SHA256 = (
    "sha256:8c2713ae02710e8dbdeeff04fa4be84b818690b9d881104a23069c218f5b83c1"
)
FROZEN_REGISTRATION_CONTRACT_CANONICAL_SHA256 = (
    "sha256:51d8a2917408a48ef76cf25cc7110a677ff5dc9d46af5faec8396c11a47fc675"
)
FAMILY_PARTS = {
    "SHFE.au": ("SHFE", "au"),
    "SHFE.ag": ("SHFE", "ag"),
    "CZCE.TA": ("CZCE", "TA"),
    "CZCE.MA": ("CZCE", "MA"),
    "SHFE.cu": ("SHFE", "cu"),
    "DCE.i": ("DCE", "i"),
}
STAGED_WINDOWS = [
    ("P1-EXP-002-TRAIN", date(2021, 11, 1), date(2023, 6, 30)),
    ("P1-EXP-002-VALIDATE", date(2023, 7, 8), date(2024, 12, 31)),
    ("P1-EXP-002-HOLDOUT", date(2025, 1, 11), date(2026, 4, 30)),
]
REQUIRED_FIELDS = {
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "open_interest",
}
PROVIDER_METADATA_KEYS = {
    "source_provider",
    "timestamp_semantics",
    "bar_timestamp_position",
}
EXPECTED_GUARDRAILS = {
    "external_access_read_only": True,
    "source_refresh": False,
    "source_mutation": False,
    "outcome_access": False,
    "strategy_event_construction": False,
    "instrument_ranking": False,
    "option_input_access": False,
    "bid_ask_synthesis": False,
    "delta_synthesis": False,
    "iv_synthesis": False,
    "m7": False,
    "m8": False,
    "execution": False,
}
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
CLOCK_PATTERN = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
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
DATA_BLOCKERS = {
    "required_source_cell_missing",
    "source_file_unreadable_or_invalid",
    "duplicate_normalized_source_identity",
    "required_row_fields_missing",
    "timestamp_storage_contract_mismatch",
    "unusable_timestamps_present",
    "null_timestamps_present",
    "duplicate_contract_timestamps_present",
    "history_start_coverage_missing",
    "formal_horizon_coverage_missing",
    "staged_window_coverage_missing",
    "ohlc_quality_findings_present",
    "activity_quality_findings_present",
}
SEMANTIC_BLOCKERS = {
    "provider_bar_end_semantics_unbound",
    "timestamps_outside_frozen_session_end_grid",
}
ALLOWED_BLOCKERS = DATA_BLOCKERS | SEMANTIC_BLOCKERS


class NativeSourceRegistrationError(ValueError):
    """Raised when the Issue #58 audit boundary or input contract is violated."""


def pretty_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def canonical_hash(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, nested in pairs:
        if key in value:
            raise NativeSourceRegistrationError(f"duplicate JSON key: {key}")
        value[key] = nested
    return value


def strict_json_loads(value: str) -> Any:
    try:
        return json.loads(
            value,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda constant: (_ for _ in ()).throw(
                NativeSourceRegistrationError(f"non-standard JSON constant: {constant}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise NativeSourceRegistrationError(f"invalid JSON: {exc}") from exc


def _read_regular_file_once(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise NativeSourceRegistrationError("required file is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise NativeSourceRegistrationError("required file must be regular")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            content = handle.read()
        after = os.fstat(descriptor)
        identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if identity_before != identity_after or len(content) != after.st_size:
            raise NativeSourceRegistrationError("required file changed during capture")
        return content
    finally:
        os.close(descriptor)


def _assert_public_safe(value: Any) -> None:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    lowered = text.lower()
    if any(token.lower() in lowered for token in FORBIDDEN_TEXT):
        raise NativeSourceRegistrationError("public artifact contains a forbidden path or filename")
    if RAW_CONTRACT_ID.search(text):
        raise NativeSourceRegistrationError("public artifact contains a raw contract identifier")
    if TOKEN_PREFIX.search(text):
        raise NativeSourceRegistrationError("public artifact contains a credential-like token")


def load_contract_capture(path: Path) -> tuple[dict[str, Any], bytes]:
    content = _read_regular_file_once(path)
    if sha256_bytes(content) != FROZEN_REGISTRATION_CONTRACT_SHA256:
        raise NativeSourceRegistrationError("registration contract byte identity drifted")
    contract = strict_json_loads(content.decode("utf-8"))
    if not isinstance(contract, dict):
        raise NativeSourceRegistrationError("registration contract must be an object")
    validate_contract(contract)
    return contract, content


def load_contract(path: Path) -> dict[str, Any]:
    return load_contract_capture(path)[0]


def validate_contract(contract: dict[str, Any]) -> None:
    if canonical_hash(contract) != FROZEN_REGISTRATION_CONTRACT_CANONICAL_SHA256:
        raise NativeSourceRegistrationError("registration contract content drifted")
    if contract.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        raise NativeSourceRegistrationError("unexpected registration contract schema")
    if (
        contract.get("contract_id") != CONTRACT_ID
        or contract.get("issue_number") != 58
        or contract.get("audit_as_of_utc") != AUDIT_AS_OF_UTC
    ):
        raise NativeSourceRegistrationError("issue or audit-time binding drifted")
    dependency = contract.get("dependency", {})
    if (
        dependency.get("issue_50_status") != "done"
        or dependency.get("merged_gate_contract_sha256") != FROZEN_CONTRACT_SHA256
        or dependency.get("approved_native_source_version_manifest_sha256_before_audit") is not None
    ):
        raise NativeSourceRegistrationError("Issue #50 dependency binding drifted")
    runtime = contract.get("runtime_input", {})
    if (
        runtime.get("binding") != "QUANT_DATA_ROOT"
        or runtime.get("access") != "read_only"
        or runtime.get("allowed_relative_roots") != REQUIRED_CADENCES
        or runtime.get("direct_children_only") is not True
        or runtime.get("symlinks_allowed") is not False
    ):
        raise NativeSourceRegistrationError("runtime input boundary drifted")
    candidate = contract.get("source_version_candidate", {})
    if (
        candidate.get("required_families") != EXPECTED_FAMILIES
        or candidate.get("required_cadences") != REQUIRED_CADENCES
        or candidate.get("required_matrix_cells") != 18
        or candidate.get("history_start_inclusive") != "2021-06-01T00:00:00+08:00"
        or candidate.get("last_formal_decision_local") != "2026-04-30T15:00:00+08:00"
    ):
        raise NativeSourceRegistrationError("source candidate matrix drifted")
    row_policy = contract.get("row_policy", {})
    if (
        row_policy.get("required_fields")
        != [
            "datetime",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "open_interest",
        ]
        or set(row_policy.get("provider_metadata_keys", [])) != PROVIDER_METADATA_KEYS
        or row_policy.get("required_bar_timestamp_position") != "end"
        or row_policy.get("intraday_normalization")
        != "none_without_bound_provider_bar_end_semantics"
        or row_policy.get("approved_provider_metadata_value_sha256") is not None
        or row_policy.get("unexplained_timestamp_action") != "contract_revision_required"
    ):
        raise NativeSourceRegistrationError("row or timestamp policy drifted")
    session = contract.get("session_policy", {})
    if (
        session.get("calendar_versions") != EXPECTED_CALENDAR_VERSIONS
        or session.get("slot_policy") != "frozen_exchange_sessions_and_family_night_segments"
    ):
        raise NativeSourceRegistrationError("session policy drifted")
    stages = [
        (row.get("window_id"), row.get("decision_date_start"), row.get("decision_date_end"))
        for row in contract.get("staged_windows", [])
    ]
    if stages != [
        (name, start.isoformat(), end.isoformat()) for name, start, end in STAGED_WINDOWS
    ]:
        raise NativeSourceRegistrationError("staged windows drifted")
    if contract.get("guardrails") != EXPECTED_GUARDRAILS:
        raise NativeSourceRegistrationError("registration guardrails were weakened")
    _assert_public_safe(contract)


def _metadata(schema: pa.Schema) -> dict[str, str]:
    return {
        key.decode("utf-8", errors="replace"): value.decode("utf-8", errors="replace")
        for key, value in (schema.metadata or {}).items()
    }


def _source_file_id(family: str, cadence: str, suffix: str) -> str:
    return sha256_bytes(f"{family}\0{cadence}\0{suffix}".encode())


def _family_pattern(family: str) -> re.Pattern[str]:
    exchange, product = FAMILY_PARTS[family]
    return re.compile(
        rf"^{re.escape(exchange)}\.{re.escape(product)}(?P<suffix>[0-9]{{3,4}})\.parquet$",
        re.IGNORECASE,
    )


def _enumerate_source_files(
    data_root: Path,
) -> tuple[dict[tuple[str, str], list[tuple[str, str]]], dict[str, int]]:
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        root_descriptor = os.open(data_root, directory_flags)
    except OSError as exc:
        raise NativeSourceRegistrationError("data root must be a real directory") from exc
    cadence_descriptors: dict[str, int] = {}
    try:
        if not stat.S_ISDIR(os.fstat(root_descriptor).st_mode):
            raise NativeSourceRegistrationError("data root must be a real directory")
        entries_by_cadence: dict[str, list[str]] = {}
        for cadence in REQUIRED_CADENCES:
            try:
                descriptor = os.open(cadence, directory_flags, dir_fd=root_descriptor)
            except OSError as exc:
                raise NativeSourceRegistrationError(
                    "a required cadence root is unavailable"
                ) from exc
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                os.close(descriptor)
                raise NativeSourceRegistrationError("a required cadence root is unavailable")
            cadence_descriptors[cadence] = descriptor
            with os.scandir(descriptor) as iterator:
                entries_by_cadence[cadence] = sorted(
                    (entry.name for entry in iterator if entry.is_file(follow_symlinks=False)),
                    key=str.encode,
                )
        matrix: dict[tuple[str, str], list[tuple[str, str]]] = {}
        for cadence in REQUIRED_CADENCES:
            for family in EXPECTED_FAMILIES:
                pattern = _family_pattern(family)
                selected: list[tuple[str, str]] = []
                for filename in entries_by_cadence[cadence]:
                    match = pattern.fullmatch(filename)
                    if match is not None and match.group("suffix") != "0":
                        selected.append((filename, match.group("suffix")))
                matrix[(family, cadence)] = selected
        return matrix, cadence_descriptors
    except Exception:
        for descriptor in cadence_descriptors.values():
            os.close(descriptor)
        raise
    finally:
        os.close(root_descriptor)


@lru_cache(maxsize=None)
def _legal_slot_map(
    *,
    family: str,
    cadence: str,
    minimum: date | None = None,
    maximum: date | None = None,
) -> dict[datetime, date]:
    local = ZoneInfo(SOURCE_TIMEZONE)
    history_start = HISTORY_START_UTC.astimezone(local)
    minimum = minimum or history_start.date() - timedelta(days=12)
    maximum = (
        maximum
        or datetime.fromisoformat(AUDIT_AS_OF_UTC.replace("Z", "+00:00")).astimezone(local).date()
    )
    mapping: dict[datetime, date] = {}
    current = minimum
    while current <= maximum:
        for observed in authoritative_session_slots(
            instrument_family=family,
            cadence=cadence,
            session_date=current,
        ):
            wall_clock = observed.astimezone(local).replace(tzinfo=None)
            prior = mapping.setdefault(wall_clock, current)
            if prior != current:
                raise NativeSourceRegistrationError("authoritative slot maps to multiple sessions")
        current = date.fromordinal(current.toordinal() + 1)
    return mapping


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _scan_file(
    *,
    directory_descriptor: int,
    filename: str,
    suffix: str,
    family: str,
    cadence: str,
    legal_slots: dict[datetime, date],
    approved_provider_metadata_value_sha256: str | None,
) -> dict[str, Any]:
    identity = _source_file_id(family, cadence, suffix)
    relative = f"{cadence}/{filename}"
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(filename, flags, dir_fd=directory_descriptor)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise NativeSourceRegistrationError("source input must be a regular file")
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                content = handle.read()
            after = os.fstat(descriptor)
            identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            if identity_before != identity_after or len(content) != after.st_size:
                raise NativeSourceRegistrationError("source input changed during capture")
        finally:
            os.close(descriptor)
    except (OSError, NativeSourceRegistrationError):
        return {
            "family": family,
            "cadence": cadence,
            "source_file_identity_sha256": identity,
            "source_file_sha256": None,
            "byte_size": 0,
            "row_count": 0,
            "readable": False,
            "schema_sha256": None,
            "required_fields_complete": False,
            "timestamp_storage_valid": False,
            "embedded_provider_metadata_complete": False,
            "bar_end_semantics_bound": cadence == "daily",
            "minimum_native_wall_clock": None,
            "maximum_native_wall_clock": None,
            "minimum_authorized_endpoint_wall_clock": None,
            "maximum_authorized_endpoint_wall_clock": None,
            "unusable_timestamp_rows": 0,
            "null_timestamp_rows": 0,
            "duplicate_timestamp_rows": 0,
            "prehistory_rows": 0,
            "candidate_rows": 0,
            "authorized_endpoint_rows": 0,
            "unexplained_timestamp_rows": 0,
            "daily_normalized_rows": 0,
            "ohlc_violation_rows": 0,
            "nonfinite_or_negative_activity_rows": 0,
            "clock_counts": {},
            "stage_counts": {
                name: {"candidate_rows": 0, "authorized_rows": 0} for name, _, _ in STAGED_WINDOWS
            },
            "_private_inventory": {
                "relative_path": relative,
                "capture_status": "unavailable",
            },
        }

    source_hash = sha256_bytes(content)
    try:
        parquet = pq.ParquetFile(pa.BufferReader(content))
        schema = parquet.schema_arrow
        selected_fields = [field for field in REQUIRED_FIELDS if field in schema.names]
        table = parquet.read(columns=sorted(selected_fields))
    except (OSError, pa.ArrowException):
        return {
            "family": family,
            "cadence": cadence,
            "source_file_identity_sha256": identity,
            "source_file_sha256": source_hash,
            "byte_size": len(content),
            "row_count": 0,
            "readable": False,
            "schema_sha256": None,
            "required_fields_complete": False,
            "timestamp_storage_valid": False,
            "embedded_provider_metadata_complete": False,
            "bar_end_semantics_bound": cadence == "daily",
            "minimum_native_wall_clock": None,
            "maximum_native_wall_clock": None,
            "minimum_authorized_endpoint_wall_clock": None,
            "maximum_authorized_endpoint_wall_clock": None,
            "unusable_timestamp_rows": 0,
            "null_timestamp_rows": 0,
            "duplicate_timestamp_rows": 0,
            "prehistory_rows": 0,
            "candidate_rows": 0,
            "authorized_endpoint_rows": 0,
            "unexplained_timestamp_rows": 0,
            "daily_normalized_rows": 0,
            "ohlc_violation_rows": 0,
            "nonfinite_or_negative_activity_rows": 0,
            "clock_counts": {},
            "stage_counts": {
                name: {"candidate_rows": 0, "authorized_rows": 0} for name, _, _ in STAGED_WINDOWS
            },
            "_private_inventory": {
                "relative_path": relative,
                "source_file_sha256": source_hash,
                "byte_size": len(content),
                "capture_status": "invalid_parquet",
            },
        }

    metadata = _metadata(schema)
    provider_metadata = {key: metadata.get(key) for key in sorted(PROVIDER_METADATA_KEYS)}
    embedded_provider_metadata_complete = (
        all(provider_metadata.values()) and provider_metadata["bar_timestamp_position"] == "end"
    )
    missing_fields = sorted(REQUIRED_FIELDS - set(schema.names))
    timestamp_type = schema.field("datetime").type if "datetime" in schema.names else None
    timestamp_storage_valid = (
        timestamp_type is not None
        and pa.types.is_timestamp(timestamp_type)
        and getattr(timestamp_type, "tz", None) is None
    )
    provider_metadata_value_sha256 = canonical_hash(provider_metadata)
    provider_metadata_bound = (
        embedded_provider_metadata_complete
        and approved_provider_metadata_value_sha256 is not None
        and provider_metadata_value_sha256 == approved_provider_metadata_value_sha256
    )

    timestamps = (
        table["datetime"].to_pylist()
        if "datetime" in table.column_names and timestamp_storage_valid
        else []
    )
    columns = {
        field: table[field].to_pylist()
        for field in ("open", "high", "low", "close", "volume", "open_interest")
        if field in table.column_names
    }
    null_timestamps = 0
    unusable_timestamps = 0 if timestamp_storage_valid else parquet.metadata.num_rows
    prehistory_rows = 0
    candidate_rows = 0
    authorized_rows = 0
    unexplained_rows = 0
    daily_normalized_rows = 0
    stage_counts = {
        name: {"candidate_rows": 0, "authorized_rows": 0} for name, _, _ in STAGED_WINDOWS
    }
    clock_counts: Counter[str] = Counter()
    timestamp_counts: Counter[str] = Counter()
    minimum: datetime | None = None
    maximum: datetime | None = None
    minimum_authorized: datetime | None = None
    maximum_authorized: datetime | None = None
    candidate_flags: list[bool] = []
    local_history_start = HISTORY_START_UTC.astimezone(ZoneInfo(SOURCE_TIMEZONE)).replace(
        tzinfo=None
    )

    for observed in timestamps:
        if observed is None:
            null_timestamps += 1
            candidate_flags.append(False)
            continue
        if observed.tzinfo is not None:
            observed = observed.astimezone(ZoneInfo(SOURCE_TIMEZONE)).replace(tzinfo=None)
        minimum = observed if minimum is None or observed < minimum else minimum
        maximum = observed if maximum is None or observed > maximum else maximum
        clock_counts[observed.strftime("%H:%M")] += 1
        if observed < local_history_start:
            prehistory_rows += 1
            candidate_flags.append(False)
            continue
        candidate_rows += 1
        candidate_flags.append(True)
        timestamp_counts[observed.isoformat(timespec="seconds")] += 1
        session_date: date | None = None
        effective_endpoint: datetime | None = None
        if cadence == "daily":
            close_key = observed.replace(hour=15, minute=0, second=0, microsecond=0)
            if observed in legal_slots:
                session_date = legal_slots[observed]
                effective_endpoint = observed
            elif observed.time() == datetime.min.time() and close_key in legal_slots:
                session_date = legal_slots[close_key]
                effective_endpoint = close_key
                daily_normalized_rows += 1
        else:
            session_date = legal_slots.get(observed)
            effective_endpoint = observed if session_date is not None else None
        if session_date is None:
            unexplained_rows += 1
        else:
            authorized_rows += 1
            minimum_authorized = (
                effective_endpoint
                if minimum_authorized is None or effective_endpoint < minimum_authorized
                else minimum_authorized
            )
            maximum_authorized = (
                effective_endpoint
                if maximum_authorized is None or effective_endpoint > maximum_authorized
                else maximum_authorized
            )
        for name, start, end in STAGED_WINDOWS:
            comparison_date = session_date or observed.date()
            if start <= comparison_date <= end:
                stage_counts[name]["candidate_rows"] += 1
                if session_date is not None:
                    stage_counts[name]["authorized_rows"] += 1

    duplicate_rows = sum(count - 1 for count in timestamp_counts.values() if count > 1)
    ohlc_violations = 0
    activity_violations = 0
    if not missing_fields:
        for index in range(len(timestamps)):
            if not candidate_flags[index]:
                continue
            prices = [columns[field][index] for field in ("open", "high", "low", "close")]
            if not all(_finite_number(value) and float(value) > 0 for value in prices):
                ohlc_violations += 1
            else:
                open_, high, low, close = (float(value) for value in prices)
                if high < max(open_, close, low) or low > min(open_, close, high):
                    ohlc_violations += 1
            activity = [columns[field][index] for field in ("volume", "open_interest")]
            if not all(_finite_number(value) and float(value) >= 0 for value in activity):
                activity_violations += 1

    return {
        "family": family,
        "cadence": cadence,
        "source_file_identity_sha256": identity,
        "source_file_sha256": source_hash,
        "byte_size": len(content),
        "row_count": parquet.metadata.num_rows,
        "readable": True,
        "schema_sha256": sha256_bytes(str(schema.remove_metadata()).encode()),
        "required_fields_complete": not missing_fields,
        "timestamp_storage_valid": timestamp_storage_valid,
        "embedded_provider_metadata_complete": embedded_provider_metadata_complete,
        "bar_end_semantics_bound": cadence == "daily" or provider_metadata_bound,
        "minimum_native_wall_clock": minimum.isoformat(timespec="seconds") if minimum else None,
        "maximum_native_wall_clock": maximum.isoformat(timespec="seconds") if maximum else None,
        "minimum_authorized_endpoint_wall_clock": (
            minimum_authorized.isoformat(timespec="seconds") if minimum_authorized else None
        ),
        "maximum_authorized_endpoint_wall_clock": (
            maximum_authorized.isoformat(timespec="seconds") if maximum_authorized else None
        ),
        "unusable_timestamp_rows": unusable_timestamps,
        "null_timestamp_rows": null_timestamps,
        "duplicate_timestamp_rows": duplicate_rows,
        "prehistory_rows": prehistory_rows,
        "candidate_rows": candidate_rows,
        "authorized_endpoint_rows": authorized_rows,
        "unexplained_timestamp_rows": unexplained_rows,
        "daily_normalized_rows": daily_normalized_rows,
        "ohlc_violation_rows": ohlc_violations,
        "nonfinite_or_negative_activity_rows": activity_violations,
        "clock_counts": dict(sorted(clock_counts.items())),
        "stage_counts": stage_counts,
        "_private_inventory": {
            "relative_path": relative,
            "source_file_sha256": source_hash,
            "byte_size": len(content),
            "row_count": parquet.metadata.num_rows,
        },
    }


def _sum_field(rows: list[dict[str, Any]], field: str) -> int:
    return sum(int(row[field]) for row in rows)


def _aggregate_cell(
    *,
    family: str,
    cadence: str,
    rows: list[dict[str, Any]],
    required_first_endpoint: datetime,
    required_last_endpoint: datetime,
) -> dict[str, Any]:
    clock_counts: Counter[str] = Counter()
    for row in rows:
        clock_counts.update(row["clock_counts"])
    minimum = min(
        (row["minimum_native_wall_clock"] for row in rows if row["minimum_native_wall_clock"]),
        default=None,
    )
    maximum = max(
        (row["maximum_native_wall_clock"] for row in rows if row["maximum_native_wall_clock"]),
        default=None,
    )
    minimum_authorized = min(
        (
            row["minimum_authorized_endpoint_wall_clock"]
            for row in rows
            if row["minimum_authorized_endpoint_wall_clock"]
        ),
        default=None,
    )
    maximum_authorized = max(
        (
            row["maximum_authorized_endpoint_wall_clock"]
            for row in rows
            if row["maximum_authorized_endpoint_wall_clock"]
        ),
        default=None,
    )
    stage_coverage = []
    for name, _, _ in STAGED_WINDOWS:
        candidate = sum(row["stage_counts"][name]["candidate_rows"] for row in rows)
        authorized = sum(row["stage_counts"][name]["authorized_rows"] for row in rows)
        stage_coverage.append(
            {
                "window_id": name,
                "candidate_rows": candidate,
                "authorized_endpoint_rows": authorized,
                "compatible": candidate > 0 and authorized == candidate,
            }
        )
    public_membership = [
        {
            "source_file_identity_sha256": row["source_file_identity_sha256"],
            "source_file_sha256": row["source_file_sha256"],
        }
        for row in rows
    ]
    private_inventory = [row["_private_inventory"] for row in rows]
    blockers: list[str] = []
    if not rows:
        blockers.append("required_source_cell_missing")
    readable_rows = [row for row in rows if row["readable"]]
    if len(readable_rows) != len(rows):
        blockers.append("source_file_unreadable_or_invalid")
    identities = [row["source_file_identity_sha256"] for row in rows]
    if len(set(identities)) != len(identities):
        blockers.append("duplicate_normalized_source_identity")
    if any(not row["required_fields_complete"] for row in readable_rows):
        blockers.append("required_row_fields_missing")
    if any(not row["timestamp_storage_valid"] for row in readable_rows):
        blockers.append("timestamp_storage_contract_mismatch")
    if any(not row["bar_end_semantics_bound"] for row in readable_rows):
        blockers.append("provider_bar_end_semantics_unbound")
    for field, reason in (
        ("unusable_timestamp_rows", "unusable_timestamps_present"),
        ("null_timestamp_rows", "null_timestamps_present"),
        ("duplicate_timestamp_rows", "duplicate_contract_timestamps_present"),
        ("ohlc_violation_rows", "ohlc_quality_findings_present"),
        (
            "nonfinite_or_negative_activity_rows",
            "activity_quality_findings_present",
        ),
        ("unexplained_timestamp_rows", "timestamps_outside_frozen_session_end_grid"),
    ):
        if _sum_field(rows, field):
            blockers.append(reason)
    if rows and (
        minimum_authorized is None
        or datetime.fromisoformat(minimum_authorized) > required_first_endpoint
    ):
        blockers.append("history_start_coverage_missing")
    if rows and (
        maximum_authorized is None
        or datetime.fromisoformat(maximum_authorized) < required_last_endpoint
    ):
        blockers.append("formal_horizon_coverage_missing")
    if rows and any(stage["candidate_rows"] == 0 for stage in stage_coverage):
        blockers.append("staged_window_coverage_missing")
    return {
        "instrument_family": family,
        "cadence": cadence,
        "source_file_count": len(rows),
        "source_byte_count": _sum_field(rows, "byte_size"),
        "source_row_count": _sum_field(rows, "row_count"),
        "source_inventory_membership_sha256": canonical_hash(public_membership),
        "private_raw_inventory_manifest_sha256": canonical_hash(private_inventory),
        "schema_variant_count": len(
            {row["schema_sha256"] for row in readable_rows if row["schema_sha256"] is not None}
        ),
        "normalized_source_identity_count": len(set(identities)),
        "readable_source_file_count": len(readable_rows),
        "required_field_complete_file_count": sum(
            row["required_fields_complete"] for row in readable_rows
        ),
        "minimum_native_wall_clock": minimum,
        "maximum_native_wall_clock": maximum,
        "minimum_authorized_endpoint_wall_clock": minimum_authorized,
        "maximum_authorized_endpoint_wall_clock": maximum_authorized,
        "source_to_candidate_accounting": {
            "prehistory_rows_excluded": _sum_field(rows, "prehistory_rows"),
            "candidate_rows_at_or_after_history_start": _sum_field(rows, "candidate_rows"),
            "daily_rows_normalizable_to_session_close": _sum_field(rows, "daily_normalized_rows"),
            "intraday_or_normalized_rows_on_authorized_endpoints": _sum_field(
                rows, "authorized_endpoint_rows"
            ),
            "unexplained_timestamp_rows": _sum_field(rows, "unexplained_timestamp_rows"),
        },
        "timestamp_semantics": {
            "timezone_naive_storage_file_count": sum(
                row["timestamp_storage_valid"] for row in readable_rows
            ),
            "embedded_provider_metadata_file_count": sum(
                row["embedded_provider_metadata_complete"] for row in readable_rows
            ),
            "provider_bar_end_semantics_bound_file_count": sum(
                row["bar_end_semantics_bound"] for row in readable_rows
            ),
            "observed_native_clock_counts": [
                {"clock": clock, "rows": count} for clock, count in sorted(clock_counts.items())
            ],
        },
        "quality": {
            "unusable_timestamp_rows": _sum_field(rows, "unusable_timestamp_rows"),
            "null_timestamp_rows": _sum_field(rows, "null_timestamp_rows"),
            "duplicate_contract_timestamp_rows": _sum_field(rows, "duplicate_timestamp_rows"),
            "ohlc_violation_rows": _sum_field(rows, "ohlc_violation_rows"),
            "nonfinite_or_negative_activity_rows": _sum_field(
                rows, "nonfinite_or_negative_activity_rows"
            ),
        },
        "stage_coverage": stage_coverage,
        "materialization_status": (
            "eligible_for_private_snapshot_materialization"
            if not blockers
            else "not_emitted_fail_closed"
        ),
        "registration_blockers": sorted(set(blockers)),
    }


def build_audit(
    *,
    contract: dict[str, Any],
    contract_path: Path,
    data_root: Path,
    workers: int = 8,
    contract_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Scan each raw input from one captured byte view and publish aggregates only."""

    if contract_bytes is None:
        captured_contract, contract_bytes = load_contract_capture(contract_path)
    else:
        if sha256_bytes(contract_bytes) != FROZEN_REGISTRATION_CONTRACT_SHA256:
            raise NativeSourceRegistrationError("registration contract byte identity drifted")
        captured_contract = strict_json_loads(contract_bytes.decode("utf-8"))
        if not isinstance(captured_contract, dict):
            raise NativeSourceRegistrationError("registration contract must be an object")
        validate_contract(captured_contract)
    if captured_contract != contract:
        raise NativeSourceRegistrationError(
            "contract object does not match captured contract bytes"
        )
    contract = captured_contract
    if workers < 1 or workers > 32:
        raise NativeSourceRegistrationError("workers must be between 1 and 32")
    matrix, cadence_descriptors = _enumerate_source_files(data_root)
    try:
        legal_slots = {key: _legal_slot_map(family=key[0], cadence=key[1]) for key in matrix}
        history_start_local = datetime.fromisoformat(
            contract["source_version_candidate"]["history_start_inclusive"]
        ).replace(tzinfo=None)
        last_formal_decision_local = datetime.fromisoformat(
            contract["source_version_candidate"]["last_formal_decision_local"]
        ).replace(tzinfo=None)
        tasks = [
            (family, cadence, filename, suffix)
            for (family, cadence), paths in matrix.items()
            for filename, suffix in paths
        ]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(
                    _scan_file,
                    directory_descriptor=cadence_descriptors[cadence],
                    filename=filename,
                    suffix=suffix,
                    family=family,
                    cadence=cadence,
                    legal_slots=legal_slots[(family, cadence)],
                    approved_provider_metadata_value_sha256=contract["row_policy"][
                        "approved_provider_metadata_value_sha256"
                    ],
                )
                for family, cadence, filename, suffix in tasks
            ]
            scanned = [future.result() for future in futures]
    finally:
        for descriptor in cadence_descriptors.values():
            os.close(descriptor)
    scanned.sort(
        key=lambda row: (
            EXPECTED_FAMILIES.index(row["family"]),
            REQUIRED_CADENCES.index(row["cadence"]),
            row["source_file_identity_sha256"],
        )
    )
    cells = [
        _aggregate_cell(
            family=family,
            cadence=cadence,
            rows=[row for row in scanned if row["family"] == family and row["cadence"] == cadence],
            required_first_endpoint=min(
                endpoint
                for endpoint in legal_slots[(family, cadence)]
                if endpoint >= history_start_local
            ),
            required_last_endpoint=max(
                endpoint
                for endpoint in legal_slots[(family, cadence)]
                if endpoint <= last_formal_decision_local
            ),
        )
        for family in EXPECTED_FAMILIES
        for cadence in REQUIRED_CADENCES
    ]
    observed_blockers = {blocker for cell in cells for blocker in cell["registration_blockers"]}
    if observed_blockers & DATA_BLOCKERS:
        verdict = "data_blocked"
    elif observed_blockers & SEMANTIC_BLOCKERS:
        verdict = "contract_revision_required"
    else:
        verdict = "registered"
    if verdict == "registered":
        raise NativeSourceRegistrationError(
            "registration requires a separate reviewed manifest-and-contract update"
        )
    artifact = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "audit_id": AUDIT_ID,
        "issue_number": 58,
        "audit_as_of_utc": AUDIT_AS_OF_UTC,
        "contract_sha256": sha256_bytes(contract_bytes),
        "dependency": {
            "issue_50_status": "done",
            "merged_gate_contract_sha256": FROZEN_CONTRACT_SHA256,
            "approved_native_source_version_manifest_sha256": None,
        },
        "source": {
            "runtime_binding": "QUANT_DATA_ROOT",
            "public_alias": "external://quant-data/",
            "access": "read_only",
            "captured_once_per_source_file": True,
            "matrix_cell_count": len(cells),
            "source_file_count": len(scanned),
            "source_byte_count": sum(cell["source_byte_count"] for cell in cells),
            "source_row_count": sum(cell["source_row_count"] for cell in cells),
            "complete_private_inventory_sha256": canonical_hash(
                [
                    {
                        "instrument_family": cell["instrument_family"],
                        "cadence": cell["cadence"],
                        "private_raw_inventory_manifest_sha256": cell[
                            "private_raw_inventory_manifest_sha256"
                        ],
                    }
                    for cell in cells
                ]
            ),
            "public_membership_sha256": canonical_hash(
                [
                    {
                        "instrument_family": cell["instrument_family"],
                        "cadence": cell["cadence"],
                        "source_inventory_membership_sha256": cell[
                            "source_inventory_membership_sha256"
                        ],
                    }
                    for cell in cells
                ]
            ),
        },
        "source_version_candidate": {
            "source_version_id": contract["source_version_candidate"]["source_version_id"],
            "history_start_inclusive": contract["source_version_candidate"][
                "history_start_inclusive"
            ],
            "last_formal_decision_local": contract["source_version_candidate"][
                "last_formal_decision_local"
            ],
            "last_outcome_observation_date": contract["source_version_candidate"][
                "last_outcome_observation_date"
            ],
            "required_matrix_cells": 18,
            "materialized_private_snapshot_cells": 0,
            "native_source_version_manifest_sha256": None,
        },
        "cells": cells,
        "verdict": {
            "status": verdict,
            "approved_native_source_version_registered": False,
            "contract_updated": False,
            "formal_allow_demonstrated": False,
            "issue_51_unblocked": False,
            "reason_codes": sorted(observed_blockers),
            "required_next_actions": [
                action
                for required, action in (
                    (
                        bool(observed_blockers & DATA_BLOCKERS),
                        "repair_or_replace_the_invalid_required_source_cells",
                    ),
                    (
                        bool(observed_blockers & SEMANTIC_BLOCKERS),
                        "revise_and_review_a_lossless_source_specific_timestamp_normalization_contract",
                    ),
                )
                if required
            ],
        },
        "claim_boundary": {
            "strategy_outcomes_accessed": False,
            "strategy_events_materialized": False,
            "option_inputs_accessed": False,
            "source_refreshed_or_mutated": False,
            "private_paths_or_rows_published": False,
            "m7_or_m8_authorized": False,
            "execution_authorized": False,
        },
    }
    _assert_public_safe(artifact)
    validate_audit(artifact, contract=contract)
    return artifact


def validate_audit(audit: dict[str, Any], *, contract: dict[str, Any]) -> None:
    validate_contract(contract)
    if (
        set(audit)
        != {
            "schema_version",
            "audit_id",
            "issue_number",
            "audit_as_of_utc",
            "contract_sha256",
            "dependency",
            "source",
            "source_version_candidate",
            "cells",
            "verdict",
            "claim_boundary",
        }
        or audit.get("schema_version") != AUDIT_SCHEMA_VERSION
        or audit.get("audit_id") != AUDIT_ID
        or audit.get("audit_as_of_utc") != AUDIT_AS_OF_UTC
    ):
        raise NativeSourceRegistrationError("registration audit fields drifted")
    if (
        audit.get("issue_number") != 58
        or audit.get("contract_sha256") != FROZEN_REGISTRATION_CONTRACT_SHA256
    ):
        raise NativeSourceRegistrationError("registration audit binding is invalid")
    dependency = audit.get("dependency")
    if not isinstance(dependency, dict) or set(dependency) != {
        "issue_50_status",
        "merged_gate_contract_sha256",
        "approved_native_source_version_manifest_sha256",
    }:
        raise NativeSourceRegistrationError("registration dependency fields drifted")
    if dependency != {
        "issue_50_status": "done",
        "merged_gate_contract_sha256": FROZEN_CONTRACT_SHA256,
        "approved_native_source_version_manifest_sha256": None,
    }:
        raise NativeSourceRegistrationError("registration dependency claim is invalid")
    source = audit.get("source")
    if not isinstance(source, dict) or set(source) != {
        "runtime_binding",
        "public_alias",
        "access",
        "captured_once_per_source_file",
        "matrix_cell_count",
        "source_file_count",
        "source_byte_count",
        "source_row_count",
        "complete_private_inventory_sha256",
        "public_membership_sha256",
    }:
        raise NativeSourceRegistrationError("registration source fields drifted")
    if (
        source.get("runtime_binding") != "QUANT_DATA_ROOT"
        or source.get("public_alias") != "external://quant-data/"
        or source.get("access") != "read_only"
        or source.get("captured_once_per_source_file") is not True
        or source.get("matrix_cell_count") != 18
        or not HASH_PATTERN.fullmatch(str(source.get("complete_private_inventory_sha256")))
        or not HASH_PATTERN.fullmatch(str(source.get("public_membership_sha256")))
    ):
        raise NativeSourceRegistrationError("registration source claim is invalid")
    candidate = audit.get("source_version_candidate")
    if not isinstance(candidate, dict) or set(candidate) != {
        "source_version_id",
        "history_start_inclusive",
        "last_formal_decision_local",
        "last_outcome_observation_date",
        "required_matrix_cells",
        "materialized_private_snapshot_cells",
        "native_source_version_manifest_sha256",
    }:
        raise NativeSourceRegistrationError("source candidate fields drifted")
    if (
        candidate.get("source_version_id")
        != contract["source_version_candidate"]["source_version_id"]
        or candidate.get("history_start_inclusive")
        != contract["source_version_candidate"]["history_start_inclusive"]
        or candidate.get("last_formal_decision_local")
        != contract["source_version_candidate"]["last_formal_decision_local"]
        or candidate.get("last_outcome_observation_date")
        != contract["source_version_candidate"]["last_outcome_observation_date"]
        or candidate.get("required_matrix_cells") != 18
        or candidate.get("materialized_private_snapshot_cells") != 0
        or candidate.get("native_source_version_manifest_sha256") is not None
    ):
        raise NativeSourceRegistrationError("source candidate claim is invalid")
    cells = audit.get("cells")
    expected_matrix = [
        (family, cadence) for family in EXPECTED_FAMILIES for cadence in REQUIRED_CADENCES
    ]
    if (
        not isinstance(cells, list)
        or [(row.get("instrument_family"), row.get("cadence")) for row in cells] != expected_matrix
    ):
        raise NativeSourceRegistrationError("registration audit matrix is incomplete")
    for cell in cells:
        if set(cell) != {
            "instrument_family",
            "cadence",
            "source_file_count",
            "source_byte_count",
            "source_row_count",
            "source_inventory_membership_sha256",
            "private_raw_inventory_manifest_sha256",
            "schema_variant_count",
            "normalized_source_identity_count",
            "readable_source_file_count",
            "required_field_complete_file_count",
            "minimum_native_wall_clock",
            "maximum_native_wall_clock",
            "minimum_authorized_endpoint_wall_clock",
            "maximum_authorized_endpoint_wall_clock",
            "source_to_candidate_accounting",
            "timestamp_semantics",
            "quality",
            "stage_coverage",
            "materialization_status",
            "registration_blockers",
        }:
            raise NativeSourceRegistrationError("registration cell fields drifted")
        accounting = cell.get("source_to_candidate_accounting")
        semantics = cell.get("timestamp_semantics")
        quality = cell.get("quality")
        stages = cell.get("stage_coverage")
        if not isinstance(accounting, dict) or set(accounting) != {
            "prehistory_rows_excluded",
            "candidate_rows_at_or_after_history_start",
            "daily_rows_normalizable_to_session_close",
            "intraday_or_normalized_rows_on_authorized_endpoints",
            "unexplained_timestamp_rows",
        }:
            raise NativeSourceRegistrationError("source accounting fields drifted")
        if not isinstance(semantics, dict) or set(semantics) != {
            "timezone_naive_storage_file_count",
            "embedded_provider_metadata_file_count",
            "provider_bar_end_semantics_bound_file_count",
            "observed_native_clock_counts",
        }:
            raise NativeSourceRegistrationError("timestamp semantic fields drifted")
        if not isinstance(quality, dict) or set(quality) != {
            "unusable_timestamp_rows",
            "null_timestamp_rows",
            "duplicate_contract_timestamp_rows",
            "ohlc_violation_rows",
            "nonfinite_or_negative_activity_rows",
        }:
            raise NativeSourceRegistrationError("source quality fields drifted")
        if (
            not isinstance(stages, list)
            or [stage.get("window_id") for stage in stages]
            != [name for name, _, _ in STAGED_WINDOWS]
            or any(
                not isinstance(stage, dict)
                or set(stage)
                != {
                    "window_id",
                    "candidate_rows",
                    "authorized_endpoint_rows",
                    "compatible",
                }
                for stage in stages
            )
        ):
            raise NativeSourceRegistrationError("stage coverage fields drifted")
        clock_rows = semantics["observed_native_clock_counts"]
        if not isinstance(clock_rows, list) or any(
            not isinstance(row, dict)
            or set(row) != {"clock", "rows"}
            or not isinstance(row["clock"], str)
            or not isinstance(row["rows"], int)
            or isinstance(row["rows"], bool)
            or row["rows"] < 0
            for row in clock_rows
        ):
            raise NativeSourceRegistrationError("clock-count evidence is invalid")
        numeric_values = [
            cell["source_file_count"],
            cell["source_byte_count"],
            cell["source_row_count"],
            cell["schema_variant_count"],
            cell["normalized_source_identity_count"],
            cell["readable_source_file_count"],
            cell["required_field_complete_file_count"],
            *accounting.values(),
            *quality.values(),
            semantics["timezone_naive_storage_file_count"],
            semantics["embedded_provider_metadata_file_count"],
            semantics["provider_bar_end_semantics_bound_file_count"],
            *(
                value
                for stage in stages
                for value in (
                    stage["candidate_rows"],
                    stage["authorized_endpoint_rows"],
                )
            ),
        ]
        if (
            any(
                not isinstance(value, int) or isinstance(value, bool) or value < 0
                for value in numeric_values
            )
            or not HASH_PATTERN.fullmatch(str(cell.get("source_inventory_membership_sha256")))
            or not HASH_PATTERN.fullmatch(str(cell.get("private_raw_inventory_manifest_sha256")))
            or cell.get("materialization_status")
            not in {
                "eligible_for_private_snapshot_materialization",
                "not_emitted_fail_closed",
            }
            or not isinstance(cell.get("registration_blockers"), list)
            or any(not isinstance(reason, str) for reason in cell["registration_blockers"])
            or cell["registration_blockers"] != sorted(set(cell["registration_blockers"]))
            or any(reason not in ALLOWED_BLOCKERS for reason in cell["registration_blockers"])
            or any(not isinstance(stage["compatible"], bool) for stage in stages)
        ):
            raise NativeSourceRegistrationError("registration cell is invalid")
        range_values: dict[str, datetime | None] = {}
        for field in (
            "minimum_native_wall_clock",
            "maximum_native_wall_clock",
            "minimum_authorized_endpoint_wall_clock",
            "maximum_authorized_endpoint_wall_clock",
        ):
            raw_value = cell[field]
            if raw_value is None:
                range_values[field] = None
                continue
            if not isinstance(raw_value, str):
                raise NativeSourceRegistrationError("registration timestamp range is invalid")
            try:
                parsed = datetime.fromisoformat(raw_value)
            except ValueError as exc:
                raise NativeSourceRegistrationError(
                    "registration timestamp range is invalid"
                ) from exc
            if parsed.tzinfo is not None:
                raise NativeSourceRegistrationError("registration timestamp must be a wall clock")
            range_values[field] = parsed
        if (
            (range_values["minimum_native_wall_clock"] is None)
            != (range_values["maximum_native_wall_clock"] is None)
            or (range_values["minimum_authorized_endpoint_wall_clock"] is None)
            != (range_values["maximum_authorized_endpoint_wall_clock"] is None)
            or (
                range_values["minimum_native_wall_clock"] is not None
                and range_values["minimum_native_wall_clock"]
                > range_values["maximum_native_wall_clock"]
            )
            or (
                range_values["minimum_authorized_endpoint_wall_clock"] is not None
                and range_values["minimum_authorized_endpoint_wall_clock"]
                > range_values["maximum_authorized_endpoint_wall_clock"]
            )
        ):
            raise NativeSourceRegistrationError("registration timestamp range is inconsistent")
        if (
            any(not CLOCK_PATTERN.fullmatch(row["clock"]) for row in clock_rows)
            or [row["clock"] for row in clock_rows] != sorted(row["clock"] for row in clock_rows)
            or len({row["clock"] for row in clock_rows}) != len(clock_rows)
            or sum(row["rows"] for row in clock_rows)
            + quality["null_timestamp_rows"]
            + quality["unusable_timestamp_rows"]
            != cell["source_row_count"]
        ):
            raise NativeSourceRegistrationError("clock-count evidence is inconsistent")
        expected_blockers: list[str] = []
        if cell["source_file_count"] == 0:
            expected_blockers.append("required_source_cell_missing")
        if cell["readable_source_file_count"] != cell["source_file_count"]:
            expected_blockers.append("source_file_unreadable_or_invalid")
        if cell["normalized_source_identity_count"] != cell["source_file_count"]:
            expected_blockers.append("duplicate_normalized_source_identity")
        if (
            cell["schema_variant_count"] > cell["readable_source_file_count"]
            or cell["normalized_source_identity_count"] > cell["source_file_count"]
            or cell["required_field_complete_file_count"] > cell["readable_source_file_count"]
            or semantics["timezone_naive_storage_file_count"] > cell["readable_source_file_count"]
            or semantics["embedded_provider_metadata_file_count"]
            > cell["readable_source_file_count"]
            or (
                cell["cadence"] != "daily"
                and semantics["provider_bar_end_semantics_bound_file_count"]
                > semantics["embedded_provider_metadata_file_count"]
            )
        ):
            raise NativeSourceRegistrationError("schema evidence is inconsistent")
        if cell["required_field_complete_file_count"] != cell["readable_source_file_count"]:
            expected_blockers.append("required_row_fields_missing")
        if semantics["timezone_naive_storage_file_count"] != cell["readable_source_file_count"]:
            expected_blockers.append("timestamp_storage_contract_mismatch")
        if (
            cell["cadence"] != "daily"
            and cell["readable_source_file_count"] > 0
            and semantics["provider_bar_end_semantics_bound_file_count"]
            != cell["readable_source_file_count"]
        ):
            expected_blockers.append("provider_bar_end_semantics_unbound")
        for field, reason in (
            ("unusable_timestamp_rows", "unusable_timestamps_present"),
            ("null_timestamp_rows", "null_timestamps_present"),
            ("duplicate_contract_timestamp_rows", "duplicate_contract_timestamps_present"),
            ("ohlc_violation_rows", "ohlc_quality_findings_present"),
            (
                "nonfinite_or_negative_activity_rows",
                "activity_quality_findings_present",
            ),
        ):
            if quality[field]:
                expected_blockers.append(reason)
        if accounting["unexplained_timestamp_rows"]:
            expected_blockers.append("timestamps_outside_frozen_session_end_grid")
        required_slots = _legal_slot_map(
            family=cell["instrument_family"],
            cadence=cell["cadence"],
        )
        history_start_local = datetime.fromisoformat(
            contract["source_version_candidate"]["history_start_inclusive"]
        ).replace(tzinfo=None)
        last_formal_decision_local = datetime.fromisoformat(
            contract["source_version_candidate"]["last_formal_decision_local"]
        ).replace(tzinfo=None)
        required_first = min(
            endpoint for endpoint in required_slots if endpoint >= history_start_local
        )
        required_last = max(
            endpoint for endpoint in required_slots if endpoint <= last_formal_decision_local
        )
        if cell["source_file_count"] > 0 and (
            range_values["minimum_authorized_endpoint_wall_clock"] is None
            or range_values["minimum_authorized_endpoint_wall_clock"] > required_first
        ):
            expected_blockers.append("history_start_coverage_missing")
        if cell["source_file_count"] > 0 and (
            range_values["maximum_authorized_endpoint_wall_clock"] is None
            or range_values["maximum_authorized_endpoint_wall_clock"] < required_last
        ):
            expected_blockers.append("formal_horizon_coverage_missing")
        if cell["source_file_count"] > 0 and any(stage["candidate_rows"] == 0 for stage in stages):
            expected_blockers.append("staged_window_coverage_missing")
        if (
            accounting["prehistory_rows_excluded"]
            + accounting["candidate_rows_at_or_after_history_start"]
            + quality["null_timestamp_rows"]
            + quality["unusable_timestamp_rows"]
            != cell["source_row_count"]
            or accounting["intraday_or_normalized_rows_on_authorized_endpoints"]
            + accounting["unexplained_timestamp_rows"]
            != accounting["candidate_rows_at_or_after_history_start"]
            or accounting["daily_rows_normalizable_to_session_close"]
            > accounting["intraday_or_normalized_rows_on_authorized_endpoints"]
            or any(
                stage["authorized_endpoint_rows"] > stage["candidate_rows"]
                or stage["compatible"]
                is not (
                    stage["candidate_rows"] > 0
                    and stage["authorized_endpoint_rows"] == stage["candidate_rows"]
                )
                for stage in stages
            )
            or (cell["materialization_status"] == "eligible_for_private_snapshot_materialization")
            is bool(cell["registration_blockers"])
            or cell["registration_blockers"] != sorted(set(expected_blockers))
        ):
            raise NativeSourceRegistrationError("registration cell accounting is inconsistent")
    verdict = audit.get("verdict", {})
    if (
        not isinstance(verdict, dict)
        or set(verdict)
        != {
            "status",
            "approved_native_source_version_registered",
            "contract_updated",
            "formal_allow_demonstrated",
            "issue_51_unblocked",
            "reason_codes",
            "required_next_actions",
        }
        or verdict.get("status") not in {"data_blocked", "contract_revision_required"}
        or verdict.get("approved_native_source_version_registered") is not False
        or verdict.get("contract_updated") is not False
        or verdict.get("formal_allow_demonstrated") is not False
        or verdict.get("issue_51_unblocked") is not False
        or not isinstance(verdict.get("reason_codes"), list)
        or not isinstance(verdict.get("required_next_actions"), list)
        or not verdict["required_next_actions"]
        or any(not isinstance(action, str) for action in verdict["required_next_actions"])
    ):
        raise NativeSourceRegistrationError("registration verdict is invalid")
    observed_blockers = sorted(
        {reason for cell in cells for reason in cell["registration_blockers"]}
    )
    expected_status = (
        "data_blocked" if set(observed_blockers) & DATA_BLOCKERS else "contract_revision_required"
    )
    expected_actions = [
        action
        for required, action in (
            (
                bool(set(observed_blockers) & DATA_BLOCKERS),
                "repair_or_replace_the_invalid_required_source_cells",
            ),
            (
                bool(set(observed_blockers) & SEMANTIC_BLOCKERS),
                "revise_and_review_a_lossless_source_specific_timestamp_normalization_contract",
            ),
        )
        if required
    ]
    if (
        verdict["reason_codes"] != observed_blockers
        or verdict["status"] != expected_status
        or verdict["required_next_actions"] != expected_actions
        or source["source_file_count"] != sum(cell["source_file_count"] for cell in cells)
        or source["source_byte_count"] != sum(cell["source_byte_count"] for cell in cells)
        or source["source_row_count"] != sum(cell["source_row_count"] for cell in cells)
        or source["complete_private_inventory_sha256"]
        != canonical_hash(
            [
                {
                    "instrument_family": cell["instrument_family"],
                    "cadence": cell["cadence"],
                    "private_raw_inventory_manifest_sha256": cell[
                        "private_raw_inventory_manifest_sha256"
                    ],
                }
                for cell in cells
            ]
        )
        or source["public_membership_sha256"]
        != canonical_hash(
            [
                {
                    "instrument_family": cell["instrument_family"],
                    "cadence": cell["cadence"],
                    "source_inventory_membership_sha256": cell[
                        "source_inventory_membership_sha256"
                    ],
                }
                for cell in cells
            ]
        )
    ):
        raise NativeSourceRegistrationError("registration verdict or totals are inconsistent")
    if audit.get("claim_boundary") != {
        "strategy_outcomes_accessed": False,
        "strategy_events_materialized": False,
        "option_inputs_accessed": False,
        "source_refreshed_or_mutated": False,
        "private_paths_or_rows_published": False,
        "m7_or_m8_authorized": False,
        "execution_authorized": False,
    }:
        raise NativeSourceRegistrationError("claim boundary was weakened")
    _assert_public_safe(audit)
