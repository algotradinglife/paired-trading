from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from engine.pa_feitian.liquid_premium_membership import (
    ARTIFACT_FIELDS,
    COVERAGE_DIMENSIONS,
    COVERAGE_FIELDS,
    MEMBER_FIELDS,
    load_contract,
    read_file_units,
    validate_artifact,
    validate_contract,
    verify_bound_inputs,
    verify_inventory,
)
from engine.pa_feitian.liquid_premium_evidence import _inventory_digest


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "docs/research/pa-feitian-m6-liquid-premium-membership-contract-v1.json"
ARTIFACT_PATH = (
    ROOT
    / "doc/repro/pa-feitian-m6-unit-membership-2026-07-12/liquid_premium_membership_v1.json"
)


def _frame() -> pd.DataFrame:
    timestamps = pd.date_range("2025-01-02 09:00", "2025-01-02 15:00", freq="5min")
    return pd.DataFrame(
        {
            "datetime": timestamps,
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.0,
            "volume": 10.0,
            "turnover": 100.0,
            "open_interest": 600.0,
        }
    )


def test_contract_preserves_bare_k_membership_boundary() -> None:
    contract = load_contract(CONTRACT_PATH)
    assert contract["hermes_task"] == "t_02ba3dea"
    assert contract["frozen_before_external_option_data_inspection"] is True
    assert contract["frozen_boundary"]["historical_bid_ask_required"] is False
    assert contract["frozen_boundary"]["contract_delta_required"] is False
    assert contract["frozen_boundary"]["exact_expiry_or_dte_required"] is False
    assert contract["membership_output"]["member_fields_exactly"] == list(MEMBER_FIELDS)


def test_contract_rejects_price_path_promotion() -> None:
    contract = json.loads(CONTRACT_PATH.read_text())
    contract["membership_output"]["premium_paths"] = True
    with pytest.raises(ValueError, match="membership-only"):
        validate_contract(contract)


def test_bound_input_hash_validation() -> None:
    contract = load_contract(CONTRACT_PATH)
    verify_bound_inputs(contract, ROOT)
    changed = json.loads(CONTRACT_PATH.read_text())
    changed["bound_inputs"][0]["sha256"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_bound_inputs(changed, ROOT)


def test_post_cutoff_row_cannot_change_eligibility(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.parquet"
    amended_path = tmp_path / "amended.parquet"
    baseline = _frame()
    baseline.to_parquet(baseline_path, index=False)
    future = baseline.iloc[[-1]].copy()
    future["datetime"] = pd.Timestamp("2025-01-02 21:00")
    future[["open", "high", "low", "close"]] = 999999.0
    pd.concat([baseline, future], ignore_index=True).to_parquet(amended_path, index=False)
    kwargs = {"cadence_minutes": 5, "first_day": date(2025, 1, 2), "last_day": date(2025, 1, 2)}
    before = read_file_units(baseline_path, **kwargs)
    after = read_file_units(amended_path, **kwargs)
    assert before[0]["eligible"] is True
    assert after[0]["eligible"] is True
    assert before[0]["local_date"] == after[0]["local_date"]
    assert after[0]["source_rows_after_cutoff_excluded"] == 1


def test_missing_schema_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "missing.parquet"
    _frame().drop(columns=["turnover"]).to_parquet(path, index=False)
    with pytest.raises(ValueError, match="missing_required_schema"):
        read_file_units(path, cadence_minutes=5, first_day=date(2025, 1, 2), last_day=date(2025, 1, 2))


def test_missing_and_unexpected_inventory_fail_closed(tmp_path: Path) -> None:
    cadence = tmp_path / "min5"
    cadence.mkdir()
    one = cadence / "SHFE.au2501C400.parquet"
    two = cadence / "SHFE.au2501P400.parquet"
    one.touch()
    expected = {
        "product": "au",
        "cadence": "min5",
        "source_files": 2,
        "source_inventory_sha256": "unused",
    }
    with pytest.raises(ValueError, match="missing_expected_file"):
        verify_inventory([one], tmp_path, expected)
    two.touch()
    expected["source_files"] = 1
    with pytest.raises(ValueError, match="unexpected_inventory_file"):
        verify_inventory([one, two], tmp_path, expected)
    expected["source_files"] = 2
    expected["source_inventory_sha256"] = _inventory_digest([one, two], tmp_path)
    verify_inventory([one, two], tmp_path, expected)


def test_artifact_rejects_non_allowlisted_member_field() -> None:
    contract = load_contract(CONTRACT_PATH)
    artifact = json.loads(ARTIFACT_PATH.read_text())
    artifact["members"] = []
    with pytest.raises(ValueError, match="reconcile"):
        validate_artifact(artifact, contract=contract)
    artifact["members"] = [{field: "x" for field in MEMBER_FIELDS} | {"close": 10}]
    with pytest.raises(ValueError, match="allowlist"):
        validate_artifact(artifact, contract=contract)


def test_artifact_rejects_injected_top_level_raw_field() -> None:
    contract = load_contract(CONTRACT_PATH)
    artifact = json.loads(ARTIFACT_PATH.read_text())
    artifact["raw_rows"] = []
    with pytest.raises(ValueError, match="artifact fields differ"):
        validate_artifact(artifact, contract=contract)


def test_artifact_rejects_injected_coverage_field() -> None:
    contract = load_contract(CONTRACT_PATH)
    artifact = json.loads(ARTIFACT_PATH.read_text())
    artifact["coverage"][0]["close"] = 10.0
    with pytest.raises(ValueError, match="coverage fields differ"):
        validate_artifact(artifact, contract=contract)


def test_artifact_rejects_coverage_dimension_drift() -> None:
    contract = load_contract(CONTRACT_PATH)
    artifact = json.loads(ARTIFACT_PATH.read_text())
    artifact["coverage"] = deepcopy(artifact["coverage"])
    artifact["coverage"][0]["product"] = "ag"
    with pytest.raises(ValueError, match="coverage dimensions"):
        validate_artifact(artifact, contract=contract)


def test_committed_artifact_is_public_safe_and_reconciled() -> None:
    contract = load_contract(CONTRACT_PATH)
    artifact = json.loads(ARTIFACT_PATH.read_text())
    validate_artifact(artifact, contract=contract)
    assert len(artifact["members"]) == 47_079
    assert artifact["contract"]["freeze_commit"] == "e81d283fac967db06932cd2bc3bdf5eeab8e8ef4"
    assert set(artifact) == set(ARTIFACT_FIELDS)
    assert [
        (row["product"], row["cadence"]) for row in artifact["coverage"]
    ] == list(COVERAGE_DIMENSIONS)
    assert all(set(row) == set(COVERAGE_FIELDS) for row in artifact["coverage"])
    assert all(set(member) == set(MEMBER_FIELDS) for member in artifact["members"])
