"""Deterministic reviewer-blind daily bare-K episode pack for M6R."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import stat
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from statistics import median
from typing import Any, Callable, Iterable

import pyarrow as pa
import pyarrow.parquet as pq


CONTRACT_SCHEMA_VERSION = "pa_feitian_m6r_historical_bare_k_episode_pack_contract_v1"
MANIFEST_SCHEMA_VERSION = "pa_feitian_m6r_historical_bare_k_episode_manifest_v1"
BLIND_SCHEMA_VERSION = "pa_feitian_m6r_blind_bare_k_episode_pack_v1"
SEALED_SCHEMA_VERSION = "pa_feitian_m6r_sealed_bare_k_reveal_pack_v1"
REVEAL_SCHEMA_VERSION = "pa_feitian_m6r_bare_k_reveal_payload_v1"
COVERAGE_SCHEMA_VERSION = "pa_feitian_m6r_bare_k_episode_coverage_v1"
ANNOTATION_SCHEMA_VERSION = "pa_feitian_m6r_blind_annotations_v1"
CONTRACT_PUBLIC_PATH = (
    "docs/research/pa-feitian-m6r-historical-bare-k-episode-pack-contract-v1.json"
)
ARTIFACT_PUBLIC_DIRECTORY = "doc/repro/pa-feitian-m6r-historical-bare-k-episode-pack-2026-07-31"
AUDIT_AS_OF_LOCAL_DATE = "2026-07-31"
FROZEN_CONTRACT_CANONICAL_SHA256 = (
    "sha256:495c1b993e56cbf80b2f65ca24bb82bec3a6518a66c8ce30c77e9a5cbad1846a"
)
FROZEN_CANDIDATE_UNIVERSE = [
    {
        "instrument_family": "SHFE.cu",
        "exchange": "SHFE",
        "product": "cu",
        "role": "non_precious_industrial_metal",
    },
    {
        "instrument_family": "SHFE.al",
        "exchange": "SHFE",
        "product": "al",
        "role": "non_precious_industrial_metal",
    },
    {
        "instrument_family": "SHFE.rb",
        "exchange": "SHFE",
        "product": "rb",
        "role": "ferrous_material",
    },
    {"instrument_family": "DCE.p", "exchange": "DCE", "product": "p", "role": "agricultural"},
    {"instrument_family": "DCE.m", "exchange": "DCE", "product": "m", "role": "agricultural"},
    {
        "instrument_family": "DCE.pp",
        "exchange": "DCE",
        "product": "pp",
        "role": "industrial_chemical",
    },
    {
        "instrument_family": "CZCE.TA",
        "exchange": "CZCE",
        "product": "TA",
        "role": "industrial_chemical",
    },
    {
        "instrument_family": "CZCE.MA",
        "exchange": "CZCE",
        "product": "MA",
        "role": "industrial_chemical",
    },
    {"instrument_family": "CZCE.CF", "exchange": "CZCE", "product": "CF", "role": "agricultural"},
]
EXPECTED_FAMILIES = [row["instrument_family"] for row in FROZEN_CANDIDATE_UNIVERSE]
FROZEN_FAMILY_BINDINGS = {row["instrument_family"]: row for row in FROZEN_CANDIDATE_UNIVERSE}
REVEAL_ELIGIBILITY_MATERIALIZATION_WORDING = (
    "candidate eligibility and episode materialization require a complete valid 20-bar "
    "reveal window; this gate uses only row availability and quality, not future "
    "direction, magnitude, strategy outcomes, or profitability"
)
OUTPUT_FILENAMES = {
    "manifest": "episode_manifest_v1.json",
    "blind": "blind_episode_pack_v1.json",
    "sealed_reveal": "sealed_reveal_pack_v1.json",
    "coverage": "coverage_and_exclusions_v1.json",
    "annotation_template": "blind_annotation_template_v1.json",
}
REQUIRED_FIELDS = [
    "datetime",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "open_interest",
]
BLIND_EPISODE_FIELDS = {"episode_id", "bars"}
BLIND_BAR_FIELDS = {
    "bar_index",
    "open_index",
    "high_index",
    "low_index",
    "close_index",
}
FORBIDDEN_PUBLIC_TEXT = (
    "/home/",
    "/mnt/",
    "/root/",
    "/tmp/",
    "\\users\\",
    ".parquet",
    ".csv",
)
RAW_CONTRACT_ID = re.compile(r"\b(?:SHFE|CZCE|DCE)\.[A-Za-z]+\d", re.IGNORECASE)
TOKEN_PREFIX = re.compile(
    r"(?i)(?:\bgithub_pat_|\bgh[opusr]_|\bsk-(?:proj-)?|\bxox[baprs]-|"
    r"\bAKIA[0-9A-Z]{12,}|\bAIza[0-9A-Za-z_-]{20,}|\bya29\.)"
)


class HistoricalBareKEpisodePackError(ValueError):
    """Raised when the Issue #64 contract or evidence boundary is violated."""


@dataclass(frozen=True)
class SourceTask:
    family: str
    exchange: str
    product: str
    role: str
    source_alias: str
    source_path: Path


@dataclass(frozen=True)
class NativeRow:
    timestamp: str | None
    trading_date: date | None
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    open_interest: float | None
    quality_findings: tuple[str, ...]


@dataclass(frozen=True)
class SourceScan:
    task: SourceTask
    source_sha256: str | None
    rows: tuple[NativeRow, ...]
    exclusion_reason: str | None
    post_audit_row_count: int = 0


@dataclass(frozen=True)
class Candidate:
    task: SourceTask
    source_sha256: str
    anchor_index: int
    stratum: str
    activity_score: float
    blind_rows: tuple[NativeRow, ...]
    reveal_rows: tuple[NativeRow, ...]
    sampling_role: str = ""
    episode_id: str = ""


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


def _round(value: float) -> float:
    return round(value, 6)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HistoricalBareKEpisodePackError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json_loads(value: str) -> Any:
    try:
        return json.loads(
            value,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda constant: (_ for _ in ()).throw(
                HistoricalBareKEpisodePackError(f"non-standard JSON constant: {constant}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise HistoricalBareKEpisodePackError(f"invalid JSON: {exc}") from exc


def load_contract(path: Path) -> dict[str, Any]:
    contract = strict_json_loads(path.read_text(encoding="utf-8"))
    if not isinstance(contract, dict):
        raise HistoricalBareKEpisodePackError("contract must be a JSON object")
    validate_contract(contract)
    return contract


def validate_contract(contract: dict[str, Any]) -> None:
    if canonical_hash(contract) != FROZEN_CONTRACT_CANONICAL_SHA256:
        raise HistoricalBareKEpisodePackError("contract content drifted")
    if (
        contract.get("schema_version") != CONTRACT_SCHEMA_VERSION
        or contract.get("issue_number") != 64
        or contract.get("audit_as_of_local_date") != AUDIT_AS_OF_LOCAL_DATE
    ):
        raise HistoricalBareKEpisodePackError("contract identity drifted")
    runtime = contract.get("runtime_input", {})
    if (
        runtime.get("binding") != "QUANT_DATA_ROOT"
        or runtime.get("access") != "read_only"
        or runtime.get("relative_root") != "daily"
        or runtime.get("direct_children_only") is not True
        or runtime.get("symlinks_allowed") is not False
        or runtime.get("required_fields") != REQUIRED_FIELDS
    ):
        raise HistoricalBareKEpisodePackError("runtime input boundary drifted")
    if contract.get("candidate_universe") != FROZEN_CANDIDATE_UNIVERSE:
        raise HistoricalBareKEpisodePackError("frozen candidate universe binding drifted")
    protocol = contract.get("episode_protocol", {})
    expected_numbers = {
        "blind_completed_daily_bars": 40,
        "activity_score_trailing_daily_bars": 20,
        "sealed_reveal_completed_daily_bars": 20,
        "candidate_anchor_stride_bars": 5,
        "episodes_per_family": 8,
        "activity_episodes_per_family": 4,
        "ordinary_control_episodes_per_family": 4,
        "total_episode_count": 72,
    }
    if any(protocol.get(key) != value for key, value in expected_numbers.items()):
        raise HistoricalBareKEpisodePackError("episode dimensions drifted")
    if len(protocol.get("anchor_strata", [])) != 4:
        raise HistoricalBareKEpisodePackError("anchor strata drifted")
    required_false = (
        "cross_contract_stitching",
        "cadence_resampling",
        "missing_bar_repair",
        "forward_fill",
        "synthetic_rows",
        "ranking_or_labeling_uses_reveal_direction_magnitude_metrics_outcomes_or_profitability",
        "selection_uses_strategy_outcomes_or_profitability",
        "same_source_selected_windows_may_overlap",
        "same_family_selected_full_calendar_intervals_may_overlap_across_sources",
    )
    if any(protocol.get(key) is not False for key in required_false):
        raise HistoricalBareKEpisodePackError("episode guardrails were weakened")
    if (
        protocol.get("reveal_eligibility_materialization_gate")
        != REVEAL_ELIGIBILITY_MATERIALIZATION_WORDING
        or protocol.get(
            "ranking_candidate_activity_control_ids_and_tiebreaking_use_only_blind_rows"
        )
        is not True
    ):
        raise HistoricalBareKEpisodePackError(
            "reveal eligibility and causal selection boundary drifted"
        )
    representation = contract.get("public_representation", {})
    if representation.get("anonymous_episode_id") != (
        "opaque deterministic identifier derived only from the canonical normalized "
        "pre-anchor blind payload; no provenance or selection metadata participates"
    ):
        raise HistoricalBareKEpisodePackError("anonymous blind-id boundary drifted")
    quality = contract.get("quality_protocol", {})
    if quality.get("invalid_or_missing_rows_may_be_skipped_or_concatenated_across") is not False:
        raise HistoricalBareKEpisodePackError("invalid-row boundary drifted")
    blind = contract.get("blind_reveal_protocol", {})
    if blind.get("blind_episode_allowed_fields") != ["episode_id", "bars"]:
        raise HistoricalBareKEpisodePackError("blind episode surface drifted")
    if set(blind.get("blind_bar_allowed_fields", [])) != BLIND_BAR_FIELDS:
        raise HistoricalBareKEpisodePackError("blind bar surface drifted")
    for key in (
        "blind_pack_exposes_family_exchange_or_product",
        "blind_pack_exposes_contract_identity_or_source_commitment",
        "blind_pack_exposes_calendar_dates_or_era",
        "blind_pack_exposes_sampling_role",
        "blind_pack_contains_future_dates",
        "blind_pack_contains_future_paths",
        "blind_pack_contains_reveal_metrics",
        "blind_pack_references_sealed_reveal_location",
    ):
        if blind.get(key) is not False:
            raise HistoricalBareKEpisodePackError("reviewer blinding was weakened")
    if (
        blind.get("annotation_template_exposes_only_episode_id_and_blank_annotation") is not True
        or blind.get("reveal_requires_complete_blind_annotation") is not True
        or blind.get("reveal_requires_explicit_first_pass_acknowledgement") is not True
    ):
        raise HistoricalBareKEpisodePackError("reveal gate drifted")
    guardrails = contract.get("guardrails", {})
    if guardrails.get("external_access_read_only") is not True:
        raise HistoricalBareKEpisodePackError("read-only source guardrail drifted")
    if any(
        guardrails.get(key) is not False
        for key in (
            "source_refresh",
            "source_mutation",
            "strategy_rule_definition",
            "signal_threshold",
            "profitability_calculation",
            "pnl",
            "ev",
            "win_rate",
            "family_performance_ranking",
            "hypothesis_approval",
            "outcome_informed_blind_editing",
            "historical_event_recall_fields_in_blind_pack",
            "selection_framing_fields_in_blind_pack",
            "option_input_access",
            "m7_authorization",
            "execution",
        )
    ):
        raise HistoricalBareKEpisodePackError("research boundary was weakened")


def _source_alias(name: str) -> str:
    return sha256_bytes(f"m6r-bare-k-source-v1\0{name.lower()}".encode())


def discover_sources(data_root: Path, contract: dict[str, Any]) -> list[SourceTask]:
    daily_root = data_root / "daily"
    if not daily_root.is_dir():
        raise HistoricalBareKEpisodePackError("caller-provided data root has no daily interface")
    candidates = contract["candidate_universe"]
    tasks: list[SourceTask] = []
    try:
        entries = list(daily_root.iterdir())
    except OSError as exc:
        raise HistoricalBareKEpisodePackError("daily interface is unreadable") from exc
    for path in entries:
        if path.is_symlink() or not path.is_file():
            continue
        for candidate in candidates:
            pattern = re.compile(
                rf"^{re.escape(candidate['exchange'])}\."
                rf"{re.escape(candidate['product'])}[0-9]{{3,4}}\.parquet$",
                re.IGNORECASE,
            )
            if not pattern.fullmatch(path.name):
                continue
            tasks.append(
                SourceTask(
                    family=candidate["instrument_family"],
                    exchange=candidate["exchange"],
                    product=candidate["product"],
                    role=candidate["role"],
                    source_alias=_source_alias(path.name),
                    source_path=path,
                )
            )
            break
    tasks.sort(key=lambda task: (EXPECTED_FAMILIES.index(task.family), task.source_alias))
    present = Counter(task.family for task in tasks)
    missing = [family for family in EXPECTED_FAMILIES if not present[family]]
    if missing:
        raise HistoricalBareKEpisodePackError(
            f"verified daily inventory lacks required families: {missing}"
        )
    return tasks


def _capture_regular_file(path: Path) -> tuple[bytes | None, str | None]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None, "source_disappeared_after_discovery"
    except OSError:
        return None, "source_unreadable_after_discovery"
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            return None, "source_unreadable_after_discovery"
        try:
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                content = handle.read()
        except OSError:
            return None, "source_unreadable_after_discovery"
        after = os.fstat(descriptor)
        before_id = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        after_id = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if before_id != after_id or len(content) != after.st_size:
            return None, "source_changed_during_read"
        return content, None
    finally:
        os.close(descriptor)


def _as_datetime(value: Any) -> tuple[str | None, date | None]:
    if value is None:
        return None, None
    if isinstance(value, datetime):
        return value.isoformat(), value.date()
    if isinstance(value, date):
        return value.isoformat(), value
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None, None
    return parsed.isoformat(), parsed.date()


def _as_finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _row_from_values(values: dict[str, Any], previous_date: date | None) -> NativeRow:
    timestamp, trading_date = _as_datetime(values["datetime"])
    numeric = {field: _as_finite(values[field]) for field in REQUIRED_FIELDS[1:]}
    findings: list[str] = []
    if trading_date is None:
        findings.append("missing_or_invalid_timestamp")
    elif previous_date is not None and trading_date <= previous_date:
        findings.append("duplicate_or_nonincreasing_timestamp")
    ohlc = [numeric[field] for field in ("open", "high", "low", "close")]
    if any(value is None or value <= 0 for value in ohlc):
        findings.append("missing_nonfinite_or_nonpositive_ohlc")
    else:
        open_, high, low, close = ohlc
        if high < low or high < open_ or high < close or low > open_ or low > close:
            findings.append("ohlc_incoherent")
    for field in ("volume", "open_interest"):
        if numeric[field] is None or numeric[field] < 0:
            findings.append(f"missing_nonfinite_or_negative_{field}")
    return NativeRow(
        timestamp=timestamp,
        trading_date=trading_date,
        open=numeric["open"],
        high=numeric["high"],
        low=numeric["low"],
        close=numeric["close"],
        volume=numeric["volume"],
        open_interest=numeric["open_interest"],
        quality_findings=tuple(findings),
    )


def read_source_task(task: SourceTask, audit_date: date) -> SourceScan:
    content, exclusion = _capture_regular_file(task.source_path)
    if exclusion is not None or content is None:
        return SourceScan(task, None, (), exclusion)
    source_sha256 = sha256_bytes(content)
    try:
        parquet = pq.ParquetFile(pa.BufferReader(content))
        missing = [field for field in REQUIRED_FIELDS if field not in parquet.schema_arrow.names]
        if missing:
            return SourceScan(task, source_sha256, (), "source_required_schema_missing")
        table = parquet.read(columns=REQUIRED_FIELDS)
    except Exception:
        return SourceScan(task, source_sha256, (), "source_unreadable_after_discovery")
    rows: list[NativeRow] = []
    post_audit = 0
    previous_native_date: date | None = None
    for index in range(table.num_rows):
        values = {field: table[field][index].as_py() for field in REQUIRED_FIELDS}
        row = _row_from_values(values, previous_native_date)
        if row.trading_date is not None:
            previous_native_date = row.trading_date
        if row.trading_date is not None and row.trading_date > audit_date:
            post_audit += 1
            continue
        rows.append(row)
    if not rows:
        return SourceScan(
            task,
            source_sha256,
            (),
            "source_has_no_observation_on_or_before_audit",
            post_audit,
        )
    return SourceScan(task, source_sha256, tuple(rows), None, post_audit)


def scan_discovered_sources(
    tasks: Iterable[SourceTask], *, audit_date: date, workers: int
) -> list[SourceScan]:
    if workers <= 0:
        raise HistoricalBareKEpisodePackError("worker count must be positive")
    ordered = list(tasks)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        scans = list(executor.map(lambda task: read_source_task(task, audit_date), ordered))
    return scans


def _stratum_for(day: date, strata: list[dict[str, str]]) -> str | None:
    for row in strata:
        start = date.fromisoformat(row["start_date_inclusive"])
        end = date.fromisoformat(row["end_date_inclusive"])
        if start <= day <= end:
            return row["stratum"]
    return None


def enumerate_candidates(
    scan: SourceScan, contract: dict[str, Any]
) -> tuple[list[Candidate], Counter[str]]:
    exclusions: Counter[str] = Counter()
    if scan.exclusion_reason is not None:
        exclusions[scan.exclusion_reason] += 1
        return [], exclusions
    protocol = contract["episode_protocol"]
    blind_count = protocol["blind_completed_daily_bars"]
    score_count = protocol["activity_score_trailing_daily_bars"]
    reveal_count = protocol["sealed_reveal_completed_daily_bars"]
    stride = protocol["candidate_anchor_stride_bars"]
    rows = scan.rows
    if len(rows) < blind_count + reveal_count:
        exclusions["source_insufficient_rows_for_episode"] += 1
        return [], exclusions
    candidates: list[Candidate] = []
    for anchor in range(blind_count - 1, len(rows) - reveal_count, stride):
        blind = rows[anchor - blind_count + 1 : anchor + 1]
        reveal = rows[anchor + 1 : anchor + 1 + reveal_count]
        if any(row.quality_findings for row in blind):
            exclusions["blind_window_invalid_or_missing_row"] += 1
            continue
        if any(row.quality_findings for row in reveal):
            exclusions["reveal_window_invalid_or_missing_row"] += 1
            continue
        anchor_date = blind[-1].trading_date
        if anchor_date is None:
            exclusions["blind_anchor_timestamp_invalid"] += 1
            continue
        stratum = _stratum_for(anchor_date, protocol["anchor_strata"])
        if stratum is None:
            exclusions["anchor_outside_frozen_strata"] += 1
            continue
        score_rows = blind[-score_count:]
        if (
            median(row.volume for row in score_rows) <= 0
            or median(row.open_interest for row in score_rows) <= 0
        ):
            exclusions["blind_activity_gate_failed"] += 1
            continue
        score = median((row.high - row.low) / row.close * 100 for row in score_rows)
        candidates.append(
            Candidate(
                task=scan.task,
                source_sha256=scan.source_sha256 or "",
                anchor_index=anchor,
                stratum=stratum,
                activity_score=score,
                blind_rows=blind,
                reveal_rows=reveal,
            )
        )
    return candidates, exclusions


def _overlaps(left: Candidate, right: Candidate) -> bool:
    if left.task.family != right.task.family:
        return False
    left_start = left.blind_rows[0].trading_date
    left_end = left.reveal_rows[-1].trading_date
    right_start = right.blind_rows[0].trading_date
    right_end = right.reveal_rows[-1].trading_date
    if None in (left_start, left_end, right_start, right_end):
        raise HistoricalBareKEpisodePackError("selected interval has no native date")
    return not (left_end < right_start or right_end < left_start)


def _candidate_tiebreak(candidate: Candidate) -> tuple[str, str]:
    timestamp = candidate.blind_rows[-1].timestamp or ""
    return timestamp, candidate.task.source_alias


def _blind_payload(candidate: Candidate) -> dict[str, Any]:
    """Return the only material permitted to influence an anonymous episode ID."""
    return {
        "bars": _indexed_bars(
            candidate.blind_rows,
            base=candidate.blind_rows[0].open,
            first_index=-(len(candidate.blind_rows) - 1),
        )
    }


def _anonymous_blind_payload_id(candidate: Candidate) -> str:
    """Derive an opaque ID from normalized blind bars, not from provenance or order."""
    domain = b"m6r-anonymous-normalized-blind-payload-v1\0"
    payload = canonical_json_bytes(_blind_payload(candidate))
    return f"M6R-{hashlib.sha256(domain + payload).hexdigest()[:20]}"


def assign_anonymous_blind_payload_ids(selected: list[Candidate]) -> list[Candidate]:
    """Attach public IDs that are independent of provenance, role, and position."""
    return [
        replace(candidate, episode_id=_anonymous_blind_payload_id(candidate))
        for candidate in selected
    ]


def select_episodes(candidates: list[Candidate], contract: dict[str, Any]) -> list[Candidate]:
    strata = [row["stratum"] for row in contract["episode_protocol"]["anchor_strata"]]
    selected: list[Candidate] = []
    for family in EXPECTED_FAMILIES:
        family_selected: list[Candidate] = []
        for stratum in strata:
            population = [
                candidate
                for candidate in candidates
                if candidate.task.family == family and candidate.stratum == stratum
            ]
            available = [
                candidate
                for candidate in population
                if not any(_overlaps(candidate, prior) for prior in family_selected)
            ]
            if len(available) < 2:
                raise HistoricalBareKEpisodePackError(
                    f"insufficient non-overlapping candidates for {family} {stratum}"
                )
            activity = min(
                available,
                key=lambda candidate: (
                    -candidate.activity_score,
                    *_candidate_tiebreak(candidate),
                ),
            )
            activity = replace(activity, sampling_role="candidate_activity")
            family_selected.append(activity)
            control_pool = [
                candidate
                for candidate in population
                if not any(_overlaps(candidate, prior) for prior in family_selected)
            ]
            if not control_pool:
                raise HistoricalBareKEpisodePackError(
                    f"no non-overlapping ordinary control for {family} {stratum}"
                )
            target = median(candidate.activity_score for candidate in population)
            control = min(
                control_pool,
                key=lambda candidate: (
                    abs(candidate.activity_score - target),
                    *_candidate_tiebreak(candidate),
                ),
            )
            family_selected.append(replace(control, sampling_role="ordinary_control"))
        selected.extend(family_selected)
    with_ids = assign_anonymous_blind_payload_ids(selected)
    ids = [candidate.episode_id for candidate in with_ids]
    if len(ids) != len(set(ids)):
        raise HistoricalBareKEpisodePackError("anonymous episode id collision")
    expected = contract["episode_protocol"]["total_episode_count"]
    if len(with_ids) != expected:
        raise HistoricalBareKEpisodePackError("selected episode count drifted")
    return sorted(with_ids, key=lambda candidate: candidate.episode_id)


def _native_slice_commitment(rows: Iterable[NativeRow]) -> str:
    payload = [
        {
            "timestamp": row.timestamp,
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
            "volume": row.volume,
            "open_interest": row.open_interest,
        }
        for row in rows
    ]
    return canonical_hash(payload)


def _indexed_bars(
    rows: tuple[NativeRow, ...], *, base: float, first_index: int
) -> list[dict[str, float | int]]:
    return [
        {
            "bar_index": first_index + offset,
            "open_index": _round(row.open / base * 100),
            "high_index": _round(row.high / base * 100),
            "low_index": _round(row.low / base * 100),
            "close_index": _round(row.close / base * 100),
        }
        for offset, row in enumerate(rows)
    ]


def _blind_episode(candidate: Candidate) -> dict[str, Any]:
    return {
        "episode_id": candidate.episode_id,
        **_blind_payload(candidate),
    }


def _reveal_metrics(candidate: Candidate) -> dict[str, float]:
    anchor_close = candidate.blind_rows[-1].close
    future_closes = [row.close for row in candidate.reveal_rows]
    future_highs = [row.high for row in candidate.reveal_rows]
    future_lows = [row.low for row in candidate.reveal_rows]
    return {
        "path_change_from_anchor_close_pct": _round((future_closes[-1] / anchor_close - 1) * 100),
        "maximum_rise_from_anchor_close_pct": _round((max(future_highs) / anchor_close - 1) * 100),
        "maximum_decline_from_anchor_close_pct": _round(
            (min(future_lows) / anchor_close - 1) * 100
        ),
        "future_total_excursion_pct": _round((max(future_highs) / min(future_lows) - 1) * 100),
    }


def _reveal_episode(candidate: Candidate) -> dict[str, Any]:
    base = candidate.blind_rows[0].open
    return {
        "episode_id": candidate.episode_id,
        "provenance": {
            "instrument_family": candidate.task.family,
            "exchange": candidate.task.exchange,
            "product": candidate.task.product,
            "family_role": candidate.task.role,
            "anchor_stratum": candidate.stratum,
            "sampling_role": candidate.sampling_role,
            "anonymous_source_alias": candidate.task.source_alias,
            "source_file_sha256": candidate.source_sha256,
            "blind_native_slice_sha256": _native_slice_commitment(candidate.blind_rows),
            "reveal_native_slice_sha256": _native_slice_commitment(candidate.reveal_rows),
            "blind_start_timestamp": candidate.blind_rows[0].timestamp,
            "decision_timestamp": candidate.blind_rows[-1].timestamp,
            "blind_bar_timestamps": [row.timestamp for row in candidate.blind_rows],
        },
        "future_bars": [
            {
                "bar_offset": offset,
                "timestamp": row.timestamp,
                "open_index": _round(row.open / base * 100),
                "high_index": _round(row.high / base * 100),
                "low_index": _round(row.low / base * 100),
                "close_index": _round(row.close / base * 100),
            }
            for offset, row in enumerate(candidate.reveal_rows, start=1)
        ],
        "descriptive_reveal_metrics": _reveal_metrics(candidate),
    }


def _assert_public_safe(value: Any) -> None:
    if isinstance(value, dict):
        for nested in value.values():
            _assert_public_safe(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_public_safe(nested)
    elif isinstance(value, str):
        lowered = value.lower()
        if any(token in lowered for token in FORBIDDEN_PUBLIC_TEXT):
            raise HistoricalBareKEpisodePackError(
                "public artifact contains a local path or source filename"
            )
        if RAW_CONTRACT_ID.search(value):
            raise HistoricalBareKEpisodePackError(
                "public artifact contains a raw contract identifier"
            )
        if TOKEN_PREFIX.search(value):
            raise HistoricalBareKEpisodePackError(
                "public artifact contains a credential-like token"
            )


def validate_blind_pack(blind: dict[str, Any]) -> None:
    if blind.get("schema_version") != BLIND_SCHEMA_VERSION:
        raise HistoricalBareKEpisodePackError("unexpected blind pack schema")
    episodes = blind.get("episodes")
    if not isinstance(episodes, list) or blind.get("episode_count") != len(episodes):
        raise HistoricalBareKEpisodePackError("blind episode count is invalid")
    if set(blind) != {"schema_version", "issue_number", "episode_count", "episodes"}:
        raise HistoricalBareKEpisodePackError("blind top-level surface drifted")
    for episode in episodes:
        if not isinstance(episode, dict) or set(episode) != BLIND_EPISODE_FIELDS:
            raise HistoricalBareKEpisodePackError("blind episode exposes identity metadata")
        if not re.fullmatch(r"M6R-[0-9a-f]{20}", episode.get("episode_id", "")):
            raise HistoricalBareKEpisodePackError("blind episode id is not anonymous")
        bars = episode.get("bars")
        if not isinstance(bars, list) or len(bars) != 40:
            raise HistoricalBareKEpisodePackError("blind episode bar count drifted")
        if [bar.get("bar_index") for bar in bars] != list(range(-39, 1)):
            raise HistoricalBareKEpisodePackError("blind relative bar indices drifted")
        for bar in bars:
            if not isinstance(bar, dict) or set(bar) != BLIND_BAR_FIELDS:
                raise HistoricalBareKEpisodePackError("blind bar exposes forbidden metadata")
            values = [bar[key] for key in BLIND_BAR_FIELDS if key != "bar_index"]
            if not all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and value > 0
                for value in values
            ):
                raise HistoricalBareKEpisodePackError("blind indexed OHLC is invalid")
            if (
                bar["high_index"] < bar["low_index"]
                or bar["high_index"] < bar["open_index"]
                or bar["high_index"] < bar["close_index"]
                or bar["low_index"] > bar["open_index"]
                or bar["low_index"] > bar["close_index"]
            ):
                raise HistoricalBareKEpisodePackError("blind indexed OHLC is incoherent")
    ids = [episode["episode_id"] for episode in episodes]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise HistoricalBareKEpisodePackError("blind episode ordering or identity drifted")
    text = json.dumps(blind, sort_keys=True)
    for forbidden in (
        "family",
        "exchange",
        "product",
        "contract",
        "source",
        "timestamp",
        "date",
        "era",
        "stratum",
        "activity",
        "control",
        "sampling",
        "reveal",
        "future",
    ):
        if forbidden in text.lower():
            raise HistoricalBareKEpisodePackError(
                f"blind pack leaks reviewer-framing field: {forbidden}"
            )
    _assert_public_safe(blind)


def decode_sealed_reveal(sealed: dict[str, Any]) -> dict[str, Any]:
    if set(sealed) != {
        "schema_version",
        "issue_number",
        "encoding",
        "encoding_is_encryption",
        "payload_sha256",
        "payload_base64",
    }:
        raise HistoricalBareKEpisodePackError("sealed reveal wrapper surface drifted")
    if (
        sealed.get("schema_version") != SEALED_SCHEMA_VERSION
        or sealed.get("issue_number") != 64
        or sealed.get("encoding") != "base64_canonical_json"
        or sealed.get("encoding_is_encryption") is not False
    ):
        raise HistoricalBareKEpisodePackError("sealed reveal wrapper drifted")
    try:
        payload_bytes = base64.b64decode(sealed["payload_base64"], validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise HistoricalBareKEpisodePackError("sealed reveal payload is invalid") from exc
    if sha256_bytes(payload_bytes) != sealed["payload_sha256"]:
        raise HistoricalBareKEpisodePackError("sealed reveal payload hash mismatch")
    payload = strict_json_loads(payload_bytes.decode("utf-8"))
    if canonical_json_bytes(payload) != payload_bytes:
        raise HistoricalBareKEpisodePackError("reveal payload is not canonical JSON")
    validate_reveal_payload(payload)
    return payload


def validate_reveal_payload(payload: dict[str, Any]) -> None:
    if set(payload) != {
        "schema_version",
        "issue_number",
        "blind_pack_sha256",
        "episode_count",
        "annotation_gate",
        "episodes",
        "interpretation_boundary",
    }:
        raise HistoricalBareKEpisodePackError("reveal payload surface drifted")
    if (
        payload.get("schema_version") != REVEAL_SCHEMA_VERSION
        or payload.get("issue_number") != 64
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", payload.get("blind_pack_sha256", ""))
    ):
        raise HistoricalBareKEpisodePackError("reveal payload identity drifted")
    gate = payload.get("annotation_gate")
    if gate != {
        "schema_version": ANNOTATION_SCHEMA_VERSION,
        "all_episode_ids_required": True,
        "nonempty_annotation_per_episode_required": True,
        "explicit_first_pass_acknowledgement_required": True,
    }:
        raise HistoricalBareKEpisodePackError("reveal annotation gate drifted")
    episodes = payload.get("episodes")
    if not isinstance(episodes, list) or payload.get("episode_count") != len(episodes):
        raise HistoricalBareKEpisodePackError("reveal episode count is invalid")
    ids: list[str] = []
    intervals_by_family: dict[str, list[tuple[datetime, datetime]]] = {}
    for episode in episodes:
        if set(episode) != {
            "episode_id",
            "provenance",
            "future_bars",
            "descriptive_reveal_metrics",
        }:
            raise HistoricalBareKEpisodePackError("reveal episode surface drifted")
        episode_id = episode["episode_id"]
        if not re.fullmatch(r"M6R-[0-9a-f]{20}", episode_id):
            raise HistoricalBareKEpisodePackError("reveal episode id is invalid")
        ids.append(episode_id)
        provenance = episode["provenance"]
        expected_provenance = {
            "instrument_family",
            "exchange",
            "product",
            "family_role",
            "anchor_stratum",
            "sampling_role",
            "anonymous_source_alias",
            "source_file_sha256",
            "blind_native_slice_sha256",
            "reveal_native_slice_sha256",
            "blind_start_timestamp",
            "decision_timestamp",
            "blind_bar_timestamps",
        }
        if set(provenance) != expected_provenance:
            raise HistoricalBareKEpisodePackError("reveal provenance surface drifted")
        family_binding = FROZEN_FAMILY_BINDINGS.get(provenance["instrument_family"])
        if family_binding is None:
            raise HistoricalBareKEpisodePackError("reveal family mapping drifted")
        if (
            provenance["exchange"] != family_binding["exchange"]
            or provenance["product"] != family_binding["product"]
            or provenance["family_role"] != family_binding["role"]
        ):
            raise HistoricalBareKEpisodePackError("reveal candidate-universe binding drifted")
        if provenance["sampling_role"] not in {"candidate_activity", "ordinary_control"}:
            raise HistoricalBareKEpisodePackError("reveal sampling label drifted")
        if provenance["anchor_stratum"] not in {"era_1", "era_2", "era_3", "era_4"}:
            raise HistoricalBareKEpisodePackError("reveal anchor stratum drifted")
        if not all(
            re.fullmatch(r"sha256:[0-9a-f]{64}", provenance[key] or "")
            for key in (
                "anonymous_source_alias",
                "source_file_sha256",
                "blind_native_slice_sha256",
                "reveal_native_slice_sha256",
            )
        ):
            raise HistoricalBareKEpisodePackError("reveal source commitment drifted")
        timestamps = provenance["blind_bar_timestamps"]
        if not isinstance(timestamps, list) or len(timestamps) != 40:
            raise HistoricalBareKEpisodePackError("reveal blind timestamp map drifted")
        if provenance["blind_start_timestamp"] != timestamps[0]:
            raise HistoricalBareKEpisodePackError("reveal blind start timestamp drifted")
        if timestamps[-1] != provenance["decision_timestamp"]:
            raise HistoricalBareKEpisodePackError("reveal decision timestamp drifted")
        try:
            blind_times = [datetime.fromisoformat(timestamp) for timestamp in timestamps]
        except (TypeError, ValueError) as exc:
            raise HistoricalBareKEpisodePackError("reveal blind timestamp is invalid") from exc
        if any(left >= right for left, right in zip(blind_times, blind_times[1:])):
            raise HistoricalBareKEpisodePackError(
                "reveal blind timestamps are not strictly increasing"
            )
        decision = blind_times[-1]
        future = episode["future_bars"]
        if not isinstance(future, list) or len(future) != 20:
            raise HistoricalBareKEpisodePackError("reveal bar count drifted")
        future_times: list[datetime] = []
        for offset, bar in enumerate(future, start=1):
            if set(bar) != {
                "bar_offset",
                "timestamp",
                "open_index",
                "high_index",
                "low_index",
                "close_index",
            }:
                raise HistoricalBareKEpisodePackError("reveal bar surface drifted")
            if bar["bar_offset"] != offset:
                raise HistoricalBareKEpisodePackError("reveal bar offsets drifted")
            try:
                future_time = datetime.fromisoformat(bar["timestamp"])
            except (TypeError, ValueError) as exc:
                raise HistoricalBareKEpisodePackError("reveal timestamp is invalid") from exc
            if future_time <= decision:
                raise HistoricalBareKEpisodePackError("reveal is not strictly after decision")
            future_times.append(future_time)
            values = [bar[key] for key in ("open_index", "high_index", "low_index", "close_index")]
            if not all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and value > 0
                for value in values
            ):
                raise HistoricalBareKEpisodePackError("reveal normalized OHLC is invalid")
            if (
                bar["high_index"] < bar["low_index"]
                or bar["high_index"] < bar["open_index"]
                or bar["high_index"] < bar["close_index"]
                or bar["low_index"] > bar["open_index"]
                or bar["low_index"] > bar["close_index"]
            ):
                raise HistoricalBareKEpisodePackError("reveal normalized OHLC is incoherent")
        if any(left >= right for left, right in zip(future_times, future_times[1:])):
            raise HistoricalBareKEpisodePackError(
                "reveal future timestamps are not strictly increasing"
            )
        intervals_by_family.setdefault(provenance["instrument_family"], []).append(
            (
                datetime.fromisoformat(provenance["blind_start_timestamp"]),
                datetime.fromisoformat(future[-1]["timestamp"]),
            )
        )
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise HistoricalBareKEpisodePackError("reveal episode ordering or identity drifted")
    for family, intervals in intervals_by_family.items():
        for index, (left_start, left_end) in enumerate(intervals):
            for right_start, right_end in intervals[index + 1 :]:
                if not (left_end < right_start or right_end < left_start):
                    raise HistoricalBareKEpisodePackError(
                        f"same-family selected calendar intervals overlap: {family}"
                    )
    _assert_public_safe(payload)


def validate_annotation_document(
    annotations: dict[str, Any],
    *,
    blind_pack_sha256: str,
    episode_ids: set[str],
    require_complete: bool,
) -> None:
    if set(annotations) != {
        "schema_version",
        "blind_pack_sha256",
        "annotations",
    }:
        raise HistoricalBareKEpisodePackError("annotation document surface drifted")
    if (
        annotations.get("schema_version") != ANNOTATION_SCHEMA_VERSION
        or annotations.get("blind_pack_sha256") != blind_pack_sha256
    ):
        raise HistoricalBareKEpisodePackError("annotation document binding drifted")
    rows = annotations.get("annotations")
    if not isinstance(rows, list):
        raise HistoricalBareKEpisodePackError("annotations must be a list")
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"episode_id", "annotation"}:
            raise HistoricalBareKEpisodePackError("annotation template exposes identity metadata")
        if not isinstance(row["annotation"], str):
            raise HistoricalBareKEpisodePackError("annotation must be text")
    ids = [row["episode_id"] for row in rows]
    if ids != sorted(ids) or set(ids) != episode_ids or len(ids) != len(set(ids)):
        raise HistoricalBareKEpisodePackError("annotation episode identity drifted")
    if require_complete and any(not row["annotation"].strip() for row in rows):
        raise HistoricalBareKEpisodePackError(
            "every blind episode requires a first-pass annotation"
        )
    _assert_public_safe(annotations)


def _coverage_artifact(
    *,
    tasks: list[SourceTask],
    scans: list[SourceScan],
    candidates: list[Candidate],
    selected: list[Candidate],
    scan_exclusions: dict[str, Counter[str]],
) -> dict[str, Any]:
    family_rows: list[dict[str, Any]] = []
    for family in EXPECTED_FAMILIES:
        family_tasks = [task for task in tasks if task.family == family]
        family_scans = [scan for scan in scans if scan.task.family == family]
        family_candidates = [item for item in candidates if item.task.family == family]
        family_selected = [item for item in selected if item.task.family == family]
        exclusion_counts: Counter[str] = Counter()
        for scan in family_scans:
            exclusion_counts.update(scan_exclusions.get(scan.task.source_alias, Counter()))
        dates = [
            row.trading_date
            for scan in family_scans
            if scan.exclusion_reason is None
            for row in scan.rows
            if row.trading_date is not None
        ]
        family_rows.append(
            {
                "instrument_family": family,
                "exchange": family_tasks[0].exchange,
                "product": family_tasks[0].product,
                "role": family_tasks[0].role,
                "discovered_source_count": len(family_tasks),
                "readable_source_count": sum(
                    scan.exclusion_reason is None for scan in family_scans
                ),
                "minimum_native_observation_date": min(dates).isoformat() if dates else None,
                "maximum_native_observation_date": max(dates).isoformat() if dates else None,
                "post_audit_row_count": sum(scan.post_audit_row_count for scan in family_scans),
                "eligible_anchor_count": len(family_candidates),
                "selected_episode_count": len(family_selected),
                "selected_by_sampling_role": {
                    "candidate_activity": sum(
                        item.sampling_role == "candidate_activity" for item in family_selected
                    ),
                    "ordinary_control": sum(
                        item.sampling_role == "ordinary_control" for item in family_selected
                    ),
                },
                "selected_by_anchor_stratum": {
                    stratum: sum(item.stratum == stratum for item in family_selected)
                    for stratum in ("era_1", "era_2", "era_3", "era_4")
                },
                "explicit_exclusion_counts": dict(sorted(exclusion_counts.items())),
            }
        )
    exchange_rows = [
        {
            "exchange": exchange,
            "family_count": sum(row["exchange"] == exchange for row in family_rows),
            "selected_episode_count": sum(
                row["selected_episode_count"] for row in family_rows if row["exchange"] == exchange
            ),
        }
        for exchange in ("SHFE", "DCE", "CZCE")
    ]
    return {
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "issue_number": 64,
        "audit_as_of_local_date": AUDIT_AS_OF_LOCAL_DATE,
        "cadence": "daily",
        "family_coverage": family_rows,
        "exchange_coverage": exchange_rows,
        "aggregate": {
            "family_count": len(family_rows),
            "exchange_count": len(exchange_rows),
            "discovered_source_count": len(tasks),
            "readable_source_count": sum(scan.exclusion_reason is None for scan in scans),
            "eligible_anchor_count": len(candidates),
            "selected_episode_count": len(selected),
            "candidate_activity_episode_count": sum(
                item.sampling_role == "candidate_activity" for item in selected
            ),
            "ordinary_control_episode_count": sum(
                item.sampling_role == "ordinary_control" for item in selected
            ),
            "source_disappeared_after_discovery_count": sum(
                scan.exclusion_reason == "source_disappeared_after_discovery" for scan in scans
            ),
            "source_unreadable_after_discovery_count": sum(
                scan.exclusion_reason == "source_unreadable_after_discovery" for scan in scans
            ),
        },
        "interpretation_boundary": (
            "Coverage and exclusions describe input materialization only; they do "
            "not rank families, score a strategy, or expose an episode mapping."
        ),
    }


def build_episode_pack(
    *,
    contract: dict[str, Any],
    contract_path: Path,
    data_root: Path,
    workers: int = 8,
    after_discovery: Callable[[list[SourceTask]], None] | None = None,
) -> dict[str, dict[str, Any]]:
    validate_contract(contract)
    tasks = discover_sources(data_root, contract)
    if after_discovery is not None:
        after_discovery(tasks)
    audit_date = date.fromisoformat(contract["audit_as_of_local_date"])
    scans = scan_discovered_sources(tasks, audit_date=audit_date, workers=workers)
    all_candidates: list[Candidate] = []
    scan_exclusions: dict[str, Counter[str]] = {}
    for scan in scans:
        candidates, exclusions = enumerate_candidates(scan, contract)
        all_candidates.extend(candidates)
        scan_exclusions[scan.task.source_alias] = exclusions
    selected = select_episodes(all_candidates, contract)

    blind = {
        "schema_version": BLIND_SCHEMA_VERSION,
        "issue_number": 64,
        "episode_count": len(selected),
        "episodes": [_blind_episode(candidate) for candidate in selected],
    }
    validate_blind_pack(blind)
    blind_bytes = pretty_json_bytes(blind)
    blind_sha256 = sha256_bytes(blind_bytes)
    episode_ids = {candidate.episode_id for candidate in selected}

    annotations = {
        "schema_version": ANNOTATION_SCHEMA_VERSION,
        "blind_pack_sha256": blind_sha256,
        "annotations": [
            {"episode_id": episode_id, "annotation": ""} for episode_id in sorted(episode_ids)
        ],
    }
    validate_annotation_document(
        annotations,
        blind_pack_sha256=blind_sha256,
        episode_ids=episode_ids,
        require_complete=False,
    )

    reveal_payload = {
        "schema_version": REVEAL_SCHEMA_VERSION,
        "issue_number": 64,
        "blind_pack_sha256": blind_sha256,
        "episode_count": len(selected),
        "annotation_gate": {
            "schema_version": ANNOTATION_SCHEMA_VERSION,
            "all_episode_ids_required": True,
            "nonempty_annotation_per_episode_required": True,
            "explicit_first_pass_acknowledgement_required": True,
        },
        "episodes": [_reveal_episode(candidate) for candidate in selected],
        "interpretation_boundary": (
            "The mapping and future paths are descriptive research material only; "
            "they do not define a rule, signal, PnL, EV, win rate, family ranking, "
            "hypothesis approval, M7 authorization, or execution readiness."
        ),
    }
    reveal_payload_bytes = canonical_json_bytes(reveal_payload)
    sealed = {
        "schema_version": SEALED_SCHEMA_VERSION,
        "issue_number": 64,
        "encoding": "base64_canonical_json",
        "encoding_is_encryption": False,
        "payload_sha256": sha256_bytes(reveal_payload_bytes),
        "payload_base64": base64.b64encode(reveal_payload_bytes).decode("ascii"),
    }
    decoded = decode_sealed_reveal(sealed)
    if decoded != reveal_payload:
        raise HistoricalBareKEpisodePackError("sealed reveal round trip drifted")

    coverage = _coverage_artifact(
        tasks=tasks,
        scans=scans,
        candidates=all_candidates,
        selected=selected,
        scan_exclusions=scan_exclusions,
    )
    readable_sources = [
        {
            "instrument_family": scan.task.family,
            "anonymous_source_alias": scan.task.source_alias,
            "source_file_sha256": scan.source_sha256,
        }
        for scan in scans
        if scan.exclusion_reason is None
    ]
    source_inventory_sha256 = canonical_hash(readable_sources)
    contract_sha256 = sha256_bytes(contract_path.read_bytes())
    component_bytes = {
        "blind": blind_bytes,
        "sealed_reveal": pretty_json_bytes(sealed),
        "coverage": pretty_json_bytes(coverage),
        "annotation_template": pretty_json_bytes(annotations),
    }
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "issue_number": 64,
        "audit_as_of_local_date": AUDIT_AS_OF_LOCAL_DATE,
        "study_label": "blind_historical_observation_material_only",
        "contract": {
            "public_location": CONTRACT_PUBLIC_PATH,
            "sha256": contract_sha256,
            "canonical_sha256": FROZEN_CONTRACT_CANONICAL_SHA256,
        },
        "source": {
            "runtime_binding": "QUANT_DATA_ROOT",
            "public_alias": "external://quant-data/daily/",
            "access": "read_only",
            "source_refresh_performed": False,
            "source_mutation_performed": False,
            "filesystem_timestamps_used": False,
            "readable_inventory_sha256": source_inventory_sha256,
        },
        "episode_count": len(selected),
        "artifact_bindings": {
            name: {
                "public_location": f"{ARTIFACT_PUBLIC_DIRECTORY}/{OUTPUT_FILENAMES[name]}",
                "sha256": sha256_bytes(content),
            }
            for name, content in component_bytes.items()
        },
        "review_order": [
            OUTPUT_FILENAMES["blind"],
            OUTPUT_FILENAMES["annotation_template"],
            "freeze a complete external annotation document",
            "run the explicit reveal command",
        ],
        "first_pass_warning": (
            "Do not inspect the manifest coverage details, sealed reveal, repository "
            "history, or source inventory while annotating the anonymous blind pack."
        ),
        "episode_mapping_in_manifest": False,
        "strategy_or_performance_claim": False,
        "m7_authorized": False,
    }
    artifacts = {
        "manifest": manifest,
        "blind": blind,
        "sealed_reveal": sealed,
        "coverage": coverage,
        "annotation_template": annotations,
    }
    for artifact in artifacts.values():
        _assert_public_safe(artifact)
    return artifacts


def validate_output_directory(
    *, output_directory: Path, data_root: Path, contract_path: Path
) -> Path:
    resolved_output = output_directory.resolve()
    resolved_data = data_root.resolve()
    resolved_contract = contract_path.resolve()
    if resolved_output == resolved_data or resolved_data in resolved_output.parents:
        raise HistoricalBareKEpisodePackError(
            "output directory must be outside the read-only data root"
        )
    if resolved_contract == resolved_output or resolved_output in resolved_contract.parents:
        raise HistoricalBareKEpisodePackError(
            "output directory may not contain or replace the contract"
        )
    return resolved_output


def validate_reveal_output_path(
    *,
    output: Path,
    sealed_reveal: Path,
    blind_annotations: Path,
    repository_root: Path,
) -> Path:
    """Require decoded reveal material to be written outside committed artifacts."""
    resolved_output = output.resolve()
    resolved_repository = repository_root.resolve()
    if resolved_output in {
        sealed_reveal.resolve(),
        blind_annotations.resolve(),
    }:
        raise HistoricalBareKEpisodePackError("output must not replace an input")
    if resolved_output == resolved_repository or resolved_repository in resolved_output.parents:
        raise HistoricalBareKEpisodePackError(
            "decoded reveal output must be outside the repository"
        )
    return resolved_output


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_episode_pack(output_directory: Path, artifacts: dict[str, dict[str, Any]]) -> None:
    if set(artifacts) != set(OUTPUT_FILENAMES):
        raise HistoricalBareKEpisodePackError("artifact set drifted")
    encoded = {name: pretty_json_bytes(artifact) for name, artifact in artifacts.items()}
    for name in ("blind", "sealed_reveal", "coverage", "annotation_template", "manifest"):
        atomic_write(output_directory / OUTPUT_FILENAMES[name], encoded[name])


def reveal_with_annotations(
    *,
    sealed: dict[str, Any],
    annotations: dict[str, Any],
    acknowledge_first_pass_complete: bool,
) -> dict[str, Any]:
    if not acknowledge_first_pass_complete:
        raise HistoricalBareKEpisodePackError(
            "explicit first-pass-complete acknowledgement is required"
        )
    payload = decode_sealed_reveal(sealed)
    episode_ids = {episode["episode_id"] for episode in payload["episodes"]}
    validate_annotation_document(
        annotations,
        blind_pack_sha256=payload["blind_pack_sha256"],
        episode_ids=episode_ids,
        require_complete=True,
    )
    return payload
