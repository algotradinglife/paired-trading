"""Finalized-vintage, no-lookahead AU/AG underlying signal corpus.

The corpus is intentionally descriptive.  It consumes only two explicit,
hash-pinned continuous 5-minute files and the causal trading-date roll ledger
bound by M6-PROV-001.  It never reads the candidates' quarantined embedded
``main_month`` or ``is_roll`` annotations.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from engine.pa_feitian.continuous_provenance import (
    _canonical_hash,
    _git_blob,
    _load_continuous_module,
    _pin_discovery,
    _roll_records,
    _sha256_bytes,
    validate_manifest_boundary,
)
from engine.pa_feitian.continuous_source_audit import _trading_date_and_offset
from engine.pa_feitian.manifest import sha256_file


CONTRACT_VERSION = "pa_feitian_m6_underlying_corpus_contract_v1"
ARTIFACT_VERSION = "pa_feitian_m6_underlying_signal_corpus_v1"
TASK_ID = "t_715f7397"
LEVELS = ("D", "W", "60min", "15min")
SOURCE_COLUMNS = (
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "turnover",
    "open_interest",
)
_SHANGHAI = "Asia/Shanghai"
_EXCLUDED_CAPABILITIES = {
    "date_only_iv_or_regime",
    "options_or_option_premiums",
    "delta_or_dte",
    "dd_line",
    "bid_or_ask",
    "performance_or_outcomes",
    "candidate_selection",
    "m7",
    "execution",
}
_ARTIFACT_GUARDS = {
    "explicit_hash_pinned_paths_only": True,
    "directory_or_catalog_discovery": False,
    "implicit_current_time": False,
    "future_rows_allowed": False,
    "filter_before_session_mapping_or_resample": True,
    "embedded_roll_annotations_consumed": False,
    "contract_selection_or_reselection": False,
    "proxy_or_imputation": False,
    "descriptive_underlying_only": True,
    "downstream_promotion": False,
}
_SIGNALS = {
    "bar_direction": "up when close > open, down when close < open, otherwise flat",
    "bar_range": "high - low",
    "body_fraction": "abs(close - open) / (high - low), null for zero range",
    "close_location": "(close - low) / (high - low), null for zero range",
    "prior_20_high": "maximum high of the 20 aggregated bars strictly before the current bar",
    "prior_20_low": "minimum low of the 20 aggregated bars strictly before the current bar",
    "prior_20_mean_range": "mean high-low of the 20 aggregated bars strictly before the current bar",
    "range_over_prior_20_mean": "current range / prior_20_mean_range, null when the baseline is zero",
    "breakout_20": "up when close > prior_20_high, down when close < prior_20_low, otherwise none",
    "ema_5": "causal close EWM with span 5 and adjust=false through the current bar",
    "ema_20": "causal close EWM with span 20 and adjust=false through the current bar",
    "ema_alignment": "above when ema_5 > ema_20, below when ema_5 < ema_20, otherwise equal",
}


def canonical_json_bytes(value: Any) -> bytes:
    """Stable artifact encoding used by the builder and verifier."""

    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def canonical_payload_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def load_contract(path: str | Path) -> dict[str, Any]:
    contract = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_contract(contract)
    return contract


def validate_contract(contract: dict[str, Any]) -> None:
    """Reject any widening or post-freeze drift in the corpus specification."""

    if contract.get("schema_version") != CONTRACT_VERSION:
        raise ValueError("unsupported underlying corpus contract")
    if contract.get("hermes_task") != TASK_ID:
        raise ValueError("wrong Hermes task")
    if contract.get("research_mode") != "retrospective_finalized":
        raise ValueError("corpus must remain retrospective_finalized")
    window = contract.get("window", {})
    if window != {
        "first_trading_date": "2025-01-02",
        "last_trading_date": "2026-06-08",
        "lookback_calendar_days": 260,
        "source_timezone": _SHANGHAI,
        "timestamp_semantics": "naive_local_period_end",
    }:
        raise ValueError("frozen date range or timestamp contract drifted")
    cadence = contract.get("decision_cadence", {})
    if (
        cadence.get("rule")
        != "every trading date present in the declared causal roll schedule within the frozen window"
        or cadence.get("local_time") != "15:00:00"
        or cadence.get("utc_time") != "07:00:00Z"
        or cadence.get("requires_source_bar_at_local_close") is not True
        or cadence.get("current_time_or_calendar_discovery") is not False
    ):
        raise ValueError("frozen decision cadence drifted")
    aggregation = contract.get("aggregation", {})
    if (
        aggregation.get("levels") != list(LEVELS)
        or aggregation.get("filter_before_session_mapping_or_resample") is not True
        or aggregation.get("source_cutoff") != "timestamp <= decision_ts_utc"
        or aggregation.get("minimum_aggregated_rows") != 21
        or aggregation.get("missing_data_policy")
        != "exclude_level_without_proxy_or_imputation"
        or aggregation.get("ohlcv_rules")
        != {
            "open": "first",
            "high": "maximum",
            "low": "minimum",
            "close": "last",
            "volume": "sum",
            "open_interest": "last",
        }
    ):
        raise ValueError("frozen aggregation rules drifted")
    roll = contract.get("causal_roll_rule", {})
    if roll != {
        "selection": "prior_session_OI_when_all_active_positive_else_volume",
        "confirmation_sessions": 3,
        "effective_session": "next_session_after_third_confirmation",
        "date_semantics": "exchange_trading_date",
        "embedded_calendar_date_annotations_consumed": False,
    }:
        raise ValueError("causal roll rule drifted")
    bindings = contract.get("source_bindings", [])
    expected_source_coordinates = [
        ("au", "shfe_au0_underlying_5min", "SHFE.au0.5min.parquet"),
        ("ag", "shfe_ag0_underlying_5min", "SHFE.ag0.5min.parquet"),
    ]
    if [
        (row.get("product"), row.get("source_id"), row.get("filename"))
        for row in bindings
    ] != expected_source_coordinates:
        raise ValueError("source bindings must remain the frozen AU/AG files")
    if any(
        not str(row.get(field, "")).startswith("sha256:")
        for row in bindings
        for field in ("sha256", "raw_input_set_sha256", "causal_roll_records_sha256")
    ):
        raise ValueError("every source identity must be SHA-256 pinned")
    guards = contract.get("guardrails", {})
    if (
        guards.get("directory_or_catalog_discovery") is not False
        or guards.get("implicit_current_time") is not False
        or guards.get("future_rows_allowed") is not False
        or guards.get("contract_selection_or_reselection") is not False
        or guards.get("proxy_or_imputation") is not False
        or guards.get("descriptive_underlying_only") is not True
    ):
        raise ValueError("corpus guardrails were weakened")
    if set(contract.get("excluded_capabilities", [])) != _EXCLUDED_CAPABILITIES:
        raise ValueError("excluded capability boundary drifted")
    if contract.get("signals") != _SIGNALS:
        raise ValueError("frozen descriptive signal definitions drifted")
    output = contract.get("output_schema", {})
    if (
        output.get("schema_version") != ARTIFACT_VERSION
        or output.get("record_key") != ["product", "trading_date"]
        or output.get("level_order") != list(LEVELS)
        or output.get("numeric_rounding_decimal_places") != 10
        or output.get("json_sort_keys") is not True
    ):
        raise ValueError("frozen output schema drifted")
    if any(contract.get("promotion", {}).values()):
        raise ValueError("corpus contract cannot promote downstream capability")
    if len(contract.get("revision_and_observability_limitations", [])) != 4:
        raise ValueError("finalized-vintage limitations must remain explicit")


def _aggregate_groups(frame: pd.DataFrame, by: str | list[str]) -> pd.DataFrame:
    grouped = frame.groupby(by, sort=True)
    result = grouped.agg(
        timestamp=("timestamp", "last"),
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        open_interest=("open_interest", "last"),
        constituent_count=("timestamp", "size"),
    ).reset_index()
    if "constituent_count" in frame:
        counts = grouped["constituent_count"].sum().to_numpy()
        result["constituent_count"] = counts
    return result


def aggregate_at_decision(
    frame: pd.DataFrame,
    *,
    decision_ts_utc: datetime,
    causal_sessions: list[date],
    lookback_calendar_days: int,
    mapping_cache: dict[pd.Timestamp, tuple[date | None, int | None]] | None = None,
) -> tuple[dict[str, pd.DataFrame], int, str | None]:
    """Filter first, then map sessions and aggregate from prefix-only inputs."""

    if decision_ts_utc.tzinfo is None or decision_ts_utc.utcoffset() is None:
        raise ValueError("decision_ts_utc must be timezone-aware")
    missing = set(SOURCE_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"source missing columns {sorted(missing)}")
    cutoff = pd.Timestamp(decision_ts_utc).tz_convert("UTC")
    start = cutoff - pd.Timedelta(days=lookback_calendar_days)
    if "_timestamp_utc" in frame:
        timestamps = frame["_timestamp_utc"]
    else:
        timestamps = pd.to_datetime(frame["datetime"])
        if timestamps.isna().any() or timestamps.dt.tz is not None:
            raise ValueError("source datetime must be complete naive local period-end")
        timestamps = timestamps.dt.tz_localize(_SHANGHAI).dt.tz_convert("UTC")
    # Mandatory first temporal operation: later rows cannot affect mapping or grouping.
    mask = (timestamps >= start) & (timestamps <= cutoff)
    raw = frame.loc[mask, list(SOURCE_COLUMNS)].copy()
    raw["timestamp"] = timestamps.loc[mask].to_numpy()
    raw = raw.sort_values("timestamp").reset_index(drop=True)
    empty = {level: pd.DataFrame() for level in LEVELS}
    if raw.empty:
        return empty, 0, None
    sessions = sorted(day for day in causal_sessions if day <= cutoff.date())
    local = raw["timestamp"].dt.tz_convert(_SHANGHAI).dt.tz_localize(None)
    cache = mapping_cache if mapping_cache is not None else {}
    mapped = []
    for ts in local:
        result = cache.get(ts)
        if result is None:
            result = _trading_date_and_offset(ts, sessions)
            cache[ts] = result
        mapped.append(result)
    raw["trading_date"] = [item[0] for item in mapped]
    raw["trading_minute_offset"] = [item[1] for item in mapped]
    valid = raw.dropna(subset=["trading_date", "trading_minute_offset"]).copy()
    valid["trading_minute_offset"] = valid["trading_minute_offset"].astype(int)

    daily = _aggregate_groups(valid, "trading_date")
    daily["trading_date"] = daily["trading_date"].map(date.isoformat)
    if daily.empty:
        return empty, len(raw), _timestamp(raw["timestamp"].iloc[-1])
    dates = pd.to_datetime(daily["trading_date"])
    iso = dates.dt.isocalendar()
    daily["iso_year"] = iso["year"].to_numpy()
    daily["iso_week"] = iso["week"].to_numpy()
    weekly = _aggregate_groups(daily, ["iso_year", "iso_week"])
    intraday: dict[str, pd.DataFrame] = {}
    for level, width in (("60min", 60), ("15min", 15)):
        candidate = valid.copy()
        candidate["bucket"] = (
            (candidate["trading_minute_offset"] - 1).clip(lower=0) // width
        )
        intraday[level] = _aggregate_groups(candidate, ["trading_date", "bucket"])
        intraday[level]["trading_date"] = intraday[level]["trading_date"].map(
            date.isoformat
        )
    return (
        {"D": daily, "W": weekly, **intraday},
        len(raw),
        _timestamp(raw["timestamp"].iloc[-1]),
    )


def _round(value: Any) -> float | int | None:
    if pd.isna(value):
        return None
    if isinstance(value, int):
        return value
    return round(float(value), 10)


def _timestamp(value: Any) -> str:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert("UTC").isoformat().replace("+00:00", "Z")


def describe_latest(frame: pd.DataFrame) -> dict[str, Any] | None:
    """Return the frozen causal diagnostics for the latest aggregate."""

    if len(frame) < 21:
        return None
    ordered = frame.sort_values("timestamp").reset_index(drop=True)
    closes = ordered["close"].astype(float)
    prior = ordered.iloc[-21:-1]
    current = ordered.iloc[-1]
    current_range = float(current["high"] - current["low"])
    prior_mean_range = float(
        (prior["high"].astype(float) - prior["low"].astype(float)).mean()
    )
    prior_high = float(prior["high"].max())
    prior_low = float(prior["low"].min())
    close = float(current["close"])
    open_ = float(current["open"])
    ema5 = float(closes.ewm(span=5, adjust=False).mean().iloc[-1])
    ema20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
    return {
        "last_bar_timestamp_utc": _timestamp(current["timestamp"]),
        "aggregated_row_count": int(len(ordered)),
        "bar": {
            key: _round(current[key])
            for key in (
                "open",
                "high",
                "low",
                "close",
                "volume",
                "open_interest",
                "constituent_count",
            )
        },
        "diagnostics": {
            "bar_range": _round(current_range),
            "body_fraction": _round(abs(close - open_) / current_range)
            if current_range
            else None,
            "close_location": _round((close - float(current["low"])) / current_range)
            if current_range
            else None,
            "prior_20_high": _round(prior_high),
            "prior_20_low": _round(prior_low),
            "prior_20_mean_range": _round(prior_mean_range),
            "range_over_prior_20_mean": _round(current_range / prior_mean_range)
            if prior_mean_range
            else None,
            "ema_5": _round(ema5),
            "ema_20": _round(ema20),
        },
        "signals": {
            "bar_direction": "up" if close > open_ else "down" if close < open_ else "flat",
            "breakout_20": "up"
            if close > prior_high
            else "down"
            if close < prior_low
            else "none",
            "ema_alignment": "above"
            if ema5 > ema20
            else "below"
            if ema5 < ema20
            else "equal",
        },
    }


def build_corpus(
    *,
    contract: dict[str, Any],
    contract_path: Path,
    predecessor_refs: list[dict[str, str]],
    frames: dict[str, pd.DataFrame],
    schedules: dict[str, dict[date, str]],
) -> dict[str, Any]:
    """Build the deterministic corpus from already verified explicit inputs."""

    validate_contract(contract)
    first = date.fromisoformat(contract["window"]["first_trading_date"])
    last = date.fromisoformat(contract["window"]["last_trading_date"])
    lookback = int(contract["window"]["lookback_calendar_days"])
    records: list[dict[str, Any]] = []
    product_coverage: list[dict[str, Any]] = []
    total_reasons: dict[str, int] = {}

    for binding in contract["source_bindings"]:
        product = binding["product"]
        frame = frames[product].copy()
        source_timestamps = pd.to_datetime(frame["datetime"])
        if source_timestamps.isna().any() or source_timestamps.dt.tz is not None:
            raise ValueError("source datetime must be complete naive local period-end")
        frame["_timestamp_utc"] = source_timestamps.dt.tz_localize(
            _SHANGHAI
        ).dt.tz_convert("UTC")
        schedule = schedules[product]
        session_dates = sorted(schedule)
        requested = [day for day in session_dates if first <= day <= last]
        included = 0
        supported_series = 0
        reasons: dict[str, int] = {}
        close_dates = {
            ts.date() for ts in source_timestamps if ts.time() == time(15, 0)
        }
        mapping_cache: dict[pd.Timestamp, tuple[date | None, int | None]] = {}
        previous_month: str | None = None
        prior_month_by_day: dict[date, str | None] = {}
        for day in session_dates:
            prior_month_by_day[day] = previous_month
            previous_month = schedule[day]

        for day in requested:
            if day not in close_dates:
                reasons["missing_15_00_source_bar"] = (
                    reasons.get("missing_15_00_source_bar", 0) + 1
                )
                continue
            decision = datetime.combine(day, time(7, 0), tzinfo=UTC)
            aggregates, source_rows, max_source = aggregate_at_decision(
                frame,
                decision_ts_utc=decision,
                causal_sessions=[value for value in session_dates if value <= day],
                lookback_calendar_days=lookback,
                mapping_cache=mapping_cache,
            )
            levels = {level: describe_latest(aggregates[level]) for level in LEVELS}
            missing_levels = [level for level, value in levels.items() if value is None]
            if missing_levels:
                for level in missing_levels:
                    key = f"insufficient_{level}_history"
                    reasons[key] = reasons.get(key, 0) + 1
                continue
            if max_source is None or pd.Timestamp(max_source) > pd.Timestamp(decision):
                raise AssertionError("future source row escaped decision cutoff")
            included += 1
            supported_series += len(LEVELS)
            records.append(
                {
                    "record_id": f"retfin_{product}_{day.isoformat().replace('-', '')}_1500_cst",
                    "product": product,
                    "trading_date": day.isoformat(),
                    "decision_ts_utc": decision.isoformat().replace("+00:00", "Z"),
                    "source_id": binding["source_id"],
                    "source_sha256": binding["sha256"],
                    "raw_input_set_sha256": binding["raw_input_set_sha256"],
                    "causal_roll_records_sha256": binding[
                        "causal_roll_records_sha256"
                    ],
                    "causal_main_month": schedule[day],
                    "causal_roll_session": prior_month_by_day[day] not in {
                        None,
                        schedule[day],
                    },
                    "source_rows_in_lookback": source_rows,
                    "max_source_timestamp_utc": max_source,
                    "levels": {level: levels[level] for level in LEVELS},
                }
            )
        for key, count in reasons.items():
            total_reasons[key] = total_reasons.get(key, 0) + count
        product_coverage.append(
            {
                "product": product,
                "requested_decisions": len(requested),
                "included_records": included,
                "excluded_decisions": len(requested) - included,
                "requested_series": len(requested) * len(LEVELS),
                "supported_series": supported_series,
                "exclusion_reasons": reasons,
            }
        )

    records.sort(key=lambda row: (row["decision_ts_utc"], row["product"]))
    artifact = {
        "schema_version": ARTIFACT_VERSION,
        "hermes_task": TASK_ID,
        "research_mode": "retrospective_finalized",
        "contract": {
            "path": str(contract_path),
            "sha256": sha256_file(contract_path),
        },
        "predecessors": predecessor_refs,
        "guardrails": _ARTIFACT_GUARDS,
        "limitations": contract["revision_and_observability_limitations"],
        "coverage": {
            "first_trading_date": first.isoformat(),
            "last_trading_date": last.isoformat(),
            "decision_cadence": "causal_schedule_session_close_15_00_Asia_Shanghai",
            "products": product_coverage,
            "requested_decisions": sum(row["requested_decisions"] for row in product_coverage),
            "included_records": len(records),
            "excluded_decisions": sum(row["excluded_decisions"] for row in product_coverage),
            "requested_series": sum(row["requested_series"] for row in product_coverage),
            "supported_series": sum(row["supported_series"] for row in product_coverage),
            "exclusion_reasons": total_reasons,
        },
        "records": records,
    }
    validate_corpus(artifact, contract=contract)
    return artifact


def validate_corpus(artifact: dict[str, Any], *, contract: dict[str, Any]) -> None:
    """Validate scope, source identities, cutoff ordering, and coverage math."""

    validate_contract(contract)
    if artifact.get("schema_version") != ARTIFACT_VERSION:
        raise ValueError("unsupported corpus artifact")
    if artifact.get("hermes_task") != TASK_ID:
        raise ValueError("wrong corpus task")
    if artifact.get("research_mode") != "retrospective_finalized":
        raise ValueError("artifact research mode drifted")
    if artifact.get("guardrails") != _ARTIFACT_GUARDS:
        raise ValueError("artifact guardrails were weakened")
    if artifact.get("limitations") != contract["revision_and_observability_limitations"]:
        raise ValueError("finalized-vintage limitations drifted")
    bindings = {row["product"]: row for row in contract["source_bindings"]}
    seen: set[tuple[str, str]] = set()
    previous: tuple[str, str] | None = None
    for record in artifact.get("records", []):
        key = (record.get("product"), record.get("trading_date"))
        if key in seen:
            raise ValueError("duplicate product/trading-date record")
        seen.add(key)
        order = (record.get("decision_ts_utc", ""), record.get("product", ""))
        if previous is not None and order < previous:
            raise ValueError("corpus records are not deterministically ordered")
        previous = order
        binding = bindings.get(record.get("product"))
        if binding is None or any(
            record.get(record_field) != binding[binding_field]
            for record_field, binding_field in (
                ("source_id", "source_id"),
                ("source_sha256", "sha256"),
                ("raw_input_set_sha256", "raw_input_set_sha256"),
                ("causal_roll_records_sha256", "causal_roll_records_sha256"),
            )
        ):
            raise ValueError("record source identity drifted")
        cutoff = pd.Timestamp(record["decision_ts_utc"])
        if cutoff.hour != 7 or cutoff.minute != 0 or cutoff.second != 0:
            raise ValueError("record decision cadence drifted")
        if record["trading_date"] != cutoff.date().isoformat():
            raise ValueError("record trading date does not match decision cutoff")
        if pd.Timestamp(record["max_source_timestamp_utc"]) > cutoff:
            raise ValueError("record contains future source data")
        if list(record.get("levels", {})) != list(LEVELS):
            raise ValueError("record levels drifted")
        for level in record["levels"].values():
            if pd.Timestamp(level["last_bar_timestamp_utc"]) > cutoff:
                raise ValueError("derived level contains a future bar")
            if level["aggregated_row_count"] < 21:
                raise ValueError("derived level lacks frozen prior-20 history")
    coverage = artifact.get("coverage", {})
    if (
        coverage.get("first_trading_date")
        != contract["window"]["first_trading_date"]
        or coverage.get("last_trading_date")
        != contract["window"]["last_trading_date"]
    ):
        raise ValueError("coverage window drifted")
    if coverage.get("included_records") != len(artifact.get("records", [])):
        raise ValueError("coverage record count mismatch")
    if coverage.get("requested_decisions") != (
        coverage.get("included_records", 0) + coverage.get("excluded_decisions", 0)
    ):
        raise ValueError("coverage decision funnel mismatch")
    product_counts = {
        product: sum(record["product"] == product for record in artifact["records"])
        for product in bindings
    }
    if [row.get("product") for row in coverage.get("products", [])] != ["au", "ag"]:
        raise ValueError("coverage products drifted")
    for row in coverage.get("products", []):
        if (
            row.get("included_records") != product_counts.get(row.get("product"))
            or row.get("requested_decisions")
            != row.get("included_records", 0) + row.get("excluded_decisions", 0)
            or row.get("requested_series") != row.get("requested_decisions", 0) * len(LEVELS)
            or row.get("supported_series") != row.get("included_records", 0) * len(LEVELS)
        ):
            raise ValueError("product coverage funnel mismatch")
    if (
        coverage.get("requested_series")
        != coverage.get("requested_decisions", 0) * len(LEVELS)
        or coverage.get("supported_series") != len(artifact["records"]) * len(LEVELS)
    ):
        raise ValueError("series coverage funnel mismatch")
    forbidden_record_fields = {
        "iv",
        "regime",
        "option",
        "premium",
        "delta",
        "dte",
        "dd_line",
        "bid",
        "ask",
        "performance",
        "outcome",
        "candidate",
        "execution",
    }
    record_keys = set()
    for record in artifact.get("records", []):
        record_keys.update(_nested_keys(record))
    if record_keys & forbidden_record_fields:
        raise ValueError("corpus records crossed the descriptive underlying boundary")


def _nested_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _nested_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _nested_keys(item)}
    return set()


def load_verified_external_inputs(
    *,
    contract: dict[str, Any],
    provenance: dict[str, Any],
    raw_root: Path,
    quant_repo: Path,
    paired_repo: Path,
) -> tuple[dict[str, pd.DataFrame], dict[str, dict[date, str]]]:
    """Verify consumed provenance identities, then load manifest-listed paths."""

    validate_manifest_boundary(provenance)
    for source in provenance["generator_sources"]:
        repo = quant_repo if source["repository"] == "quant" else paired_repo
        if _sha256_bytes(_git_blob(repo, source["commit"], source["path"])) != source[
            "sha256"
        ]:
            raise ValueError(f"generator blob drift for {source['repository']}")
    bound = {row["source_id"]: row for row in provenance["bound_candidates"]}
    source = next(
        row for row in provenance["generator_sources"] if row["repository"] == "paired-trading"
    )
    module = _load_continuous_module(_git_blob(paired_repo, source["commit"], source["path"]))
    entries: list[dict[str, str]] = []
    for binding in contract["source_bindings"]:
        candidate = bound[binding["source_id"]]
        if any(
            candidate[field] != binding[target]
            for field, target in (
                ("sha256", "sha256"),
                ("raw_input_set_sha256", "raw_input_set_sha256"),
            )
        ) or candidate["causal_roll_schedule"]["records_sha256"] != binding[
            "causal_roll_records_sha256"
        ]:
            raise ValueError(f"provenance binding drift for {binding['source_id']}")
        if _canonical_hash(candidate["raw_inputs"]) != binding["raw_input_set_sha256"]:
            raise ValueError(f"raw input set identity drift for {binding['source_id']}")
        for row in candidate["raw_inputs"]:
            if sha256_file(raw_root / row["path"]) != row["sha256"]:
                raise ValueError(f"raw input hash drift for {row['path']}")
        entries.extend({**row, "product": binding["product"]} for row in candidate["raw_inputs"])
    _pin_discovery(module, raw_root, entries)

    frames: dict[str, pd.DataFrame] = {}
    schedules: dict[str, dict[date, str]] = {}
    for binding in contract["source_bindings"]:
        product = binding["product"]
        candidate = bound[binding["source_id"]]
        path = raw_root / "continuous" / binding["filename"]
        if sha256_file(path) != binding["sha256"]:
            raise ValueError(f"source hash mismatch for {binding['filename']}")
        frame = pd.read_parquet(path)
        frames[product] = frame[list(SOURCE_COLUMNS)].copy()
        schedule = module.build_main_schedule(raw_root, "SHFE", product)
        records = _roll_records(schedule, date.fromisoformat(candidate["window_start_local"]))
        if _canonical_hash(records) != binding["causal_roll_records_sha256"]:
            raise ValueError(f"causal roll schedule drift for {product}")
        schedules[product] = schedule
    return frames, schedules


def build_from_external_sources(
    *,
    contract_path: Path,
    provenance_path: Path,
    raw_root: Path,
    quant_repo: Path,
    paired_repo: Path,
) -> dict[str, Any]:
    contract, predecessor_refs, frames, schedules = _external_build_context(
        contract_path=contract_path,
        provenance_path=provenance_path,
        raw_root=raw_root,
        quant_repo=quant_repo,
        paired_repo=paired_repo,
    )
    return build_corpus(
        contract=contract,
        contract_path=contract_path,
        predecessor_refs=predecessor_refs,
        frames=frames,
        schedules=schedules,
    )


def _external_build_context(
    *,
    contract_path: Path,
    provenance_path: Path,
    raw_root: Path,
    quant_repo: Path,
    paired_repo: Path,
) -> tuple[
    dict[str, Any],
    list[dict[str, str]],
    dict[str, pd.DataFrame],
    dict[str, dict[date, str]],
]:
    contract = load_contract(contract_path)
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    predecessor_refs = []
    for ref in contract["predecessors"]:
        path = Path(ref["path"])
        if sha256_file(path) != ref["sha256"]:
            raise ValueError(f"predecessor hash drift for {ref['name']}")
        predecessor_refs.append(dict(ref))
    if predecessor_refs[1]["path"] != str(provenance_path):
        raise ValueError("unexpected provenance path")
    frames, schedules = load_verified_external_inputs(
        contract=contract,
        provenance=provenance,
        raw_root=raw_root,
        quant_repo=quant_repo,
        paired_repo=paired_repo,
    )
    return contract, predecessor_refs, frames, schedules


def verify_external_corpus(
    artifact: dict[str, Any],
    *,
    contract_path: Path,
    provenance_path: Path,
    raw_root: Path,
    quant_repo: Path,
    paired_repo: Path,
) -> dict[str, Any]:
    contract, predecessor_refs, frames, schedules = _external_build_context(
        contract_path=contract_path,
        provenance_path=provenance_path,
        raw_root=raw_root,
        quant_repo=quant_repo,
        paired_repo=paired_repo,
    )
    rebuilt = build_corpus(
        contract=contract,
        contract_path=contract_path,
        predecessor_refs=predecessor_refs,
        frames=frames,
        schedules=schedules,
    )
    if canonical_json_bytes(rebuilt) != canonical_json_bytes(artifact):
        raise ValueError("corpus is not a deterministic rerun of pinned inputs")
    future_day = date.fromisoformat(contract["window"]["last_trading_date"]) + timedelta(
        days=30
    )
    tainted_frames: dict[str, pd.DataFrame] = {}
    tainted_schedules = {product: dict(schedule) for product, schedule in schedules.items()}
    for product, frame in frames.items():
        future = pd.DataFrame(
            [
                {
                    "datetime": datetime.combine(future_day, time(15, 0)),
                    "open": 1e100,
                    "high": 1e100,
                    "low": -1e100,
                    "close": -1e100,
                    "volume": 1e100,
                    "turnover": 1e100,
                    "open_interest": 1e100,
                }
            ]
        )
        tainted_frames[product] = pd.concat([frame, future], ignore_index=True)
        tainted_schedules[product][future_day] = "999999"
    future_tainted = build_corpus(
        contract=contract,
        contract_path=contract_path,
        predecessor_refs=predecessor_refs,
        frames=tainted_frames,
        schedules=tainted_schedules,
    )
    if canonical_json_bytes(future_tainted) != canonical_json_bytes(rebuilt):
        raise ValueError("corpus changed after future rows or roll records were appended")
    source_text = Path(__file__).read_text(encoding="utf-8")
    forbidden_discovery = (
        "date." + "today(",
        "datetime." + "now(",
        "." + "glob(",
        "." + "rglob(",
        "." + "iterdir(",
    )
    if any(token in source_text for token in forbidden_discovery):
        raise ValueError("corpus implementation contains hidden time or discovery")
    return {
        "ok": True,
        "task": TASK_ID,
        "records": rebuilt["coverage"]["included_records"],
        "supported_series": rebuilt["coverage"]["supported_series"],
        "corpus_payload_sha256": canonical_payload_hash(rebuilt),
        "retrospective_finalized": "enabled_with_explicit_limitations",
        "operational_observability": "blocked",
        "future_row_invariance": True,
        "hidden_current_time_or_discovery": False,
        "advance_m7": False,
    }
