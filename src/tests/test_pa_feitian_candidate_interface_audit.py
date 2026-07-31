from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from engine.pa_feitian.candidate_interface_audit import (
    CandidateInterfaceAuditError,
    build_audit,
    load_contract,
    validate_audit,
    validate_contract,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = (
    REPO_ROOT / "docs/research/pa-feitian-phase1-candidate-interface-audit-contract-v1.json"
)
ARTIFACT_PATH = (
    REPO_ROOT
    / "doc/repro/pa-feitian-phase1-data-capability-2026-07-30"
    / "candidate_interface_audit_v1.json"
)


def _table(*, duplicate: bool = False, violation: bool = False) -> pa.Table:
    timestamps = [
        datetime(2026, 7, 28, 14, 55),
        datetime(2026, 7, 28, 15, 0),
    ]
    if duplicate:
        timestamps[1] = timestamps[0]
    return pa.table(
        {
            "datetime": timestamps,
            "open": [10.0, 11.0],
            "high": [12.0, 10.0 if violation else 13.0],
            "low": [9.0, 10.0],
            "close": [11.0, 12.0],
            "volume": [0, 4],
            "turnover": [0.0, 8.0],
            "open_interest": [5, 6],
        }
    )


def _write_fixture_root(root: Path) -> None:
    option_prefixes = {
        "SHFE.au": "SHFE.au",
        "SHFE.ag": "SHFE.ag",
        "CZCE.TA": "CZCE.ta",
        "CZCE.MA": "CZCE.ma",
        "SHFE.cu": "SHFE.cu",
        "DCE.i": "DCE.i",
    }
    month_width = {
        "SHFE.au": "2608",
        "SHFE.ag": "2608",
        "CZCE.TA": "608",
        "CZCE.MA": "608",
        "SHFE.cu": "2608",
        "DCE.i": "2608",
    }
    for cadence in ("daily", "hour", "min15", "min5"):
        cadence_root = root / cadence
        cadence_root.mkdir(parents=True)
        for index, (family, prefix) in enumerate(option_prefixes.items()):
            month = month_width[family]
            if family == "DCE.i":
                option_suffix = f"{month}-C-100"
            elif family in {"CZCE.TA", "CZCE.MA"}:
                option_suffix = f"{month}c100"
            else:
                option_suffix = f"{month}C100"
            pq.write_table(
                _table(
                    duplicate=family == "SHFE.au" and cadence == "min5",
                    violation=family == "SHFE.ag" and cadence == "min15",
                ),
                cadence_root / f"{prefix}{option_suffix}.parquet",
            )
            exchange, product = family.split(".")
            pq.write_table(
                _table(),
                cadence_root / f"{exchange}.{product}{month}.parquet",
            )
            if index == 0:
                (cadence_root / "unrelated.txt").write_text("ignored", encoding="utf-8")


def _build(tmp_path: Path) -> tuple[dict, dict]:
    root = tmp_path / "quant"
    _write_fixture_root(root)
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


def test_contract_freezes_six_families_cadences_and_read_only_boundary() -> None:
    contract = load_contract(CONTRACT_PATH)
    assert [row["instrument_family"] for row in contract["candidate_universe"]] == [
        "SHFE.au",
        "SHFE.ag",
        "CZCE.TA",
        "CZCE.MA",
        "SHFE.cu",
        "DCE.i",
    ]
    assert contract["cadences"] == ["daily", "hour", "min15", "min5"]
    assert contract["runtime_input"]["binding"] == "QUANT_DATA_ROOT"
    assert contract["runtime_input"]["access"] == "read_only"

    weakened = copy.deepcopy(contract)
    weakened["guardrails"]["instrument_ranking"] = True
    with pytest.raises(CandidateInterfaceAuditError, match="weakened"):
        validate_contract(weakened)

    grammar_drift = copy.deepcopy(contract)
    grammar_drift["filename_interface_grammar"]["case_insensitive_family_prefix"] = False
    with pytest.raises(CandidateInterfaceAuditError, match="grammar"):
        validate_contract(grammar_drift)


def test_audit_classifies_underlying_and_option_case_variants(tmp_path: Path) -> None:
    contract, audit = _build(tmp_path)
    validate_audit(audit, contract=contract)
    rows = {row["instrument_family"]: row for row in audit["decision_surface"]}

    for family in rows:
        for cadence in rows[family]["cadences"]:
            assert cadence["matched_files"] == 2
            assert cadence["interfaces"]["underlying"]["matched_files"] == 1
            assert cadence["interfaces"]["option_premium"]["matched_files"] == 1
            assert cadence["interfaces"]["option_premium"]["rows"] == 2


def test_audit_reports_freshness_schema_duplicates_ohlc_and_activity(
    tmp_path: Path,
) -> None:
    _, audit = _build(tmp_path)
    rows = {row["instrument_family"]: row for row in audit["decision_surface"]}
    au = {row["cadence"]: row for row in rows["SHFE.au"]["cadences"]}["min5"]["interfaces"][
        "option_premium"
    ]
    ag = {row["cadence"]: row for row in rows["SHFE.ag"]["cadences"]}["min15"]["interfaces"][
        "option_premium"
    ]

    assert au["freshness"]["status"] == "fresh"
    assert au["schema"]["consistent"] is True
    assert au["timestamp_quality"]["duplicate_rows"] == 1
    assert ag["ohlc_quality"]["violation_rows"] == 1
    assert au["activity_fields"]["turnover"]["nonzero_rows"] == 1
    assert au["liquidity_proxy"] == {
        "all_rows": 2,
        "minimum_pass_rate": None,
        "name": "rows_with_any_observed_nonzero_activity_rate",
        "ranking_or_outcomes_used": False,
        "rate": 1.0,
        "rows_with_any_nonzero_activity": 2,
    }


def test_audit_public_output_omits_paths_filenames_contract_ids_and_rows(
    tmp_path: Path,
) -> None:
    _, audit = _build(tmp_path)
    encoded = json.dumps(audit, sort_keys=True)
    assert str(tmp_path) not in encoded
    assert ".parquet" not in encoded
    assert "SHFE.au2608" not in encoded
    assert audit["source"]["runtime_binding"] == "QUANT_DATA_ROOT"
    assert audit["public_safety"]["raw_rows"] is False
    assert all("records" not in row for row in audit["decision_surface"])


def test_missing_cadence_root_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "quant"
    root.mkdir()
    contract = load_contract(CONTRACT_PATH)
    with pytest.raises(CandidateInterfaceAuditError, match="cadence root"):
        build_audit(
            contract=contract,
            contract_path=CONTRACT_PATH,
            data_root=root,
        )


def test_committed_candidate_interface_artifact_is_valid() -> None:
    contract = load_contract(CONTRACT_PATH)
    audit = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    validate_audit(audit, contract=contract)
    assert audit["source"]["matched_candidate_files"] > 0
