from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from engine.pa_feitian.raw_availability import (
    EVIDENCE_FIELDS,
    GAP_CODES,
    _online_schedule,
    validate_blocker_packet,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKET = (
    REPO_ROOT
    / "doc/repro/pa-feitian-m6-raw-availability-2026-07-12"
    / "raw_availability_blocker_v1.json"
)


def _daily(rows: list[tuple[str, float, float]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["day", "open_interest", "volume"])
    frame.index = pd.to_datetime(frame.pop("day")).dt.date
    return frame


def test_online_schedule_uses_prior_session_and_third_confirmation() -> None:
    panel = {
        "202606": _daily(
            [
                ("2026-05-25", 100, 100),
                ("2026-05-26", 90, 90),
                ("2026-05-27", 80, 80),
                ("2026-05-28", 70, 70),
                ("2026-05-29", 60, 60),
            ]
        ),
        "202608": _daily(
            [
                ("2026-05-25", 50, 50),
                ("2026-05-26", 100, 100),
                ("2026-05-27", 110, 110),
                ("2026-05-28", 120, 120),
                ("2026-05-29", 130, 130),
            ]
        ),
    }
    schedule = _online_schedule(panel)
    assert schedule[pd.Timestamp("2026-05-28").date()] == "202606"
    assert schedule[pd.Timestamp("2026-05-29").date()] == "202608"


def test_packet_enumerates_every_raw_input_and_retains_quarantine() -> None:
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    validate_blocker_packet(packet)
    assert packet["hermes_task"] == "t_550fa726"
    assert packet["audit_scope"]["raw_input_count"] == 210
    assert packet["audit_scope"]["unique_raw_path_count"] == 210
    assert packet["audit_scope"]["by_product"] == {"ag": 130, "au": 80}
    assert packet["audit_scope"]["by_role"] == {
        "constituent_5min": 105,
        "schedule_daily": 105,
    }
    assert all(
        set(row["evidence"]) == set(EVIDENCE_FIELDS)
        and row["missing_evidence"] == list(GAP_CODES)
        and row["parquet_metadata_keys"] == ["ARROW:schema"]
        and row["status"] == "quarantined"
        for row in packet["raw_inputs"]
    )
    assert [row["session_prefixes_checked"] for row in packet["roll_schedule_audit"]] == [
        1313,
        1313,
    ]
    assert packet["gap_summary"]["inputs_with_complete_evidence"] == 0
    assert not packet["capability_boundary"]["underlying_candidates_eligible_for_score_today"]


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("raw_inputs", 0, "historical_as_of_availability"), "proven"),
        (("raw_inputs", 0, "status"), "supported"),
        (("capability_boundary", "underlying_candidates_eligible_for_score_today"), True),
        (("capability_boundary", "performance_evaluation_allowed"), True),
        (("capability_boundary", "iv_or_regime_promotion_attempted"), True),
        (("capability_boundary", "advance_m7"), True),
        (("capability_boundary", "execution_change_allowed"), True),
    ],
)
def test_boundary_validator_rejects_promotion(path: tuple, value: object) -> None:
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    corrupted = copy.deepcopy(packet)
    target = corrupted
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        validate_blocker_packet(corrupted)
