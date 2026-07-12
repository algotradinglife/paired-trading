from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from engine.pa_feitian.retrospective_replay import (
    OPERATIONAL_MODE,
    RETROSPECTIVE_MODE,
    truncate_finalized_at_decision,
    validate_contract,
    validate_replay_evidence,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKET = REPO_ROOT / "doc/repro/pa-feitian-m6-retrospective-replay-2026-07-12"
CONTRACT = REPO_ROOT / "docs/research/pa-feitian-m6-epistemic-replay-contract-v1.json"
ARTIFACT = PACKET / "retrospective_replay_evidence_v1.json"


def test_finalized_replay_truncates_before_derivation_and_ignores_future_append() -> None:
    historical = pd.DataFrame(
        {
            "datetime": pd.to_datetime(
                ["2026-06-02 14:55:00", "2026-06-02 15:00:00", "2026-06-02 21:05:00"]
            ),
            "close": [1.0, 2.0, 999.0],
        }
    )
    cutoff = "2026-06-02T07:00:00Z"
    expected = truncate_finalized_at_decision(historical.iloc[:2], decision_ts_utc=cutoff)
    observed = truncate_finalized_at_decision(historical, decision_ts_utc=cutoff)
    pd.testing.assert_frame_equal(observed, expected)
    assert observed["close"].tolist() == [1.0, 2.0]


def test_missing_acquisition_metadata_enables_research_but_blocks_operations() -> None:
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    validate_replay_evidence(artifact)
    assert artifact["acquisition_metadata"]["complete_inputs"] == 0
    assert artifact["mode_results"][RETROSPECTIVE_MODE] == {
        "status": "enabled_with_explicit_limitations",
        "causal_roll_schedule_reuse": True,
        "missing_acquisition_metadata_is_blocker": False,
    }
    assert artifact["mode_results"][OPERATIONAL_MODE] == {
        "status": "blocked",
        "causal_roll_schedule_reuse": False,
        "missing_acquisition_metadata_is_blocker": True,
    }
    assert all(row["limitations"] for row in artifact["decision_gates"])


def test_contract_keeps_acquisition_manifests_in_m8_and_all_promotions_out() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    validate_contract(contract)
    assert contract["claim_modes"][OPERATIONAL_MODE]["requirement_owner"] == "M8"
    assert "date_only_iv_or_regime" in contract["excluded_capabilities"]
    assert "execution" in contract["excluded_capabilities"]


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("acquisition_metadata", "required_for_retrospective_finalized"), True),
        (("acquisition_metadata", "required_for_operational_observability"), False),
        (("mode_results", RETROSPECTIVE_MODE, "causal_roll_schedule_reuse"), False),
        (("mode_results", OPERATIONAL_MODE, "causal_roll_schedule_reuse"), True),
        (("mode_results", OPERATIONAL_MODE, "status"), "enabled"),
        (("decision_gates", 0, "contract_reselection"), True),
        (("excluded_capabilities", 0), "promoted"),
        (("promotion", "performance_or_strategy_screening"), True),
        (("promotion", "m7"), True),
        (("promotion", "execution"), True),
    ],
)
def test_evidence_validator_rejects_epistemic_or_scope_promotion(
    path: tuple, value: object
) -> None:
    corrupted = copy.deepcopy(json.loads(ARTIFACT.read_text(encoding="utf-8")))
    target = corrupted
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        validate_replay_evidence(corrupted)
