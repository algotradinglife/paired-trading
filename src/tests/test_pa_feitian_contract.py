from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.contract import (  # noqa: E402
    PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION,
    PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION,
    SIGNAL_STATUSES,
    PaFeitianSignal,
    load_snapshot,
    load_snapshot_v1,
)


SRC_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = SRC_ROOT / "tests" / "fixtures" / "pa_feitian_snapshot_v0.json"
FIXTURE_V1_PATH = SRC_ROOT / "tests" / "fixtures" / "pa_feitian_snapshot_v1.json"
SCHEMA_PATH = SRC_ROOT.parent / "doc" / "schemas" / "pa_feitian_snapshot_v0.schema.json"
SCHEMA_V1_PATH = SRC_ROOT.parent / "doc" / "schemas" / "pa_feitian_snapshot_v1.schema.json"
TRACE_SCHEMA_PATH = SRC_ROOT.parent / "doc" / "schemas" / "pa_feitian_decision_trace_v1.schema.json"


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def test_fixture_validates_against_contract_model():
    snapshot = load_snapshot(FIXTURE_PATH)

    assert snapshot.schema_version == PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION
    assert snapshot.generated_at_utc.tzinfo is not None
    assert snapshot.generated_at_utc.astimezone(UTC).tzinfo == UTC
    assert len(snapshot.signals) == 2
    assert {signal.status for signal in snapshot.signals} == {"advisory", "data_blocked"}


def test_schema_declares_stable_status_enum():
    schema = _load_json(SCHEMA_PATH)

    assert schema["properties"]["schema_version"]["const"] == PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION
    assert tuple(schema["$defs"]["status"]["enum"]) == SIGNAL_STATUSES


def test_v1_schema_extends_signal_with_shadow_trace_only():
    v0_signal = _load_json(SCHEMA_PATH)["$defs"]["signal"]
    v1_schema = _load_json(SCHEMA_V1_PATH)
    v1_signal = v1_schema["$defs"]["signal"]
    trace_schema = _load_json(TRACE_SCHEMA_PATH)

    assert (
        v1_schema["properties"]["schema_version"]["const"] == PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION
    )
    assert v1_signal["properties"]["decision_trace_v1"]["$ref"].endswith(
        "pa_feitian_decision_trace_v1.schema.json"
    )
    assert set(v0_signal["required"]).issubset(v1_signal["required"])
    assert set(v1_signal["required"]) == set(v0_signal["required"]) | {"decision_trace_v1"}
    assert "decision_trace_v1" not in v0_signal["properties"]
    assert trace_schema["properties"]["trace_version"]["const"] == "decision_trace_v1"
    assert tuple(trace_schema["$defs"]["signal_status"]["enum"]) == SIGNAL_STATUSES


def test_fixture_uses_utc_timestamps_and_no_lookahead_markers():
    snapshot = load_snapshot(FIXTURE_PATH)

    for signal in snapshot.signals:
        assert signal.ts_utc.astimezone(UTC).tzinfo == UTC
        assert signal.features_det["lookahead_free"] is True
        assert signal.features_det["cutoff_ts_utc"].endswith("Z")


def test_outcomes_are_explicitly_separated():
    fixture = _load_json(FIXTURE_PATH)
    signal_schema = _load_json(SCHEMA_PATH)["$defs"]["signal"]["properties"]

    explicit_outcomes = {
        "underlying_r_outcome",
        "premium_r_outcome",
        "option_runner_outcome",
        "proxy_outcome",
    }
    assert explicit_outcomes.issubset(signal_schema)
    assert "outcome" not in signal_schema

    for signal in fixture["signals"]:
        assert explicit_outcomes.issubset(signal)
        assert "outcome" not in signal
        assert "r" not in signal


def test_schema_and_fixture_include_defensive_frontend_states():
    schema_statuses = set(_load_json(SCHEMA_PATH)["$defs"]["status"]["enum"])
    fixture_statuses = {signal["status"] for signal in _load_json(FIXTURE_PATH)["signals"]}

    assert {"advisory", "data_blocked", "model_dominated"}.issubset(schema_statuses)
    assert {"advisory", "data_blocked"}.issubset(fixture_statuses)


def test_v1_fixture_covers_shadow_trace_statuses_and_keeps_v0_strict():
    snapshot = load_snapshot_v1(FIXTURE_V1_PATH)

    assert snapshot.schema_version == PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION
    assert {signal.status for signal in snapshot.signals} == {
        "keep",
        "data_blocked",
        "model_dominated",
    }
    for signal in snapshot.signals:
        trace = signal.decision_trace_v1
        assert trace.trace_version == "decision_trace_v1"
        assert trace.status == signal.status
        assert trace.action == signal.decision
        assert trace.input_refs[0].source == "score_today_json"
        assert [node.id for node in trace.nodes[:3]] == [
            "underlying_signal",
            "policy_rule",
            "option_selection",
        ]

    with pytest.raises(ValidationError):
        PaFeitianSignal.model_validate(_load_json(FIXTURE_V1_PATH)["signals"][0])


def test_producer_cli_emits_valid_snapshot(tmp_path: Path):
    out = tmp_path / "pa_feitian_snapshot_v0.json"
    cmd = [
        sys.executable,
        str(SRC_ROOT / "scripts" / "emit_pa_feitian_snapshot.py"),
        "--out",
        str(out),
        "--source-commit",
        "50b3cf92f4058f4fcaf521784600bbd5a55cf8ab",
    ]

    subprocess.run(cmd, cwd=SRC_ROOT, check=True)
    snapshot = load_snapshot(out)

    assert snapshot.schema_version == PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION
    assert snapshot.source_commit == "50b3cf92f4058f4fcaf521784600bbd5a55cf8ab"
    assert snapshot.summary["signals_total"] == len(snapshot.signals)
    assert "decision_trace_v1" not in _load_json(out)["signals"][0]


def test_producer_cli_emits_v1_shadow_snapshot_when_requested(tmp_path: Path):
    out = tmp_path / "pa_feitian_snapshot_v1.json"
    cmd = [
        sys.executable,
        str(SRC_ROOT / "scripts" / "emit_pa_feitian_snapshot.py"),
        "--out",
        str(out),
        "--source-commit",
        "50b3cf92f4058f4fcaf521784600bbd5a55cf8ab",
        "--contract-version",
        PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION,
    ]

    subprocess.run(cmd, cwd=SRC_ROOT, check=True)
    snapshot = load_snapshot_v1(out)

    assert snapshot.schema_version == PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION
    assert snapshot.run_config["contract"] == PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION
    assert snapshot.summary["by_status"] == {
        "keep": 1,
        "data_blocked": 1,
        "model_dominated": 1,
    }
    assert snapshot.signals[0].decision_trace_v1.summary.primary_blocker == "iv_rank_missing"
