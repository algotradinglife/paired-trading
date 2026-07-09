from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.contract import (  # noqa: E402
    PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION,
    load_decision_intent,
    load_snapshot,
    load_snapshot_v1,
    write_snapshot,
)
from engine.pa_feitian.manifest import load_run_manifest, sha256_file  # noqa: E402
from engine.pa_feitian.schema_validation import validate_pa_feitian_run_manifest_schema  # noqa: E402
from engine.pa_feitian.scorecard_producer import snapshot_from_scorecard  # noqa: E402


SRC_ROOT = Path(__file__).resolve().parents[1]
COMMIT = "a" * 40
SCORECARD_V1_FIXTURE = SRC_ROOT / "tests" / "fixtures" / "pa_feitian_scorecard_v1.json"


def _scored_record(
    *,
    date: str,
    iv: float,
    symbol: str = "kq_m_shfe_au",
    calls: list[dict] | None = None,
) -> dict:
    return {
        "symbol": symbol,
        "date": date,
        "direction": "bottom",
        "level": "pa_h2",
        "subtype": "pa_h2",
        "confidence": 0.75,
        "invalidation_level": 820.0,
        "matched_sweet_spots": [],
        "policy_rule": "pa-h2-cn-metal-tr-phase",
        "policy_weight": 0.75,
        "pa_isolated": True,
        "score": 4,
        "underlying_price": 860.0,
        "options_calls": calls
        if calls is not None
        else [
            {
                "rank": 1,
                "strike": 880,
                "otm_pct": 2.33,
                "expiry_month": "2608",
                "expiry_date": "2026-08-17",
                "contract_sym": "au2608c880",
                "days_to_expiry": 45,
                "mm_target_pct": None,
                "is_mm_strike": False,
                "option_price": 18.5,
                "price_source": "store",
                "iv": iv,
            }
        ],
        "pa_phase": "TR",
        "position_size": "half",
        "signal_bar_quality": {"body_frac": 0.82, "close_pos": 0.97, "double_strong": True},
    }


def _scorecard() -> dict:
    return {
        "pool": "CN_METAL",
        "instrument_class": "cn_metal_futures",
        "window_days": 30,
        "active_rules": ["pa-h2-cn-metal"],
        "scored": [
            {
                "symbol": "kq_m_shfe_cu",
                "date": "2026-06-01",
                "direction": "bottom",
                "level": "vflush",
                "score": 3,
                "options_calls": None,
            },
            _scored_record(date="2026-06-01", iv=20.0),
            _scored_record(
                date="2026-06-02",
                iv=10.0,
                calls=[
                    {
                        "rank": 1,
                        "strike": 880,
                        "otm_pct": 2.33,
                        "expiry_month": "2608",
                        "expiry_date": "2026-08-17",
                        "contract_sym": "au2608c880",
                        "days_to_expiry": 44,
                        "mm_target_pct": 4.0,
                        "is_mm_strike": False,
                        "option_price": 18.5,
                        "price_source": "store",
                        "iv": 12.0,
                    },
                    {
                        "rank": 2,
                        "strike": 896,
                        "otm_pct": 4.19,
                        "expiry_month": "2608",
                        "expiry_date": "2026-08-17",
                        "contract_sym": "au2608c896",
                        "days_to_expiry": 44,
                        "mm_target_pct": 4.0,
                        "is_mm_strike": True,
                        "option_price": 11.2,
                        "price_source": "store",
                        "iv": 10.0,
                    },
                ],
            ),
        ],
    }


def _scorecard_with_model_dominated() -> dict:
    scorecard = _scorecard()
    scorecard["scored"].append(
        _scored_record(
            date="2026-06-03",
            iv=12.0,
            calls=[
                {
                    "rank": 1,
                    "strike": 880,
                    "otm_pct": 2.33,
                    "expiry_month": "2608",
                    "expiry_date": "2026-08-17",
                    "contract_sym": "au2608c880",
                    "days_to_expiry": 43,
                    "is_mm_strike": False,
                    "option_price": 10.4,
                    "price_source": "model",
                    "model_dominated": True,
                    "iv": 12.0,
                }
            ],
        )
    )
    return scorecard


def _decision_intent_scorecard() -> dict:
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
                        "option_price": 12.2,
                        "price_source": "store",
                        "model_dominated": False,
                        "iv": 10.0,
                        "iv_rank": 0.1,
                    }
                ],
                "premium_stop": {
                    "status": "clear",
                    "source": "swing_low_premium",
                    "stop_premium": 11.2,
                    "asof_ts_utc": "2026-06-29T00:00:00Z",
                },
                "premium_confirmation": {
                    "status": "confirmed",
                    "source": "premium_macd",
                    "confirmed_at_utc": "2026-06-29T00:00:00Z",
                    "macd_alert_only": False,
                },
                "liquidity": {
                    "quote_count": 18,
                    "last_quote_age_seconds": 15,
                    "recovery_required": False,
                },
                "pa_phase": "TR",
                "position_size": "half",
            }
        ],
    }


def test_scorecard_snapshot_uses_real_option_emission_and_validates(tmp_path: Path):
    snapshot = snapshot_from_scorecard(
        _scorecard(),
        source_commit=COMMIT,
        generated_at_utc=datetime(2026, 7, 7, tzinfo=UTC),
        iv_warmup=1,
    )

    assert snapshot.run_config["mode"] == "scorecard"
    assert snapshot.data_quality["source_records_total"] == 3
    assert snapshot.data_quality["source_records_with_options"] == 2
    assert snapshot.summary["by_status"] == {"data_blocked": 1, "keep": 1}

    kept = snapshot.signals[-1]
    assert kept.status == "keep"
    assert kept.instrument == "SHFE.au"
    assert kept.option_leg.side == "call"
    assert kept.option_leg.strike == 896
    assert kept.option_leg.otm_rank == 2
    assert kept.features_det["selected_option_contract"] == "au2608c896"
    assert kept.iv_regime.iv_rank == 0.0

    out = tmp_path / "snapshot.json"
    write_snapshot(snapshot, out)
    loaded = load_snapshot(out)
    assert loaded.summary["signals_total"] == 2


def test_scorecard_snapshot_v1_adds_shadow_trace_only_when_requested(tmp_path: Path):
    default_snapshot = snapshot_from_scorecard(
        _scorecard_with_model_dominated(),
        source_commit=COMMIT,
        generated_at_utc=datetime(2026, 7, 7, tzinfo=UTC),
        iv_warmup=1,
    )
    assert default_snapshot.schema_version == "pa_feitian_snapshot_v0"
    assert not hasattr(default_snapshot.signals[-1], "decision_trace_v1")

    snapshot = snapshot_from_scorecard(
        _scorecard_with_model_dominated(),
        source_commit=COMMIT,
        generated_at_utc=datetime(2026, 7, 7, tzinfo=UTC),
        iv_warmup=1,
        contract_version=PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION,
    )

    assert snapshot.schema_version == PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION
    assert snapshot.summary["by_status"] == {
        "data_blocked": 1,
        "keep": 1,
        "model_dominated": 1,
    }
    assert snapshot.data_quality["raw_data_access"] == "not_used_by_pa_feitian_producer"

    model_dominated = snapshot.signals[-1]
    assert model_dominated.status == "model_dominated"
    assert model_dominated.decision_trace_v1.summary.primary_blocker == "model_dominated_premium"
    assert [node.id for node in model_dominated.decision_trace_v1.nodes] == [
        "underlying_signal",
        "policy_rule",
        "option_selection",
        "iv_regime",
        "premium_entry",
        "exit_policy",
    ]

    out = tmp_path / "snapshot-v1.json"
    write_snapshot(snapshot, out)
    loaded = load_snapshot_v1(out)
    assert loaded.signals[-1].decision_trace_v1.status == "model_dominated"


def test_producer_cli_converts_scorecard_file(tmp_path: Path):
    scorecard = tmp_path / "scorecard.json"
    scorecard.write_text(json.dumps(_scorecard()), encoding="utf-8")
    out = tmp_path / "pa_feitian_snapshot_v0.json"

    subprocess.run(
        [
            sys.executable,
            str(SRC_ROOT / "scripts" / "emit_pa_feitian_snapshot.py"),
            "--out",
            str(out),
            "--scorecard",
            str(scorecard),
            "--source-commit",
            COMMIT,
            "--iv-warmup",
            "1",
        ],
        cwd=SRC_ROOT,
        check=True,
    )

    snapshot = load_snapshot(out)
    assert snapshot.source_commit == COMMIT
    assert snapshot.run_config["mode"] == "scorecard"
    assert snapshot.summary["signals_total"] == 2
    assert snapshot.signals[-1].status == "keep"


def test_producer_cli_converts_scorecard_file_to_v1(tmp_path: Path):
    scorecard = tmp_path / "scorecard.json"
    scorecard.write_text(json.dumps(_scorecard_with_model_dominated()), encoding="utf-8")
    out = tmp_path / "pa_feitian_snapshot_v1.json"

    subprocess.run(
        [
            sys.executable,
            str(SRC_ROOT / "scripts" / "emit_pa_feitian_snapshot.py"),
            "--out",
            str(out),
            "--scorecard",
            str(scorecard),
            "--source-commit",
            COMMIT,
            "--iv-warmup",
            "1",
            "--contract-version",
            PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION,
        ],
        cwd=SRC_ROOT,
        check=True,
    )

    snapshot = load_snapshot_v1(out)
    assert snapshot.source_commit == COMMIT
    assert snapshot.run_config["contract"] == PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION
    assert snapshot.summary["signals_total"] == 3
    assert snapshot.signals[-1].decision_trace_v1.action == "watch"


def test_producer_cli_emits_v1_manifest_and_frontend_copy(tmp_path: Path):
    scorecard = tmp_path / "scorecard.json"
    snapshot_path = tmp_path / "pa_feitian_snapshot_v1.json"
    manifest_path = tmp_path / "pa_feitian_run_manifest_v1.json"
    frontend_copy = tmp_path / "dashboard" / "pa_feitian_snapshot_v1.json"
    scorecard.write_text(json.dumps(_scorecard_with_model_dominated()), encoding="utf-8")

    command = [
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
        "--frontend-copy",
        str(frontend_copy),
        "--data-access-status",
        "fixture_fallback",
        "--data-access-source",
        "test deterministic scorecard fixture",
        "--data-access-note",
        "deterministic test scorecard; no live score_today run invoked",
    ]

    subprocess.run(command, cwd=SRC_ROOT, check=True)
    first_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    subprocess.run(command, cwd=SRC_ROOT, check=True)
    second_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert second_manifest == first_manifest
    validate_pa_feitian_run_manifest_schema(second_manifest)

    snapshot = load_snapshot_v1(snapshot_path)
    manifest = load_run_manifest(manifest_path)
    assert snapshot.schema_version == PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION
    assert manifest.source_commit == COMMIT
    assert manifest.scorecard_artifact.sha256 == sha256_file(scorecard)
    assert manifest.snapshot_artifact.sha256 == sha256_file(snapshot_path)
    assert manifest.output_hashes["snapshot_artifact"] == sha256_file(snapshot_path)
    assert manifest.output_hashes["frontend_copy"] == sha256_file(frontend_copy)
    assert manifest.frontend_copy_path == str(frontend_copy)
    assert manifest.data_access.status == "fixture_fallback"
    assert manifest.data_access.source == "test deterministic scorecard fixture"
    assert manifest.run_config["contract"] == PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION
    assert manifest.run_config["mode"] == "scorecard"


def test_producer_cli_manifest_falls_back_to_committed_scorecard_fixture(tmp_path: Path):
    snapshot_path = tmp_path / "pa_feitian_snapshot_v1.json"
    manifest_path = tmp_path / "pa_feitian_run_manifest_v1.json"

    subprocess.run(
        [
            sys.executable,
            str(SRC_ROOT / "scripts" / "emit_pa_feitian_snapshot.py"),
            "--out",
            str(snapshot_path),
            "--source-commit",
            COMMIT,
            "--generated-at-utc",
            "2026-07-07T00:00:00Z",
            "--contract-version",
            PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION,
            "--manifest-out",
            str(manifest_path),
            "--iv-warmup",
            "1",
        ],
        cwd=SRC_ROOT,
        check=True,
    )

    snapshot = load_snapshot_v1(snapshot_path)
    manifest = load_run_manifest(manifest_path)
    assert snapshot.run_config["mode"] == "scorecard"
    assert manifest.data_access.status == "fixture_fallback"
    assert manifest.data_access.source == "src/tests/fixtures/pa_feitian_scorecard_v1.json"
    assert manifest.scorecard_artifact.sha256 == sha256_file(SCORECARD_V1_FIXTURE)
    assert manifest.run_config["contract"] == PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION
    assert manifest.run_config["source_scorecard"].endswith(
        "src/tests/fixtures/pa_feitian_scorecard_v1.json"
    )


def test_producer_cli_locates_score_today_artifact_for_v1_manifest_and_sidecar(
    tmp_path: Path,
):
    artifact_dir = tmp_path / "score_today_artifacts"
    artifact_dir.mkdir()
    stale_artifact = artifact_dir / "2026-07-08_score_today.json"
    score_today_artifact = artifact_dir / "2026-07-09_score_today.json"
    stale_artifact.write_text(json.dumps(_scorecard()), encoding="utf-8")
    score_today_artifact.write_text(json.dumps(_decision_intent_scorecard()), encoding="utf-8")
    snapshot_path = tmp_path / "pa_feitian_snapshot_v1.json"
    manifest_path = tmp_path / "pa_feitian_run_manifest_v1.json"
    sidecar_path = tmp_path / "pa_feitian_decision_intent_v1.json"

    command = [
        sys.executable,
        str(SRC_ROOT / "scripts" / "emit_pa_feitian_snapshot.py"),
        "--out",
        str(snapshot_path),
        "--score-today-artifact-dir",
        str(artifact_dir),
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
    ]

    subprocess.run(command, cwd=SRC_ROOT, check=True)
    first_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    first_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    first_sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))

    subprocess.run(command, cwd=SRC_ROOT, check=True)
    second_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    second_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    second_sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))

    assert second_snapshot == first_snapshot
    assert second_manifest == first_manifest
    assert second_sidecar == first_sidecar

    snapshot = load_snapshot_v1(snapshot_path)
    manifest = load_run_manifest(manifest_path)
    sidecar = load_decision_intent(sidecar_path)

    assert snapshot.summary["signals_total"] == 1
    assert sidecar.intents[0].decision_state == "trade_ready"
    assert manifest.data_access.status == "real_data_available"
    assert manifest.data_access.source == score_today_artifact.as_posix()
    assert manifest.data_access.notes[0] == (
        "located existing score_today JSON artifact; producer did not read raw data stores"
    )
    assert manifest.scorecard_artifact.sha256 == sha256_file(score_today_artifact)
    assert manifest.snapshot_artifact.sha256 == sha256_file(snapshot_path)
    assert manifest.decision_intent_artifact is not None
    assert manifest.decision_intent_artifact.sha256 == sha256_file(sidecar_path)
    assert sidecar.provenance.snapshot_artifact_sha256 == sha256_file(snapshot_path)


def test_producer_cli_fixture_fallback_can_emit_manifest_and_sidecar(tmp_path: Path):
    snapshot_path = tmp_path / "pa_feitian_snapshot_v1.json"
    manifest_path = tmp_path / "pa_feitian_run_manifest_v1.json"
    sidecar_path = tmp_path / "pa_feitian_decision_intent_v1.json"

    command = [
        sys.executable,
        str(SRC_ROOT / "scripts" / "emit_pa_feitian_snapshot.py"),
        "--out",
        str(snapshot_path),
        "--source-commit",
        COMMIT,
        "--generated-at-utc",
        "2026-07-07T00:00:00Z",
        "--contract-version",
        PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION,
        "--manifest-out",
        str(manifest_path),
        "--decision-intent-out",
        str(sidecar_path),
        "--iv-warmup",
        "1",
    ]

    subprocess.run(command, cwd=SRC_ROOT, check=True)
    first_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    first_sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))

    subprocess.run(command, cwd=SRC_ROOT, check=True)
    second_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    second_sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))

    assert second_manifest == first_manifest
    assert second_sidecar == first_sidecar

    manifest = load_run_manifest(manifest_path)
    sidecar = load_decision_intent(sidecar_path)

    assert manifest.data_access.status == "fixture_fallback"
    assert manifest.data_access.source == "src/tests/fixtures/pa_feitian_scorecard_v1.json"
    assert manifest.scorecard_artifact.sha256 == sha256_file(SCORECARD_V1_FIXTURE)
    assert manifest.decision_intent_artifact is not None
    assert manifest.decision_intent_artifact.sha256 == sha256_file(sidecar_path)
    assert sidecar.provenance.snapshot_artifact_sha256 == sha256_file(snapshot_path)
