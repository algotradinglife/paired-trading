from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import UTC
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.premium_outcome import (  # noqa: E402
    PA_FEITIAN_PREMIUM_OUTCOME_SCHEMA_VERSION,
    load_premium_outcome,
    premium_outcome_to_jsonable,
    validate_premium_outcome,
    write_premium_outcome,
)
from engine.pa_feitian.schema_validation import (  # noqa: E402
    JsonSchemaValidationError,
    validate_pa_feitian_premium_outcome_schema,
)


SRC_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC_ROOT.parent
FIXTURE_PATH = SRC_ROOT / "tests" / "fixtures" / "pa_feitian_premium_outcome_v1.json"
SCHEMA_PATH = REPO_ROOT / "doc" / "schemas" / "pa_feitian_premium_outcome_v1.schema.json"
SNAPSHOT_V0_SCHEMA_PATH = REPO_ROOT / "doc" / "schemas" / "pa_feitian_snapshot_v0.schema.json"
SNAPSHOT_V1_SCHEMA_PATH = REPO_ROOT / "doc" / "schemas" / "pa_feitian_snapshot_v1.schema.json"
DECISION_INTENT_SCHEMA_PATH = REPO_ROOT / "doc" / "schemas" / (
    "pa_feitian_decision_intent_v1.schema.json"
)


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def test_premium_outcome_fixture_validates_against_model_and_schema():
    data = _load_json(FIXTURE_PATH)

    validate_pa_feitian_premium_outcome_schema(data)
    sidecar = load_premium_outcome(FIXTURE_PATH)

    assert sidecar.schema_version == PA_FEITIAN_PREMIUM_OUTCOME_SCHEMA_VERSION
    assert sidecar.generated_at_utc.astimezone(UTC).tzinfo == UTC
    assert sidecar.provenance.role == "manifest_referenced_premium_outcome_sidecar"
    assert sidecar.provenance.snapshot_schema_version == "pa_feitian_snapshot_v1"
    assert [outcome.evaluation_status for outcome in sidecar.outcomes] == [
        "observed",
        "ambiguous",
        "data_blocked",
        "not_evaluable",
    ]

    observed = sidecar.outcomes[0]
    assert observed.data_quality.premium_price_source_type == "observed"
    assert observed.data_quality.bar_granularity == "daily"
    assert observed.exit_reason == "premium_target"
    assert observed.policy.origin == "retrospective_fixed"
    assert observed.policy.declared_at_utc > observed.decision_ts_utc
    assert observed.policy.fixed_before_traversal is True
    assert (
        sidecar.provenance.policy_hashes[observed.policy.provenance_hash_key]
        == observed.policy.digest
    )
    assert observed.premium_metrics is not None
    assert observed.premium_metrics.risk.denominator_label == "declared_premium_risk_after_costs"
    assert observed.underlying_context is not None
    assert observed.underlying_context.underlying_r_denominator is not None
    assert "underlying_r" not in observed.premium_metrics.model_dump()

    assert sidecar.outcomes[1].data_quality.ambiguity is not None
    assert sidecar.outcomes[2].data_quality.data_gap is not None
    assert sidecar.outcomes[3].data_quality.premium_price_source_type == "model_derived"
    for outcome in sidecar.outcomes:
        if outcome.policy.origin == "retrospective_fixed":
            assert "policy_rule" not in {ref.kind for ref in outcome.no_lookahead_inputs}


def test_premium_outcome_schema_declares_m5_states_and_external_ref():
    schema = _load_json(SCHEMA_PATH)
    decision_intent_schema = _load_json(DECISION_INTENT_SCHEMA_PATH)

    assert schema["properties"]["schema_version"]["const"] == (
        PA_FEITIAN_PREMIUM_OUTCOME_SCHEMA_VERSION
    )
    assert schema["$defs"]["evaluation_status"]["enum"] == [
        "observed",
        "ambiguous",
        "data_blocked",
        "not_evaluable",
    ]
    assert schema["$defs"]["data_quality"]["properties"]["bar_granularity"]["enum"] == [
        "daily",
        "intraday",
        "tick",
        "unknown",
    ]
    assert "policy_hashes" in schema["$defs"]["provenance"]["required"]
    assert schema["$defs"]["policy"]["properties"]["origin"]["enum"] == [
        "decision_declared",
        "retrospective_fixed",
    ]
    assert {"digest", "fixed_before_traversal", "traversal_started_at_utc"}.issubset(
        schema["$defs"]["policy"]["required"]
    )
    assert schema["$defs"]["outcome"]["properties"]["no_lookahead_inputs"]["items"]["$ref"] == (
        "pa_feitian_decision_intent_v1.schema.json#/$defs/no_lookahead_input"
    )
    assert "policy_rule" in decision_intent_schema["$defs"]["no_lookahead_input"]["properties"][
        "kind"
    ]["enum"]


def test_premium_outcome_schema_resolves_no_lookahead_external_ref():
    data = _load_json(FIXTURE_PATH)
    broken = deepcopy(data)
    broken["outcomes"][0]["no_lookahead_inputs"][0]["kind"] = "posterior_outcome"

    with pytest.raises(JsonSchemaValidationError, match=r"no_lookahead_inputs\[0\]\.kind"):
        validate_pa_feitian_premium_outcome_schema(broken)


def test_premium_outcome_model_enforces_no_lookahead_and_observed_evidence():
    data = _load_json(FIXTURE_PATH)

    future_contract_selection = deepcopy(data)
    future_contract_selection["outcomes"][0]["selected_contract"][
        "contract_selection_asof_utc"
    ] = "2026-07-01T00:00:00Z"

    with pytest.raises(ValidationError, match="contract selection"):
        validate_premium_outcome(future_contract_selection)

    decision_declared_after_decision = deepcopy(data)
    decision_declared_after_decision["outcomes"][0]["policy"]["origin"] = "decision_declared"

    with pytest.raises(ValidationError, match="decision-declared policy"):
        validate_premium_outcome(decision_declared_after_decision)

    unfixed_policy = deepcopy(data)
    unfixed_policy["outcomes"][0]["policy"]["fixed_before_traversal"] = False

    with pytest.raises(ValidationError, match="fixed before premium path traversal"):
        validate_premium_outcome(unfixed_policy)

    policy_hash_drift = deepcopy(data)
    policy_hash_drift["provenance"]["policy_hashes"][
        "paft_premium_outcome_0002_daily_target_v1:policy"
    ] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"

    with pytest.raises(ValidationError, match="policy digest"):
        validate_premium_outcome(policy_hash_drift)

    future_entry = deepcopy(data)
    future_entry["outcomes"][0]["first_eligible_entry_ts_utc"] = "2026-06-29T00:00:00Z"

    with pytest.raises(ValidationError, match="first eligible entry"):
        validate_premium_outcome(future_entry)

    ambiguous_observed = deepcopy(data)
    ambiguous_observed["outcomes"][0]["data_quality"]["ambiguity"] = deepcopy(
        data["outcomes"][1]["data_quality"]["ambiguity"]
    )

    with pytest.raises(ValidationError, match="cannot carry ambiguity"):
        validate_premium_outcome(ambiguous_observed)

    model_as_observed = deepcopy(data)
    model_as_observed["outcomes"][3]["evaluation_status"] = "observed"
    model_as_observed["outcomes"][3]["exit_reason"] = "premium_target"

    with pytest.raises(ValidationError, match="model-derived premium data"):
        validate_premium_outcome(model_as_observed)


def test_premium_outcome_write_round_trips_jsonable(tmp_path: Path):
    sidecar = load_premium_outcome(FIXTURE_PATH)
    out = tmp_path / "pa_feitian_premium_outcome_v1.json"

    write_premium_outcome(sidecar, out)

    assert _load_json(out) == premium_outcome_to_jsonable(sidecar)
    assert load_premium_outcome(out) == sidecar


def test_snapshot_and_decision_intent_contracts_do_not_gain_outcome_fields():
    forbidden_snapshot_fields = {
        "premium_outcome_artifact",
        "premium_outcome",
        "premium_metrics",
        "entry_fill",
        "exit_fill",
        "evaluation_status",
    }
    forbidden_decision_intent_fields = {
        "premium_outcome_artifact",
        "premium_metrics",
        "exit_reason",
        "entry_fill",
        "exit_fill",
    }

    for schema_path in (SNAPSHOT_V0_SCHEMA_PATH, SNAPSHOT_V1_SCHEMA_PATH):
        signal_props = _load_json(schema_path)["$defs"]["signal"]["properties"]
        assert forbidden_snapshot_fields.isdisjoint(signal_props)

    intent_props = _load_json(DECISION_INTENT_SCHEMA_PATH)["$defs"]["intent"]["properties"]
    assert forbidden_decision_intent_fields.isdisjoint(intent_props)
