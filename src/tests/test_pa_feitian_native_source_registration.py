from __future__ import annotations

import copy
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from engine.pa_feitian.historical_backtest_gate import (
    EXPECTED_FAMILIES,
    REQUIRED_CADENCES,
    authoritative_session_slots,
)
from engine.pa_feitian.native_source_registration import (
    NativeSourceRegistrationError,
    build_audit,
    load_contract,
    validate_audit,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = (
    REPO_ROOT / "docs/research/pa-feitian-m6-native-source-registration-contract-v1.json"
)
ARTIFACT_PATH = (
    REPO_ROOT
    / "doc/repro/pa-feitian-m6-native-source-registration-2026-07-30"
    / "native_source_registration_audit_v1.json"
)
FAMILY_PARTS = {
    "SHFE.au": ("SHFE", "au"),
    "SHFE.ag": ("SHFE", "ag"),
    "CZCE.TA": ("CZCE", "TA"),
    "CZCE.MA": ("CZCE", "MA"),
    "SHFE.cu": ("SHFE", "cu"),
    "DCE.i": ("DCE", "i"),
}
SESSION_DATES = [
    date(2021, 6, 1),
    date(2022, 1, 20),
    date(2024, 1, 18),
    date(2025, 6, 18),
    date(2026, 4, 30),
]


def _native_timestamps(family: str, cadence: str) -> list[datetime]:
    if cadence == "daily":
        return [datetime.combine(session, datetime.min.time()) for session in SESSION_DATES]
    local = ZoneInfo("Asia/Shanghai")
    observed: list[datetime] = []
    for index, session in enumerate(SESSION_DATES):
        slots = [
            value.astimezone(local).replace(tzinfo=None)
            for value in authoritative_session_slots(
                instrument_family=family,
                cadence=cadence,
                session_date=session,
            )
        ]
        if index == 0:
            observed.append(min(value for value in slots if value >= datetime(2021, 6, 1)))
        elif index == len(SESSION_DATES) - 1:
            observed.append(max(value for value in slots if value <= datetime(2026, 4, 30, 15)))
        else:
            observed.append(max(slots))
    return observed


def _write_source(
    path: Path,
    *,
    family: str,
    cadence: str,
    timestamps: list[datetime] | None = None,
    provider_metadata: bool = True,
    invalid_ohlc: bool = False,
) -> None:
    observed = timestamps or _native_timestamps(family, cadence)
    highs = [102.0 + index for index in range(len(observed))]
    if invalid_ohlc:
        highs[1] = 98.0
    opens = [100.0 + index for index in range(len(observed))]
    lows = [99.0 + index for index in range(len(observed))]
    closes = [101.0 + index for index in range(len(observed))]
    table = pa.table(
        {
            "datetime": pa.array(observed, type=pa.timestamp("us")),
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [10.0 + index for index in range(len(observed))],
            "turnover": [1000.0 + 100.0 * index for index in range(len(observed))],
            "open_interest": [100.0 + index for index in range(len(observed))],
        }
    )
    if provider_metadata:
        table = table.replace_schema_metadata(
            {
                b"source_provider": b"fixture-provider-v1",
                b"timestamp_semantics": b"completed-bar-end",
                b"bar_timestamp_position": b"end",
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)


def _data_root(tmp_path: Path) -> Path:
    root = tmp_path / "private-data"
    for family in EXPECTED_FAMILIES:
        exchange, product = FAMILY_PARTS[family]
        for cadence in REQUIRED_CADENCES:
            _write_source(
                root / cadence / f"{exchange}.{product}2601.parquet",
                family=family,
                cadence=cadence,
            )
    return root


def _audit(root: Path) -> tuple[dict, dict]:
    contract = load_contract(CONTRACT_PATH)
    return (
        contract,
        build_audit(
            contract=contract,
            contract_path=CONTRACT_PATH,
            data_root=root,
            workers=2,
        ),
    )


def test_mixed_hour_grid_requires_contract_revision_and_is_deterministic(
    tmp_path: Path,
) -> None:
    root = _data_root(tmp_path)
    path = root / "hour" / "SHFE.au2601.parquet"
    timestamps = _native_timestamps("SHFE.au", "hour")
    timestamps[1] = timestamps[1].replace(hour=9, minute=0)
    _write_source(
        path,
        family="SHFE.au",
        cadence="hour",
        timestamps=timestamps,
    )

    contract, first = _audit(root)
    _, second = _audit(root)

    assert first == second
    assert first["verdict"]["status"] == "contract_revision_required"
    assert first["verdict"]["approved_native_source_version_registered"] is False
    cell = next(
        row
        for row in first["cells"]
        if row["instrument_family"] == "SHFE.au" and row["cadence"] == "hour"
    )
    assert cell["source_to_candidate_accounting"]["unexplained_timestamp_rows"] == 1
    assert cell["materialization_status"] == "not_emitted_fail_closed"
    validate_audit(first, contract=contract)

    public_text = json.dumps(first, sort_keys=True)
    assert ".parquet" not in public_text
    assert str(tmp_path) not in public_text
    assert "SHFE.au2601" not in public_text


def test_ohlc_finding_is_data_blocked(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    _write_source(
        root / "daily" / "CZCE.TA2601.parquet",
        family="CZCE.TA",
        cadence="daily",
        invalid_ohlc=True,
    )

    _, audit = _audit(root)

    assert audit["verdict"]["status"] == "data_blocked"
    assert "ohlc_quality_findings_present" in audit["verdict"]["reason_codes"]
    assert audit["verdict"]["required_next_actions"] == [
        "repair_or_replace_the_invalid_required_source_cells",
        "revise_and_review_a_lossless_source_specific_timestamp_normalization_contract",
    ]


def test_missing_provider_semantics_blocks_intraday_registration(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    _write_source(
        root / "min15" / "DCE.i2601.parquet",
        family="DCE.i",
        cadence="min15",
        provider_metadata=False,
    )

    _, audit = _audit(root)

    assert audit["verdict"]["status"] == "contract_revision_required"
    assert "provider_bar_end_semantics_unbound" in audit["verdict"]["reason_codes"]


def test_missing_required_cell_is_data_blocked(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    (root / "daily" / "SHFE.au2601.parquet").unlink()

    _, audit = _audit(root)

    assert audit["verdict"]["status"] == "data_blocked"
    assert "required_source_cell_missing" in audit["verdict"]["reason_codes"]


def test_validator_rejects_recursive_raw_or_outcome_additions(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    path = root / "hour" / "SHFE.au2601.parquet"
    timestamps = _native_timestamps("SHFE.au", "hour")
    timestamps[1] = timestamps[1].replace(hour=9, minute=0)
    _write_source(path, family="SHFE.au", cadence="hour", timestamps=timestamps)
    contract, audit = _audit(root)

    raw = copy.deepcopy(audit)
    raw["cells"][0]["raw_rows"] = [{"close": 100.0}]
    with pytest.raises(NativeSourceRegistrationError):
        validate_audit(raw, contract=contract)

    outcome = copy.deepcopy(audit)
    outcome["cells"][0]["quality"]["strategy_outcome"] = 1.0
    with pytest.raises(NativeSourceRegistrationError):
        validate_audit(outcome, contract=contract)

    inconsistent = copy.deepcopy(audit)
    inconsistent["source"]["source_row_count"] += 1
    with pytest.raises(NativeSourceRegistrationError):
        validate_audit(inconsistent, contract=contract)


def test_source_symlinks_are_not_admitted_to_the_matrix(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    source = root / "daily" / "SHFE.au2601.parquet"
    source.rename(source.with_suffix(".real"))
    source.symlink_to(source.with_suffix(".real"))
    contract = load_contract(CONTRACT_PATH)
    audit = build_audit(
        contract=contract,
        contract_path=CONTRACT_PATH,
        data_root=root,
        workers=1,
    )
    assert audit["verdict"]["status"] == "data_blocked"
    assert "required_source_cell_missing" in audit["verdict"]["reason_codes"]


def test_unreadable_or_wrong_timestamp_schema_is_data_blocked(tmp_path: Path) -> None:
    corrupt_root = _data_root(tmp_path / "corrupt")
    (corrupt_root / "daily" / "SHFE.au2601.parquet").write_bytes(b"not parquet")
    _, corrupt = _audit(corrupt_root)
    assert corrupt["verdict"]["status"] == "data_blocked"
    assert "source_file_unreadable_or_invalid" in corrupt["verdict"]["reason_codes"]

    wrong_type_root = _data_root(tmp_path / "wrong-type")
    path = wrong_type_root / "daily" / "SHFE.au2601.parquet"
    table = pa.table(
        {
            "datetime": [session.isoformat() for session in SESSION_DATES],
            "open": [100.0] * len(SESSION_DATES),
            "high": [101.0] * len(SESSION_DATES),
            "low": [99.0] * len(SESSION_DATES),
            "close": [100.0] * len(SESSION_DATES),
            "volume": [1.0] * len(SESSION_DATES),
            "open_interest": [1.0] * len(SESSION_DATES),
        }
    )
    pq.write_table(table, path)
    _, wrong_type = _audit(wrong_type_root)
    assert wrong_type["verdict"]["status"] == "data_blocked"
    assert "timestamp_storage_contract_mismatch" in wrong_type["verdict"]["reason_codes"]
    assert "unusable_timestamps_present" in wrong_type["verdict"]["reason_codes"]


def test_daily_authoritative_close_is_accepted_and_recent_truncation_blocks(
    tmp_path: Path,
) -> None:
    root = _data_root(tmp_path)
    daily_path = root / "daily" / "SHFE.au2601.parquet"
    _write_source(
        daily_path,
        family="SHFE.au",
        cadence="daily",
        timestamps=[
            datetime.combine(session, datetime.min.time()).replace(hour=15)
            for session in SESSION_DATES
        ],
    )
    _, accepted = _audit(root)
    daily = next(
        cell
        for cell in accepted["cells"]
        if cell["instrument_family"] == "SHFE.au" and cell["cadence"] == "daily"
    )
    assert daily["source_to_candidate_accounting"]["unexplained_timestamp_rows"] == 0
    assert "formal_horizon_coverage_missing" not in daily["registration_blockers"]

    _write_source(
        daily_path,
        family="SHFE.au",
        cadence="daily",
        timestamps=[
            datetime.combine(session, datetime.min.time()) for session in SESSION_DATES[:-1]
        ],
    )
    _, truncated = _audit(root)
    assert truncated["verdict"]["status"] == "data_blocked"
    assert "formal_horizon_coverage_missing" in truncated["verdict"]["reason_codes"]


def test_case_variant_identity_collision_and_only_candidate_duplicates_block(
    tmp_path: Path,
) -> None:
    root = _data_root(tmp_path)
    _write_source(
        root / "daily" / "shfe.AU2601.parquet",
        family="SHFE.au",
        cadence="daily",
    )
    _, collision = _audit(root)
    assert collision["verdict"]["status"] == "data_blocked"
    assert "duplicate_normalized_source_identity" in collision["verdict"]["reason_codes"]

    clean_root = _data_root(tmp_path / "prehistory")
    timestamps = [
        datetime(2021, 5, 1),
        datetime(2021, 5, 1),
        *[datetime.combine(session, datetime.min.time()) for session in SESSION_DATES],
    ]
    _write_source(
        clean_root / "daily" / "SHFE.au2601.parquet",
        family="SHFE.au",
        cadence="daily",
        timestamps=timestamps,
    )
    _, prehistory = _audit(clean_root)
    daily = next(
        cell
        for cell in prehistory["cells"]
        if cell["instrument_family"] == "SHFE.au" and cell["cadence"] == "daily"
    )
    assert daily["source_to_candidate_accounting"]["prehistory_rows_excluded"] == 2
    assert daily["quality"]["duplicate_contract_timestamp_rows"] == 0


def test_contract_and_audit_validation_rejects_identity_or_evidence_forgery(
    tmp_path: Path,
) -> None:
    contract, audit = _audit(_data_root(tmp_path))

    drifted_contract = copy.deepcopy(contract)
    drifted_contract["output"]["raw_rows"] = True
    with pytest.raises(NativeSourceRegistrationError):
        validate_audit(audit, contract=drifted_contract)

    wrong_hash = copy.deepcopy(audit)
    wrong_hash["contract_sha256"] = "sha256:" + "f" * 64
    with pytest.raises(NativeSourceRegistrationError):
        validate_audit(wrong_hash, contract=contract)

    wrong_identity = copy.deepcopy(audit)
    wrong_identity["audit_id"] = "forged-audit"
    with pytest.raises(NativeSourceRegistrationError):
        validate_audit(wrong_identity, contract=contract)

    forged_blocker = copy.deepcopy(audit)
    forged_blocker["cells"][0]["registration_blockers"].append(
        "strategy_outcome_win_rate_99_percent"
    )
    forged_blocker["cells"][0]["registration_blockers"].sort()
    forged_blocker["verdict"]["reason_codes"] = sorted(
        set(forged_blocker["verdict"]["reason_codes"]) | {"strategy_outcome_win_rate_99_percent"}
    )
    with pytest.raises(NativeSourceRegistrationError):
        validate_audit(forged_blocker, contract=contract)

    missing_evidence_blocker = copy.deepcopy(audit)
    cell = next(
        value
        for value in missing_evidence_blocker["cells"]
        if "provider_bar_end_semantics_unbound" in value["registration_blockers"]
    )
    cell["registration_blockers"].remove("provider_bar_end_semantics_unbound")
    with pytest.raises(NativeSourceRegistrationError):
        validate_audit(missing_evidence_blocker, contract=contract)


def test_cli_writes_public_audit_without_overwriting_inputs(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    path = root / "hour" / "SHFE.au2601.parquet"
    timestamps = _native_timestamps("SHFE.au", "hour")
    timestamps[1] = timestamps[1].replace(hour=9, minute=0)
    _write_source(path, family="SHFE.au", cadence="hour", timestamps=timestamps)
    output = tmp_path / "audit.json"

    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "src/scripts/build_pa_feitian_native_source_registration.py"),
            "--contract",
            str(CONTRACT_PATH),
            "--data-root",
            str(root),
            "--output",
            str(output),
            "--workers",
            "2",
        ],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    observed = json.loads(output.read_text(encoding="utf-8"))
    assert observed["verdict"]["status"] == "contract_revision_required"

    with pytest.raises(subprocess.CalledProcessError):
        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "src/scripts/build_pa_feitian_native_source_registration.py"),
                "--contract",
                str(CONTRACT_PATH),
                "--data-root",
                str(root),
                "--output",
                str(CONTRACT_PATH),
            ],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

    protected_source = root / "daily" / "SHFE.au2601.parquet"
    protected_bytes = protected_source.read_bytes()
    with pytest.raises(subprocess.CalledProcessError):
        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "src/scripts/build_pa_feitian_native_source_registration.py"),
                "--contract",
                str(CONTRACT_PATH),
                "--data-root",
                str(root),
                "--output",
                str(protected_source),
            ],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
    assert protected_source.read_bytes() == protected_bytes

    linked_root = tmp_path / "linked-data"
    linked_root.symlink_to(root, target_is_directory=True)
    with pytest.raises(subprocess.CalledProcessError):
        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "src/scripts/build_pa_feitian_native_source_registration.py"),
                "--contract",
                str(CONTRACT_PATH),
                "--data-root",
                str(linked_root),
                "--output",
                str(output),
            ],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )


def test_committed_real_source_audit_is_valid() -> None:
    contract = load_contract(CONTRACT_PATH)
    audit = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))

    validate_audit(audit, contract=contract)
    assert audit["verdict"]["status"] == "data_blocked"
    assert audit["source"]["matrix_cell_count"] == 18
    assert audit["source"]["source_file_count"] > 0
    assert audit["source_version_candidate"]["native_source_version_manifest_sha256"] is None
