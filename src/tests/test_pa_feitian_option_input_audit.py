from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from engine.pa_feitian.option_input_audit import (
    canonical_json_bytes,
    load_contract,
    parse_option_filename,
    validate_audit,
    validate_contract,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "docs/research/pa-feitian-m6-option-input-audit-contract-v1.json"
ARTIFACT_PATH = (
    REPO_ROOT
    / "doc/repro/pa-feitian-m6-option-input-audit-2026-07-12"
    / "option_input_capability_audit_v1.json"
)


def test_contract_freezes_window_roots_and_boundaries() -> None:
    contract = load_contract(CONTRACT_PATH)
    assert contract["window"]["first_trading_date"] == "2025-01-02"
    assert contract["window"]["last_trading_date"] == "2026-06-08"
    assert contract["external_roots"][0]["allowed_relative_roots"] == [
        "min5",
        "min15",
        "daily",
        "continuous",
    ]
    weakened = copy.deepcopy(contract)
    weakened["guardrails"]["evaluation"] = True
    with pytest.raises(ValueError, match="guardrails"):
        validate_contract(weakened)


def test_filename_parser_and_inventory_order_are_deterministic() -> None:
    contract = load_contract(CONTRACT_PATH)
    names = [
        "SHFE.au2606P800.parquet",
        "SHFE.ag2508C10000.parquet",
        "SHFE.ag2508C9000.parquet",
        "SHFE.ag2508.parquet",
    ]
    parsed = [parse_option_filename("min5", name, contract) for name in names]
    parsed = [row for row in parsed if row is not None]
    ordered = sorted(
        parsed,
        key=lambda row: tuple(row[key] for key in contract["inventory"]["ordering"]),
    )
    assert [row["relative_path"] for row in ordered] == [
        "min5/SHFE.ag2508C9000.parquet",
        "min5/SHFE.ag2508C10000.parquet",
        "min5/SHFE.au2606P800.parquet",
    ]
    assert canonical_json_bytes(ordered) == canonical_json_bytes(ordered)
    assert parsed[-1]["strike"] == 9000.0


def test_implementation_has_no_hidden_current_time() -> None:
    implementation = (
        REPO_ROOT / "src/engine/pa_feitian/option_input_audit.py"
    ).read_text(encoding="utf-8")
    assert "date.today(" not in implementation
    assert "datetime.now(" not in implementation
    assert "time.time(" not in implementation


def test_committed_artifact_is_public_safe_and_retains_blocker() -> None:
    contract = load_contract(CONTRACT_PATH)
    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    validate_audit(artifact, contract=contract)
    encoded = canonical_json_bytes(artifact).decode()
    assert "/home/" not in encoded
    assert "/mnt/" not in encoded
    assert artifact["decision"]["faithful_option_corpus"] == "blocked"
    assert not artifact["decision"]["option_corpus_generation_warranted_now"]


@pytest.mark.parametrize("forbidden", ["pnl", "selected_contract", "win_rate"])
def test_boundary_rejects_forbidden_evaluation_fields(forbidden: str) -> None:
    contract = load_contract(CONTRACT_PATH)
    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    damaged = copy.deepcopy(artifact)
    damaged[forbidden] = 0
    with pytest.raises(ValueError, match="forbidden evaluation fields"):
        validate_audit(damaged, contract=contract)


def test_parquet_fixture_has_explicit_static_timestamp_not_current_time(tmp_path: Path) -> None:
    path = tmp_path / "SHFE.ag2508C9000.parquet"
    pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2025-01-02 14:55", "2025-01-02 15:00"]),
            "open": [1.0, 2.0],
            "high": [2.0, 3.0],
            "low": [0.5, 1.5],
            "close": [1.5, 2.5],
            "volume": [1, 2],
            "turnover": [1.5, 5.0],
            "open_interest": [10, 11],
        }
    ).to_parquet(path, index=False)
    assert pd.read_parquet(path)["datetime"].max() == pd.Timestamp("2025-01-02 15:00")
