from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.contract import (  # noqa: E402
    PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION,
    decision_intent_to_jsonable,
    load_decision_intent,
    write_decision_intent,
    write_snapshot,
)
from engine.pa_feitian.decision_intent_adapter import (  # noqa: E402
    build_decision_intent_sidecar,
)
from engine.pa_feitian.manifest import load_run_manifest, sha256_file  # noqa: E402
from engine.pa_feitian.schema_validation import (  # noqa: E402
    validate_pa_feitian_decision_intent_schema,
    validate_pa_feitian_run_manifest_schema,
)
from engine.pa_feitian.scorecard_producer import snapshot_from_scorecard  # noqa: E402


SRC_ROOT = Path(__file__).resolve().parents[1]
COMMIT = "b" * 40
GENERATED_AT = datetime(2026, 7, 7, tzinfo=UTC)


def _au_call_record(
    date: str,
    *,
    option_price: float = 12.2,
    stop_source: str = "swing_low_premium",
    stop_premium: float | None = 11.2,
    stop_status: str = "clear",
    confirmation_status: str = "confirmed",
    confirmation_source: str = "premium_macd",
    macd_alert_only: bool = False,
    liquidity: dict | None = None,
    direction: str = "bottom",
    right_tail_observation: bool = False,
) -> dict:
    if liquidity is None:
        liquidity = {
            "quote_count": 18,
            "last_quote_age_seconds": 15,
            "recovery_required": False,
        }
    return {
        "symbol": "kq_m_shfe_au",
        "date": date,
        "direction": direction,
        "level": "pa_h2",
        "subtype": "pa_h2",
        "confidence": 0.75,
        "score": 4,
        "policy_rule": "pa-h2-cn-metal-tr-phase",
        "policy_weight": 0.75,
        "underlying_price": 860.0,
        "options_calls": [
            {
                "rank": 1,
                "strike": 880,
                "otm_pct": 2.33,
                "expiry_month": "2608",
                "expiry_date": "2026-08-17",
                "contract_sym": "au2608c880",
                "days_to_expiry": 45,
                "is_mm_strike": False,
                "option_price": option_price,
                "price_source": "store",
                "model_dominated": False,
                "iv": 10.0,
                "iv_rank": 0.1,
            }
        ],
        "premium_stop": {
            "status": stop_status,
            "source": stop_source,
            "stop_premium": stop_premium,
            "asof_ts_utc": f"{date}T00:00:00Z",
        },
        "premium_confirmation": {
            "status": confirmation_status,
            "source": confirmation_source,
            "confirmed_at_utc": f"{date}T00:00:00Z"
            if confirmation_status == "confirmed"
            else None,
            "macd_alert_only": macd_alert_only,
        },
        "liquidity": liquidity,
        "right_tail_observation": right_tail_observation,
        "pa_phase": "TR",
        "position_size": "half",
    }


def _scorecard(records: list[dict]) -> dict:
    return {
        "pool": "CN_METAL",
        "instrument_class": "cn_metal_futures",
        "window_days": 30,
        "active_rules": ["pa-h2-cn-metal"],
        "scored": records,
    }


def _sidecar_for_scorecard(scorecard: dict, tmp_path: Path):
    snapshot = snapshot_from_scorecard(
        scorecard,
        source_commit=COMMIT,
        generated_at_utc=GENERATED_AT,
        iv_warmup=1,
        contract_version=PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION,
    )
    snapshot_path = tmp_path / "pa_feitian_snapshot_v1.json"
    write_snapshot(snapshot, snapshot_path)
    return build_decision_intent_sidecar(
        snapshot,
        source_commit=COMMIT,
        source_manifest_path=tmp_path / "pa_feitian_run_manifest_v1.json",
        snapshot_artifact_path=snapshot_path,
        generated_at_utc=GENERATED_AT,
        source_manifest_generated_at_utc=GENERATED_AT,
        scorecard=scorecard,
    )


def test_v02_adapter_golden_cases(tmp_path: Path):
    scorecard = _scorecard(
        [
            _au_call_record(
                "2026-06-28",
                option_price=18.5,
                stop_premium=17.9,
            ),
            _au_call_record("2026-06-29"),
            _au_call_record(
                "2026-06-30",
                option_price=10.0,
                stop_source="half_loss_fixed",
                stop_premium=None,
            ),
            _au_call_record(
                "2026-07-01",
                confirmation_status="pending",
                confirmation_source="underlying_only",
                macd_alert_only=True,
            ),
            _au_call_record(
                "2026-07-02",
                liquidity={"quote_count": 2, "last_quote_age_seconds": 360},
                right_tail_observation=True,
            ),
            _au_call_record("2026-07-03", direction="top"),
        ]
    )

    sidecar = _sidecar_for_scorecard(scorecard, tmp_path)
    assert [intent.decision_state for intent in sidecar.intents] == [
        "armed_watch",
        "trade_ready",
        "armed_watch",
        "armed_watch",
        "observation_runner",
        "reject",
    ]
    assert [intent.execution_allowed for intent in sidecar.intents] == [
        False,
        True,
        False,
        False,
        False,
        False,
    ]

    soft_gate = sidecar.intents[0]
    assert soft_gate.premium_stop.status == "unclear"
    assert soft_gate.premium_stop.stop_distance_pct == pytest.approx(3.243, abs=0.001)
    assert "STOP_DISTANCE_OUTSIDE_SOFT_GATE" in soft_gate.reason_codes
    assert "STOP_CLEAR_DOWNGRADED" in soft_gate.reason_codes

    trade_ready = sidecar.intents[1]
    assert trade_ready.product_direction_tier == "aligned_trade_candidate"
    assert trade_ready.premium_stop.status == "clear"
    assert trade_ready.confirmation.status == "confirmed"
    assert trade_ready.liquidity.status == "adequate"
    assert "TRADE_READY_PREMIUM_CONFIRMED" in trade_ready.reason_codes

    half_loss = sidecar.intents[2]
    assert half_loss.premium_stop.source == "half_loss_fixed"
    assert half_loss.premium_stop.status == "unclear"
    assert "HALF_LOSS_FIXED_DOWNGRADE" in half_loss.reason_codes

    macd_alert = sidecar.intents[3]
    assert macd_alert.confirmation.status == "pending"
    assert macd_alert.confirmation.source == "underlying_only"
    assert "MACD_ALERT_ONLY" in macd_alert.reason_codes

    observation = sidecar.intents[4]
    assert observation.liquidity.status == "thin_and_stale"
    assert observation.liquidity.recovery_required
    assert "THIN_STALE_RIGHT_TAIL_OBSERVATION" in observation.reason_codes

    blocked_direction = sidecar.intents[5]
    assert blocked_direction.product_direction_tier == "direction_blocked"
    assert "PRODUCT_DIRECTION_BLOCKED" in blocked_direction.reason_codes

    data = decision_intent_to_jsonable(sidecar)
    validate_pa_feitian_decision_intent_schema(data)
    for intent in data["intents"]:
        assert intent["no_lookahead_inputs"][0]["digest"].startswith("sha256:")
        decision_ts = datetime.fromisoformat(
            intent["decision_ts_utc"].replace("Z", "+00:00")
        )
        for input_ref in intent["no_lookahead_inputs"]:
            assert input_ref["digest"] is not None
            assert "outcome" not in input_ref["source"]
            input_ts = datetime.fromisoformat(
                input_ref["asof_ts_utc"].replace("Z", "+00:00")
            )
            assert input_ts <= decision_ts


def test_v02_adapter_rejects_future_decision_time_inputs(tmp_path: Path):
    scorecard = _scorecard([_au_call_record("2026-06-29")])
    scorecard["scored"][0]["premium_stop"]["asof_ts_utc"] = "2026-06-29T00:00:01Z"

    with pytest.raises(ValueError, match="premium_stop.asof_ts_utc"):
        _sidecar_for_scorecard(scorecard, tmp_path)

    scorecard = _scorecard([_au_call_record("2026-06-29")])
    scorecard["scored"][0]["decision_context_asof_ts_utc"] = "2026-06-29T00:00:01Z"

    with pytest.raises(ValueError, match="scorecard_record.asof_ts_utc"):
        _sidecar_for_scorecard(scorecard, tmp_path)


def test_producer_cli_emits_and_attaches_decision_intent_sidecar(tmp_path: Path):
    scorecard = tmp_path / "scorecard.json"
    snapshot_path = tmp_path / "pa_feitian_snapshot_v1.json"
    sidecar_path = tmp_path / "pa_feitian_decision_intent_v1.json"
    manifest_path = tmp_path / "pa_feitian_run_manifest_v1.json"
    scorecard.write_text(
        json.dumps(_scorecard([_au_call_record("2026-06-29")])),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(SRC_ROOT / "scripts" / "emit_pa_feitian_snapshot.py"),
            "--out",
            str(snapshot_path),
            "--scorecard",
            str(scorecard),
            "--source-commit",
            COMMIT,
            "--generated-at-utc",
            "2026-07-07T00:00:00Z",
            "--iv-warmup",
            "1",
            "--contract-version",
            PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION,
            "--manifest-out",
            str(manifest_path),
            "--decision-intent-out",
            str(sidecar_path),
            "--data-access-status",
            "fixture_fallback",
            "--data-access-source",
            "test deterministic scorecard fixture",
        ],
        cwd=SRC_ROOT,
        check=True,
    )

    sidecar = load_decision_intent(sidecar_path)
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_pa_feitian_run_manifest_schema(manifest_payload)
    manifest = load_run_manifest(manifest_path)

    assert sidecar.intents[0].decision_state == "trade_ready"
    assert manifest.decision_intent_artifact is not None
    assert manifest.decision_intent_artifact.path == str(sidecar_path)
    assert manifest.decision_intent_artifact.sha256 == sha256_file(sidecar_path)
    assert manifest.output_hashes["decision_intent_artifact"] == sha256_file(sidecar_path)
    assert sidecar.provenance.source_manifest_path == str(manifest_path)
    assert sidecar.provenance.snapshot_artifact_sha256 == sha256_file(snapshot_path)

    out = tmp_path / "roundtrip_decision_intent.json"
    write_decision_intent(sidecar, out)
    assert load_decision_intent(out) == sidecar
