from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.score_today_intake import (  # noqa: E402
    is_score_today_artifact,
    resolve_score_today_artifact,
)


def _score_today_artifact() -> dict:
    return {
        "pool": "CN_METAL",
        "instrument_class": "cn_metal_futures",
        "window_days": 30,
        "active_rules": ["pa-h2-cn-metal"],
        "scored": [
            {
                "symbol": "kq_m_shfe_au",
                "date": "2026-06-29",
                "direction": "bottom",
                "level": "pa_h2",
                "score": 4,
                "options_calls": [
                    {
                        "rank": 1,
                        "strike": 880,
                        "contract_sym": "au2608c880",
                        "option_price": 12.2,
                        "price_source": "store",
                        "iv": 10.0,
                        "iv_rank": 0.1,
                    }
                ],
            }
        ],
    }


def test_score_today_intake_locates_real_artifact_shape_deterministically(tmp_path: Path):
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    stale = artifact_dir / "2026-07-08_score_today.json"
    selected = artifact_dir / "2026-07-09_score_today.json"
    invalid = artifact_dir / "notes.json"
    stale.write_text(json.dumps({**_score_today_artifact(), "window_days": 7}), encoding="utf-8")
    selected.write_text(json.dumps(_score_today_artifact()), encoding="utf-8")
    invalid.write_text(json.dumps({"not": "score_today"}), encoding="utf-8")

    intake = resolve_score_today_artifact(artifact_dirs=[artifact_dir])

    assert is_score_today_artifact(selected)
    assert intake.status == "real_data_available"
    assert intake.scorecard_path == selected
    assert intake.source == selected.as_posix()
    assert "selected lexicographically last path from 2 valid candidate(s)" in intake.notes
    assert "ignored 1 non-score_today artifact candidate(s)" in intake.notes


def test_score_today_intake_classifies_fixture_fallback_blocked_and_unknown(tmp_path: Path):
    fixture = tmp_path / "fixture_score_today.json"
    fixture.write_text(json.dumps(_score_today_artifact()), encoding="utf-8")

    fixture_intake = resolve_score_today_artifact(
        fixture_path=fixture,
        allow_fixture_fallback=True,
    )
    blocked_intake = resolve_score_today_artifact(artifact_dirs=[tmp_path / "missing"])
    unknown_intake = resolve_score_today_artifact()

    assert fixture_intake.status == "fixture_fallback"
    assert fixture_intake.scorecard_path == fixture
    assert fixture_intake.used_fixture_fallback is True
    assert blocked_intake.status == "data_blocked"
    assert unknown_intake.status == "unknown"
