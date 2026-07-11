"""Bounded, no-lookahead input artifacts for historical PA / Feitian research."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from data.store import BarStore
from engine.pa_feitian.manifest import sha256_file


PROTOCOL_VERSION = "pa_feitian_historical_asof_protocol_v1"
ARTIFACT_VERSION = "pa_feitian_historical_asof_inputs_v1"
AUDIT_VERSION = "pa_feitian_historical_asof_coverage_audit_v1"
PUBLIC_DATA_ROOT = "external://quant-data"
_SUPPORTED_LEVELS = frozenset({"D", "W", "60min", "15min"})


def _write_json(payload: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _utc(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def load_asof_protocol(path: str | Path) -> dict[str, Any]:
    """Load the frozen lane protocol and reject unsafe or unbounded variants."""

    protocol = json.loads(Path(path).read_text(encoding="utf-8"))
    if protocol.get("schema_version") != PROTOCOL_VERSION:
        raise ValueError(f"protocol schema_version must be {PROTOCOL_VERSION!r}")
    if protocol.get("research_mode") != "coverage_and_feasibility_only":
        raise ValueError("historical as-of lane is coverage_and_feasibility_only")
    if "15:00 Asia/Shanghai (07:00Z)" not in protocol.get("decision_time_rule", ""):
        raise ValueError("protocol must freeze the SHFE daily-bar availability cutoff")
    source = protocol.get("source_policy", {})
    required_source_guards = {
        "explicit_paths_only": True,
        "allow_continuous_synthesis": False,
        "allow_json_fallback": False,
        "allow_raw_store_scan": False,
        "allow_contract_selection": False,
        "allow_contract_reselection": False,
        "allow_proxies": False,
    }
    for key, expected in required_source_guards.items():
        if source.get(key) is not expected:
            raise ValueError(f"unsafe source_policy {key!r}")
    lookback = protocol.get("lookback_calendar_days")
    if not isinstance(lookback, int) or not 1 <= lookback <= 366:
        raise ValueError("lookback_calendar_days must be in [1, 366]")
    levels = protocol.get("levels")
    if not isinstance(levels, list) or not levels or len(levels) != len(set(levels)):
        raise ValueError("levels must be a non-empty unique list")
    if not set(levels).issubset(_SUPPORTED_LEVELS):
        raise ValueError(f"levels must be a subset of {sorted(_SUPPORTED_LEVELS)}")
    minimum_rows = protocol.get("minimum_rows")
    if not isinstance(minimum_rows, dict) or set(minimum_rows) != set(levels):
        raise ValueError("minimum_rows must define every frozen level exactly once")
    if any(not isinstance(value, int) or not 1 <= value <= 5000 for value in minimum_rows.values()):
        raise ValueError("minimum_rows values must be integers in [1, 5000]")
    universe = protocol.get("universe")
    if not isinstance(universe, list) or not 1 <= len(universe) <= 4:
        raise ValueError("universe must contain between one and four explicit members")
    universe_ids: set[str] = set()
    for member in universe:
        required = {"id", "source_symbol", "quant_symbol", "exchange_mic"}
        if not required.issubset(member):
            raise ValueError("every universe member must define explicit source coordinates")
        if member["exchange_mic"] != "XSHF" or member["quant_symbol"] not in {
            "ag0",
            "au0",
        }:
            raise ValueError("v1 universe is restricted to explicit SHFE ag0/au0 paths")
        universe_ids.add(str(member["id"]))
    if len(universe_ids) != len(universe):
        raise ValueError("universe ids must be unique")
    decisions = protocol.get("decisions")
    if not isinstance(decisions, list) or not 1 <= len(decisions) <= 12:
        raise ValueError("decisions must contain between one and twelve entries")
    seen: set[str] = set()
    previous: datetime | None = None
    for decision in decisions:
        decision_id = str(decision.get("id", ""))
        if not decision_id or decision_id in seen:
            raise ValueError("decision ids must be present and unique")
        seen.add(decision_id)
        if decision.get("universe_id") not in universe_ids:
            raise ValueError("decision universe_id must be frozen in universe")
        ts = _utc(decision.get("decision_ts_utc"), "decision_ts_utc")
        if previous is not None and ts < previous:
            raise ValueError("decisions must be time ordered")
        previous = ts
    capabilities = protocol.get("capability_policy", {})
    expected_capabilities = {
        "source_identity_pinning": "supported",
        "strict_asof_aggregation_mechanics": "supported",
        "underlying_ohlcv_asof": "data_present_but_unverified",
        "roll_provenance": "data_present_but_unverified",
        "delta_dte": "blocked",
        "causal_iv": "data_present_but_unverified",
        "regime": "blocked",
        "option_price_cadence": "blocked",
        "dd_line": "blocked",
        "bid_ask": "blocked",
    }
    if {key: value.get("status") for key, value in capabilities.items()} != (
        expected_capabilities
    ):
        raise ValueError("capability statuses must retain the frozen support boundary")
    candidates = protocol.get("candidate_sources")
    if not isinstance(candidates, list) or len(candidates) != 6:
        raise ValueError("protocol must pin the six exact continuous candidates")
    expected_filenames = {
        f"SHFE.{product}0.{suffix}.parquet"
        for product in ("ag", "au")
        for suffix in ("5min", "option_ivskew", "regime")
    }
    if {item.get("filename") for item in candidates} != expected_filenames:
        raise ValueError("candidate source filenames are not the frozen exact set")
    for candidate in candidates:
        if not str(candidate.get("sha256", "")).startswith("sha256:"):
            raise ValueError("every candidate source must pin SHA-256")
    return protocol


def _json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    return value


def _series_payload(frame: pd.DataFrame) -> list[dict[str, Any]]:
    columns = [
        name
        for name in ("timestamp", "open", "high", "low", "close", "volume", "open_interest")
        if name in frame.columns
    ]
    rows: list[dict[str, Any]] = []
    for record in frame[columns].to_dict(orient="records"):
        ts = pd.Timestamp(record.pop("timestamp"))
        rows.append(
            {
                "timestamp": ts.isoformat().replace("+00:00", "Z"),
                **{key: _json_value(value) for key, value in record.items()},
            }
        )
    return rows


def build_historical_asof_artifacts(
    *,
    protocol: dict[str, Any],
    protocol_path: str | Path,
    quant_data_root: str | Path,
    generated_at_utc: datetime,
    source_commit: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build decision-time input snapshots without discovery or fallback."""

    if generated_at_utc.tzinfo is None or generated_at_utc.utcoffset() is None:
        raise ValueError("generated_at_utc must be timezone-aware")
    members = {str(item["id"]): item for item in protocol["universe"]}
    snapshots: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    root = Path(quant_data_root)
    store = BarStore(root)
    lookback = timedelta(days=int(protocol["lookback_calendar_days"]))

    for decision in protocol["decisions"]:
        member = members[str(decision["universe_id"])]
        as_of = _utc(decision["decision_ts_utc"], "decision_ts_utc")
        series: list[dict[str, Any]] = []
        for level in protocol["levels"]:
            folder = {"D": "daily", "W": "weekly", "60min": "hour", "15min": "min15"}[
                level
            ]
            filename = f"SHFE.{member['quant_symbol']}.parquet"
            public_path = f"{PUBLIC_DATA_ROOT}/{folder}/{filename}"
            try:
                barframe = store.load_barframe(
                    str(member["quant_symbol"]),
                    str(member["exchange_mic"]),
                    str(level),
                    start=as_of - lookback,
                    end=as_of,
                    as_of=as_of,
                    allow_continuous_synthesis=False,
                )
            except (FileNotFoundError, KeyError, OSError, ValueError) as exc:
                status = "data_blocked"
                rows: list[dict[str, Any]] = []
                payload_hash = None
                first_ts = None
                last_ts = None
                reason = type(exc).__name__
            else:
                rows = _series_payload(barframe.df)
                first_ts = rows[0]["timestamp"]
                last_ts = rows[-1]["timestamp"]
                if any(_utc(row["timestamp"], "bar timestamp") > as_of for row in rows):
                    raise AssertionError("future bar escaped BarStore as_of guard")
                if len(rows) < int(protocol["minimum_rows"][level]):
                    status = "data_blocked"
                    payload_hash = None
                    reason = "insufficient_history"
                else:
                    status = "supported"
                    payload_hash = barframe.payload_hash
                    reason = None
            counts[status] += 1
            item = {
                "level": level,
                "status": status,
                "source": public_path,
                "row_count": len(rows),
                "first_timestamp": first_ts,
                "last_timestamp": last_ts,
                "payload_hash": payload_hash,
                "blocked_reason": reason,
                "bars": rows,
            }
            series.append(item)
            coverage_rows.append(
                {
                    "decision_id": decision["id"],
                    "decision_ts_utc": decision["decision_ts_utc"],
                    "universe_id": member["id"],
                    **{key: value for key, value in item.items() if key != "bars"},
                }
            )
        snapshots.append(
            {
                "decision_id": decision["id"],
                "decision_ts_utc": decision["decision_ts_utc"],
                "universe_id": member["id"],
                "source_symbol": member["source_symbol"],
                "series": series,
            }
        )

    generated = generated_at_utc.astimezone(UTC).isoformat().replace("+00:00", "Z")
    common = {
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": sha256_file(protocol_path),
        "generated_at_utc": generated,
        "source_commit": source_commit,
        "data_root": PUBLIC_DATA_ROOT,
    }
    artifact = {
        "schema_version": ARTIFACT_VERSION,
        **common,
        "snapshots": snapshots,
        "guardrails": {
            "explicit_source_paths_only": True,
            "as_of_required": True,
            "date_today_used": False,
            "future_rows_allowed": False,
            "continuous_synthesis": False,
            "json_fallback": False,
            "raw_store_scan": False,
            "contract_selection": "none",
            "contract_reselection": False,
        },
    }
    capabilities = [
        {"capability": name, **details}
        for name, details in protocol["capability_policy"].items()
    ]
    audit = {
        "schema_version": AUDIT_VERSION,
        **common,
        "funnel": {
            "requested_series": len(coverage_rows),
            "supported_series": counts["supported"],
            "data_blocked_series": counts["data_blocked"],
        },
        "coverage": coverage_rows,
        "capabilities": capabilities,
        "gate": {
            "classification": "coverage_feasibility_only",
            "faithful_feitian_ready": False,
            "performance_evaluation_allowed": False,
            "strategy_inference_allowed": False,
            "advance_m7": False,
            "next_gate": protocol["next_gate"],
        },
    }
    verify_historical_asof_artifact(artifact)
    return artifact, audit


def verify_historical_asof_artifact(artifact: dict[str, Any]) -> None:
    """Reject future rows and any artifact that weakens the frozen guards."""

    if artifact.get("schema_version") != ARTIFACT_VERSION:
        raise ValueError("unexpected historical as-of artifact schema")
    guards = artifact.get("guardrails", {})
    required = {
        "explicit_source_paths_only": True,
        "as_of_required": True,
        "date_today_used": False,
        "future_rows_allowed": False,
        "continuous_synthesis": False,
        "json_fallback": False,
        "raw_store_scan": False,
        "contract_selection": "none",
        "contract_reselection": False,
    }
    if guards != required:
        raise ValueError("historical as-of artifact guardrails were weakened")
    for snapshot in artifact.get("snapshots", []):
        as_of = _utc(snapshot.get("decision_ts_utc"), "decision_ts_utc")
        for series in snapshot.get("series", []):
            for row in series.get("bars", []):
                if _utc(row.get("timestamp"), "bar timestamp") > as_of:
                    raise ValueError("historical as-of artifact contains a future bar")


def run_historical_asof_lane(
    *,
    protocol_path: str | Path,
    quant_data_root: str | Path,
    artifact_out: str | Path,
    audit_out: str | Path,
    generated_at_utc: datetime,
    source_commit: str,
) -> dict[str, Any]:
    protocol = load_asof_protocol(protocol_path)
    artifact, audit = build_historical_asof_artifacts(
        protocol=protocol,
        protocol_path=protocol_path,
        quant_data_root=quant_data_root,
        generated_at_utc=generated_at_utc,
        source_commit=source_commit,
    )
    _write_json(artifact, artifact_out)
    _write_json(audit, audit_out)
    return audit
