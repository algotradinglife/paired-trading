"""Deterministic public-safe membership for frozen bare-K eligibility units.

Only the statistics required by the already-frozen eligibility rule are read.
No price or premium path is returned or serialized.
"""

from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from engine.pa_feitian.liquid_premium_evidence import (
    REQUIRED_COLUMNS,
    _inventory_digest,
    evaluate_contract_frame,
    load_contract as load_eligibility_contract,
)
from engine.pa_feitian.manifest import sha256_file


SCHEMA_VERSION = "pa_feitian_m6_liquid_premium_membership_v1"
CONTRACT_SCHEMA_VERSION = "pa_feitian_m6_liquid_premium_membership_contract_v1"
TASK_ID = "t_02ba3dea"
CONTRACT_FREEZE_COMMIT = "e81d283fac967db06932cd2bc3bdf5eeab8e8ef4"
MEMBER_FIELDS = (
    "product",
    "local_date",
    "underlying_month",
    "option_type",
    "strike",
    "cadence",
    "source_alias",
)
BOUND_PATHS = (
    "docs/research/pa-feitian-m6-liquid-premium-eligibility-contract-v1.json",
    "doc/repro/pa-feitian-m6-liquid-premium-2026-07-12/liquid_premium_evidence_v1.json",
)


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def load_contract(path: Path) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    validate_contract(contract)
    return contract


def validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        raise ValueError("unexpected membership contract schema")
    if contract.get("hermes_task") != TASK_ID:
        raise ValueError("wrong Hermes task")
    if contract.get("frozen_before_external_option_data_inspection") is not True:
        raise ValueError("membership contract was not frozen before option access")
    boundary = contract.get("frozen_boundary", {})
    if boundary.get("products") != ["au", "ag"]:
        raise ValueError("product universe changed")
    if boundary.get("cadences") != ["min5", "min15"]:
        raise ValueError("cadence universe changed")
    if boundary.get("decision_time_local_inclusive") != "15:00:00":
        raise ValueError("decision cutoff changed")
    if not boundary.get("finalized_vintage"):
        raise ValueError("finalized-vintage label was weakened")
    for key in (
        "historical_bid_ask_required",
        "contract_delta_required",
        "exact_expiry_or_dte_required",
    ):
        if boundary.get(key) is not False:
            raise ValueError(f"bare-K boundary changed: {key}")
    output = contract.get("membership_output", {})
    if output.get("member_fields_exactly") != list(MEMBER_FIELDS):
        raise ValueError("member identity fields changed")
    if output.get("premium_paths") is not False or output.get("performance_fields") is not False:
        raise ValueError("membership-only output boundary changed")
    expected = contract.get("data_access_policy", {}).get("expected_inventories", [])
    dimensions = [(row.get("product"), row.get("cadence")) for row in expected]
    if dimensions != [("au", "min5"), ("ag", "min5"), ("au", "min15"), ("ag", "min15")]:
        raise ValueError("expected inventory dimensions changed")


def verify_bound_inputs(contract: dict[str, Any], repo_root: Path) -> None:
    bindings = contract.get("bound_inputs", [])
    if len(bindings) != len(BOUND_PATHS):
        raise ValueError("bound input list changed")
    for binding, relative_path in zip(bindings, BOUND_PATHS):
        path = repo_root / relative_path
        if sha256_file(path) != binding.get("sha256"):
            raise ValueError(f"bound input hash mismatch: {relative_path}")
    eligibility = load_eligibility_contract(repo_root / BOUND_PATHS[0])
    evidence = json.loads((repo_root / BOUND_PATHS[1]).read_text(encoding="utf-8"))
    if evidence.get("label") != "retrospective_finalized":
        raise ValueError("bound evidence label changed")
    if evidence.get("contract", {}).get("sha256") != bindings[0]["sha256"]:
        raise ValueError("bound evidence does not bind the eligibility contract")
    if eligibility["window"]["eligibility_cutoff_local_time_inclusive"] != "15:00:00":
        raise ValueError("eligibility cutoff changed")


def _expected_by_dimension(contract: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (row["product"], row["cadence"]): row
        for row in contract["data_access_policy"]["expected_inventories"]
    }


def enumerate_inventory(data_root: Path, cadence: str, product: str, identity_regex: str) -> list[Path]:
    cadence_root = data_root / cadence
    if not cadence_root.is_dir():
        raise ValueError(f"missing_expected_file: {cadence}/{product}")
    paths: list[Path] = []
    prefix = f"SHFE.{product}"
    for path in cadence_root.iterdir():
        if path.name.startswith(prefix) and path.name.endswith(".parquet"):
            if path.is_symlink():
                raise ValueError(f"unexpected_inventory_file: symlink {cadence}/{path.name}")
            if re.fullmatch(identity_regex, path.name):
                paths.append(path)
    return sorted(paths, key=lambda path: path.relative_to(data_root).as_posix().encode())


def verify_inventory(paths: list[Path], data_root: Path, expected: dict[str, Any]) -> None:
    observed_count = len(paths)
    observed_digest = _inventory_digest(paths, data_root)
    if observed_count < expected["source_files"]:
        raise ValueError(f"missing_expected_file: {expected['product']}/{expected['cadence']}")
    if observed_count > expected["source_files"]:
        raise ValueError(f"unexpected_inventory_file: {expected['product']}/{expected['cadence']}")
    if observed_digest != expected["source_inventory_sha256"]:
        raise ValueError(f"unexpected_inventory_file: digest mismatch for {expected['product']}/{expected['cadence']}")


def _content_manifest_digest(rows: list[list[str]]) -> str:
    return f"sha256:{hashlib.sha256(canonical_json_bytes(rows)).hexdigest()}"


def _parse_identity(path: Path, identity_regex: str) -> dict[str, str]:
    match = re.fullmatch(identity_regex, path.name)
    if match is None:
        raise ValueError(f"invalid contract identity: {path.name}")
    product, month, option_type, strike = match.groups()
    return {
        "product": product,
        "underlying_month": month,
        "option_type": option_type,
        "strike": strike,
    }


def read_file_units(
    path: Path,
    *,
    cadence_minutes: int,
    first_day: date,
    last_day: date,
) -> list[dict[str, Any]]:
    try:
        parquet = pq.ParquetFile(path)
    except Exception as exc:
        raise ValueError(f"unreadable_expected_file: {path.name}") from exc
    missing = sorted(set(REQUIRED_COLUMNS) - set(parquet.schema_arrow.names))
    if missing:
        raise ValueError(f"missing_required_schema: {path.name}: {missing}")
    read_start = datetime.combine(first_day, time.min)
    read_end = datetime.combine(last_day + timedelta(days=1), time.min)
    try:
        table = pq.read_table(
            path,
            columns=list(REQUIRED_COLUMNS),
            filters=[("datetime", ">=", read_start), ("datetime", "<", read_end)],
        )
    except Exception as exc:
        raise ValueError(f"unreadable_expected_file: {path.name}") from exc
    return evaluate_contract_frame(
        table.to_pandas(),
        cadence_minutes=cadence_minutes,
        first_day=first_day,
        last_day=last_day,
    )


def _member_sort_key(member: dict[str, str]) -> tuple[Any, ...]:
    return (
        member["local_date"],
        member["product"],
        int(member["underlying_month"]),
        0 if member["option_type"] == "C" else 1,
        Decimal(member["strike"]),
        0 if member["cadence"] == "min5" else 1,
        member["source_alias"].encode(),
    )


def _read_file_result(
    args: tuple[Path, str, int, date, date],
) -> tuple[dict[str, str], list[dict[str, Any]], str]:
    path, identity_regex, cadence_minutes, first_day, last_day = args
    identity = _parse_identity(path, identity_regex)
    units = read_file_units(
        path,
        cadence_minutes=cadence_minutes,
        first_day=first_day,
        last_day=last_day,
    )
    return identity, units, sha256_file(path)


def build_membership(
    *,
    contract: dict[str, Any],
    contract_path: Path,
    eligibility_contract_path: Path,
    data_root: Path,
    repo_root: Path,
    workers: int = 1,
) -> dict[str, Any]:
    validate_contract(contract)
    verify_bound_inputs(contract, repo_root)
    eligibility = load_eligibility_contract(eligibility_contract_path)
    first_day = date.fromisoformat(contract["frozen_boundary"]["first_local_date"])
    last_day = date.fromisoformat(contract["frozen_boundary"]["last_local_date"])
    expected_by_dimension = _expected_by_dimension(contract)
    members: list[dict[str, str]] = []
    coverage: list[dict[str, Any]] = []

    for cadence in contract["frozen_boundary"]["cadences"]:
        cadence_minutes = 5 if cadence == "min5" else 15
        for product in contract["frozen_boundary"]["products"]:
            expected = expected_by_dimension[(product, cadence)]
            paths = enumerate_inventory(data_root, cadence, product, eligibility["unit"]["identity_regex"])
            verify_inventory(paths, data_root, expected)
            eligible_count = 0
            contract_date_units = 0
            work = [
                (path, eligibility["unit"]["identity_regex"], cadence_minutes, first_day, last_day)
                for path in paths
            ]
            if workers > 1:
                executor = ProcessPoolExecutor(max_workers=workers)
                results = executor.map(_read_file_result, work, chunksize=8)
            else:
                executor = None
                results = map(_read_file_result, work)
            content_rows: list[list[str]] = []
            for path, (identity, units, content_sha256) in zip(paths, results):
                content_rows.append([path.relative_to(data_root).as_posix(), content_sha256])
                contract_date_units += len(units)
                for unit in units:
                    if unit["eligible"]:
                        eligible_count += 1
                        members.append(
                            {
                                "product": identity["product"],
                                "local_date": unit["local_date"],
                                "underlying_month": identity["underlying_month"],
                                "option_type": identity["option_type"],
                                "strike": identity["strike"],
                                "cadence": cadence,
                                "source_alias": expected["source_alias"],
                            }
                        )
            if executor is not None:
                executor.shutdown()
            if eligible_count != expected["expected_eligible_units"]:
                raise ValueError(f"eligible count mismatch for {product}/{cadence}: {eligible_count}")
            coverage.append(
                {
                    "product": product,
                    "cadence": cadence,
                    "inventory_state": "verified_complete",
                    "source_alias": expected["source_alias"],
                    "source_files": len(paths),
                    "source_inventory_sha256": expected["source_inventory_sha256"],
                    "source_content_manifest_sha256": _content_manifest_digest(content_rows),
                    "contract_date_units": contract_date_units,
                    "eligible_units": eligible_count,
                    "ineligible_units": contract_date_units - eligible_count,
                }
            )

    members.sort(key=_member_sort_key)
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "hermes_task": TASK_ID,
        "research_mode": contract["research_mode"],
        "label": "retrospective_finalized",
        "contract": {
            "alias": f"public://paired-trading/{contract_path.relative_to(repo_root).as_posix()}",
            "frozen_before_external_option_data_inspection": True,
            "freeze_commit": CONTRACT_FREEZE_COMMIT,
            "sha256": sha256_file(contract_path),
        },
        "bound_inputs": contract["bound_inputs"],
        "decision_cutoff": {
            "timezone": "Asia/Shanghai",
            "inclusive_local_time": "15:00:00",
            "post_cutoff_rows_excluded_before_eligibility": True,
        },
        "coverage": coverage,
        "member_fields": list(MEMBER_FIELDS),
        "members": members,
        "limitations": contract["limitations"],
        "promotion": contract["promotion"],
    }
    validate_artifact(artifact, contract=contract)
    return artifact


def validate_artifact(artifact: dict[str, Any], *, contract: dict[str, Any]) -> None:
    if artifact.get("schema_version") != SCHEMA_VERSION or artifact.get("hermes_task") != TASK_ID:
        raise ValueError("unexpected membership artifact identity")
    if artifact.get("label") != "retrospective_finalized":
        raise ValueError("finalized-vintage label changed")
    members = artifact.get("members", [])
    if any(set(member) != set(MEMBER_FIELDS) or len(member) != len(MEMBER_FIELDS) for member in members):
        raise ValueError("member fields differ from exact allowlist")
    keys = [tuple(member[field] for field in MEMBER_FIELDS) for member in members]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate unit key")
    if members != sorted(members, key=_member_sort_key):
        raise ValueError("members are not in frozen total order")
    expected_counts = {
        (row["product"], row["cadence"]): row["expected_eligible_units"]
        for row in contract["data_access_policy"]["expected_inventories"]
    }
    observed_counts = {(row["product"], row["cadence"]): row["eligible_units"] for row in artifact["coverage"]}
    if observed_counts != expected_counts or sum(observed_counts.values()) != len(members):
        raise ValueError("member counts do not reconcile")
    encoded = canonical_json_bytes(artifact).decode()
    for forbidden in (str(Path.home()), "/mnt/", "\\Users\\", "AKIA", "selected_contract"):
        if forbidden in encoded:
            raise ValueError("artifact contains forbidden public content")


def write_artifact(artifact: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(artifact, indent=2, sort_keys=True).encode() + b"\n")


__all__ = [
    "MEMBER_FIELDS",
    "build_membership",
    "enumerate_inventory",
    "load_contract",
    "read_file_units",
    "validate_artifact",
    "validate_contract",
    "verify_bound_inputs",
    "verify_inventory",
    "write_artifact",
]
