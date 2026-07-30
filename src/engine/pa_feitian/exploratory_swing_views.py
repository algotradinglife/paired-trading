"""Deterministic public-safe exploratory swing views for the M6 universe."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from statistics import median, pstdev
from typing import Any, Iterable

import pyarrow.parquet as pq


CONTRACT_SCHEMA_VERSION = "pa_feitian_m6_exploratory_swing_views_contract_v1"
ARTIFACT_SCHEMA_VERSION = "pa_feitian_m6_exploratory_swing_views_v1"
AUDIT_SCHEMA_VERSION = "pa_feitian_phase1_candidate_interface_audit_v1"
AUDIT_AS_OF_LOCAL_DATE = "2026-07-30"
CONTRACT_PUBLIC_PATH = "docs/research/pa-feitian-m6-exploratory-swing-views-contract-v1.json"
AUDIT_PUBLIC_PATH = (
    "doc/repro/pa-feitian-phase1-data-capability-2026-07-30/candidate_interface_audit_v1.json"
)

_EXPECTED_FAMILIES = [
    "SHFE.au",
    "SHFE.ag",
    "CZCE.TA",
    "CZCE.MA",
    "SHFE.cu",
    "DCE.i",
]
_EXPECTED_CADENCES = ["daily", "hour", "min15", "min5"]
_REGIME_TARGETS = [
    {"label": "quiet", "percentile": 0.2},
    {"label": "typical", "percentile": 0.5},
    {"label": "volatile", "percentile": 0.8},
]
_FORBIDDEN_EXACT_KEYS = {
    "ask",
    "bid",
    "close",
    "delta",
    "entry",
    "exit",
    "fill",
    "future_return",
    "high",
    "low",
    "open",
    "outcome",
    "path",
    "pnl",
    "price",
    "profit",
    "raw_row",
    "recommendation",
    "selected_contract",
    "signal",
    "source_filename",
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
_TOKEN_PREFIX = re.compile(
    r"(?i)(?:\bgithub_pat_|\bgh[opusr]_|\bsk-(?:proj-)?|\bxox[baprs]-|"
    r"\bAKIA[0-9A-Z]{12,}|\bAIza[0-9A-Za-z_-]{20,}|\bya29\.)"
)


class ExploratorySwingViewError(ValueError):
    """Raised when the frozen exploration or public-safety boundary drifts."""


@dataclass(frozen=True)
class _SourceTask:
    family: str
    source_alias: str
    source_path: Path


@dataclass(frozen=True)
class _Window:
    family: str
    source_alias: str
    start_date: str | None
    end_date: str | None
    observation_count: int
    invalid_observations: int
    duplicate_timestamps: int
    future_timestamps: int
    quality_status: str
    metrics: dict[str, float] | None
    trading_dates: tuple[date, ...]
    normalized_ohlc_path: tuple[dict[str, float | int], ...] | None


@dataclass(frozen=True)
class _UnderlyingScan:
    task: _SourceTask
    included_in_inventory: bool
    windows: tuple[_Window, ...]


@dataclass(frozen=True)
class _OptionScan:
    task: _SourceTask
    included_in_inventory: bool
    overlay_records: tuple[dict[str, Any], ...]


def pretty_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def sha256_file(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def load_contract(path: Path) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    validate_contract(contract)
    return contract


def validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        raise ExploratorySwingViewError("unexpected swing-view contract schema")
    if contract.get("issue_number") != 53:
        raise ExploratorySwingViewError("issue binding drifted")
    if contract.get("audit_as_of_local_date") != AUDIT_AS_OF_LOCAL_DATE:
        raise ExploratorySwingViewError("fixed audit date drifted")
    families = [row.get("instrument_family") for row in contract.get("candidate_universe", [])]
    if families != _EXPECTED_FAMILIES:
        raise ExploratorySwingViewError("candidate universe or order drifted")
    runtime = contract.get("runtime_input", {})
    if runtime.get("binding") != "QUANT_DATA_ROOT":
        raise ExploratorySwingViewError("runtime binding drifted")
    if runtime.get("access") != "read_only" or runtime.get("relative_root") != "daily":
        raise ExploratorySwingViewError("read-only daily input boundary drifted")
    if runtime.get("interfaces") != [
        "underlying_contract_ohlc_activity",
        "option_premium_ohlc_activity",
    ]:
        raise ExploratorySwingViewError("daily input interfaces drifted")
    evidence = contract.get("candidate_interface_evidence", {})
    if evidence.get("path") != AUDIT_PUBLIC_PATH:
        raise ExploratorySwingViewError("candidate-interface evidence path drifted")
    if evidence.get("schema_version") != AUDIT_SCHEMA_VERSION:
        raise ExploratorySwingViewError("candidate-interface evidence schema drifted")
    protocol = contract.get("window_protocol", {})
    if protocol.get("completed_observations") != 20:
        raise ExploratorySwingViewError("window length drifted")
    if protocol.get("stride_observations") != 20:
        raise ExploratorySwingViewError("window stride drifted")
    if protocol.get("representative_requires_daily_option_coverage") is not True:
        raise ExploratorySwingViewError("representative option-coverage boundary drifted")
    if protocol.get("post_audit_rows") != (
        "excluded_before_series_inventory_and_window_partitioning"
    ):
        raise ExploratorySwingViewError("post-audit row boundary drifted")
    if protocol.get("future_only_files") != "excluded_from_source_inventory":
        raise ExploratorySwingViewError("future-only inventory boundary drifted")
    if protocol.get("regime_percentile_targets") != _REGIME_TARGETS:
        raise ExploratorySwingViewError("regime targets drifted")
    if protocol.get("selection_scope") != "within_family_only":
        raise ExploratorySwingViewError("family-local selection boundary drifted")
    if protocol.get("selection_uses_strategy_outcomes_or_profitability") is not False:
        raise ExploratorySwingViewError("selection boundary was weakened")
    quality = contract.get("quality_protocol", {})
    if quality.get("fresh_max_calendar_lag_days") != 7:
        raise ExploratorySwingViewError("freshness threshold drifted")
    option_overlay = contract.get("option_premium_overlay", {})
    if option_overlay.get("selection_influence") is not False:
        raise ExploratorySwingViewError("option overlay influenced selection")
    if option_overlay.get("required_distinct_dates_for_comparable_path") != 20:
        raise ExploratorySwingViewError("option overlay coverage threshold drifted")
    if option_overlay.get("duplicate_date_series_in_path_distribution") is not False:
        raise ExploratorySwingViewError("duplicate option paths are not excluded")
    if option_overlay.get("incomplete_fragment_series_in_path_distribution") is not False:
        raise ExploratorySwingViewError("fragmented option paths are not excluded")
    if option_overlay.get("call_put_or_contract_selection") is not False:
        raise ExploratorySwingViewError("option overlay selection boundary drifted")
    guardrails = contract.get("guardrails", {})
    required_false = (
        "source_refresh",
        "implicit_current_time",
        "filesystem_timestamps_as_freshness",
        "strategy_outcome_access",
        "performance_calculation",
        "profitability_ranking",
        "family_ranking",
        "cross_contract_stitching",
        "cadence_resampling_or_substitution",
        "source_refresh_or_mutation",
        "bid_ask_synthesis",
        "delta_synthesis",
        "preregistered_evidence_claim",
        "live_or_shadow_readiness_claim",
        "execution",
    )
    if any(guardrails.get(key) is not False for key in required_false):
        raise ExploratorySwingViewError("contract guardrails were weakened")
    required_true = ("explicit_runtime_root_required", "external_access_read_only")
    if any(guardrails.get(key) is not True for key in required_true):
        raise ExploratorySwingViewError("contract input guardrails were weakened")
    output = contract.get("output", {})
    if (
        output.get("atomic_same_directory_replace") is not True
        or output.get("output_inside_data_root") is not False
        or output.get("output_may_overwrite_contract_or_candidate_audit") is not False
    ):
        raise ExploratorySwingViewError("output write boundary drifted")


def _validate_candidate_audit(audit: dict[str, Any]) -> None:
    if audit.get("schema_version") != AUDIT_SCHEMA_VERSION:
        raise ExploratorySwingViewError("unexpected candidate-interface audit schema")
    if audit.get("issue_number") != 43:
        raise ExploratorySwingViewError("candidate-interface issue binding drifted")
    if audit.get("audit_as_of_local_date") != AUDIT_AS_OF_LOCAL_DATE:
        raise ExploratorySwingViewError("candidate-interface audit date drifted")
    if audit.get("source", {}).get("access") != "read_only":
        raise ExploratorySwingViewError("candidate-interface source is not read-only")
    if audit.get("source", {}).get("source_refresh_performed") is not False:
        raise ExploratorySwingViewError("candidate-interface source was refreshed")
    families = [row.get("instrument_family") for row in audit.get("decision_surface", [])]
    if families != _EXPECTED_FAMILIES:
        raise ExploratorySwingViewError("candidate-interface universe drifted")
    for row in audit["decision_surface"]:
        if [entry.get("cadence") for entry in row.get("cadences", [])] != (_EXPECTED_CADENCES):
            raise ExploratorySwingViewError("candidate-interface cadences drifted")


def _source_alias(name: str) -> str:
    return _sha256_text(f"m6-exploratory-swing-source-v1\0{name.lower()}")


def _discover_daily_tasks(
    data_root: Path, candidates: Iterable[dict[str, Any]]
) -> tuple[list[_SourceTask], list[_SourceTask]]:
    daily_root = data_root / "daily"
    if not daily_root.is_dir():
        raise ExploratorySwingViewError("caller-provided data root has no daily interface")
    candidate_rows = list(candidates)
    underlying_tasks: list[_SourceTask] = []
    option_tasks: list[_SourceTask] = []
    for source_path in daily_root.iterdir():
        if source_path.is_symlink() or not source_path.is_file():
            continue
        name = source_path.name
        if not name.lower().endswith(".parquet"):
            continue
        stem = name[: -len(".parquet")]
        for candidate in candidate_rows:
            prefix = f"{candidate['exchange']}.{candidate['product']}"
            if not stem.lower().startswith(prefix.lower()):
                continue
            suffix = stem[len(prefix) :]
            task = _SourceTask(
                family=candidate["instrument_family"],
                source_alias=_source_alias(name),
                source_path=source_path,
            )
            if re.fullmatch(
                r"[0-9]{3,4}(?:[CP][0-9]+(?:\.[0-9]+)?|"
                r"-[CP]-[0-9]+(?:\.[0-9]+)?)",
                suffix,
                flags=re.IGNORECASE,
            ):
                option_tasks.append(task)
            elif re.fullmatch(r"[0-9]{3,4}", suffix):
                underlying_tasks.append(task)
            break
    underlying = sorted(underlying_tasks, key=lambda item: (item.family, item.source_alias))
    options = sorted(option_tasks, key=lambda item: (item.family, item.source_alias))
    underlying_counts = Counter(task.family for task in underlying)
    option_counts = Counter(task.family for task in options)
    missing_underlying = [family for family in _EXPECTED_FAMILIES if not underlying_counts[family]]
    if missing_underlying:
        raise ExploratorySwingViewError(
            f"no daily underlying inputs for candidate families: {missing_underlying}"
        )
    missing_options = [family for family in _EXPECTED_FAMILIES if not option_counts[family]]
    if missing_options:
        raise ExploratorySwingViewError(
            f"no daily option inputs for candidate families: {missing_options}"
        )
    return underlying, options


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None


def _as_finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _round(value: float) -> float:
    return round(value, 6)


def _window_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    first = rows[0]
    closes = [row["close"] for row in rows]
    log_changes = [math.log(closes[index] / closes[index - 1]) for index in range(1, len(closes))]
    realized = pstdev(log_changes) * math.sqrt(252) * 100 if log_changes else 0.0
    activity_observed = [
        any(
            value is not None and value != 0
            for value in (
                row.get("volume"),
                row.get("turnover"),
                row.get("open_interest"),
            )
        )
        for row in rows
    ]
    return {
        "net_change_pct": _round((closes[-1] / first["open"] - 1) * 100),
        "total_excursion_pct": _round(
            (max(row["high"] for row in rows) / min(row["low"] for row in rows) - 1) * 100
        ),
        "realized_variability_annualized_pct": _round(realized),
        "median_bar_range_pct": _round(
            median((row["high"] - row["low"]) / row["close"] * 100 for row in rows)
        ),
        "up_bar_share": _round(sum(row["close"] > row["open"] for row in rows) / len(rows)),
        "nonzero_activity_share": _round(sum(activity_observed) / len(activity_observed)),
    }


def _normalized_ohlc_path(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, float | int], ...]:
    base = rows[0]["open"]
    return tuple(
        {
            "bar_index": index,
            "open_index": _round(row["open"] / base * 100),
            "high_index": _round(row["high"] / base * 100),
            "low_index": _round(row["low"] / base * 100),
            "close_index": _round(row["close"] / base * 100),
        }
        for index, row in enumerate(rows)
    )


def _scan_task(
    task: _SourceTask, *, window_size: int, stride: int, audit_date: date
) -> _UnderlyingScan:
    parquet = pq.ParquetFile(task.source_path)
    required = ["datetime", "open", "high", "low", "close"]
    missing = [field for field in required if field not in parquet.schema_arrow.names]
    if missing:
        raise ExploratorySwingViewError(
            f"daily underlying schema lacks required fields for {task.family}"
        )
    activity = [
        field
        for field in ("volume", "turnover", "open_interest")
        if field in parquet.schema_arrow.names
    ]
    table = pq.read_table(task.source_path, columns=[*required, *activity])
    rows: list[dict[str, Any]] = []
    for index in range(table.num_rows):
        row = {
            field: table[field][index].as_py() if field in table.column_names else None
            for field in [*required, "volume", "turnover", "open_interest"]
        }
        row["trading_date"] = _as_date(row.pop("datetime"))
        for field in ("open", "high", "low", "close", *activity):
            row[field] = _as_finite(row[field])
        rows.append(row)
    included_in_inventory = any(
        row["trading_date"] is not None and row["trading_date"] <= audit_date for row in rows
    )
    rows = [row for row in rows if row["trading_date"] is None or row["trading_date"] <= audit_date]
    rows.sort(
        key=lambda row: (
            row["trading_date"] is None,
            row["trading_date"] or date.max,
        )
    )

    windows: list[_Window] = []
    for start in range(0, len(rows) - window_size + 1, stride):
        chunk = rows[start : start + window_size]
        timestamps = [row["trading_date"] for row in chunk]
        concrete_dates = [value for value in timestamps if value is not None]
        duplicate_count = len(concrete_dates) - len(set(concrete_dates))
        future_count = 0
        valid_rows: list[dict[str, Any]] = []
        invalid_count = 0
        for row in chunk:
            values = [row[field] for field in ("open", "high", "low", "close")]
            valid = row["trading_date"] is not None and all(
                value is not None and value > 0 for value in values
            )
            if valid:
                open_, high, low, close = values
                valid = (
                    high >= low
                    and high >= open_
                    and high >= close
                    and low <= open_
                    and low <= close
                )
            if valid:
                valid_rows.append(row)
            else:
                invalid_count += 1
        if duplicate_count or future_count or invalid_count >= 5:
            status = "invalid"
        elif invalid_count:
            status = "messy"
        else:
            status = "clean"
        metrics = _window_metrics(valid_rows) if status == "clean" else None
        normalized_path = _normalized_ohlc_path(valid_rows) if status == "clean" else None
        windows.append(
            _Window(
                family=task.family,
                source_alias=task.source_alias,
                start_date=min(concrete_dates).isoformat() if concrete_dates else None,
                end_date=max(concrete_dates).isoformat() if concrete_dates else None,
                observation_count=len(chunk),
                invalid_observations=invalid_count,
                duplicate_timestamps=duplicate_count,
                future_timestamps=future_count,
                quality_status=status,
                metrics=metrics,
                trading_dates=tuple(concrete_dates),
                normalized_ohlc_path=normalized_path,
            )
        )
    return _UnderlyingScan(
        task=task,
        included_in_inventory=included_in_inventory,
        windows=tuple(windows),
    )


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        raise ExploratorySwingViewError("cannot calculate an empty percentile")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = percentile * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _public_window(window: _Window) -> dict[str, Any]:
    return {
        "instrument_family": window.family,
        "start_date": window.start_date,
        "end_date": window.end_date,
        "observation_count": window.observation_count,
        "quality_status": window.quality_status,
        "quality_findings": {
            "invalid_observations": window.invalid_observations,
            "duplicate_timestamps": window.duplicate_timestamps,
            "future_timestamps": window.future_timestamps,
        },
    }


def _interface_summary(audit: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for family in audit["decision_surface"]:
        cadences = []
        for cadence in family["cadences"]:
            interfaces = {}
            for interface in ("underlying", "option_premium"):
                source = cadence["interfaces"][interface]
                coverage = source["coverage"]
                freshness = source["freshness"]
                interfaces[interface] = {
                    "available": source["scanned_files"] > 0,
                    "file_count": source["scanned_files"],
                    "row_count": source["rows"],
                    "coverage": {
                        "minimum_observation_timestamp": coverage["minimum_observation_timestamp"],
                        "maximum_observation_timestamp": coverage["maximum_observation_timestamp"],
                    },
                    "freshness": {
                        "latest_observation": freshness["latest_observation"],
                        "calendar_lag_days": freshness["calendar_lag_days"],
                        "status": freshness["status"],
                    },
                    "ohlc_quality": {
                        "rows_checked": source["ohlc_quality"]["rows_checked"],
                        "null_rows": source["ohlc_quality"]["null_rows"],
                        "violation_rows": source["ohlc_quality"]["violation_rows"],
                    },
                    "activity": {
                        "definition": source["liquidity_proxy"]["name"],
                        "nonzero_observation_count": source["liquidity_proxy"][
                            "rows_with_any_nonzero_activity"
                        ],
                        "observation_count": source["liquidity_proxy"]["all_rows"],
                        "share": source["liquidity_proxy"]["rate"],
                        "selection_threshold": None,
                    },
                }
            cadences.append({"cadence": cadence["cadence"], "interfaces": interfaces})
        result.append(
            {
                "instrument_family": family["instrument_family"],
                "role": family["role"],
                "cadences": cadences,
            }
        )
    return result


def _daily_option_bounds(audit: dict[str, Any]) -> dict[str, tuple[date, date]]:
    result: dict[str, tuple[date, date]] = {}
    for family in audit["decision_surface"]:
        daily = next(row for row in family["cadences"] if row["cadence"] == "daily")
        coverage = daily["interfaces"]["option_premium"]["coverage"]
        minimum = coverage["minimum_observation_timestamp"]
        maximum = coverage["maximum_observation_timestamp"]
        if minimum is None or maximum is None:
            raise ExploratorySwingViewError(
                f"daily option coverage is unbound for {family['instrument_family']}"
            )
        result[family["instrument_family"]] = (
            date.fromisoformat(minimum[:10]),
            date.fromisoformat(maximum[:10]),
        )
    return result


def _eligible_clean_windows(
    windows: list[_Window], option_bounds: tuple[date, date]
) -> list[_Window]:
    option_start, option_end = option_bounds
    return [
        window
        for window in windows
        if window.quality_status == "clean"
        and window.metrics is not None
        and window.start_date is not None
        and window.end_date is not None
        and date.fromisoformat(window.start_date) >= option_start
        and date.fromisoformat(window.end_date) <= option_end
    ]


def _excursion_percentiles(windows: list[_Window]) -> dict[str, float]:
    values = [
        window.metrics["total_excursion_pct"] for window in windows if window.metrics is not None
    ]
    if not values:
        raise ExploratorySwingViewError("clean window population is empty")
    return {
        "p20": _round(_percentile(values, 0.2)),
        "p50": _round(_percentile(values, 0.5)),
        "p80": _round(_percentile(values, 0.8)),
    }


def _distribution_summary(
    family: str,
    role: str,
    windows: list[_Window],
    as_of: date,
    option_bounds: tuple[date, date],
) -> dict[str, Any]:
    counts = Counter(window.quality_status for window in windows)
    clean = [window for window in windows if window.quality_status == "clean"]
    eligible = _eligible_clean_windows(windows, option_bounds)
    latest = max(
        (date.fromisoformat(window.end_date) for window in windows if window.end_date is not None),
        default=None,
    )
    return {
        "instrument_family": family,
        "role": role,
        "anonymous_underlying_series_count": len({window.source_alias for window in windows}),
        "all_complete_windows": {
            "window_count": len(windows),
            "quality_counts": {status: counts[status] for status in ("clean", "messy", "invalid")},
            "clean_window_total_excursion_pct": _excursion_percentiles(clean),
        },
        "representative_eligible_clean_windows": {
            "definition": (
                "clean complete windows wholly inside audited daily option-premium coverage"
            ),
            "window_count": len(eligible),
            "share_of_all_clean_windows": _round(len(eligible) / len(clean)),
            "daily_option_coverage": {
                "minimum_observation_date": option_bounds[0].isoformat(),
                "maximum_observation_date": option_bounds[1].isoformat(),
            },
            "total_excursion_pct": _excursion_percentiles(eligible),
        },
        "latest_window_observation_date": latest.isoformat() if latest else None,
        "latest_window_calendar_lag_days": (as_of - latest).days if latest else None,
        "freshness_status": (
            "fresh" if latest is not None and (as_of - latest).days <= 7 else "stale"
        ),
    }


def _representatives(
    family: str,
    windows: list[_Window],
    *,
    as_of: date,
    option_bounds: tuple[date, date],
) -> list[tuple[dict[str, Any], _Window]]:
    clean = _eligible_clean_windows(windows, option_bounds)
    if len(clean) < len(_REGIME_TARGETS):
        raise ExploratorySwingViewError(
            f"insufficient clean windows for representative slices: {family}"
        )
    values = [window.metrics["total_excursion_pct"] for window in clean]
    selected: list[_Window] = []
    result: list[tuple[dict[str, Any], _Window]] = []
    for target in _REGIME_TARGETS:
        target_value = _percentile(values, target["percentile"])
        available = [window for window in clean if window not in selected]
        chosen = min(
            available,
            key=lambda window: (
                abs(window.metrics["total_excursion_pct"] - target_value),
                window.start_date or "",
                window.end_date or "",
                window.source_alias,
            ),
        )
        selected.append(chosen)
        end = date.fromisoformat(chosen.end_date) if chosen.end_date else None
        lag = (as_of - end).days if end else None
        result.append(
            (
                {
                    "instrument_family": family,
                    "regime_slice": target["label"],
                    "within_family_percentile_target": target["percentile"],
                    "start_date": chosen.start_date,
                    "end_date": chosen.end_date,
                    "observation_count": chosen.observation_count,
                    "calendar_span_days": (
                        date.fromisoformat(chosen.end_date) - date.fromisoformat(chosen.start_date)
                    ).days,
                    "descriptive_metrics": chosen.metrics,
                    "normalized_ohlc_path": list(chosen.normalized_ohlc_path or ()),
                    "normalized_path_encoding": {
                        "base": "first completed bar open equals 100",
                        "raw_prices_published": False,
                        "bar_count": chosen.observation_count,
                    },
                    "input_quality": {
                        "status": chosen.quality_status,
                        "invalid_observations": chosen.invalid_observations,
                        "duplicate_timestamps": chosen.duplicate_timestamps,
                    },
                    "freshness": {
                        "calendar_lag_days": lag,
                        "status": "fresh" if lag is not None and lag <= 7 else "stale",
                    },
                },
                chosen,
            )
        )
    return result


def _scan_option_task(
    task: _SourceTask,
    *,
    representative_windows: dict[str, _Window],
    audit_date: date,
) -> _OptionScan:
    parquet = pq.ParquetFile(task.source_path)
    required = ["datetime", "open", "high", "low", "close"]
    missing = [field for field in required if field not in parquet.schema_arrow.names]
    if missing:
        raise ExploratorySwingViewError(
            f"daily option schema lacks required fields for {task.family}"
        )
    activity = [
        field
        for field in ("volume", "turnover", "open_interest")
        if field in parquet.schema_arrow.names
    ]
    table = pq.read_table(task.source_path, columns=[*required, *activity])
    rows: list[dict[str, Any]] = []
    for index in range(table.num_rows):
        row = {
            field: table[field][index].as_py() if field in table.column_names else None
            for field in [*required, "volume", "turnover", "open_interest"]
        }
        row["trading_date"] = _as_date(row.pop("datetime"))
        for field in ("open", "high", "low", "close", *activity):
            row[field] = _as_finite(row[field])
        rows.append(row)
    included_in_inventory = any(
        row["trading_date"] is not None and row["trading_date"] <= audit_date for row in rows
    )
    rows = [row for row in rows if row["trading_date"] is None or row["trading_date"] <= audit_date]
    rows.sort(
        key=lambda row: (
            row["trading_date"] is None,
            row["trading_date"] or date.max,
        )
    )

    result: list[dict[str, Any]] = []
    for regime_slice, representative_window in representative_windows.items():
        required_dates = set(representative_window.trading_dates)
        selected = [
            row
            for row in rows
            if row["trading_date"] is not None and row["trading_date"] in required_dates
        ]
        if not selected:
            continue
        coherent: list[dict[str, Any]] = []
        nonpositive_or_missing = 0
        ohlc_incoherent = 0
        activity_count = 0
        for row in selected:
            values = [row[field] for field in ("open", "high", "low", "close")]
            positive = all(value is not None and value > 0 for value in values)
            coherent_ohlc = False
            if positive:
                open_, high, low, close = values
                coherent_ohlc = (
                    high >= low
                    and high >= open_
                    and high >= close
                    and low <= open_
                    and low <= close
                )
            if not positive:
                nonpositive_or_missing += 1
            elif not coherent_ohlc:
                ohlc_incoherent += 1
            else:
                coherent.append(row)
            if any(
                row.get(field) is not None and row.get(field) != 0
                for field in ("volume", "turnover", "open_interest")
            ):
                activity_count += 1
        concrete_dates = [
            row["trading_date"] for row in selected if row["trading_date"] is not None
        ]
        duplicate_count = len(concrete_dates) - len(set(concrete_dates))
        distinct_date_count = len(set(concrete_dates))
        complete_comparable_path = (
            duplicate_count == 0
            and distinct_date_count == representative_window.observation_count
            and set(concrete_dates) == required_dates
            and len(coherent) == representative_window.observation_count
        )
        record: dict[str, Any] = {
            "instrument_family": task.family,
            "regime_slice": regime_slice,
            "observation_count": len(selected),
            "coherent_observation_count": len(coherent),
            "nonpositive_or_missing_observation_count": nonpositive_or_missing,
            "ohlc_incoherent_observation_count": ohlc_incoherent,
            "duplicate_date_count": duplicate_count,
            "distinct_date_count": distinct_date_count,
            "nonzero_activity_observation_count": activity_count,
            "complete_comparable_path": complete_comparable_path,
        }
        if complete_comparable_path:
            record["close_path_change_pct"] = (
                coherent[-1]["close"] / coherent[0]["close"] - 1
            ) * 100
            record["total_excursion_pct"] = (
                max(row["high"] for row in coherent) / min(row["low"] for row in coherent) - 1
            ) * 100
        result.append(record)
    return _OptionScan(
        task=task,
        included_in_inventory=included_in_inventory,
        overlay_records=tuple(result),
    )


def _complete_path_metrics(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    if not records:
        return {
            "status": "unavailable",
            "required_distinct_date_count": 20,
            "anonymous_series_count": 0,
            "reason": (
                "no anonymous option series has one coherent positive "
                "observation on each of the 20 required dates"
            ),
        }
    path_changes = [record["close_path_change_pct"] for record in records]
    excursions = [record["total_excursion_pct"] for record in records]
    return {
        "status": "available",
        "required_distinct_date_count": 20,
        "anonymous_series_count": len(records),
        "close_path_change_pct_distribution": {
            "p20": _round(_percentile(path_changes, 0.2)),
            "p50": _round(_percentile(path_changes, 0.5)),
            "p80": _round(_percentile(path_changes, 0.8)),
        },
        "total_excursion_pct_distribution": {
            "p20": _round(_percentile(excursions, 0.2)),
            "p50": _round(_percentile(excursions, 0.5)),
            "p80": _round(_percentile(excursions, 0.8)),
        },
    }


def _option_premium_overlays(
    *,
    option_tasks: list[_SourceTask],
    representative_windows: dict[tuple[str, str], _Window],
    workers: int,
    audit_date: date,
) -> tuple[
    dict[tuple[str, str], dict[str, Any]],
    list[_SourceTask],
]:
    windows_by_family = {
        family: {
            target["label"]: representative_windows[(family, target["label"])]
            for target in _REGIME_TARGETS
        }
        for family in _EXPECTED_FAMILIES
    }
    with ThreadPoolExecutor(max_workers=workers) as executor:
        scanned = list(
            executor.map(
                lambda task: _scan_option_task(
                    task,
                    representative_windows=windows_by_family[task.family],
                    audit_date=audit_date,
                ),
                option_tasks,
            )
        )
    included_tasks = [result.task for result in scanned if result.included_in_inventory]
    records = [record for result in scanned for record in result.overlay_records]
    overlays: dict[tuple[str, str], dict[str, Any]] = {}
    for family in _EXPECTED_FAMILIES:
        for target in _REGIME_TARGETS:
            key = (family, target["label"])
            selected = [
                record
                for record in records
                if (
                    record["instrument_family"],
                    record["regime_slice"],
                )
                == key
            ]
            observations = sum(record["observation_count"] for record in selected)
            coherent = sum(record["coherent_observation_count"] for record in selected)
            nonpositive_or_missing = sum(
                record["nonpositive_or_missing_observation_count"] for record in selected
            )
            ohlc_incoherent = sum(
                record["ohlc_incoherent_observation_count"] for record in selected
            )
            duplicates = sum(record["duplicate_date_count"] for record in selected)
            invalid = nonpositive_or_missing + ohlc_incoherent + duplicates
            activity = sum(record["nonzero_activity_observation_count"] for record in selected)
            path_records = [record for record in selected if record["complete_comparable_path"]]
            if not observations:
                raise ExploratorySwingViewError(
                    "representative window has no daily option-premium overlay: "
                    f"{family} {target['label']}"
                )
            violation_share = invalid / observations
            if invalid == 0:
                quality_status = "clean"
            elif violation_share <= 0.2:
                quality_status = "messy"
            else:
                quality_status = "invalid"
            coverage_lengths = [float(record["distinct_date_count"]) for record in selected]
            overlays[key] = {
                "anonymous_series_with_observations": len(selected),
                "observation_count": observations,
                "coherent_observation_count": coherent,
                "input_quality_violation_observation_count": invalid,
                "input_quality_violation_share": _round(violation_share),
                "nonpositive_or_missing_observation_count": nonpositive_or_missing,
                "ohlc_incoherent_observation_count": ohlc_incoherent,
                "duplicate_date_observation_count": duplicates,
                "quality_status": quality_status,
                "nonzero_activity_observation_count": activity,
                "nonzero_activity_share": _round(activity / observations),
                "distinct_date_coverage": {
                    "required_for_comparable_path": 20,
                    "distribution": {
                        "p20": _round(_percentile(coverage_lengths, 0.2)),
                        "p50": _round(_percentile(coverage_lengths, 0.5)),
                        "p80": _round(_percentile(coverage_lengths, 0.8)),
                    },
                    "two_point_fragment_series_count": sum(
                        record["distinct_date_count"] == 2 for record in selected
                    ),
                    "incomplete_fragment_series_count": sum(
                        record["distinct_date_count"] < 20 for record in selected
                    ),
                    "duplicate_date_series_count": sum(
                        record["duplicate_date_count"] > 0 for record in selected
                    ),
                },
                "comparable_complete_path_metrics": _complete_path_metrics(path_records),
                "selection_influence": False,
                "interpretation": (
                    "anonymous descriptive premium paths within the frozen "
                    "underlying date window; not outcomes or profitability"
                ),
            }
    return overlays, included_tasks


def _quality_examples(windows: list[_Window], *, as_of: date) -> dict[str, Any]:
    def earliest(status: str) -> _Window:
        matches = [window for window in windows if window.quality_status == status]
        if not matches:
            raise ExploratorySwingViewError(f"required {status} quality example is absent")
        return min(
            matches,
            key=lambda window: (
                _EXPECTED_FAMILIES.index(window.family),
                window.start_date or "",
                window.end_date or "",
                window.source_alias,
            ),
        )

    clean = earliest("clean")
    messy = earliest("messy")
    invalid = earliest("invalid")
    stale_candidates = [
        window
        for window in windows
        if window.quality_status == "clean"
        and window.end_date is not None
        and (as_of - date.fromisoformat(window.end_date)).days > 7
    ]
    if not stale_candidates:
        raise ExploratorySwingViewError("required stale quality example is absent")
    stale = max(
        stale_candidates,
        key=lambda window: (
            window.end_date or "",
            -_EXPECTED_FAMILIES.index(window.family),
            window.source_alias,
        ),
    )
    return {
        "clean": {
            **_public_window(clean),
            "interpretation": "complete coherent input suitable for descriptive viewing",
        },
        "messy": {
            **_public_window(messy),
            "interpretation": "limited incoherent observations; exclude from representative metrics",
        },
        "invalid": {
            **_public_window(invalid),
            "interpretation": "quality threshold failed; do not calculate or inspect swing metrics",
        },
        "stale": {
            **_public_window(stale),
            "freshness": {
                "calendar_lag_days": (as_of - date.fromisoformat(stale.end_date)).days,
                "status": "stale",
            },
            "interpretation": "coherent historical input whose latest observation exceeds the seven-day freshness threshold",
        },
    }


def _assert_public_safe(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = set(value) & _FORBIDDEN_EXACT_KEYS
        if forbidden:
            raise ExploratorySwingViewError(
                f"public artifact contains forbidden fields: {sorted(forbidden)}"
            )
        for nested in value.values():
            _assert_public_safe(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_public_safe(nested)
    elif isinstance(value, str):
        lowered = value.lower()
        if any(token.lower() in lowered for token in _FORBIDDEN_TEXT):
            raise ExploratorySwingViewError("public artifact contains local source text")
        if _RAW_CONTRACT_ID.search(value):
            raise ExploratorySwingViewError("public artifact contains a raw contract identifier")
        if _TOKEN_PREFIX.search(value):
            raise ExploratorySwingViewError("public artifact contains a token prefix")


def build_exploratory_swing_views(
    *,
    contract: dict[str, Any],
    contract_path: Path,
    candidate_audit: dict[str, Any],
    candidate_audit_path: Path,
    data_root: Path,
    workers: int = 8,
) -> dict[str, Any]:
    validate_contract(contract)
    _validate_candidate_audit(candidate_audit)
    if workers <= 0:
        raise ExploratorySwingViewError("worker count must be positive")
    underlying_tasks, option_tasks = _discover_daily_tasks(
        data_root, contract["candidate_universe"]
    )
    as_of = date.fromisoformat(contract["audit_as_of_local_date"])
    window_size = contract["window_protocol"]["completed_observations"]
    stride = contract["window_protocol"]["stride_observations"]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        scanned = list(
            executor.map(
                lambda task: _scan_task(
                    task,
                    window_size=window_size,
                    stride=stride,
                    audit_date=as_of,
                ),
                underlying_tasks,
            )
        )
    included_underlying_tasks = [result.task for result in scanned if result.included_in_inventory]
    windows = [
        window for result in scanned if result.included_in_inventory for window in result.windows
    ]
    roles = {row["instrument_family"]: row["role"] for row in contract["candidate_universe"]}
    option_bounds = _daily_option_bounds(candidate_audit)
    by_family = {
        family: [window for window in windows if window.family == family]
        for family in _EXPECTED_FAMILIES
    }
    summaries = [
        _distribution_summary(
            family,
            roles[family],
            by_family[family],
            as_of,
            option_bounds[family],
        )
        for family in _EXPECTED_FAMILIES
    ]
    representative_pairs = [
        pair
        for family in _EXPECTED_FAMILIES
        for pair in _representatives(
            family,
            by_family[family],
            as_of=as_of,
            option_bounds=option_bounds[family],
        )
    ]
    representatives = [view for view, _ in representative_pairs]
    representative_windows = {
        (view["instrument_family"], view["regime_slice"]): window
        for view, window in representative_pairs
    }
    option_overlays, included_option_tasks = _option_premium_overlays(
        option_tasks=option_tasks,
        representative_windows=representative_windows,
        workers=workers,
        audit_date=as_of,
    )
    for view in representatives:
        view["option_premium_overlay"] = option_overlays[
            (view["instrument_family"], view["regime_slice"])
        ]
    artifact = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "issue_number": 53,
        "audit_as_of_local_date": AUDIT_AS_OF_LOCAL_DATE,
        "study_label": "exploratory_historical_data_view_only",
        "contract": {
            "public_location": CONTRACT_PUBLIC_PATH,
            "sha256": sha256_file(contract_path),
        },
        "candidate_interface_evidence": {
            "public_location": AUDIT_PUBLIC_PATH,
            "sha256": sha256_file(candidate_audit_path),
            "source_inventory_sha256": candidate_audit["source"]["inventory_sha256"],
        },
        "source": {
            "runtime_binding": "QUANT_DATA_ROOT",
            "public_alias": "external://quant-data/daily/",
            "access": "read_only",
            "source_refresh_performed": False,
            "filesystem_timestamps_used_as_freshness": False,
            "post_audit_rows_excluded_before_partitioning": True,
            "future_only_files_excluded_from_inventory": True,
            "daily_underlying_files_in_frozen_inventory": len(included_underlying_tasks),
            "daily_option_files_in_frozen_inventory": len(included_option_tasks),
            "daily_underlying_inventory_sha256": "sha256:"
            + _sha256_text(
                json.dumps(
                    [
                        {"family": task.family, "source_alias": task.source_alias}
                        for task in included_underlying_tasks
                    ],
                    sort_keys=True,
                    separators=(",", ":"),
                )
            ),
            "daily_option_inventory_sha256": "sha256:"
            + _sha256_text(
                json.dumps(
                    [
                        {"family": task.family, "source_alias": task.source_alias}
                        for task in included_option_tasks
                    ],
                    sort_keys=True,
                    separators=(",", ":"),
                )
            ),
        },
        "interface_availability": _interface_summary(candidate_audit),
        "underlying_window_method": {
            "completed_observations": window_size,
            "stride_observations": stride,
            "cross_contract_stitching": False,
            "cadence_resampling": False,
            "daily_option_coverage_required": True,
            "representative_selection": (
                "nearest clean within-family total-excursion percentile; "
                "no strategy outcomes or profitability"
            ),
            "regime_percentile_targets": _REGIME_TARGETS,
        },
        "family_window_summaries": summaries,
        "representative_swing_views": representatives,
        "quality_examples": _quality_examples(windows, as_of=as_of),
        "strategy_handoff": {
            "suggested_inspection_groups": [
                {
                    "role": "continuity_candidate",
                    "families": ["SHFE.au", "SHFE.ag"],
                    "use": "inspect quiet, typical, and volatile underlying windows alongside the daily option-premium OHLC caveat",
                },
                {
                    "role": "mainstream_candidate",
                    "families": ["CZCE.TA", "CZCE.MA"],
                    "use": "inspect all three regime slices and retain the underlying-input quality flags",
                },
                {
                    "role": "control",
                    "families": ["SHFE.cu", "DCE.i"],
                    "use": "inspect as non-CZCE contrasts; preserve the option-quality and activity caveats",
                },
            ],
            "family_or_contract_profitability_ranking": False,
            "all_six_families_retained": True,
        },
        "evidence_separation": {
            "exploration": "descriptive historical data views only",
            "preregistered_evidence": "not produced",
            "future_live_or_shadow": "not authorized or assessed",
            "p1_exp_001_or_p1_exp_002_outcomes": "not accessed",
            "issue_51_unblocked": False,
        },
        "public_safety": {
            "local_paths": False,
            "local_usernames": False,
            "source_filenames": False,
            "raw_contract_identifiers": False,
            "raw_rows": False,
            "raw_ohlc_values": False,
            "credentials": False,
            "strategy_outcomes": False,
            "profitability_metrics": False,
            "bid_ask_or_delta_synthesis": False,
        },
        "limitations": [
            "The representative windows are descriptive anonymous-contract views, not continuous-series or executable-contract evidence.",
            "Current-vintage historical files do not prove the bytes observable at any historical decision time.",
            "Historical presence and activity do not establish current freshness, causal IV, bid/ask, delta, or live/shadow readiness.",
            "Within-family volatility slices are not signals, forecasts, performance results, or family rankings.",
        ],
    }
    validate_artifact(artifact, contract=contract, candidate_audit=candidate_audit)
    return artifact


def validate_artifact(
    artifact: dict[str, Any],
    *,
    contract: dict[str, Any],
    candidate_audit: dict[str, Any],
) -> None:
    validate_contract(contract)
    _validate_candidate_audit(candidate_audit)
    if artifact.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        raise ExploratorySwingViewError("unexpected swing-view artifact schema")
    if artifact.get("issue_number") != 53:
        raise ExploratorySwingViewError("artifact issue binding drifted")
    if artifact.get("study_label") != "exploratory_historical_data_view_only":
        raise ExploratorySwingViewError("artifact study label drifted")
    if artifact.get("contract", {}).get("public_location") != CONTRACT_PUBLIC_PATH:
        raise ExploratorySwingViewError("artifact contract location drifted")
    evidence = artifact.get("candidate_interface_evidence", {})
    if evidence.get("public_location") != AUDIT_PUBLIC_PATH:
        raise ExploratorySwingViewError("artifact evidence location drifted")
    if evidence.get("source_inventory_sha256") != candidate_audit["source"].get("inventory_sha256"):
        raise ExploratorySwingViewError("source inventory binding drifted")
    families = [row.get("instrument_family") for row in artifact.get("family_window_summaries", [])]
    if families != _EXPECTED_FAMILIES:
        raise ExploratorySwingViewError("artifact family order drifted")
    for family in artifact.get("interface_availability", []):
        for cadence in family.get("cadences", []):
            for interface in ("underlying", "option_premium"):
                source = cadence.get("interfaces", {}).get(interface, {})
                if set(source.get("coverage", {})) != {
                    "minimum_observation_timestamp",
                    "maximum_observation_timestamp",
                }:
                    raise ExploratorySwingViewError("interface coverage projection drifted")
                if set(source.get("freshness", {})) != {
                    "latest_observation",
                    "calendar_lag_days",
                    "status",
                }:
                    raise ExploratorySwingViewError("interface freshness projection drifted")
    for summary in artifact["family_window_summaries"]:
        all_windows = summary.get("all_complete_windows", {})
        eligible = summary.get("representative_eligible_clean_windows", {})
        clean_count = all_windows.get("quality_counts", {}).get("clean", 0)
        eligible_count = eligible.get("window_count", 0)
        if clean_count <= 0 or eligible_count <= 0 or eligible_count > clean_count:
            raise ExploratorySwingViewError("representative population counts are invalid")
        if summary.get("latest_window_calendar_lag_days", -1) < 0:
            raise ExploratorySwingViewError("negative family freshness lag")
    views = artifact.get("representative_swing_views", [])
    if len(views) != len(_EXPECTED_FAMILIES) * len(_REGIME_TARGETS):
        raise ExploratorySwingViewError("representative view count drifted")
    for family in _EXPECTED_FAMILIES:
        labels = [
            view.get("regime_slice") for view in views if view.get("instrument_family") == family
        ]
        if labels != [target["label"] for target in _REGIME_TARGETS]:
            raise ExploratorySwingViewError(f"representative regimes drifted for {family}")
        if any(
            view.get("input_quality", {}).get("status") != "clean"
            for view in views
            if view.get("instrument_family") == family
        ):
            raise ExploratorySwingViewError("representative view used non-clean input")
        for view in (row for row in views if row.get("instrument_family") == family):
            normalized_path = view.get("normalized_ohlc_path", [])
            if (
                len(normalized_path) != 20
                or [row.get("bar_index") for row in normalized_path] != list(range(20))
                or normalized_path[0].get("open_index") != 100
            ):
                raise ExploratorySwingViewError("representative normalized path drifted")
            for bar in normalized_path:
                values = [
                    bar.get(field)
                    for field in ("open_index", "high_index", "low_index", "close_index")
                ]
                if not all(
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(value)
                    and value > 0
                    for value in values
                ):
                    raise ExploratorySwingViewError(
                        "representative normalized path contains invalid values"
                    )
                open_, high, low, close = values
                if high < low or high < open_ or high < close or low > open_ or low > close:
                    raise ExploratorySwingViewError(
                        "representative normalized path contains incoherent OHLC"
                    )
            if view.get("freshness", {}).get("calendar_lag_days", -1) < 0:
                raise ExploratorySwingViewError("negative representative freshness lag")
            overlay = view.get("option_premium_overlay", {})
            if overlay.get("selection_influence") is not False:
                raise ExploratorySwingViewError(
                    "option premium overlay influenced representative selection"
                )
            if overlay.get("observation_count", 0) <= 0:
                raise ExploratorySwingViewError("representative view lacks option premium behavior")
            if overlay.get("quality_status") not in {"clean", "messy", "invalid"}:
                raise ExploratorySwingViewError("option premium overlay quality status drifted")
            expected_violations = sum(
                overlay.get(field, 0)
                for field in (
                    "nonpositive_or_missing_observation_count",
                    "ohlc_incoherent_observation_count",
                    "duplicate_date_observation_count",
                )
            )
            if overlay.get("input_quality_violation_observation_count") != expected_violations:
                raise ExploratorySwingViewError(
                    "option premium overlay quality counts do not reconcile"
                )
            coverage = overlay.get("distinct_date_coverage", {})
            if coverage.get("required_for_comparable_path") != 20:
                raise ExploratorySwingViewError("option comparable-path coverage drifted")
            comparable = overlay.get("comparable_complete_path_metrics", {})
            if comparable.get("status") not in {"available", "unavailable"}:
                raise ExploratorySwingViewError("option comparable-path status drifted")
            if comparable.get("required_distinct_date_count") != 20:
                raise ExploratorySwingViewError("option comparable-path length drifted")
    examples = artifact.get("quality_examples", {})
    if set(examples) != {"clean", "messy", "invalid", "stale"}:
        raise ExploratorySwingViewError("quality example coverage drifted")
    separation = artifact.get("evidence_separation", {})
    if (
        separation.get("preregistered_evidence") != "not produced"
        or separation.get("future_live_or_shadow") != "not authorized or assessed"
        or separation.get("issue_51_unblocked") is not False
    ):
        raise ExploratorySwingViewError("evidence separation was weakened")
    if artifact.get("source", {}).get("source_refresh_performed") is not False:
        raise ExploratorySwingViewError("artifact reports source mutation")
    if (
        artifact.get("source", {}).get("post_audit_rows_excluded_before_partitioning") is not True
        or artifact.get("source", {}).get("future_only_files_excluded_from_inventory") is not True
    ):
        raise ExploratorySwingViewError("future-row freeze boundary drifted")
    _assert_public_safe(artifact)
