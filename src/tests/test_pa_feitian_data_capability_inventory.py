from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine.pa_feitian.data_capability_inventory import (
    DataCapabilityInventoryError,
    build_inventory,
    load_contract,
    pretty_json_bytes,
    sha256_file,
    validate_contract,
    validate_inventory,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "docs/research/pa-feitian-phase1-data-capability-contract-v1.json"
ARTIFACT_PATH = (
    REPO_ROOT
    / "doc/repro/pa-feitian-phase1-data-capability-2026-07-30"
    / "candidate_capability_inventory_v1.json"
)


def _build() -> tuple[dict, dict]:
    contract = load_contract(CONTRACT_PATH)
    return (
        contract,
        build_inventory(
            contract=contract,
            contract_path=CONTRACT_PATH,
            repo_root=REPO_ROOT,
        ),
    )


def test_contract_freezes_candidate_universe_and_experiment_scope() -> None:
    contract = load_contract(CONTRACT_PATH)
    assert [row["instrument_family"] for row in contract["candidate_universe"]] == [
        "SHFE.au",
        "SHFE.ag",
        "CZCE.TA",
        "CZCE.MA",
        "SHFE.cu",
        "DCE.i",
    ]
    assert contract["p1_exp_001"]["required_universe"] == ["SHFE.ag", "SHFE.au"]
    assert contract["audit_cadences"] == ["daily", "hour", "min15", "min5"]

    changed = copy.deepcopy(contract)
    changed["candidate_universe"].pop()
    with pytest.raises(DataCapabilityInventoryError, match="candidate universe"):
        validate_contract(changed)


def test_contract_rejects_current_time_and_ranking_drift() -> None:
    contract = load_contract(CONTRACT_PATH)
    current_time = copy.deepcopy(contract)
    current_time["freshness_policy"]["implicit_current_time"] = True
    with pytest.raises(DataCapabilityInventoryError, match="current time"):
        validate_contract(current_time)

    ranked = copy.deepcopy(contract)
    ranked["liquidity_proxy"]["minimum_pass_rate"] = 0.05
    with pytest.raises(DataCapabilityInventoryError, match="create a gate"):
        validate_contract(ranked)


def test_bound_source_hash_drift_fails_closed() -> None:
    contract = load_contract(CONTRACT_PATH)
    contract["bound_inputs"][3]["sha256"] = "sha256:" + "0" * 64
    with pytest.raises(DataCapabilityInventoryError, match="SHA-256 mismatch"):
        build_inventory(
            contract=contract,
            contract_path=CONTRACT_PATH,
            repo_root=REPO_ROOT,
        )


def test_inventory_separates_freshness_historical_use_and_experiment_permission() -> None:
    contract, inventory = _build()
    validate_inventory(inventory, contract=contract)
    rows = {row["instrument_family"]: row for row in inventory["decision_surface"]}

    for family in ("SHFE.au", "SHFE.ag"):
        row = rows[family]
        assert row["freshness"]["status"] == "stale"
        assert (
            row["historical_research_usability"]["retrospective_finalized_bare_k_premium_ohlc"]
            == "usable_with_limitations"
        )
        assert row["historical_research_usability"]["causal_p1_iv_experiment"] == "data_blocked"
        option_cadences = {
            cadence["cadence"]: cadence for cadence in row["option_premium_coverage"]["cadences"]
        }
        assert (
            option_cadences["min5"]["schema"]["fields"]["close"] == "present_in_all_scanned_files"
        )
        underlying_cadences = {
            cadence["cadence"]: cadence for cadence in row["underlying_coverage"]["cadences"]
        }
        assert underlying_cadences["hour"]["schema"]["fields"]["open"] == (
            "present_in_all_scanned_files"
        )
        assert underlying_cadences["min5"]["timestamp_quality"]["duplicate_rows"] == 0
        assert row["usable_for_p1_exp_001"] is False

    for family in ("CZCE.TA", "CZCE.MA", "SHFE.cu", "DCE.i"):
        row = rows[family]
        assert row["freshness"]["status"] == "stale"
        assert row["underlying_coverage"]["status"] == "present_all_declared_cadences"
        assert row["option_premium_coverage"]["status"] == "present_all_declared_cadences"
        assert (
            row["historical_research_usability"]["retrospective_finalized_bare_k_premium_ohlc"]
            == "usable_with_limitations"
        )
        assert (
            row["historical_research_usability"]["causal_p1_iv_experiment"]
            == "not_permitted_outside_frozen_universe"
        )
        assert "outside_frozen_p1_exp_001_universe" in row["fail_closed_reason"]
        assert row["usable_for_p1_exp_001"] is False


def test_liquidity_proxy_reconciles_without_ranking_or_outcomes() -> None:
    _, inventory = _build()
    rows = {row["instrument_family"]: row for row in inventory["decision_surface"]}

    au = {row["cadence"]: row for row in rows["SHFE.au"]["liquidity_proxy"]["cadences"]}
    ag = {row["cadence"]: row for row in rows["SHFE.ag"]["liquidity_proxy"]["cadences"]}
    assert au["min5"]["all_rows"] == 23_587_772
    assert au["min5"]["rows_with_any_nonzero_activity"] == 19_106_461
    assert au["min5"]["rate"] == round(19_106_461 / 23_587_772, 6)
    assert ag["min15"]["all_rows"] == 11_759_813
    assert ag["min15"]["rows_with_any_nonzero_activity"] == 9_500_460
    assert ag["min15"]["rate"] == round(9_500_460 / 11_759_813, 6)
    assert rows["SHFE.au"]["liquidity_proxy"]["ranking_or_performance_used"] is False


def test_inventory_is_bound_to_explicit_six_family_interface_audit() -> None:
    _, inventory = _build()
    assert inventory["research_boundary"]["explicit_candidate_interface_audited"]
    assert inventory["candidate_interface_evidence"] == {
        "access": "read_only",
        "alias": ("repository://paired-trading/phase1-candidate-interface-audit-v1"),
        "matched_candidate_files": 31_141,
        "runtime_binding": "QUANT_DATA_ROOT",
        "schema_version": "pa_feitian_phase1_candidate_interface_audit_v1",
        "sha256": ("sha256:becb9bc6b65c54908eac7ad4d3e39a3591d92e65e1e07f2a3b086e096a39f795"),
        "source_inventory_sha256": (
            "sha256:9bbd6c94ca9bf8228c76cd2078513b82655990c88084297d710cd83c2f33ec8f"
        ),
    }


def test_empty_usable_universe_stops_issue_45() -> None:
    _, inventory = _build()
    assert inventory["decision"]["usable_family_count"] == 0
    assert inventory["decision"]["usable_families"] == []
    assert inventory["decision"]["status"] == "data_blocked"
    assert inventory["decision"]["p1_exp_001_action"] == "stop_as_data_blocked"
    assert inventory["decision"]["issue_45_may_start_outcome_work"] is False


def test_public_safety_rejects_outcomes_paths_filenames_and_contract_ids() -> None:
    contract, inventory = _build()

    outcome = copy.deepcopy(inventory)
    outcome["pnl"] = 1
    with pytest.raises(DataCapabilityInventoryError, match="forbidden outcome"):
        validate_inventory(outcome, contract=contract)

    local_path = copy.deepcopy(inventory)
    local_path["decision"]["next_data_gate"].append("/home/example/private")
    with pytest.raises(DataCapabilityInventoryError, match="public-safety"):
        validate_inventory(local_path, contract=contract)

    filename = copy.deepcopy(inventory)
    filename["decision"]["next_data_gate"].append("source.parquet")
    with pytest.raises(DataCapabilityInventoryError, match="public-safety"):
        validate_inventory(filename, contract=contract)

    raw_contract = copy.deepcopy(inventory)
    raw_contract["decision"]["next_data_gate"].append("SHFE.au2608C800")
    with pytest.raises(DataCapabilityInventoryError, match="contract identifier"):
        validate_inventory(raw_contract, contract=contract)


def test_committed_artifact_is_byte_identical_to_rebuild() -> None:
    contract, rebuilt = _build()
    committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    validate_inventory(committed, contract=contract)
    assert pretty_json_bytes(rebuilt) == ARTIFACT_PATH.read_bytes()
    assert committed["contract"]["sha256"] == sha256_file(CONTRACT_PATH)


def test_builder_script_emits_byte_identical_artifact(tmp_path: Path) -> None:
    output = tmp_path / "inventory.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "src/scripts/build_pa_feitian_data_capability_inventory.py"),
            "--contract",
            str(CONTRACT_PATH),
            "--repo-root",
            str(REPO_ROOT),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert output.read_bytes() == ARTIFACT_PATH.read_bytes()


def test_implementation_has_no_hidden_current_time_or_market_root_discovery() -> None:
    implementation = (REPO_ROOT / "src/engine/pa_feitian/data_capability_inventory.py").read_text(
        encoding="utf-8"
    )
    assert "date.today(" not in implementation
    assert "datetime.now(" not in implementation
    assert "time.time(" not in implementation
    assert ".glob(" not in implementation
    assert ".rglob(" not in implementation
