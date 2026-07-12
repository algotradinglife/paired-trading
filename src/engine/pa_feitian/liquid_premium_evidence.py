"""Deterministic M6 bare-K option liquidity evidence.

This module classifies contract-date units from finalized option K-lines.  It
does not select an option leg or inspect any later premium path or outcome.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import pyarrow.parquet as pq

from engine.pa_feitian.manifest import sha256_file


SCHEMA_VERSION = "pa_feitian_m6_liquid_premium_evidence_v1"
CONTRACT_SCHEMA_VERSION = "pa_feitian_m6_liquid_premium_eligibility_contract_v1"
REQUIRED_COLUMNS = (
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "turnover",
    "open_interest",
)
EXPECTED_GUARDRAILS = {
    "external_access_read_only": True,
    "strict_event_time_truncation": True,
    "future_row_invariance_required": True,
    "deterministic_rerun_required": True,
    "outcome_or_performance_fields_forbidden": True,
    "outcome_optimized_thresholds": False,
    "bid_ask_or_spread_fields_forbidden": True,
    "delta_or_greeks_fields_forbidden": True,
    "expiry_or_dte_gate_forbidden": True,
    "proxy_or_imputation": False,
    "candidate_screening": False,
    "premium_path_evaluation": False,
    "strategy_performance_evaluation": False,
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
    if contract.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        raise ValueError("unexpected liquid-premium contract schema")
    if contract.get("hermes_task") != "t_3bf64f0c":
        raise ValueError("wrong Hermes task")
    if contract.get("frozen_before_external_data_inspection") is not True:
        raise ValueError("contract was not declared frozen before external inspection")
    window = contract.get("window", {})
    if window.get("products") != ["au", "ag"] or window.get("cadences") != [
        "min5",
        "min15",
    ]:
        raise ValueError("product or cadence boundary changed")
    if window.get("current_time_discovery") is not False:
        raise ValueError("current-time discovery is forbidden")
    if contract.get("guardrails") != EXPECTED_GUARDRAILS:
        raise ValueError("liquid-premium guardrails were weakened")
    floors = contract.get("quality_contract", {}).get("liquidity_floors_at_cutoff", {})
    if floors.get("cumulative_session_volume_minimum") != 100:
        raise ValueError("volume floor changed")
    if floors.get("latest_open_interest_minimum") != 500:
        raise ValueError("open-interest floor changed")


def _parse_filename(path: Path, contract: dict[str, Any]) -> dict[str, str] | None:
    match = re.fullmatch(contract["unit"]["identity_regex"], path.name)
    if match is None:
        return None
    product, month, option_type, strike = match.groups()
    return {
        "product": product,
        "underlying_month": month,
        "option_type": option_type,
        "strike": strike,
    }


def _expected_grid(day: date, cadence_minutes: int) -> set[pd.Timestamp]:
    start = datetime.combine(day, time(14, 0))
    end = datetime.combine(day, time(15, 0))
    return set(pd.date_range(start, end, freq=f"{cadence_minutes}min"))


def _is_finite_nonnegative(frame: pd.DataFrame, columns: Iterable[str]) -> bool:
    for column in columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any() or (values < 0).any():
            return False
        if not values.map(math.isfinite).all():
            return False
    return True


def evaluate_contract_frame(
    frame: pd.DataFrame,
    *,
    cadence_minutes: int,
    first_day: date,
    last_day: date,
) -> list[dict[str, Any]]:
    """Classify each local date after filtering every row to its 15:00 cutoff."""

    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")
    source = frame.loc[:, REQUIRED_COLUMNS].copy()
    source["datetime"] = pd.to_datetime(source["datetime"], errors="coerce")
    source = source[source["datetime"].notna()]
    source = source[
        (source["datetime"].dt.date >= first_day)
        & (source["datetime"].dt.date <= last_day)
    ]
    if source.empty:
        return []

    units = []
    for day, whole_day in source.groupby(source["datetime"].dt.date, sort=True):
        cutoff = datetime.combine(day, time(15, 0))
        causal = whole_day[whole_day["datetime"] <= cutoff].copy()
        excluded = int((whole_day["datetime"] > cutoff).sum())
        if causal.empty:
            continue
        timestamps = causal["datetime"].tolist()
        reasons: list[str] = []
        if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
            reasons.append("timestamp_not_ordered_unique")

        numeric_ok = _is_finite_nonnegative(causal, REQUIRED_COLUMNS[1:])
        coherent = bool(
            (
                (causal["high"] >= causal[["open", "close", "low"]].max(axis=1))
                & (causal["low"] <= causal[["open", "close", "high"]].min(axis=1))
            ).all()
        )
        if not numeric_ok or not coherent:
            reasons.append("invalid_numeric_or_ohlc")

        exact_cutoff = pd.Timestamp(cutoff) in set(causal["datetime"])
        if not exact_cutoff:
            reasons.append("missing_exact_cutoff_bar")

        final_hour = causal[
            (causal["datetime"] >= datetime.combine(day, time(14, 0)))
            & (causal["datetime"] <= cutoff)
        ]
        observed_grid = set(final_hour["datetime"])
        expected_grid = _expected_grid(day, cadence_minutes)
        coverage = len(observed_grid.intersection(expected_grid)) / len(expected_grid)
        minimum_points = 11 if cadence_minutes == 5 else 4
        if coverage < 0.8 or len(observed_grid.intersection(expected_grid)) < minimum_points:
            reasons.append("insufficient_final_hour_grid_coverage")
        ordered_final = sorted(observed_grid)
        max_gap_units = (
            max(
                (right - left).total_seconds() / 60 / cadence_minutes
                for left, right in zip(ordered_final, ordered_final[1:])
            )
            if len(ordered_final) >= 2
            else float("inf")
        )
        if max_gap_units > 2:
            reasons.append("excessive_final_hour_gap")

        session_volume = float(causal["volume"].sum())
        session_turnover = float(causal["turnover"].sum())
        latest_open_interest = float(causal.iloc[-1]["open_interest"])
        if session_volume < 100:
            reasons.append("session_volume_below_100")
        if session_turnover <= 0:
            reasons.append("session_turnover_not_positive")
        if latest_open_interest < 500:
            reasons.append("open_interest_below_500")

        units.append(
            {
                "local_date": day.isoformat(),
                "eligible": not reasons,
                "failure_reasons": reasons,
                "source_rows_at_or_before_cutoff": len(causal),
                "source_rows_after_cutoff_excluded": excluded,
            }
        )
    return units


def _inventory_digest(paths: list[Path], root: Path) -> str:
    relative = [str(path.relative_to(root)) for path in paths]
    return f"sha256:{hashlib.sha256(canonical_json_bytes(relative)).hexdigest()}"


def _summarize_cadence(
    *, data_root: Path, relative_root: str, contract: dict[str, Any]
) -> list[dict[str, Any]]:
    first_day = date.fromisoformat(contract["window"]["first_local_date"])
    last_day = date.fromisoformat(contract["window"]["last_local_date"])
    cadence_minutes = 5 if relative_root == "min5" else 15
    parsed_paths: list[tuple[Path, dict[str, str]]] = []
    for product in contract["window"]["products"]:
        for path in sorted((data_root / relative_root).glob(f"SHFE.{product}*.parquet")):
            identity = _parse_filename(path, contract)
            if identity is not None:
                parsed_paths.append((path, identity))
    parsed_paths.sort(key=lambda item: item[0].name)

    aggregates: dict[str, dict[str, Any]] = {}
    for product in contract["window"]["products"]:
        product_paths = [path for path, identity in parsed_paths if identity["product"] == product]
        aggregates[product] = {
            "product": product,
            "cadence": relative_root,
            "source": f"external://quant-data/{relative_root}/SHFE.{product}-options",
            "source_files": len(product_paths),
            "source_inventory_sha256": _inventory_digest(product_paths, data_root),
            "contract_date_units": 0,
            "eligible_units": 0,
            "ineligible_units": 0,
            "failure_reason_counts": Counter(),
            "source_rows_at_or_before_cutoff": 0,
            "source_rows_after_cutoff_excluded": 0,
        }

    read_start = datetime.combine(first_day, time.min)
    read_end = datetime.combine(last_day + timedelta(days=1), time.min)
    for path, identity in parsed_paths:
        parquet = pq.ParquetFile(path)
        if not set(REQUIRED_COLUMNS).issubset(parquet.schema_arrow.names):
            continue
        table = pq.read_table(
            path,
            columns=list(REQUIRED_COLUMNS),
            filters=[("datetime", ">=", read_start), ("datetime", "<", read_end)],
        )
        units = evaluate_contract_frame(
            table.to_pandas(),
            cadence_minutes=cadence_minutes,
            first_day=first_day,
            last_day=last_day,
        )
        target = aggregates[identity["product"]]
        for unit in units:
            target["contract_date_units"] += 1
            target["eligible_units" if unit["eligible"] else "ineligible_units"] += 1
            target["source_rows_at_or_before_cutoff"] += unit[
                "source_rows_at_or_before_cutoff"
            ]
            target["source_rows_after_cutoff_excluded"] += unit[
                "source_rows_after_cutoff_excluded"
            ]
            target["failure_reason_counts"].update(unit["failure_reasons"])

    results = []
    for product in contract["window"]["products"]:
        row = aggregates[product]
        row["failure_reason_counts"] = dict(sorted(row["failure_reason_counts"].items()))
        results.append(row)
    return results


def build_evidence(
    *,
    contract: dict[str, Any],
    contract_path: Path,
    data_root: Path,
    paired_repo: Path,
    quant_repo: Path,
) -> dict[str, Any]:
    validate_contract(contract)
    coverage = []
    for relative_root in ("min5", "min15"):
        coverage.extend(
            _summarize_cadence(
                data_root=data_root, relative_root=relative_root, contract=contract
            )
        )
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "hermes_task": contract["hermes_task"],
        "research_mode": contract["research_mode"],
        "label": "retrospective_finalized",
        "contract": {
            "path": str(contract_path.resolve().relative_to(paired_repo.resolve())),
            "sha256": sha256_file(contract_path),
        },
        "source_context": [
            {
                "source": "external://quant-repository/docs/strategy-data-access-guide.md",
                "sha256": sha256_file(quant_repo / "docs/strategy-data-access-guide.md"),
            },
            {
                "source": "external://quant-repository/docs/strategy-instrument-quality-framework.md",
                "sha256": sha256_file(
                    quant_repo / "docs/strategy-instrument-quality-framework.md"
                ),
            },
        ],
        "timestamp_cutoff": {
            "timezone": contract["window"]["source_timezone"],
            "source_labels": "timezone_naive_period_end",
            "inclusive_local_time": contract["window"][
                "eligibility_cutoff_local_time_inclusive"
            ],
            "future_rows_excluded_before_all_metrics": True,
        },
        "coverage": coverage,
        "classification": {
            "name": "exploratory_liquid_premium_ohlc",
            "thresholds_frozen_before_source_inspection": True,
            "thresholds_chosen_from_outcomes": False,
            "quote_or_greeks_dependency": "none",
            "exact_expiry_dependency": "none",
        },
        "limitations": [
            "Finalized historical rows may include later revisions and do not establish contemporaneous operational observability.",
            "K-line activity does not establish executable prices, transaction costs or market impact.",
            "This evidence does not select contracts or evaluate any premium path or strategy result.",
            "A faithful frozen DD-line remains absent, so this is not faithful Feitian replication.",
        ],
        "promotion": contract["promotion"],
    }
    validate_evidence(artifact, contract=contract)
    return artifact


def validate_evidence(artifact: dict[str, Any], *, contract: dict[str, Any]) -> None:
    if artifact.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unexpected liquid-premium evidence schema")
    if artifact.get("hermes_task") != "t_3bf64f0c":
        raise ValueError("wrong evidence task")
    if artifact.get("label") != "retrospective_finalized":
        raise ValueError("historical evidence label was weakened")
    if artifact.get("promotion") != contract["promotion"]:
        raise ValueError("promotion boundary differs from frozen contract")
    coverage = artifact.get("coverage", [])
    expected = [("au", "min5"), ("ag", "min5"), ("au", "min15"), ("ag", "min15")]
    if [(row["product"], row["cadence"]) for row in coverage] != expected:
        raise ValueError("coverage dimensions are incomplete or reordered")
    for row in coverage:
        if row["eligible_units"] + row["ineligible_units"] != row["contract_date_units"]:
            raise ValueError("eligibility counts do not reconcile")
    encoded = canonical_json_bytes(artifact).decode()
    if str(Path.home()) in encoded or "/mnt/" in encoded or "\\Users\\" in encoded:
        raise ValueError("evidence contains a local absolute path")


def write_evidence(artifact: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(artifact, indent=2, sort_keys=True).encode() + b"\n")


__all__ = [
    "SCHEMA_VERSION",
    "build_evidence",
    "evaluate_contract_frame",
    "load_contract",
    "validate_contract",
    "validate_evidence",
    "write_evidence",
]
