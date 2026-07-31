from __future__ import annotations

import copy
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import engine.pa_feitian.historical_backtest_gate as gate_module
from engine.pa_feitian.historical_backtest_gate import (
    HistoricalBacktestGateError,
    authoritative_session_slots,
    build_authoritative_calendar_binding,
    build_filtered_content_binding,
    build_gate_profile,
    build_native_source_version_manifest,
    canonical_hash,
    evaluate_gate_request,
    load_contract,
    pretty_json_bytes,
    sha256_bytes,
    strict_json_loads,
    validate_gate_decision,
    validate_gate_profile,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = (
    REPO_ROOT / "docs/research/pa-feitian-m6-historical-backtest-data-gate-contract-v1.json"
)
PROFILE_PATH = (
    REPO_ROOT
    / "doc/repro/pa-feitian-m6-historical-backtest-data-gate-2026-07-30"
    / "historical_backtest_data_gate_profile_v1.json"
)
FAMILIES = ["SHFE.au", "SHFE.ag", "CZCE.TA", "CZCE.MA", "SHFE.cu", "DCE.i"]
CADENCES = ["daily", "hour", "min15"]
DECISION_CUTOFF = "2026-01-20T07:00:00Z"
PRODUCTION_CONTRACT_SHA256 = gate_module.FROZEN_CONTRACT_SHA256


@pytest.fixture(autouse=True)
def _restore_frozen_contract_digest():
    yield
    gate_module.FROZEN_CONTRACT_SHA256 = PRODUCTION_CONTRACT_SHA256


def _records(
    family: str,
    *,
    cadence: str = "daily",
    count: int = 20,
    end_utc: datetime | None = None,
) -> list[dict]:
    end = end_utc or datetime(2026, 1, 20, 7, tzinfo=UTC)
    slots: list[datetime] = []
    candidate = end.astimezone().date() + timedelta(days=8)
    floor = candidate - timedelta(days=80)
    while candidate >= floor and len(slots) < count:
        slots.extend(
            observed
            for observed in authoritative_session_slots(
                instrument_family=family,
                cadence=cadence,
                session_date=candidate,
            )
            if observed <= end
        )
        candidate -= timedelta(days=1)
    selected = sorted(set(slots))[-count:]
    if len(selected) != count:
        raise AssertionError("fixture could not materialize enough authoritative slots")
    return [
        {
            "contract_id": f"{family}fixture",
            "datetime": observed.isoformat(),
            "open": 100.0 + index,
            "high": 102.0 + index,
            "low": 99.0 + index,
            "close": 101.0 + index,
            "volume": index + 1,
            "open_interest": 1000 + index,
        }
        for index, observed in enumerate(selected)
    ]


def _snapshot(family: str, cadence: str, records: list[dict] | None = None) -> bytes:
    return pretty_json_bytes(
        {
            "schema_version": "pa_feitian_causal_underlying_snapshot_v1",
            "instrument_family": family,
            "cadence": cadence,
            "records": records or _records(family, cadence=cadence),
        }
    )


def _binding(
    *,
    family: str = "SHFE.au",
    cadence: str = "daily",
    records: list[dict] | None = None,
) -> tuple[dict, bytes]:
    binding_id = f"{family.lower().replace('.', '-')}-{cadence}"
    snapshot = _snapshot(family, cadence, records)
    matrix = {
        (matrix_family, matrix_cadence): _snapshot(matrix_family, matrix_cadence)
        for matrix_family in FAMILIES
        for matrix_cadence in CADENCES
    }
    matrix[(family, cadence)] = snapshot
    manifest = build_native_source_version_manifest(
        source_version_id="fixture-native-source-v1",
        finalized_at_utc="2026-01-22T08:00:00Z",
        source_snapshots=matrix,
    )
    binding = build_filtered_content_binding(
        binding_id=binding_id,
        instrument_family=family,
        interface="underlying",
        cadence=cadence,
        source_snapshot_bytes=snapshot,
        timestamp_field="datetime",
        identity_key_fields=["contract_id", "datetime"],
        decision_cutoff_utc=DECISION_CUTOFF,
        source_version_manifest=manifest,
    )
    return binding, snapshot


def _causal_support(manifest: bytes) -> dict[str, bytes]:
    calendar = build_authoritative_calendar_binding(decision_cutoff_utc=DECISION_CUTOFF)
    ledger = pretty_json_bytes(
        {
            "schema_version": "pa_feitian_causal_roll_ledger_binding_v1",
            "decision_cutoff_utc": DECISION_CUTOFF,
            "records": [
                {
                    "instrument_family": family,
                    "effective_session": "2026-01-20",
                    "selected_contract_id": f"{family}fixture",
                    "as_of_utc": "2026-01-19T07:00:00Z",
                }
                for family in FAMILIES
            ],
        }
    )
    return {
        "native_source_version_manifest": manifest,
        "exchange_session_calendar": calendar,
        "causal_roll_ledger": ledger,
    }


def _request(*, mode: str = "historical_replay") -> tuple[dict, dict[str, bytes], dict[str, bytes]]:
    pairs = [
        _binding(family=family, cadence=cadence) for family in FAMILIES for cadence in CADENCES
    ]
    bindings = [pair[0] for pair in pairs]
    snapshots = {pair[0]["binding_id"]: pair[1] for pair in pairs}
    matrix = {
        (binding["instrument_family"], binding["cadence"]): snapshots[binding["binding_id"]]
        for binding in bindings
    }
    manifest = pretty_json_bytes(
        build_native_source_version_manifest(
            source_version_id="fixture-native-source-v1",
            finalized_at_utc="2026-01-22T08:00:00Z",
            source_snapshots=matrix,
        )
    )
    support = _causal_support(manifest)
    request = {
        "schema_version": "pa_feitian_m6_historical_backtest_gate_request_v1",
        "request_id": "p1-exp-002-gate-fixture",
        "experiment_id": "P1-EXP-002",
        "mode": mode,
        "required_capabilities": [
            "underlying_ohlcv_oi",
            "exact_decision_close",
            "exchange_session_calendar",
            "causal_roll_ledger",
        ],
        "frozen_design": {
            "registry_sha256": (
                "sha256:f2b77c11317c1f98fe6d4c95f47b2213243322f2f3d4ed6dd1ccbf92d972afa0"
            ),
            "registry_lock_sha256": (
                "sha256:d7e36900efb91807a0960922c5cdbc5241ec4ca1988eb477ac6bc5a32c940718"
            ),
            "canonical_design_sha256": (
                "sha256:4d3026e5eb398752c3c8f207cb5e21d1b2706e7fb68d40ddf31b99132486cb65"
            ),
        },
        "causal_support": {
            "native_source_version_manifest_sha256": sha256_bytes(
                support["native_source_version_manifest"]
            ),
            "exchange_session_calendar_sha256": sha256_bytes(support["exchange_session_calendar"]),
            "causal_roll_ledger_sha256": sha256_bytes(support["causal_roll_ledger"]),
        },
        "input_bindings": bindings,
        "controls": {
            "filter_before_derivation": True,
            "outcomes_accessed": False,
            "instrument_selection_uses_outcomes": False,
            "option_inputs_accessed": False,
            "proxy_or_imputation": False,
            "bid_ask_synthesized": False,
            "delta_synthesized": False,
            "iv_synthesized": False,
            "source_refresh_performed": False,
        },
        "operational_evidence": {
            "append_only_acquisition_manifest_sha256": None,
            "point_in_time_observability_verified": False,
            "current_freshness_verified": False,
            "execution_authorized": False,
        },
    }
    return request, snapshots, support


def _approved_contract(support: dict[str, bytes]) -> dict:
    gate_module.FROZEN_CONTRACT_SHA256 = PRODUCTION_CONTRACT_SHA256
    contract = copy.deepcopy(load_contract(CONTRACT_PATH))
    contract["binding_policy"]["approved_native_source_version_manifest_sha256"] = sha256_bytes(
        support["native_source_version_manifest"]
    )
    gate_module.FROZEN_CONTRACT_SHA256 = canonical_hash(contract)
    return contract


def _replace_binding(
    request: dict,
    snapshots: dict[str, bytes],
    support: dict[str, bytes],
    binding: dict,
    snapshot: bytes,
) -> None:
    index = next(
        index
        for index, row in enumerate(request["input_bindings"])
        if row["binding_id"] == binding["binding_id"]
    )
    request["input_bindings"][index] = binding
    snapshots[binding["binding_id"]] = snapshot
    matrix = {
        (row["instrument_family"], row["cadence"]): snapshots[row["binding_id"]]
        for row in request["input_bindings"]
    }
    manifest = pretty_json_bytes(
        build_native_source_version_manifest(
            source_version_id="fixture-native-source-v1",
            finalized_at_utc="2026-01-22T08:00:00Z",
            source_snapshots=matrix,
        )
    )
    support["native_source_version_manifest"] = manifest
    request["causal_support"]["native_source_version_manifest_sha256"] = sha256_bytes(manifest)


def _profile_inputs() -> tuple[dict, dict[str, Path]]:
    contract = load_contract(CONTRACT_PATH)
    paths = {row["alias"]: REPO_ROOT / row["path"] for row in contract["bound_evidence"]}
    return contract, paths


def test_contract_binds_frozen_registry_and_exact_underlying_matrix() -> None:
    contract = load_contract(CONTRACT_PATH)
    policy = contract["p1_exp_002_input_policy"]
    assert policy["required_families"] == FAMILIES
    assert policy["required_underlying_cadences"] == CADENCES
    assert policy["option_inputs_allowed"] is False
    assert policy["min5_input_allowed"] is False
    assert policy["request_scope"] == "one_decision_timestamp"
    assert policy["formal_run_coverage"] == (
        "exactly_one_allow_decision_per_materialized_decision_timestamp"
    )
    assert {row["alias"] for row in contract["bound_evidence"]} >= {
        "hypothesis_registry_v2",
        "hypothesis_registry_v2_lock",
    }
    assert (
        contract["mode_policy"]["historical_replay"]["append_only_acquisition_manifest_required"]
        is False
    )


def test_builder_hashes_exact_snapshot_and_filters_future_rows() -> None:
    baseline, baseline_snapshot = _binding()
    future = _records("SHFE.au")
    future.append(
        {
            "contract_id": "SHFE.aufixture",
            "datetime": "2026-01-21T07:00:00Z",
            "open": 999.0,
            "high": 1000.0,
            "low": 998.0,
            "close": 999.5,
            "volume": 999,
            "open_interest": 999,
        }
    )
    observed, observed_snapshot = _binding(records=future)
    assert observed["filtered_content_sha256"] == baseline["filtered_content_sha256"]
    assert observed["source_snapshot_sha256"] != baseline["source_snapshot_sha256"]
    assert observed_snapshot != baseline_snapshot
    assert observed["row_count"] == baseline["row_count"] == 20


def test_composite_identity_allows_multi_contract_timestamp_but_rejects_duplicate_key() -> None:
    records = _records("SHFE.au")
    second = dict(records[0], contract_id="SHFE.auother")
    binding, _ = _binding(records=[*records, second])
    assert binding["duplicate_timestamp_rows"] == 0
    duplicate, _ = _binding(records=[*records, dict(records[0])])
    assert duplicate["duplicate_timestamp_rows"] == 1


@pytest.mark.parametrize("field,value", [("volume", -1), ("open_interest", None)])
def test_builder_records_nonfinite_or_negative_activity(field: str, value: object) -> None:
    records = _records("SHFE.au")
    records[0][field] = value
    binding, _ = _binding(records=records)
    assert binding["nonfinite_or_negative_activity_rows"] == 1


def test_builder_rejects_posterior_or_mislabeled_snapshot_content() -> None:
    records = _records("SHFE.au")
    records[0]["forward_close"] = 123.0
    with pytest.raises(HistoricalBacktestGateError, match="causal allowlist"):
        _binding(records=records)

    mislabeled = pretty_json_bytes(
        {
            "schema_version": "pa_feitian_causal_underlying_snapshot_v1",
            "instrument_family": "SHFE.ag",
            "cadence": "daily",
            "records": _records("SHFE.ag"),
        }
    )
    _, _, support = _request()
    with pytest.raises(HistoricalBacktestGateError, match="schema"):
        build_filtered_content_binding(
            binding_id="shfe-au-daily",
            instrument_family="SHFE.au",
            interface="underlying",
            cadence="daily",
            source_snapshot_bytes=mislabeled,
            timestamp_field="datetime",
            identity_key_fields=["contract_id", "datetime"],
            decision_cutoff_utc=DECISION_CUTOFF,
            source_version_manifest=support["native_source_version_manifest"],
        )


def test_builder_derives_exact_close_and_rejects_relabelled_native_cadence() -> None:
    before_close, _ = _binding(
        records=_records(
            "SHFE.au",
            end_utc=datetime(2026, 1, 20, 6, 59, tzinfo=UTC),
        )
    )
    assert before_close["close_timestamp_status"] == "unavailable"

    with pytest.raises(HistoricalBacktestGateError, match="native cadence"):
        _binding(cadence="hour", records=_records("SHFE.au", cadence="daily"))

    mixed = _records("SHFE.au", cadence="daily", count=3)
    mixed[-1]["datetime"] = DECISION_CUTOFF
    mixed[-2]["datetime"] = "2026-01-20T06:00:00Z"
    with pytest.raises(HistoricalBacktestGateError, match="native cadence"):
        _binding(cadence="hour", records=mixed)


def test_historical_replay_allows_only_with_independently_rebuilt_sources() -> None:
    request, snapshots, support = _request()
    contract = _approved_contract(support)
    decision = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    assert decision["decision"] == "allow"
    assert decision["reason_codes"] == []
    assert decision["binding_count"] == 18
    assert decision["manifest_binding"]["filtered_input_digest"].startswith("sha256:")
    assert decision["claim_boundary"]["finalized_vintage_historical_replay"]
    assert not decision["claim_boundary"]["issue_51_unblocked"]


def test_unregistered_or_caller_truncated_native_source_version_denies() -> None:
    request, snapshots, support = _request()
    production_contract = load_contract(CONTRACT_PATH)
    unregistered = evaluate_gate_request(
        contract=production_contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    assert unregistered["decision"] == "deny"
    assert "native_source_version_manifest_artifact_invalid" in unregistered["reason_codes"]

    attacker_contract = copy.deepcopy(production_contract)
    attacker_contract["binding_policy"]["approved_native_source_version_manifest_sha256"] = (
        sha256_bytes(support["native_source_version_manifest"])
    )
    with pytest.raises(HistoricalBacktestGateError, match="contract digest drifted"):
        evaluate_gate_request(
            contract=attacker_contract,
            request=request,
            source_snapshots=snapshots,
            causal_support_artifacts=support,
        )

    approved_contract = _approved_contract(support)
    approved_manifest_sha = approved_contract["binding_policy"][
        "approved_native_source_version_manifest_sha256"
    ]
    target = request["input_bindings"][0]
    payload = strict_json_loads(snapshots[target["binding_id"]].decode())
    payload["records"] = payload["records"][-3:]
    truncated = pretty_json_bytes(payload)
    matrix = {
        (row["instrument_family"], row["cadence"]): (
            truncated if row["binding_id"] == target["binding_id"] else snapshots[row["binding_id"]]
        )
        for row in request["input_bindings"]
    }
    caller_manifest = pretty_json_bytes(
        build_native_source_version_manifest(
            source_version_id="caller-truncated-v1",
            finalized_at_utc="2026-01-22T08:00:00Z",
            source_snapshots=matrix,
        )
    )
    caller_binding = build_filtered_content_binding(
        binding_id=target["binding_id"],
        instrument_family=target["instrument_family"],
        interface="underlying",
        cadence=target["cadence"],
        source_snapshot_bytes=truncated,
        timestamp_field="datetime",
        identity_key_fields=["contract_id", "datetime"],
        decision_cutoff_utc=DECISION_CUTOFF,
        source_version_manifest=caller_manifest,
    )
    _replace_binding(request, snapshots, support, caller_binding, truncated)
    support["native_source_version_manifest"] = caller_manifest
    request["causal_support"]["native_source_version_manifest_sha256"] = sha256_bytes(
        caller_manifest
    )
    assert sha256_bytes(caller_manifest) != approved_manifest_sha
    truncated_decision = evaluate_gate_request(
        contract=approved_contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    assert truncated_decision["decision"] == "deny"
    assert "native_source_version_manifest_artifact_invalid" in truncated_decision["reason_codes"]


def test_pre_history_rows_cannot_supply_filtered_cadence_evidence() -> None:
    pre_history_slots = sorted(
        authoritative_session_slots(
            instrument_family="SHFE.au",
            cadence="hour",
            session_date=datetime(2021, 5, 28, tzinfo=UTC).date(),
        )
    )
    records = _records("SHFE.au", cadence="hour", count=3)
    records[0]["datetime"] = pre_history_slots[-2].isoformat()
    records[1]["datetime"] = pre_history_slots[-1].isoformat()
    records[2]["datetime"] = DECISION_CUTOFF
    with pytest.raises(HistoricalBacktestGateError, match="native cadence"):
        _binding(family="SHFE.au", cadence="hour", records=records)


def test_evaluator_captures_manifest_path_once_to_prevent_split_view() -> None:
    request, snapshots, support = _request()
    contract = _approved_contract(support)
    approved = support["native_source_version_manifest"]

    class FlippingPath(type(Path())):
        reads = 0

        def read_bytes(self) -> bytes:
            type(self).reads += 1
            return approved + b"\n" if type(self).reads <= 36 else approved

    supplied = dict(support)
    supplied["native_source_version_manifest"] = FlippingPath("/unused/manifest.json")
    decision = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=supplied,
    )
    assert FlippingPath.reads == 1
    assert decision["decision"] == "deny"
    assert "native_source_version_manifest_artifact_digest_mismatch" in decision["reason_codes"]


def test_authoritative_calendar_rejects_sunday_even_if_caller_self_issues_artifact() -> None:
    sunday_cutoff = "2026-01-18T07:00:00Z"
    with pytest.raises(HistoricalBacktestGateError, match="not an exchange session"):
        build_authoritative_calendar_binding(decision_cutoff_utc=sunday_cutoff)

    request, snapshots, support = _request()
    contract = _approved_contract(support)
    for binding in request["input_bindings"]:
        binding["decision_cutoff_utc"] = sunday_cutoff
        binding["required_through_utc"] = sunday_cutoff
    calendar = strict_json_loads(support["exchange_session_calendar"].decode())
    calendar["decision_cutoff_utc"] = sunday_cutoff
    for row in calendar["records"]:
        row["session_date"] = "2026-01-18"
        row["close_utc"] = sunday_cutoff
    support["exchange_session_calendar"] = pretty_json_bytes(calendar)
    request["causal_support"]["exchange_session_calendar_sha256"] = sha256_bytes(
        support["exchange_session_calendar"]
    )
    denied = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    assert "exchange_session_calendar_artifact_invalid" in denied["reason_codes"]


def test_session_aware_cadence_preserves_genuine_gaps_and_late_listings() -> None:
    monday_slots = authoritative_session_slots(
        instrument_family="SHFE.au",
        cadence="hour",
        session_date=datetime(2026, 2, 2, tzinfo=UTC).date(),
    )
    assert datetime(2026, 2, 1, 0, tzinfo=UTC) not in monday_slots
    assert datetime(2026, 2, 1, 1, tzinfo=UTC) not in monday_slots
    post_holiday_slots = authoritative_session_slots(
        instrument_family="SHFE.au",
        cadence="hour",
        session_date=datetime(2026, 2, 24, tzinfo=UTC).date(),
    )
    assert all(observed >= datetime(2026, 2, 24, 1, tzinfo=UTC) for observed in post_holiday_slots)
    new_year_slots = authoritative_session_slots(
        instrument_family="SHFE.au",
        cadence="hour",
        session_date=datetime(2025, 1, 2, tzinfo=UTC).date(),
    )
    assert datetime(2024, 12, 31, 14, tzinfo=UTC) not in new_year_slots
    assert datetime(2024, 12, 31, 15, tzinfo=UTC) not in new_year_slots

    fake_weekend = _records("SHFE.au", cadence="hour", count=3)
    fake_weekend[0]["datetime"] = "2026-01-18T00:00:00Z"
    fake_weekend[1]["datetime"] = "2026-01-18T01:00:00Z"
    fake_weekend[2]["datetime"] = DECISION_CUTOFF
    with pytest.raises(HistoricalBacktestGateError, match="native cadence"):
        _binding(family="SHFE.au", cadence="hour", records=fake_weekend)

    gapped = _records("SHFE.au", cadence="hour", count=20)
    del gapped[5]
    del gapped[9]
    binding, _ = _binding(family="SHFE.au", cadence="hour", records=gapped)
    assert binding["row_count"] == 18
    assert binding["minimum_observation_utc"] > "2021-06-01T00:00:00Z"
    assert binding["close_timestamp_status"] == "verified"

    request, snapshots, support = _request()
    contract = _approved_contract(support)
    decision = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    assert decision["decision"] == "allow"
    assert all(
        row["row_count"] == 20 and row["maximum_observation_utc"] == DECISION_CUTOFF
        for row in decision["evaluated_bindings"]
    )


def test_missing_or_fabricated_source_evidence_denies() -> None:
    request, snapshots, support = _request()
    contract = _approved_contract(support)
    binding_id = request["input_bindings"][0]["binding_id"]
    missing = evaluate_gate_request(
        contract=contract, request=request, causal_support_artifacts=support
    )
    assert missing["decision"] == "deny"
    assert f"{binding_id}:source_snapshot_not_independently_verified" in missing["reason_codes"]

    request["input_bindings"][0]["filtered_content_sha256"] = "sha256:" + "f" * 64
    mismatched = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    assert mismatched["decision"] == "deny"
    assert f"{binding_id}:source_snapshot_evidence_mismatch" in mismatched["reason_codes"]


def test_matrix_design_calendar_roll_and_cutoff_drift_deny() -> None:
    request, snapshots, support = _request()
    contract = _approved_contract(support)
    removed = request["input_bindings"].pop()
    snapshots.pop(removed["binding_id"])
    denied = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    assert "p1_exp_002_binding_matrix_mismatch" in denied["reason_codes"]

    request, snapshots, support = _request()
    request["frozen_design"]["canonical_design_sha256"] = "sha256:" + "c" * 64
    request["causal_support"]["exchange_session_calendar_sha256"] = "sha256:" + "c" * 64
    support.pop("causal_roll_ledger")
    denied = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    assert {
        "frozen_design_binding_mismatch",
        "exchange_session_calendar_artifact_digest_mismatch",
        "causal_roll_ledger_artifact_missing",
    } <= set(denied["reason_codes"])

    request, snapshots, support = _request()
    request["input_bindings"][0]["decision_cutoff_utc"] = "2026-01-20T00:00:00Z"
    denied = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    assert "inconsistent_binding_decision_cutoffs" in denied["reason_codes"]


def test_shadow_and_live_never_gain_positive_p1_claims() -> None:
    request, snapshots, support = _request(mode="prospective_shadow")
    contract = _approved_contract(support)
    request["operational_evidence"] = {
        "append_only_acquisition_manifest_sha256": "sha256:" + "d" * 64,
        "point_in_time_observability_verified": True,
        "current_freshness_verified": True,
        "execution_authorized": False,
    }
    decision = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    assert decision["decision"] == "deny"
    assert "p1_exp_002_historical_replay_only" in decision["reason_codes"]
    assert not decision["claim_boundary"]["prospective_shadow_data_input"]
    assert not decision["claim_boundary"]["point_in_time_vendor_observability_claim"]

    request, snapshots, support = _request(mode="live")
    decision = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    assert decision["decision"] == "deny"
    assert "live_execution_outside_data_gate" in decision["reason_codes"]


def test_calendar_and_roll_artifacts_must_cross_link_to_cutoff_and_snapshots() -> None:
    request, snapshots, support = _request()
    contract = _approved_contract(support)
    calendar = strict_json_loads(support["exchange_session_calendar"].decode())
    calendar["records"][0]["session_date"] = "1999-01-01"
    support["exchange_session_calendar"] = pretty_json_bytes(calendar)
    request["causal_support"]["exchange_session_calendar_sha256"] = sha256_bytes(
        support["exchange_session_calendar"]
    )
    decision = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    assert "exchange_session_calendar_artifact_invalid" in decision["reason_codes"]

    request, snapshots, support = _request()
    ledger = strict_json_loads(support["causal_roll_ledger"].decode())
    ledger["records"][0]["selected_contract_id"] = "SHFE.audifferent"
    support["causal_roll_ledger"] = pretty_json_bytes(ledger)
    request["causal_support"]["causal_roll_ledger_sha256"] = sha256_bytes(
        support["causal_roll_ledger"]
    )
    decision = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    assert "causal_roll_ledger_artifact_invalid" in decision["reason_codes"]

    request, snapshots, support = _request()
    for cadence in CADENCES:
        records = _records("SHFE.au", cadence=cadence, count=3)
        records[0]["contract_id"] = "SHFE.audecoy"
        records[1]["contract_id"] = "SHFE.audecoy"
        binding, snapshot = _binding(
            family="SHFE.au",
            cadence=cadence,
            records=records,
        )
        _replace_binding(request, snapshots, support, binding, snapshot)
    contract = _approved_contract(support)
    decision = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    assert "causal_roll_ledger_artifact_invalid" in decision["reason_codes"]

    request, snapshots, support = _request()
    for cadence in CADENCES:
        records = _records("SHFE.au", cadence=cadence)
        records[-1]["contract_id"] = "SHFE.aunew"
        binding, snapshot = _binding(
            family="SHFE.au",
            cadence=cadence,
            records=records,
        )
        _replace_binding(request, snapshots, support, binding, snapshot)
    contract = _approved_contract(support)
    decision = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    assert "causal_roll_ledger_artifact_invalid" in decision["reason_codes"]


def test_seven_local_calendar_days_is_current_and_eight_is_stale() -> None:
    request, snapshots, support = _request()
    contract = _approved_contract(support)
    seven_days, seven_snapshot = _binding(
        records=_records(
            "SHFE.au",
            end_utc=datetime(2026, 1, 13, 7, tzinfo=UTC),
        )
    )
    _replace_binding(request, snapshots, support, seven_days, seven_snapshot)
    contract = _approved_contract(support)
    allowed = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    row = next(
        row
        for row in allowed["evaluated_bindings"]
        if row["binding_id"] == seven_days["binding_id"]
    )
    assert row["coverage_lag_days"] == 7
    assert row["freshness_status"] == "current_for_declared_cutoff"

    eight_days, eight_snapshot = _binding(
        records=_records(
            "SHFE.au",
            end_utc=datetime(2026, 1, 12, 7, tzinfo=UTC),
        )
    )
    _replace_binding(request, snapshots, support, eight_days, eight_snapshot)
    contract = _approved_contract(support)
    denied = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    assert f"{eight_days['binding_id']}:stale_required_coverage" in denied["reason_codes"]


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda request: request["input_bindings"][0].update(ohlc_violation_rows=1),
            "ohlc_violation_rows",
        ),
        (
            lambda request: request["input_bindings"][0].update(
                nonfinite_or_negative_activity_rows=1
            ),
            "nonfinite_or_negative_activity_rows",
        ),
        (
            lambda request: request["controls"].update(outcomes_accessed=True),
            "control:outcomes_accessed",
        ),
        (
            lambda request: request["controls"].update(option_inputs_accessed=True),
            "control:option_inputs_accessed",
        ),
    ],
)
def test_gate_fails_closed_for_quality_and_control_findings(mutation, reason: str) -> None:
    request, snapshots, support = _request()
    contract = _approved_contract(support)
    mutation(request)
    decision = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    assert decision["decision"] == "deny"
    assert any(reason in code for code in decision["reason_codes"])


def test_request_and_decision_allowlists_and_claim_formulas_fail_closed() -> None:
    request, snapshots, support = _request()
    contract = _approved_contract(support)
    request["unexpected"] = True
    with pytest.raises(HistoricalBacktestGateError, match="exact allowlist"):
        evaluate_gate_request(
            contract=contract,
            request=request,
            source_snapshots=snapshots,
            causal_support_artifacts=support,
        )

    request, snapshots, support = _request()
    decision = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    decision["claim_boundary"]["prospective_shadow_data_input"] = True
    with pytest.raises(HistoricalBacktestGateError, match="claim boundary"):
        validate_gate_decision(
            decision,
            contract=contract,
            request=request,
            source_snapshots=snapshots,
            causal_support_artifacts=support,
        )

    decision = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    decision["manifest_binding"]["filtered_input_digest"] = "sha256:" + "f" * 64
    with pytest.raises(HistoricalBacktestGateError, match="does not reconcile"):
        validate_gate_decision(
            decision,
            contract=contract,
            request=request,
            source_snapshots=snapshots,
            causal_support_artifacts=support,
        )

    decision = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    request["controls"]["outcomes_accessed"] = True
    with pytest.raises(HistoricalBacktestGateError, match="does not attest"):
        validate_gate_decision(
            decision,
            contract=contract,
            request=request,
            source_snapshots=snapshots,
            causal_support_artifacts=support,
        )

    request, snapshots, support = _request()
    contract = _approved_contract(support)
    decision = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    decision["claim_boundary"]["strategy_outcomes_authorized"] = 0
    with pytest.raises(HistoricalBacktestGateError, match="must be booleans"):
        validate_gate_decision(
            decision,
            contract=contract,
            request=request,
            source_snapshots=snapshots,
            causal_support_artifacts=support,
        )

    decision = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    decision["decision"] = "deny"
    decision["reason_codes"] = [1]
    with pytest.raises(HistoricalBacktestGateError, match="reasons"):
        validate_gate_decision(
            decision,
            contract=contract,
            request=request,
            source_snapshots=snapshots,
            causal_support_artifacts=support,
        )


def test_strict_json_and_public_evidence_fields_reject_ambiguous_or_unsafe_input() -> None:
    with pytest.raises(HistoricalBacktestGateError, match="duplicate JSON key"):
        strict_json_loads('{"mode":"live","mode":"historical_replay"}')

    contract = load_contract(CONTRACT_PATH)
    contract["bound_evidence"][0]["api_key"] = "not-a-real-secret"
    with pytest.raises(HistoricalBacktestGateError, match="contract digest drifted"):
        build_gate_profile(
            contract=contract,
            paths={},
        )


def test_decision_attestation_rejects_every_mutated_artifact_class() -> None:
    request, snapshots, support = _request()
    contract = _approved_contract(support)
    decision = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )
    validate_gate_decision(
        decision,
        contract=contract,
        request=request,
        source_snapshots=snapshots,
        causal_support_artifacts=support,
    )

    binding_id = next(iter(snapshots))
    mutated_snapshots = dict(snapshots)
    mutated_snapshots[binding_id] += b"\n"
    with pytest.raises(HistoricalBacktestGateError, match="does not attest"):
        validate_gate_decision(
            decision,
            contract=contract,
            request=request,
            source_snapshots=mutated_snapshots,
            causal_support_artifacts=support,
        )

    for artifact_name in (
        "native_source_version_manifest",
        "exchange_session_calendar",
        "causal_roll_ledger",
    ):
        mutated_support = dict(support)
        mutated_support[artifact_name] += b"\n"
        with pytest.raises(HistoricalBacktestGateError, match="does not attest"):
            validate_gate_decision(
                decision,
                contract=contract,
                request=request,
                source_snapshots=snapshots,
                causal_support_artifacts=mutated_support,
            )


def test_evaluator_cli_rebuilds_sources_and_rejects_ambiguous_or_symlink_output(
    tmp_path: Path,
) -> None:
    request, snapshots, support = _request()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(pretty_json_bytes(request))
    calendar_path = tmp_path / "calendar.json"
    calendar_path.write_bytes(support["exchange_session_calendar"])
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_bytes(support["causal_roll_ledger"])
    manifest_path = tmp_path / "native-source-version-manifest.json"
    manifest_path.write_bytes(support["native_source_version_manifest"])
    snapshot_args: list[str] = []
    for binding_id, content in snapshots.items():
        path = tmp_path / f"{binding_id}.json"
        path.write_bytes(content)
        snapshot_args.extend(["--source-snapshot", f"{binding_id}={path}"])
    output = tmp_path / "decision.json"
    base = [
        sys.executable,
        str(REPO_ROOT / "src/scripts/evaluate_pa_feitian_historical_backtest_gate.py"),
        "--contract",
        str(CONTRACT_PATH),
        "--request",
        str(request_path),
        *snapshot_args,
        "--exchange-session-calendar",
        str(calendar_path),
        "--causal-roll-ledger",
        str(ledger_path),
        "--native-source-version-manifest",
        str(manifest_path),
    ]
    allowed = subprocess.run(
        [*base, "--output", str(output)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert allowed.returncode == 0, allowed.stderr
    cli_decision = strict_json_loads(output.read_text())
    assert cli_decision["decision"] == "deny"
    assert "native_source_version_manifest_artifact_invalid" in cli_decision["reason_codes"]

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"mode":"live","mode":"historical_replay"}')
    rejected = subprocess.run(
        [
            *base[: base.index("--request") + 1],
            str(duplicate),
            *base[base.index("--request") + 2 :],
            "--output",
            str(tmp_path / "duplicate-decision.json"),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0
    assert "duplicate JSON key" in rejected.stderr

    victim = tmp_path / "victim.json"
    victim.write_text("preserve me")
    symlink = tmp_path / "decision-symlink.json"
    symlink.symlink_to(victim)
    rejected = subprocess.run(
        [*base, "--output", str(symlink)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0
    assert "must not be a symlink" in rejected.stderr
    assert victim.read_text() == "preserve me"


def test_profile_maps_frozen_p1_consumption_without_publishing_raw_rows() -> None:
    contract, paths = _profile_inputs()
    profile = build_gate_profile(
        contract=contract,
        paths=paths,
    )
    validate_gate_profile(profile, contract=contract)
    assert profile["engineer_surface"]["p1_exp_002_required_binding_count"] == 18
    for family in profile["candidate_interface_mapping"]:
        for cadence in family["cadences"]:
            expected = (
                "conditional_exact_run_binding_required"
                if cadence["cadence"] in CADENCES
                else "not_consumed_by_p1_exp_002"
            )
            assert cadence["interfaces"]["underlying"]["formal_historical_use"] == expected
            assert (
                cadence["interfaces"]["option_premium"]["formal_historical_use"]
                == "not_consumed_by_p1_exp_002"
            )
    _, _, support = _request()
    registered_contract = _approved_contract(support)
    registered = build_gate_profile(contract=registered_contract, paths=paths)
    assert registered["engineer_surface"]["approved_native_source_version_registered"]
    assert registered["baseline"]["p1_exp_002_gate_status"] == "not_evaluated_no_formal_run_request"


def test_profile_recursive_allowlist_rejects_raw_and_outcome_injections() -> None:
    contract, paths = _profile_inputs()
    profile = build_gate_profile(contract=contract, paths=paths)
    profile["candidate_interface_mapping"][0]["cadences"][0]["interfaces"]["underlying"][
        "raw_rows"
    ] = [{"close": 1.0}]
    with pytest.raises(HistoricalBacktestGateError, match="exact allowlist"):
        validate_gate_profile(profile, contract=contract)

    profile = build_gate_profile(contract=contract, paths=paths)
    profile["limitations"][0] = "Win rate 99%; realized outcome +12R."
    with pytest.raises(HistoricalBacktestGateError, match="limitations.*exact allowlist"):
        validate_gate_profile(profile, contract=contract)

    profile = build_gate_profile(contract=contract, paths=paths)
    profile["candidate_interface_mapping"][0]["accepted_exploration_limitations"].append(
        "Raw close rows: [1.0, 2.0, 3.0]."
    )
    with pytest.raises(HistoricalBacktestGateError, match="exact vocabulary"):
        validate_gate_profile(profile, contract=contract)

    profile = build_gate_profile(contract=contract, paths=paths)
    profile["candidate_interface_mapping"][0]["role"] = "invented"
    with pytest.raises(HistoricalBacktestGateError, match="role drifted"):
        validate_gate_profile(profile, contract=contract)

    profile = build_gate_profile(contract=contract, paths=paths)
    underlying = profile["candidate_interface_mapping"][0]["cadences"][0]["interfaces"][
        "underlying"
    ]
    underlying["file_count"] = "x"
    underlying["row_count"] = -1
    underlying["audit_freshness"]["status"] = "invented"
    with pytest.raises(HistoricalBacktestGateError, match="types or ranges drifted"):
        validate_gate_profile(profile, contract=contract)

    profile = build_gate_profile(contract=contract, paths=paths)
    profile["engineer_surface"]["outcome_value"] = 1.0
    with pytest.raises(HistoricalBacktestGateError, match="exact allowlist"):
        validate_gate_profile(profile, contract=contract)


def test_profile_reads_each_bound_evidence_once_and_rejects_ambiguous_json(
    tmp_path: Path,
) -> None:
    contract, paths = _profile_inputs()
    row = contract["bound_evidence"][0]
    replacement = tmp_path / row["path"]
    replacement.parent.mkdir(parents=True)
    replacement.write_text('{"schema_version":"first","schema_version":"second"}')
    paths[row["alias"]] = replacement
    with pytest.raises(HistoricalBacktestGateError, match="cannot be read unambiguously"):
        build_gate_profile(
            contract=contract,
            paths=paths,
        )


def test_committed_profile_is_valid_and_reproducible() -> None:
    if not PROFILE_PATH.exists():
        pytest.skip("profile is generated after the frozen builder is committed")
    contract, paths = _profile_inputs()
    committed = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    rebuilt = build_gate_profile(
        contract=contract,
        paths=paths,
    )
    validate_gate_profile(committed, contract=contract)
    assert pretty_json_bytes(rebuilt) == pretty_json_bytes(committed)
