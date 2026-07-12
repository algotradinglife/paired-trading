from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from engine.pa_feitian.explicit_pa_alerts import (
    build_from_bound_files,
    canonical_json_bytes,
    extract_daily_bars,
    load_materialization_contract,
    scan_explicit_alerts,
    validate_alert_corpus,
    validate_materialization_contract,
    verify_bound_files,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = (
    REPO_ROOT
    / "docs/research/pa-feitian-m6-explicit-pa-alert-materialization-contract-v1.json"
)
CORPUS_PATH = (
    REPO_ROOT
    / "doc/repro/pa-feitian-m6-underlying-corpus-2026-07-12/underlying_signal_corpus_v1.json"
)


@pytest.fixture(scope="module")
def contract() -> dict:
    return load_materialization_contract(CONTRACT_PATH)


@pytest.fixture(scope="module")
def corpus() -> dict:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def test_contract_freezes_exact_strategy_input_and_boundaries(contract: dict) -> None:
    verify_bound_files(repo_root=REPO_ROOT, contract=contract)
    assert contract["frozen_before_historical_scan"] is True
    assert contract["guardrails"]["explicit_strategy_emission_only"] is True
    assert contract["guardrails"]["diagnostic_inference"] is False
    assert contract["guardrails"]["option_or_premium_path_reading"] is False
    assert contract["guardrails"]["outcomes_or_performance"] is False
    damaged = copy.deepcopy(contract)
    damaged["authoritative_strategy"]["constructor"]["min_quality"] = 0.2
    with pytest.raises(ValueError, match="strategy definition"):
        validate_materialization_contract(damaged)


def test_actual_artifact_is_deterministic_and_explicit(contract: dict) -> None:
    first = build_from_bound_files(repo_root=REPO_ROOT, contract_path=CONTRACT_PATH)
    second = build_from_bound_files(repo_root=REPO_ROOT, contract_path=CONTRACT_PATH)
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert first["coverage"] == {
        "input_records": 670,
        "input_records_by_product": {"au": 333, "ag": 337},
        "alerts": 11,
        "alerts_by_product": {"au": 7, "ag": 4},
        "cadence": "D",
        "first_trading_date": "2025-01-02",
        "last_trading_date": "2026-06-08",
    }
    assert first["alerts"]
    assert {
        (row["pattern"], row["pa_direction"], row["strategy_direction"])
        for row in first["alerts"]
    } == {("h2_bottom", "bottom", "long")}


def test_descriptive_diagnostics_cannot_create_or_change_alerts(
    contract: dict, corpus: dict
) -> None:
    base = scan_explicit_alerts(extract_daily_bars(corpus, contract=contract), contract=contract)
    poisoned = copy.deepcopy(corpus)
    for record in poisoned["records"]:
        for level in record["levels"].values():
            level["diagnostics"] = {
                "alert": True,
                "direction": "top",
                "later_outcome": "forbidden",
            }
            level["signals"] = {
                "alert": True,
                "direction": "top",
                "generic_candlestick": "buy",
            }
    candidate = scan_explicit_alerts(
        extract_daily_bars(poisoned, contract=contract), contract=contract
    )
    assert candidate == base


def test_rejects_post_cutoff_bar_and_duplicate_identity(
    contract: dict, corpus: dict
) -> None:
    future = copy.deepcopy(corpus)
    future["records"][0]["levels"]["D"]["last_bar_timestamp_utc"] = (
        "2030-01-01T00:00:00Z"
    )
    with pytest.raises(ValueError, match="post-cutoff daily bar"):
        extract_daily_bars(future, contract=contract)

    artifact = build_from_bound_files(repo_root=REPO_ROOT, contract_path=CONTRACT_PATH)
    duplicate = copy.deepcopy(artifact)
    duplicate["alerts"].append(copy.deepcopy(duplicate["alerts"][0]))
    duplicate["coverage"]["alerts"] += 1
    duplicate["coverage"]["alerts_by_product"][duplicate["alerts"][0]["product"]] += 1
    with pytest.raises(ValueError, match="duplicate or malformed"):
        validate_alert_corpus(duplicate, contract=contract)


def test_expanding_prefix_equivalence_and_future_row_invariance(
    contract: dict, corpus: dict
) -> None:
    extracted = extract_daily_bars(corpus, contract=contract)
    full = scan_explicit_alerts(extracted, contract=contract)
    for cutoff in sorted({row["decision_ts_utc"] for row in full}):
        prefix: dict[str, tuple[pd.DataFrame, list[dict]]] = {}
        for product, (bars, refs) in extracted.items():
            keep = [i for i, ref in enumerate(refs) if ref["decision_ts_utc"] <= cutoff]
            prefix[product] = (
                bars.iloc[keep].reset_index(drop=True),
                [refs[i] for i in keep],
            )
        expected = [row for row in full if row["decision_ts_utc"] <= cutoff]
        assert scan_explicit_alerts(prefix, contract=contract) == expected

    extended = copy.deepcopy(extracted)
    bars, refs = extended["au"]
    future_bar = bars.iloc[[-1]].copy()
    future_bar["timestamp"] = pd.Timestamp("2026-07-01T07:00:00Z")
    future_bar[["open", "high", "low", "close"]] = [1.0, 2.0, 0.5, 1.5]
    extended["au"] = (
        pd.concat([bars, future_bar], ignore_index=True),
        refs
        + [
            {
                "source_record_id": "future_row_invariance_fixture",
                "trading_date": "2026-07-01",
                "decision_ts_utc": "2026-07-01T07:00:00Z",
                "bar_timestamp_utc": "2026-07-01T07:00:00Z",
            }
        ],
    )
    extended_alerts = scan_explicit_alerts(extended, contract=contract)
    assert [
        row for row in extended_alerts if row["decision_ts_utc"] <= "2026-06-08T07:00:00Z"
    ] == full


def test_public_artifact_rejects_forbidden_or_extra_fields(contract: dict) -> None:
    artifact = build_from_bound_files(repo_root=REPO_ROOT, contract_path=CONTRACT_PATH)
    damaged = copy.deepcopy(artifact)
    damaged["alerts"][0]["pnl"] = 1
    with pytest.raises(ValueError, match="alert fields"):
        validate_alert_corpus(damaged, contract=contract)


def test_materializer_source_contains_no_diagnostic_or_performance_access() -> None:
    implementation = (
        REPO_ROOT / "src/engine/pa_feitian/explicit_pa_alerts.py"
    ).read_text(encoding="utf-8")
    extract_body = implementation.split("def extract_daily_bars", 1)[1].split(
        "def scan_explicit_alerts", 1
    )[0]
    assert '["diagnostics"]' not in extract_body
    assert '["signals"]' not in extract_body
    assert "option_store" not in implementation
    assert "premium_outcome" not in implementation
