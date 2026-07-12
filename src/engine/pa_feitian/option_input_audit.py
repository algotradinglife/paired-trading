"""Deterministic, read-only M6 audit of historical AU/AG option inputs."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from engine.pa_feitian.manifest import sha256_file


SCHEMA_VERSION = "pa_feitian_m6_option_input_capability_audit_v1"
_BAR_ROOTS = ("min5", "min15", "daily")
_EXPECTED_GUARDRAILS = {
    "external_access_read_only": True,
    "implicit_current_time": False,
    "deterministic_inventory_order": True,
    "proxy_or_imputation": False,
    "legacy_four_event_control_as_performance_evidence": False,
    "option_corpus_generation": False,
    "evaluation": False,
    "selection": False,
    "policy_change": False,
    "m7": False,
    "m8": False,
    "execution": False,
}


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def load_contract(path: Path) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    validate_contract(contract)
    return contract


def validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != "pa_feitian_m6_option_input_audit_contract_v1":
        raise ValueError("unexpected option input audit contract schema")
    if contract.get("products") != ["au", "ag"]:
        raise ValueError("product scope was changed")
    if contract.get("window", {}).get("current_time_discovery") is not False:
        raise ValueError("audit window must not use current time")
    if contract.get("guardrails") != _EXPECTED_GUARDRAILS:
        raise ValueError("option input audit guardrails were weakened")
    if any(contract.get("promotion", {}).values()):
        raise ValueError("option input audit cannot promote downstream capabilities")


def parse_option_filename(relative_root: str, filename: str, contract: dict[str, Any]) -> dict[str, Any] | None:
    match = re.fullmatch(contract["inventory"]["contract_filename_regex"], filename)
    if match is None:
        return None
    product, month, option_type, strike = match.groups()
    return {
        "relative_root": relative_root,
        "product": product,
        "underlying_month": month,
        "option_type": option_type,
        "strike": float(strike),
        "relative_path": f"{relative_root}/{filename}",
    }


def _schema_signature(schema: pa.Schema) -> str:
    return ",".join(f"{field.name}:{field.type}" for field in schema)


def _format_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _read_time_values(path: Path, column: str) -> list[Any]:
    return pq.read_table(path, columns=[column]).column(column).to_pylist()


def _file_evidence(
    path: Path,
    parsed: dict[str, Any],
    *,
    first_day: date,
    last_day: date,
) -> tuple[dict[str, Any], set[str]]:
    parquet = pq.ParquetFile(path)
    schema = parquet.schema_arrow
    if "datetime" not in schema.names:
        raise ValueError(f"option bar lacks datetime: {parsed['relative_path']}")
    values = _read_time_values(path, "datetime")
    non_null = [value for value in values if value is not None]
    encoded = [_format_timestamp(value) for value in non_null]
    dates = [value.date() if isinstance(value, datetime) else value for value in non_null]
    in_window = [day for day in dates if first_day <= day <= last_day]
    exact_close = sum(
        isinstance(value, datetime)
        and value.date() >= first_day
        and value.date() <= last_day
        and value.time() == time(15, 0)
        for value in non_null
    )
    evidence = {
        **parsed,
        "sha256": sha256_file(path),
        "schema": _schema_signature(schema),
        "row_count": parquet.metadata.num_rows,
        "minimum_observation_timestamp": min(encoded) if encoded else None,
        "maximum_observation_timestamp": max(encoded) if encoded else None,
        "rows_in_frozen_window": len(in_window),
        "duplicate_timestamp_count": len(encoded) - len(set(encoded)),
        "timestamp_ordering": "nondecreasing" if encoded == sorted(encoded) else "not_nondecreasing",
        "timezone_aware": bool(non_null and getattr(non_null[0], "tzinfo", None) is not None),
        "exact_1500_rows_in_frozen_window": exact_close,
    }
    return evidence, {day.isoformat() for day in in_window}


def _digest_records(records: list[dict[str, Any]]) -> str:
    payload = b"".join(canonical_json_bytes(record) for record in records)
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _summarize_bar_root(
    data_root: Path,
    relative_root: str,
    contract: dict[str, Any],
    *,
    first_day: date,
    last_day: date,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    candidates = sorted(
        path
        for product in contract["products"]
        for path in (data_root / relative_root).glob(f"SHFE.{product}*.parquet")
    )
    candidates = sorted(set(candidates), key=lambda path: path.name)
    parsed_paths = []
    for path in candidates:
        parsed = parse_option_filename(relative_root, path.name, contract)
        if parsed is not None:
            parsed_paths.append((path, parsed))
    parsed_paths.sort(
        key=lambda item: tuple(item[1][key] for key in contract["inventory"]["ordering"])
    )

    records: list[dict[str, Any]] = []
    dates_by_product = {product: set() for product in contract["products"]}
    for path, parsed in parsed_paths:
        evidence, dates = _file_evidence(
            path, parsed, first_day=first_day, last_day=last_day
        )
        records.append(evidence)
        dates_by_product[parsed["product"]].update(dates)

    schema_counts = Counter(record["schema"] for record in records)
    product_counts = Counter(record["product"] for record in records)
    product_rows = Counter()
    product_window_rows = Counter()
    product_overlap_files = Counter()
    for record in records:
        product = record["product"]
        product_rows[product] += record["row_count"]
        product_window_rows[product] += record["rows_in_frozen_window"]
        if record["rows_in_frozen_window"]:
            product_overlap_files[product] += 1
    summary = {
        "relative_root": relative_root,
        "source": f"external://quant-data/{relative_root}/",
        "au_ag_prefixed_parquet_candidates": len(candidates),
        "parsed_option_files": len(records),
        "rejected_non_option_or_sidecar_files": len(candidates) - len(records),
        "files_by_product": dict(sorted(product_counts.items())),
        "rows_by_product": dict(sorted(product_rows.items())),
        "rows_in_frozen_window_by_product": dict(sorted(product_window_rows.items())),
        "files_overlapping_frozen_window_by_product": dict(sorted(product_overlap_files.items())),
        "unique_calendar_dates_in_frozen_window_by_product": {
            product: len(dates_by_product[product]) for product in contract["products"]
        },
        "minimum_observation_timestamp": min(
            (record["minimum_observation_timestamp"] for record in records if record["minimum_observation_timestamp"]),
            default=None,
        ),
        "maximum_observation_timestamp": max(
            (record["maximum_observation_timestamp"] for record in records if record["maximum_observation_timestamp"]),
            default=None,
        ),
        "duplicate_timestamp_rows": sum(record["duplicate_timestamp_count"] for record in records),
        "files_not_nondecreasing": sum(record["timestamp_ordering"] != "nondecreasing" for record in records),
        "timezone_aware_files": sum(record["timezone_aware"] for record in records),
        "files_with_exact_1500_row_in_frozen_window": sum(
            record["exact_1500_rows_in_frozen_window"] > 0 for record in records
        ),
        "schema_variants": [
            {"schema": schema, "file_count": count}
            for schema, count in sorted(schema_counts.items())
        ],
        "inventory_sha256": _digest_records(records),
    }
    return summary, records


def _ivskew_evidence(data_root: Path, contract: dict[str, Any]) -> dict[str, Any]:
    first_day = date.fromisoformat(contract["window"]["first_trading_date"])
    last_day = date.fromisoformat(contract["window"]["last_trading_date"])
    records = []
    for product in contract["products"]:
        filename = f"SHFE.{product}0.option_ivskew.parquet"
        path = data_root / "continuous" / filename
        parquet = pq.ParquetFile(path)
        schema = parquet.schema_arrow
        values = _read_time_values(path, "date")
        non_null = [value for value in values if value is not None]
        records.append(
            {
                "product": product,
                "source": f"external://quant-data/continuous/{filename}",
                "sha256": sha256_file(path),
                "schema": _schema_signature(schema),
                "row_count": parquet.metadata.num_rows,
                "rows_in_frozen_window": sum(first_day <= value <= last_day for value in non_null),
                "minimum_observation_date": min(non_null).isoformat() if non_null else None,
                "maximum_observation_date": max(non_null).isoformat() if non_null else None,
                "observation_timestamp_field": False,
                "contract_bound_delta_field": False,
                "expiry_field": False,
                "bid_field": False,
                "ask_field": False,
            }
        )
    return {"files": records, "inventory_sha256": _digest_records(records)}


def build_audit(
    *,
    contract: dict[str, Any],
    contract_path: Path,
    data_root: Path,
    quant_repo: Path,
    paired_repo: Path,
) -> dict[str, Any]:
    """Build capability evidence without modifying or copying external data."""

    validate_contract(contract)
    first_day = date.fromisoformat(contract["window"]["first_trading_date"])
    last_day = date.fromisoformat(contract["window"]["last_trading_date"])
    summaries = []
    records_by_root = {}
    for relative_root in _BAR_ROOTS:
        summary, records = _summarize_bar_root(
            data_root,
            relative_root,
            contract,
            first_day=first_day,
            last_day=last_day,
        )
        summaries.append(summary)
        records_by_root[relative_root] = records

    contract_sets = {
        root: sorted(record["relative_path"].split("/", 1)[1] for record in records)
        for root, records in records_by_root.items()
    }
    contract_set_equal = all(
        contract_sets[root] == contract_sets[_BAR_ROOTS[0]] for root in _BAR_ROOTS[1:]
    )
    ivskew = _ivskew_evidence(data_root, contract)
    source_refs = []
    for repository, root, relative in (
        ("quant-repository", quant_repo, "scripts/data_backfill/build_cn_option_ivskew.py"),
        ("quant-repository", quant_repo, "scripts/data_backfill/sync_feitian_option_5min.py"),
        ("paired-trading", paired_repo, "src/scripts/analyze_ag_options_ddline.py"),
        ("paired-trading", paired_repo, "doc/xiao-feitian-options-timing-system-2026-06-16.md"),
    ):
        source_refs.append(
            {
                "source": f"repository://{repository}/{relative}",
                "sha256": sha256_file(root / relative),
            }
        )

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "hermes_task": contract["hermes_task"],
        "research_mode": contract["research_mode"],
        "contract": {
            "path": str(contract_path.resolve().relative_to(paired_repo.resolve())),
            "sha256": sha256_file(contract_path),
        },
        "window": contract["window"],
        "guardrails": contract["guardrails"],
        "inventory": {
            "bar_roots": summaries,
            "same_parsed_contract_set_across_bar_roots": contract_set_equal,
            "parsed_contract_set_count": len(contract_sets[_BAR_ROOTS[0]]),
            "parsed_contract_set_sha256": f"sha256:{hashlib.sha256(canonical_json_bytes(contract_sets[_BAR_ROOTS[0]])).hexdigest()}",
            "greeks_sibling_files": 0,
            "greeks_related_continuous": ivskew,
        },
        "source_implementation_references": source_refs,
        "availability_evidence": {
            "observation_timestamps_present": True,
            "timezone_declared_in_bar_schema": False,
            "period_start_or_end_declared_in_bar_schema": False,
            "historical_acquisition_timestamp_present": False,
            "query_cutoff_present": False,
            "filesystem_timestamps_accepted": False,
            "decision_time_availability": "unproven",
        },
        "capability_findings": [
            {
                "capability": "premium_bars_at_or_below_15_minutes",
                "state": "data_present_but_unverified",
                "basis": "Parsed min5 and min15 contract files contain OHLCV, turnover and open interest, but timestamps are naive and historical availability, query cutoff and period semantics are absent.",
            },
            {
                "capability": "contract_and_maturity_lineage",
                "state": "data_present_but_unverified",
                "basis": "Filenames deterministically bind product, underlying month, option type and strike; decision-time chain membership and append-only source lineage are absent.",
            },
            {
                "capability": "exact_exchange_expiry_and_dte",
                "state": "missing",
                "basis": "No audited bar or Greeks-related file contains exact exchange expiry or a declared DTE convention; underlying month is not an expiry date.",
            },
            {
                "capability": "decision_time_delta",
                "state": "missing",
                "basis": "No contract-bound Greeks sibling exists. The date-only continuous IV-skew files retain aggregate 25-delta interpolation outputs, not each contract delta, maturity, inputs or availability timestamp.",
            },
            {
                "capability": "historical_bid_and_ask",
                "state": "missing",
                "basis": "No audited schema contains bid or ask.",
            },
            {
                "capability": "formal_pa_feitian_dd_line",
                "state": "missing",
                "basis": "Repository references describe an explicitly approximate daily W-bottom implementation, but there is no frozen faithful formula with input fields, intraday cadence and decision rule.",
            },
        ],
        "decision": {
            "faithful_option_corpus": "blocked",
            "option_corpus_generation_warranted_now": False,
            "next_gate": "Freeze authoritative AU/AG contract metadata with exact exchange expiry and DTE convention; acquire contract-bound delta and historical bid/ask with append-only availability timestamps and query cutoffs; then freeze a faithful intraday DD-line formula before generating an option corpus.",
        },
        "promotion": contract["promotion"],
    }
    validate_audit(artifact, contract=contract)
    return artifact


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


def validate_audit(artifact: dict[str, Any], *, contract: dict[str, Any]) -> None:
    if artifact.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unexpected option input audit schema")
    if artifact.get("guardrails") != _EXPECTED_GUARDRAILS:
        raise ValueError("audit guardrails were weakened")
    if artifact.get("promotion") != contract["promotion"] or any(artifact["promotion"].values()):
        raise ValueError("audit attempted downstream promotion")
    findings = {row["capability"]: row["state"] for row in artifact["capability_findings"]}
    if set(findings) != {row["name"] for row in contract["capabilities"]}:
        raise ValueError("capability findings are incomplete")
    if any(state not in contract["finding_states"] for state in findings.values()):
        raise ValueError("unknown finding state")
    if artifact["decision"] != {
        "faithful_option_corpus": "blocked",
        "option_corpus_generation_warranted_now": False,
        "next_gate": artifact["decision"]["next_gate"],
    }:
        raise ValueError("faithful option corpus boundary was weakened")
    forbidden = set(contract["forbidden_evaluation_fields"])
    evidence_content = {
        key: value for key, value in artifact.items() if key not in {"guardrails", "promotion"}
    }
    present = forbidden.intersection(_walk_keys(evidence_content))
    if present:
        raise ValueError(f"audit contains forbidden evaluation fields: {sorted(present)}")
    encoded = canonical_json_bytes(artifact).decode()
    if str(Path.home()) in encoded or "/mnt/" in encoded or "\\Users\\" in encoded:
        raise ValueError("audit contains a local absolute path")
