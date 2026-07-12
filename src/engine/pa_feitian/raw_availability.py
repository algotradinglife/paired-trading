"""Deterministic M6 raw acquisition/availability quarantine audit.

Raw byte identity and a causal transformation do not establish that an
observation was available at an earlier decision time.  This module records
that boundary explicitly for every input in the merged M6 provenance packet.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from engine.pa_feitian.continuous_provenance import (
    _git_blob,
    _load_continuous_module,
    _pin_discovery,
    _roll_records,
)
from engine.pa_feitian.manifest import sha256_file


SCHEMA_VERSION = "pa_feitian_raw_availability_blocker_v1"
EVIDENCE_FIELDS = (
    "source_identity",
    "vendor_response_identity",
    "query_parameters",
    "acquired_at",
    "query_cutoff",
    "raw_timestamp_timezone_contract",
)
GAP_CODES = tuple(f"missing_{field}" for field in EVIDENCE_FIELDS)


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _metadata_keys(path: Path) -> list[str]:
    metadata = pq.read_metadata(path).metadata or {}
    return sorted(key.decode("utf-8", errors="replace") for key in metadata)


def _observation_bounds(path: Path) -> tuple[str | None, str | None]:
    values = pd.read_parquet(path, columns=["datetime"])["datetime"]
    if values.empty:
        return None, None
    timestamps = pd.to_datetime(values)
    return str(timestamps.min()), str(timestamps.max())


def _online_schedule(panel: dict[str, pd.DataFrame]) -> dict[date, str]:
    """Causal reference using only observations seen through each session.

    Equality with the pinned full schedule proves every session prefix by
    induction: earlier transitions are already equal and the current
    transition sees only the prior settlement plus current-session presence.
    """

    all_dates = sorted({day for frame in panel.values() for day in frame.index})
    if not all_dates:
        return {}

    def metric(day: date) -> dict[str, float]:
        oi = {
            month: float(frame.loc[day, "open_interest"])
            for month, frame in panel.items()
            if day in frame.index
        }
        if oi and all(value > 0 for value in oi.values()):
            return oi
        return {
            month: float(frame.loc[day, "volume"])
            for month, frame in panel.items()
            if day in frame.index
        }

    first = all_dates[0]
    first_metric = metric(first)
    main = max(first_metric, key=first_metric.get)
    schedule = {first: main}
    last_seen = {month: first for month, frame in panel.items() if first in frame.index}
    streak_month: str | None = None
    streak = 0

    for index in range(1, len(all_dates)):
        day, prior = all_dates[index], all_dates[index - 1]
        active = {month for month, frame in panel.items() if day in frame.index}
        for month in active:
            last_seen[month] = day
        prior_metric = metric(prior)
        if day > last_seen[main]:
            scores = {month: prior_metric.get(month, float("-inf")) for month in active}
            if all(value == float("-inf") for value in scores.values()):
                current_metric = metric(day)
                scores = {month: current_metric.get(month, float("-inf")) for month in active}
            main = max(scores, key=scores.get)
            streak_month, streak = None, 0
        else:
            others = {month for month in prior_metric if month != main}
            if others and main in prior_metric:
                leader = max(others, key=lambda month: prior_metric[month])
                if prior_metric[leader] > prior_metric[main]:
                    streak = streak + 1 if streak_month == leader else 1
                    streak_month = leader
                    if streak >= 3:
                        main = leader
                        streak_month, streak = None, 0
                else:
                    streak_month, streak = None, 0
            else:
                streak_month, streak = None, 0
        schedule[day] = main
    return schedule


def _roll_audit(
    provenance: dict[str, Any], raw_root: Path, paired_repo: Path
) -> list[dict[str, Any]]:
    source = next(
        row for row in provenance["generator_sources"] if row["repository"] == "paired-trading"
    )
    module = _load_continuous_module(_git_blob(paired_repo, source["commit"], source["path"]))
    entries: list[dict[str, str]] = []
    for candidate in provenance["bound_candidates"]:
        product = candidate["source_id"].split("_")[1][:2]
        entries.extend({**entry, "product": product} for entry in candidate["raw_inputs"])
    _pin_discovery(module, raw_root, entries)

    result = []
    for candidate in provenance["bound_candidates"]:
        product = candidate["source_id"].split("_")[1][:2]
        module._SCHEDULE_CACHE.clear()
        full = module.build_main_schedule(raw_root, "SHFE", product)
        panel = module._load_daily_panel(raw_root, "SHFE", product)
        online = _online_schedule(panel)
        if online != full:
            first = next(day for day in sorted(full) if online.get(day) != full.get(day))
            raise ValueError(f"roll schedule prefix mismatch for {product} at {first}")
        records = _roll_records(full, date.fromisoformat(candidate["window_start_local"]))
        expected = candidate["causal_roll_schedule"]
        if _canonical_hash(records) != expected["records_sha256"]:
            raise ValueError(f"roll schedule hash mismatch for {product}")
        result.append(
            {
                "product": product,
                "selection": "prior_session_OI_when_all_active_positive_else_volume",
                "confirmation_sessions": 3,
                "effective_session": "next_session_after_third_confirmation",
                "date_semantics": "exchange_trading_date",
                "session_prefixes_checked": len(full),
                "prefix_failures": 0,
                "full_schedule_records_sha256": expected["records_sha256"],
                "mathematical_causality": "supported",
                "historical_input_availability": "unproven",
                "embedded_candidate_annotations": "quarantined_calendar_date_join",
            }
        )
    return result


def build_blocker_packet(
    *,
    provenance: dict[str, Any],
    provenance_path: Path,
    raw_root: Path,
    paired_repo: Path,
) -> dict[str, Any]:
    """Audit exactly the 210 manifest inputs and retain quarantine."""

    records: list[dict[str, Any]] = []
    for candidate in provenance["bound_candidates"]:
        product = candidate["source_id"].split("_")[1][:2]
        for entry in candidate["raw_inputs"]:
            path = raw_root / entry["path"]
            if sha256_file(path) != entry["sha256"]:
                raise ValueError(f"raw input hash mismatch for {entry['path']}")
            metadata_keys = _metadata_keys(path)
            if set(metadata_keys) - {"ARROW:schema", "pandas"}:
                raise ValueError(f"unexpected custom metadata for {entry['path']}")
            first, last = _observation_bounds(path)
            records.append(
                {
                    "product": product,
                    "role": entry["role"],
                    "month": entry["month"],
                    "path": entry["path"],
                    "sha256": entry["sha256"],
                    "first_observation": first,
                    "last_observation": last,
                    "parquet_metadata_keys": metadata_keys,
                    "evidence": {
                        field: {"status": "absent", "value": None} for field in EVIDENCE_FIELDS
                    },
                    "filesystem_timestamps_accepted_as_provenance": False,
                    "historical_as_of_availability": "unproven",
                    "missing_evidence": list(GAP_CODES),
                    "status": "quarantined",
                }
            )

    if len(records) != 210 or len({row["path"] for row in records}) != 210:
        raise ValueError("audit must contain exactly 210 unique raw inputs")
    roles = Counter(row["role"] for row in records)
    products = Counter(row["product"] for row in records)
    roll = _roll_audit(provenance, raw_root, paired_repo)
    packet = {
        "schema_version": SCHEMA_VERSION,
        "hermes_task": "t_550fa726",
        "result": "deterministic_blocker_retaining_quarantine",
        "merged_provenance_packet": {
            "path": str(provenance_path),
            "sha256": sha256_file(provenance_path),
        },
        "audit_scope": {
            "raw_input_count": len(records),
            "unique_raw_path_count": len({row["path"] for row in records}),
            "by_product": dict(sorted(products.items())),
            "by_role": dict(sorted(roles.items())),
            "external_repositories_and_data_read_only": True,
            "directory_discovery_used_for_raw_inputs": False,
        },
        "evidence_contract": {
            "required_fields": list(EVIDENCE_FIELDS),
            "filesystem_mtime_or_birthtime_is_sufficient": False,
            "content_observation_bounds_are_query_cutoff_evidence": False,
            "all_required_fields_needed_for_historical_availability": True,
        },
        "raw_inputs": records,
        "gap_summary": {
            "inputs_with_complete_evidence": 0,
            "inputs_with_gaps": 210,
            "gap_counts": {code: 210 for code in GAP_CODES},
            "historical_as_of_availability_proven": 0,
        },
        "roll_schedule_audit": roll,
        "capability_boundary": {
            "causal_trading_date_roll_schedule": "supported_conditional_on_raw_bytes",
            "raw_acquisition_and_historical_availability": "quarantined",
            "embedded_main_month_is_roll": "quarantined",
            "underlying_candidates_eligible_for_score_today": False,
            "performance_evaluation_allowed": False,
            "iv_or_regime_promotion_attempted": False,
            "advance_m7": False,
            "execution_change_allowed": False,
        },
    }
    validate_blocker_packet(packet)
    return packet


def validate_blocker_packet(packet: dict[str, Any]) -> None:
    """Reject incomplete audits or any promotion beyond this task."""

    if packet.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported raw availability packet schema")
    if packet.get("hermes_task") != "t_550fa726":
        raise ValueError("wrong Hermes task")
    records = packet.get("raw_inputs", [])
    if len(records) != 210 or len({row.get("path") for row in records}) != 210:
        raise ValueError("packet must enumerate 210 unique raw inputs")
    for row in records:
        if row.get("missing_evidence") != list(GAP_CODES):
            raise ValueError(f"evidence gap drift for {row.get('path')}")
        if any(
            row["evidence"][field] != {"status": "absent", "value": None}
            for field in EVIDENCE_FIELDS
        ):
            raise ValueError(f"unsupported evidence claim for {row.get('path')}")
        if (
            row.get("historical_as_of_availability") != "unproven"
            or row.get("status") != "quarantined"
        ):
            raise ValueError(f"raw input promotion is forbidden for {row.get('path')}")
    if any(
        row.get("prefix_failures") != 0
        or row.get("mathematical_causality") != "supported"
        or row.get("historical_input_availability") != "unproven"
        for row in packet.get("roll_schedule_audit", [])
    ):
        raise ValueError("roll audit boundary invalid")
    boundary = packet["capability_boundary"]
    if (
        boundary["underlying_candidates_eligible_for_score_today"]
        or boundary["performance_evaluation_allowed"]
        or boundary["iv_or_regime_promotion_attempted"]
        or boundary["advance_m7"]
        or boundary["execution_change_allowed"]
    ):
        raise ValueError("raw availability packet cannot widen capability")


def verify_blocker_packet(
    packet: dict[str, Any],
    *,
    provenance: dict[str, Any],
    provenance_path: Path,
    raw_root: Path,
    paired_repo: Path,
) -> dict[str, Any]:
    validate_blocker_packet(packet)
    rebuilt = build_blocker_packet(
        provenance=provenance,
        provenance_path=provenance_path,
        raw_root=raw_root,
        paired_repo=paired_repo,
    )
    if rebuilt != packet:
        raise ValueError("raw availability blocker packet is not reproducible")
    return {
        "ok": True,
        "task": "t_550fa726",
        "raw_inputs": 210,
        "inputs_with_complete_evidence": 0,
        "session_prefixes_checked": sum(
            row["session_prefixes_checked"] for row in packet["roll_schedule_audit"]
        ),
        "quarantine_retained": True,
        "advance_m7": False,
    }
