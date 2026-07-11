"""Audit exact continuous candidates for the PA / Feitian historical as-of lane."""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_left, bisect_right
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

import pandas as pd

from engine.pa_feitian.historical_asof import (
    ARTIFACT_VERSION,
    AUDIT_VERSION,
    PUBLIC_DATA_ROOT,
    _utc,
    load_asof_protocol,
    verify_historical_asof_artifact,
)
from engine.pa_feitian.manifest import sha256_file


_SHANGHAI = "Asia/Shanghai"
_FIVE_MIN_COLUMNS = [
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "turnover",
    "open_interest",
    "main_month",
    "is_roll",
]


def _canonical_hash(frame: pd.DataFrame) -> str:
    records: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        record: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, pd.Timestamp):
                record[key] = value.isoformat().replace("+00:00", "Z")
            elif pd.isna(value):
                record[key] = None
            elif hasattr(value, "item"):
                record[key] = value.item()
            else:
                record[key] = value
        records.append(record)
    payload = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(payload.encode()).hexdigest()}"


def _trading_date_and_offset(
    ts: pd.Timestamp, sessions: list[date]
) -> tuple[date | None, int | None]:
    """Map naive Shanghai period-end to trading date and trading-minute offset."""

    value = ts.to_pydatetime()
    day = value.date()
    clock = value.time()
    if clock > time(16, 0):
        index = bisect_right(sessions, day)
        trading_date = sessions[index] if index < len(sessions) else None
        if clock < time(21, 0):
            return trading_date, None
        offset = (value.hour * 60 + value.minute) - 21 * 60
    elif clock <= time(4, 0):
        index = bisect_left(sessions, day)
        trading_date = sessions[index] if index < len(sessions) else None
        offset = 180 + value.hour * 60 + value.minute
    else:
        trading_date = day if day in sessions else None
        minute = value.hour * 60 + value.minute
        if 9 * 60 <= minute <= 10 * 60 + 15:
            offset = 330 + minute - 9 * 60
        elif 10 * 60 + 30 <= minute <= 11 * 60 + 30:
            offset = 405 + minute - (10 * 60 + 30)
        elif 13 * 60 + 30 <= minute <= 15 * 60:
            offset = 465 + minute - (13 * 60 + 30)
        else:
            offset = None
    return trading_date, offset


def _aggregate_group(group: pd.DataFrame) -> dict[str, Any]:
    return {
        "timestamp": group["timestamp"].iloc[-1],
        "open": float(group["open"].iloc[0]),
        "high": float(group["high"].max()),
        "low": float(group["low"].min()),
        "close": float(group["close"].iloc[-1]),
        "volume": float(group["volume"].sum()),
        "turnover": float(group["turnover"].sum()),
        "open_interest": float(group["open_interest"].iloc[-1]),
        "constituent_count": len(group),
    }


def aggregate_strict_asof(
    frame: pd.DataFrame,
    *,
    decision_ts_utc: datetime,
    lookback_calendar_days: int,
) -> dict[str, pd.DataFrame]:
    """Filter first, then deterministically derive D/W/60/15 candidates.

    The source is naive Shanghai period-end data. The aggregation policy is
    deliberately explicit and deterministic, but does not establish that the
    continuous source's roll selection was itself causal.
    """

    if decision_ts_utc.tzinfo is None or decision_ts_utc.utcoffset() is None:
        raise ValueError("decision_ts_utc must be timezone-aware")
    raw = frame[_FIVE_MIN_COLUMNS].copy()
    raw["timestamp"] = (
        pd.to_datetime(raw["datetime"]).dt.tz_localize(_SHANGHAI).dt.tz_convert("UTC")
    )
    cutoff = pd.Timestamp(decision_ts_utc).tz_convert("UTC")
    start = cutoff - pd.Timedelta(days=lookback_calendar_days)
    # This filter MUST precede calendar inference or aggregation.
    raw = raw[(raw["timestamp"] >= start) & (raw["timestamp"] <= cutoff)].copy()
    raw = raw.sort_values("timestamp").reset_index(drop=True)
    if raw.empty:
        return {level: pd.DataFrame() for level in ("D", "W", "60min", "15min")}
    local = raw["timestamp"].dt.tz_convert(_SHANGHAI).dt.tz_localize(None)
    sessions = sorted(
        {
            ts.date()
            for ts in local
            if time(8, 0) < ts.time() <= time(16, 0)
        }
    )
    mapped = [_trading_date_and_offset(ts, sessions) for ts in local]
    raw["trading_date"] = [item[0] for item in mapped]
    raw["trading_minute_offset"] = [item[1] for item in mapped]
    valid = raw.dropna(subset=["trading_date", "trading_minute_offset"]).copy()
    valid["trading_minute_offset"] = valid["trading_minute_offset"].astype(int)

    daily_rows = [
        {"trading_date": trading_date.isoformat(), **_aggregate_group(group)}
        for trading_date, group in valid.groupby("trading_date", sort=True)
    ]
    daily = pd.DataFrame(daily_rows)
    if daily.empty:
        return {level: pd.DataFrame() for level in ("D", "W", "60min", "15min")}
    daily_dates = pd.to_datetime(daily["trading_date"])
    iso = daily_dates.dt.isocalendar()
    daily["iso_year"] = iso["year"].to_numpy()
    daily["iso_week"] = iso["week"].to_numpy()
    weekly_rows = [
        _aggregate_group(group)
        for _, group in daily.groupby(["iso_year", "iso_week"], sort=True)
    ]
    weekly = pd.DataFrame(weekly_rows)

    intraday: dict[str, pd.DataFrame] = {}
    for level, width in (("15min", 15), ("60min", 60)):
        candidate = valid.copy()
        candidate["bucket"] = ((candidate["trading_minute_offset"] - 1).clip(lower=0) // width)
        rows = [
            {
                "trading_date": trading_date.isoformat(),
                "bucket": int(bucket),
                **_aggregate_group(group),
            }
            for (trading_date, bucket), group in candidate.groupby(
                ["trading_date", "bucket"], sort=True
            )
        ]
        intraday[level] = pd.DataFrame(rows)
    return {"D": daily, "W": weekly, **intraday}


def _source_schema(frame: pd.DataFrame) -> list[dict[str, str]]:
    return [{"name": name, "dtype": str(frame[name].dtype)} for name in frame.columns]


def _coverage(frame: pd.DataFrame, temporal_column: str) -> tuple[str, str]:
    values = pd.to_datetime(frame[temporal_column])
    return str(values.min()), str(values.max())


def _five_min_audit(frame: pd.DataFrame) -> dict[str, Any]:
    timestamps = pd.to_datetime(frame["datetime"])
    month_changes = frame["main_month"].ne(frame["main_month"].shift()) & (frame.index > 0)
    roll_times = timestamps[month_changes].dt.strftime("%H:%M").value_counts().sort_index()
    coherent = (
        (frame["high"] >= frame[["open", "close", "low"]].max(axis=1))
        & (frame["low"] <= frame[["open", "close", "high"]].min(axis=1))
    )
    midnight_changes = int((timestamps[month_changes].dt.time == time(0, 0)).sum())
    return {
        "timestamps_sorted": bool(timestamps.is_monotonic_increasing),
        "duplicate_timestamps": int(timestamps.duplicated().sum()),
        "invalid_ohlc_rows": int((~coherent).sum()),
        "main_month_count": int(frame["main_month"].nunique()),
        "month_change_count": int(month_changes.sum()),
        "is_roll_count": int(frame["is_roll"].sum()),
        "roll_flag_mismatch_count": int((frame["is_roll"] != month_changes).sum()),
        "roll_change_times": {key: int(value) for key, value in roll_times.items()},
        "midnight_roll_annotations": midnight_changes,
        "roll_provenance_status": "data_present_but_unverified",
        "roll_provenance_reason": (
            "main_month/is_roll are internally consistent, but most changes occur at "
            "calendar midnight inside a CN trading session and the Parquet metadata "
            "does not bind the generator, input panel, schedule, or build cutoff"
        ),
    }


def build_continuous_source_audit(
    *,
    protocol: dict[str, Any],
    protocol_path: str | Path,
    continuous_root: str | Path,
    generated_at_utc: datetime,
    source_commit: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Audit only protocol-listed files; hashes are mandatory source identity."""

    root = Path(continuous_root)
    sources: list[dict[str, Any]] = []
    loaded: dict[tuple[str, str], pd.DataFrame] = {}
    for candidate in protocol["candidate_sources"]:
        path = root / candidate["filename"]
        actual_hash = sha256_file(path)
        if actual_hash != candidate["sha256"]:
            raise ValueError(
                f"candidate source hash mismatch for {candidate['filename']}: {actual_hash}"
            )
        frame = pd.read_parquet(path)
        expected_columns = candidate["expected_columns"]
        if list(frame.columns) != expected_columns:
            raise ValueError(f"candidate schema mismatch for {candidate['filename']}")
        temporal = "datetime" if candidate["kind"] == "underlying_5min" else "date"
        first, last = _coverage(frame, temporal)
        finding: dict[str, Any] = {
            "source_id": candidate["source_id"],
            "product": candidate["product"],
            "kind": candidate["kind"],
            "source": f"{PUBLIC_DATA_ROOT}/continuous/{candidate['filename']}",
            "sha256": actual_hash,
            "byte_size": path.stat().st_size,
            "row_count": len(frame),
            "schema": _source_schema(frame),
            "first_observation": first,
            "last_observation": last,
            "parquet_provenance_metadata_present": False,
            "source_identity_pinned": True,
            "candidate_status": "data_present_but_unverified",
        }
        if candidate["kind"] == "underlying_5min":
            finding["quality_and_roll"] = _five_min_audit(frame)
        else:
            dates = set(pd.to_datetime(frame["date"]).dt.date)
            relevant = [
                decision
                for decision in protocol["decisions"]
                if decision["universe_id"].endswith(candidate["product"] + "_continuous")
            ]
            finding["frozen_decision_date_coverage"] = {
                decision["id"]: _utc(decision["decision_ts_utc"], "decision").date() in dates
                for decision in relevant
            }
            finding["availability_timestamp_present"] = False
            if candidate["kind"] == "regime":
                finding["causality_status"] = "blocked"
                finding["causality_reason"] = (
                    "date-only rows have no availability timestamp or build manifest; the "
                    "located unbound generator computes the ATR stress threshold from the "
                    "full-series 80th percentile"
                )
            else:
                finding["causality_status"] = "data_present_but_unverified"
                finding["causality_reason"] = (
                    "date-only rows do not prove when same-day option closes, maturity, "
                    "chain membership, or main-month schedule became available"
                )
        loaded[(candidate["product"], candidate["kind"])] = frame
        sources.append(finding)

    snapshots: list[dict[str, Any]] = []
    aggregation_coverage: list[dict[str, Any]] = []
    members = {item["id"]: item for item in protocol["universe"]}
    for decision in protocol["decisions"]:
        member = members[decision["universe_id"]]
        product = member["product"]
        raw = loaded[(product, "underlying_5min")]
        as_of = _utc(decision["decision_ts_utc"], "decision_ts_utc")
        levels = aggregate_strict_asof(
            raw,
            decision_ts_utc=as_of,
            lookback_calendar_days=protocol["lookback_calendar_days"],
        )
        series: list[dict[str, Any]] = []
        for level in protocol["levels"]:
            frame = levels[level]
            last_ts = None if frame.empty else frame["timestamp"].iloc[-1]
            if last_ts is not None and pd.Timestamp(last_ts) > pd.Timestamp(as_of):
                raise AssertionError("strict-as-of aggregation emitted a future row")
            finding = {
                "level": level,
                "status": "data_present_but_unverified",
                "row_count": len(frame),
                "minimum_rows_required": protocol["minimum_rows"][level],
                "minimum_rows_met": len(frame) >= protocol["minimum_rows"][level],
                "first_timestamp": (
                    None
                    if frame.empty
                    else frame["timestamp"].iloc[0].isoformat().replace("+00:00", "Z")
                ),
                "last_timestamp": (
                    None if last_ts is None else last_ts.isoformat().replace("+00:00", "Z")
                ),
                "payload_hash": _canonical_hash(frame),
                "strict_asof_passed": True,
                "semantic_eligibility": "unverified_roll_and_session_provenance",
            }
            series.append(finding)
            aggregation_coverage.append(
                {
                    "decision_id": decision["id"],
                    "decision_ts_utc": decision["decision_ts_utc"],
                    "product": product,
                    **finding,
                }
            )
        snapshots.append(
            {
                "decision_id": decision["id"],
                "decision_ts_utc": decision["decision_ts_utc"],
                "universe_id": decision["universe_id"],
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
        "source_identities": [
            {key: source[key] for key in ("source_id", "source", "sha256")}
            for source in sources
        ],
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
        "candidate_data_eligible_for_score_today": False,
    }
    audit = {
        "schema_version": AUDIT_VERSION,
        **common,
        "source_audit": sources,
        "aggregation_audit": aggregation_coverage,
        "capabilities": [
            {"capability": name, **details}
            for name, details in protocol["capability_policy"].items()
        ],
        "gate": {
            "classification": "candidate_sources_present_but_unverified",
            "faithful_feitian_ready": False,
            "performance_evaluation_allowed": False,
            "strategy_inference_allowed": False,
            "advance_m7": False,
            "next_gate": protocol["next_gate"],
        },
    }
    verify_historical_asof_artifact(artifact)
    return artifact, audit


def run_continuous_source_audit(
    *,
    protocol_path: str | Path,
    continuous_root: str | Path,
    artifact_out: str | Path,
    audit_out: str | Path,
    generated_at_utc: datetime,
    source_commit: str,
) -> dict[str, Any]:
    protocol = load_asof_protocol(protocol_path)
    artifact, audit = build_continuous_source_audit(
        protocol=protocol,
        protocol_path=protocol_path,
        continuous_root=continuous_root,
        generated_at_utc=generated_at_utc,
        source_commit=source_commit,
    )
    for payload, path in ((artifact, artifact_out), (audit, audit_out)):
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return audit
