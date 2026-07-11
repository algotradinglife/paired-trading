from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path

import pytest

from engine.pa_feitian.continuous_provenance import (
    _roll_records,
    validate_manifest_boundary,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (
    REPO_ROOT
    / "doc/repro/pa-feitian-m6-continuous-provenance-2026-07-11"
    / "continuous_provenance_manifest_v1.json"
)


def test_roll_records_use_trading_dates_and_mark_effective_session() -> None:
    records = _roll_records(
        {
            date(2026, 5, 29): "202606",
            date(2026, 6, 1): "202606",
            date(2026, 6, 2): "202608",
        },
        date(2026, 6, 1),
    )
    assert records == [
        {"trading_date": "2026-06-01", "main_month": "202606", "is_roll": False},
        {"trading_date": "2026-06-02", "main_month": "202608", "is_roll": True},
    ]


def test_evidence_manifest_binds_only_reproducible_underlyings() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["hermes_task"] == "t_6df19e2b"
    assert {row["source_id"] for row in manifest["bound_candidates"]} == {
        "shfe_au0_underlying_5min",
        "shfe_ag0_underlying_5min",
    }
    assert all(
        row["binding_status"] == "exact_byte_reconstruction_supported"
        and row["embedded_main_month_is_roll"]["status"] == "quarantined"
        and row["raw_acquisition_lineage"]["status"] == "quarantined"
        and row["build_cutoff"]["historical_execution_time"] == "unverified"
        and not row["eligible_for_score_today"]
        for row in manifest["bound_candidates"]
    )
    assert {row["source_id"] for row in manifest["quarantined_candidates"]} == {
        "shfe_au0_option_ivskew",
        "shfe_ag0_option_ivskew",
        "shfe_au0_regime",
        "shfe_ag0_regime",
    }
    assert all(
        row["status"] == "quarantined"
        and not row["manifest_binding_attempted"]
        and not row["eligible_for_score_today"]
        for row in manifest["quarantined_candidates"]
    )
    boundary = manifest["capability_boundary"]
    assert boundary["full_sample_atr_regime"] == "blocked"
    assert boundary["date_only_iv"] == "quarantined"
    assert boundary["candidate_data_eligible_for_score_today"] is False
    assert boundary["performance_evaluation_allowed"] is False
    assert boundary["advance_m7"] is False


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("bound_candidates", 0, "eligible_for_score_today"), True),
        (("quarantined_candidates", 0, "manifest_binding_attempted"), True),
        (("capability_boundary", "full_sample_atr_regime"), "supported"),
        (("capability_boundary", "performance_evaluation_allowed"), True),
        (("capability_boundary", "advance_m7"), True),
    ],
)
def test_boundary_validator_rejects_promotion(path: tuple, value: object) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    corrupted = copy.deepcopy(manifest)
    target = corrupted
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        validate_manifest_boundary(corrupted)
