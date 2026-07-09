from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import UTC
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.contract import (  # noqa: E402
    PA_FEITIAN_DECISION_INTENT_SCHEMA_VERSION,
    load_decision_intent,
    validate_decision_intent,
)
from engine.pa_feitian.schema_validation import (  # noqa: E402
    JsonSchemaValidationError,
    validate_pa_feitian_decision_intent_schema,
)


SRC_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC_ROOT.parent
FIXTURE_PATH = SRC_ROOT / "tests" / "fixtures" / "pa_feitian_decision_intent_v1.json"
SCHEMA_PATH = REPO_ROOT / "doc" / "schemas" / "pa_feitian_decision_intent_v1.schema.json"
SNAPSHOT_V0_SCHEMA_PATH = REPO_ROOT / "doc" / "schemas" / "pa_feitian_snapshot_v0.schema.json"
SNAPSHOT_V1_SCHEMA_PATH = REPO_ROOT / "doc" / "schemas" / "pa_feitian_snapshot_v1.schema.json"


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def test_decision_intent_fixture_validates_against_model_and_schema():
    data = _load_json(FIXTURE_PATH)

    validate_pa_feitian_decision_intent_schema(data)
    sidecar = load_decision_intent(FIXTURE_PATH)

    assert sidecar.schema_version == PA_FEITIAN_DECISION_INTENT_SCHEMA_VERSION
    assert sidecar.generated_at_utc.astimezone(UTC).tzinfo == UTC
    assert sidecar.provenance.role == "manifest_referenced_decision_intent_sidecar"
    assert sidecar.provenance.source_manifest_path == (
        "src/tests/fixtures/pa_feitian_run_manifest_with_decision_intent_v1.json"
    )
    assert sidecar.provenance.snapshot_schema_version == "pa_feitian_snapshot_v1"
    assert [intent.decision_state for intent in sidecar.intents] == [
        "armed_watch",
        "trade_ready",
        "watch",
    ]
    assert [intent.execution_allowed for intent in sidecar.intents] == [False, True, False]


def test_decision_intent_schema_declares_required_readiness_fields():
    schema = _load_json(SCHEMA_PATH)
    required = set(schema["$defs"]["intent"]["required"])

    assert {
        "decision_state",
        "execution_allowed",
        "product_direction_tier",
        "premium_stop",
        "confirmation",
        "liquidity",
        "reason_codes",
        "no_lookahead_inputs",
    }.issubset(required)
    assert schema["properties"]["schema_version"]["const"] == PA_FEITIAN_DECISION_INTENT_SCHEMA_VERSION
    assert "trade_ready" in schema["$defs"]["decision_state"]["enum"]
    assert schema["$defs"]["premium_stop"]["properties"]["source"]["enum"] == [
        "swing_low_premium",
        "recent_36bar_low",
        "half_loss_fixed",
        "manual",
        "unavailable",
        "not_applicable",
    ]


def test_execution_allowed_is_only_valid_for_fully_ready_trade_state():
    data = _load_json(FIXTURE_PATH)

    armed_watch_with_execution = deepcopy(data)
    armed_watch_with_execution["intents"][0]["execution_allowed"] = True

    with pytest.raises(ValidationError, match="if and only if"):
        validate_decision_intent(armed_watch_with_execution)

    trade_ready_without_execution = deepcopy(data)
    trade_ready_without_execution["intents"][1]["execution_allowed"] = False

    with pytest.raises(ValidationError, match="if and only if"):
        validate_decision_intent(trade_ready_without_execution)

    unclear_stop_trade = deepcopy(data)
    unclear_stop_trade["intents"][1]["premium_stop"]["status"] = "unclear"

    with pytest.raises(ValidationError, match="requires clear premium_stop"):
        validate_decision_intent(unclear_stop_trade)

    stale_liquidity_trade = deepcopy(data)
    stale_liquidity_trade["intents"][1]["liquidity"]["status"] = "stale"

    with pytest.raises(ValidationError, match="adequate recovered liquidity"):
        validate_decision_intent(stale_liquidity_trade)


def test_decision_intent_rejects_no_lookahead_violations():
    data = _load_json(FIXTURE_PATH)

    future_input = deepcopy(data)
    future_input["intents"][0]["no_lookahead_inputs"][0]["asof_ts_utc"] = (
        "2026-06-28T00:00:01Z"
    )

    with pytest.raises(ValidationError, match="must not be after decision_ts_utc"):
        validate_decision_intent(future_input)

    posterior_kind = deepcopy(data)
    posterior_kind["intents"][0]["no_lookahead_inputs"][0]["kind"] = "posterior_outcome"

    with pytest.raises(ValidationError):
        validate_decision_intent(posterior_kind)

    posterior_source = deepcopy(data)
    posterior_source["intents"][0]["no_lookahead_inputs"][0]["source"] = (
        "posterior_outcome_labels"
    )

    with pytest.raises(ValidationError, match="must not reference 'posterior'"):
        validate_decision_intent(posterior_source)


def test_decision_intent_schema_rejects_unknown_fields():
    data = _load_json(FIXTURE_PATH)
    data["intents"][0]["snapshot_v2_preview"] = {}

    with pytest.raises(JsonSchemaValidationError, match="snapshot_v2_preview"):
        validate_pa_feitian_decision_intent_schema(data)


def test_snapshot_contracts_do_not_grow_decision_intent_fields():
    forbidden_fields = {
        "decision_state",
        "execution_allowed",
        "product_direction_tier",
        "premium_stop",
        "confirmation",
        "liquidity",
        "reason_codes",
        "no_lookahead_inputs",
        "decision_intent_artifact",
    }

    for schema_path in (SNAPSHOT_V0_SCHEMA_PATH, SNAPSHOT_V1_SCHEMA_PATH):
        signal_props = _load_json(schema_path)["$defs"]["signal"]["properties"]
        assert forbidden_fields.isdisjoint(signal_props)
