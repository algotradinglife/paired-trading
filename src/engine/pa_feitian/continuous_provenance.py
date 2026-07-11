"""Causal provenance binding for the two reproducible continuous candidates.

This module deliberately separates exact derived-byte reconstruction from raw
provider acquisition lineage.  Reconstructing a Parquet byte stream does not
prove when the raw vendor observations were acquired or available.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import types
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from engine.pa_feitian.manifest import sha256_file


SCHEMA_VERSION = "pa_feitian_continuous_provenance_manifest_v1"
_QUARANTINED_KINDS = {"option_ivskew", "regime"}


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return _sha256_bytes(payload)


def _git_blob(repo: Path, commit: str, path: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout


def _load_continuous_module(source: bytes) -> types.ModuleType:
    module = types.ModuleType("pinned_continuous_source")
    exec(compile(source, "pinned:src/data/continuous.py", "exec"), module.__dict__)
    return module


def _source_entries(
    module: types.ModuleType, raw_root: Path, product: str
) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for role, folder in (("schedule_daily", "daily"), ("constituent_5min", "min5")):
        for month, path in sorted(
            module.discover_contracts(raw_root, folder, "SHFE", product).items()
        ):
            entries.append(
                {
                    "role": role,
                    "month": month,
                    "path": f"{folder}/{path.name}",
                    "sha256": sha256_file(path),
                }
            )
    return entries


def _pin_discovery(
    module: types.ModuleType, raw_root: Path, entries: list[dict[str, str]]
) -> None:
    pinned: dict[tuple[str, str, str], dict[str, Path]] = {}
    for entry in entries:
        folder = entry["path"].split("/", 1)[0]
        pinned.setdefault((folder, "SHFE", entry["product"]), {})[entry["month"]] = (
            raw_root / entry["path"]
        )

    def exact(_root: Path, folder: str, exchange: str, product: str) -> dict[str, Path]:
        return pinned.get((folder, exchange, product), {}).copy()

    module.discover_contracts = exact
    module._SCHEDULE_CACHE.clear()


def _roll_records(schedule: dict[date, str], start: date) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    previous: str | None = None
    for trading_date, month in sorted(schedule.items()):
        if trading_date < start:
            previous = month
            continue
        records.append(
            {
                "trading_date": trading_date.isoformat(),
                "main_month": month,
                "is_roll": previous is not None and month != previous,
            }
        )
        previous = month
    return records


def _prefix_checkpoints(
    module: types.ModuleType,
    product: str,
    raw_root: Path,
    schedule: dict[date, str],
    requested: list[str],
) -> dict[str, Any]:
    original_loader = module._load_daily_panel
    panel = original_loader(raw_root, "SHFE", product)
    checked: list[str] = []
    try:
        for value in requested:
            cutoff = date.fromisoformat(value)
            module._load_daily_panel = lambda *_args, c=cutoff, **_kwargs: {
                month: frame.loc[frame.index <= c].copy()
                for month, frame in panel.items()
                if (frame.index <= c).any()
            }
            module._SCHEDULE_CACHE.clear()
            prefix = module.build_main_schedule(raw_root, "SHFE", product)
            expected = {day: month for day, month in schedule.items() if day <= cutoff}
            if prefix != expected:
                raise ValueError(f"roll schedule is not prefix-invariant at {product} {value}")
            checked.append(value)
    finally:
        module._load_daily_panel = original_loader
        module._SCHEDULE_CACHE.clear()
    return {"status": "supported_at_declared_checkpoints", "checkpoints": checked}


def _reconstruct(
    module: types.ModuleType,
    raw_root: Path,
    candidate_path: Path,
    product: str,
    window_start: str,
) -> tuple[pd.DataFrame, dict[date, str]]:
    frame = module.synthesize_continuous(raw_root, "SHFE", product, "5min")
    frame = frame[pd.to_datetime(frame["datetime"]) >= pd.Timestamp(window_start)].reset_index(
        drop=True
    )
    schedule = module.build_main_schedule(raw_root, "SHFE", product)
    calendar_dates = pd.to_datetime(frame["datetime"]).dt.date
    months = pd.Series([schedule.get(day) for day in calendar_dates]).ffill().bfill()
    frame["main_month"] = months.values
    frame["is_roll"] = frame["main_month"].ne(frame["main_month"].shift()) & (
        frame.index > 0
    )
    expected = pd.read_parquet(candidate_path)
    pd.testing.assert_frame_equal(frame, expected, check_exact=True)
    return frame, schedule


def build_manifest(
    *,
    protocol: dict[str, Any],
    protocol_path: Path,
    raw_root: Path,
    quant_repo: Path,
    paired_repo: Path,
    quant_commit: str,
    paired_commit: str,
) -> dict[str, Any]:
    """Build a manifest for exact reconstruction; never promote score inputs."""

    continuous_path = "src/data/continuous.py"
    generator_path = "scripts/data_backfill/build_cn_continuous_5min.py"
    continuous_blob = _git_blob(paired_repo, paired_commit, continuous_path)
    generator_blob = _git_blob(quant_repo, quant_commit, generator_path)
    module = _load_continuous_module(continuous_blob)
    by_product = {"au": "2021-01-01", "ag": "2024-07-01"}
    bound: list[dict[str, Any]] = []
    all_entries: list[dict[str, str]] = []
    candidates = {row["source_id"]: row for row in protocol["candidate_sources"]}
    decision_dates = {
        product: sorted(
            {
                row["decision_ts_utc"][:10]
                for row in protocol["decisions"]
                if row["universe_id"].startswith(f"shfe_{product}_")
            }
        )
        for product in by_product
    }
    for product in by_product:
        entries = _source_entries(module, raw_root, product)
        for entry in entries:
            entry["product"] = product
        all_entries.extend(entries)
    _pin_discovery(module, raw_root, all_entries)

    for product, window_start in by_product.items():
        candidate = candidates[f"shfe_{product}0_underlying_5min"]
        path = raw_root / "continuous" / candidate["filename"]
        frame, schedule = _reconstruct(module, raw_root, path, product, window_start)
        with tempfile.TemporaryDirectory() as tmp:
            rebuilt = Path(tmp) / candidate["filename"]
            frame.to_parquet(rebuilt, index=False)
            rebuilt_hash = sha256_file(rebuilt)
        if rebuilt_hash != candidate["sha256"]:
            raise ValueError(f"byte reconstruction mismatch for {candidate['filename']}")
        roll_dates = [
            day.isoformat()
            for day, month in sorted(schedule.items())
            if day >= date.fromisoformat(window_start)
            and month != schedule.get(max((d for d in schedule if d < day), default=day))
        ]
        checkpoints = sorted(set(decision_dates[product] + roll_dates + ["2026-06-08"]))
        prefix = _prefix_checkpoints(
            module, product, raw_root, schedule, checkpoints
        )
        rolls = _roll_records(schedule, date.fromisoformat(window_start))
        manifest_inputs = [
            {k: entry[k] for k in ("role", "month", "path", "sha256")}
            for entry in all_entries
            if entry["product"] == product
        ]
        bound.append(
            {
                "source_id": candidate["source_id"],
                "filename": candidate["filename"],
                "sha256": candidate["sha256"],
                "byte_size": path.stat().st_size,
                "binding_status": "exact_byte_reconstruction_supported",
                "window_start_local": window_start,
                "build_cutoff": {
                    "maximum_raw_observation": "2026-06-08T15:00:00+08:00",
                    "historical_execution_time": "unverified",
                },
                "timestamp_contract": {
                    "timezone": "Asia/Shanghai",
                    "stamp": "naive_local_period_end",
                    "night_session_trading_date": "next_exchange_session",
                },
                "raw_inputs": manifest_inputs,
                "raw_input_set_sha256": _canonical_hash(manifest_inputs),
                "causal_roll_schedule": {
                    "selection": "prior_session_OI_when_all_active_positive_else_volume",
                    "confirmation_sessions": 3,
                    "effective_session": "next_session_after_third_confirmation",
                    "records_sha256": _canonical_hash(rolls),
                    "record_count": len(rolls),
                    "prefix_invariance": prefix,
                },
                "embedded_main_month_is_roll": {
                    "status": "quarantined",
                    "reason": "generator annotates by calendar date and ffill/bfill; it is not the causal trading-date roll ledger",
                },
                "raw_acquisition_lineage": {
                    "status": "quarantined",
                    "reason": "raw Parquets have no acquisition manifest binding vendor query time, response identity, or availability",
                },
                "eligible_for_score_today": False,
            }
        )

    quarantined = []
    for candidate in protocol["candidate_sources"]:
        if candidate["kind"] not in _QUARANTINED_KINDS:
            continue
        reason = (
            "date-only IV has no availability timestamp or raw chain/query manifest"
            if candidate["kind"] == "option_ivskew"
            else "date-only availability and raw lineage are absent; observed generator uses a full-sample ATR 80th percentile"
        )
        quarantined.append(
            {
                "source_id": candidate["source_id"],
                "filename": candidate["filename"],
                "sha256": candidate["sha256"],
                "status": "quarantined",
                "reason": reason,
                "manifest_binding_attempted": False,
                "eligible_for_score_today": False,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "hermes_task": "t_6df19e2b",
        "protocol": {"path": str(protocol_path), "sha256": sha256_file(protocol_path)},
        "generator_sources": [
            {
                "repository": "quant",
                "commit": quant_commit,
                "path": generator_path,
                "sha256": _sha256_bytes(generator_blob),
            },
            {
                "repository": "paired-trading",
                "commit": paired_commit,
                "path": continuous_path,
                "sha256": _sha256_bytes(continuous_blob),
            },
        ],
        "bound_candidates": bound,
        "quarantined_candidates": quarantined,
        "capability_boundary": {
            "exact_derived_byte_reconstruction": "supported_for_two_underlying_5min_candidates",
            "causal_roll_schedule_at_declared_checkpoints": "supported",
            "embedded_roll_annotations": "quarantined",
            "raw_provider_lineage_and_availability": "quarantined",
            "date_only_iv": "quarantined",
            "full_sample_atr_regime": "blocked",
            "candidate_data_eligible_for_score_today": False,
            "performance_evaluation_allowed": False,
            "advance_m7": False,
        },
    }


def verify_manifest(
    manifest: dict[str, Any], *, raw_root: Path, quant_repo: Path, paired_repo: Path
) -> dict[str, Any]:
    validate_manifest_boundary(manifest)
    sources = {row["repository"]: row for row in manifest["generator_sources"]}
    blobs = {}
    for name, repo in (("quant", quant_repo), ("paired-trading", paired_repo)):
        source = sources[name]
        blob = _git_blob(repo, source["commit"], source["path"])
        if _sha256_bytes(blob) != source["sha256"]:
            raise ValueError(f"committed generator hash mismatch for {name}")
        blobs[name] = blob
    module = _load_continuous_module(blobs["paired-trading"])
    entries: list[dict[str, str]] = []
    for candidate in manifest["bound_candidates"]:
        if _canonical_hash(candidate["raw_inputs"]) != candidate["raw_input_set_sha256"]:
            raise ValueError(f"raw input set hash mismatch for {candidate['source_id']}")
        cutoff_contract = candidate["build_cutoff"]
        cutoff = (
            pd.Timestamp(cutoff_contract["maximum_raw_observation"])
            .tz_convert("Asia/Shanghai")
            .tz_localize(None)
        )
        for entry in candidate["raw_inputs"]:
            path = raw_root / entry["path"]
            if sha256_file(path) != entry["sha256"]:
                raise ValueError(f"raw input hash mismatch for {entry['path']}")
            observations = pd.read_parquet(path, columns=["datetime"])
            if (
                not observations.empty
                and pd.to_datetime(observations["datetime"]).max() > cutoff
            ):
                raise ValueError(f"raw input exceeds build cutoff for {entry['path']}")
            entries.append(
                {**entry, "product": candidate["source_id"].split("_")[1][:2]}
            )
    _pin_discovery(module, raw_root, entries)
    for candidate in manifest["bound_candidates"]:
        product = candidate["source_id"].split("_")[1][:2]
        path = raw_root / "continuous" / candidate["filename"]
        if sha256_file(path) != candidate["sha256"]:
            raise ValueError(f"candidate hash mismatch for {candidate['filename']}")
        frame, schedule = _reconstruct(
            module, raw_root, path, product, candidate["window_start_local"]
        )
        with tempfile.TemporaryDirectory() as tmp:
            rebuilt = Path(tmp) / candidate["filename"]
            frame.to_parquet(rebuilt, index=False)
            if sha256_file(rebuilt) != candidate["sha256"]:
                raise ValueError(f"candidate byte reconstruction mismatch for {product}")
        records = _roll_records(
            schedule, date.fromisoformat(candidate["window_start_local"])
        )
        if _canonical_hash(records) != candidate["causal_roll_schedule"]["records_sha256"]:
            raise ValueError(f"roll schedule hash mismatch for {product}")
        _prefix_checkpoints(
            module,
            product,
            raw_root,
            schedule,
            candidate["causal_roll_schedule"]["prefix_invariance"]["checkpoints"],
        )
    return {
        "ok": True,
        "bound": [row["source_id"] for row in manifest["bound_candidates"]],
        "quarantined": [row["source_id"] for row in manifest["quarantined_candidates"]],
        "advance_m7": False,
    }


def validate_manifest_boundary(manifest: dict[str, Any]) -> None:
    """Reject any widening of this task's deliberately quarantined boundary."""

    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported continuous provenance manifest schema")
    if len(manifest.get("bound_candidates", [])) != 2:
        raise ValueError("manifest must bind exactly two underlying candidates")
    if len(manifest.get("quarantined_candidates", [])) != 4:
        raise ValueError("manifest must quarantine exactly four date-only candidates")
    if {row["source_id"] for row in manifest["bound_candidates"]} != {
        "shfe_au0_underlying_5min",
        "shfe_ag0_underlying_5min",
    }:
        raise ValueError("only the two underlying candidates may be bound")
    for candidate in manifest["bound_candidates"]:
        if candidate["binding_status"] != "exact_byte_reconstruction_supported":
            raise ValueError("underlying binding cannot exceed exact reconstruction")
        if candidate["build_cutoff"]["historical_execution_time"] != "unverified":
            raise ValueError("historical build execution time must remain unverified")
        if candidate["raw_acquisition_lineage"]["status"] != "quarantined":
            raise ValueError("raw acquisition lineage must remain quarantined")
        if candidate["embedded_main_month_is_roll"]["status"] != "quarantined":
            raise ValueError("embedded roll annotations must remain quarantined")
        if candidate["eligible_for_score_today"]:
            raise ValueError("bound derived bytes must remain quarantined from score_today")
    if any(
        row["status"] != "quarantined"
        or row["manifest_binding_attempted"]
        or row["eligible_for_score_today"]
        for row in manifest["quarantined_candidates"]
    ):
        raise ValueError("date-only IV/regime candidates must remain quarantined")
    boundary = manifest["capability_boundary"]
    if (
        boundary["date_only_iv"] != "quarantined"
        or boundary["full_sample_atr_regime"] != "blocked"
        or boundary["candidate_data_eligible_for_score_today"]
        or boundary["performance_evaluation_allowed"]
        or boundary["advance_m7"]
    ):
        raise ValueError("continuous provenance packet cannot promote candidates or M7")
