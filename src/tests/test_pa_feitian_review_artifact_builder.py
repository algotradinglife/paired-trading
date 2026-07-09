from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.contract import load_decision_intent, load_snapshot_v1  # noqa: E402
from engine.pa_feitian.manifest import load_run_manifest, sha256_file  # noqa: E402
from engine.pa_feitian.schema_validation import (  # noqa: E402
    validate_pa_feitian_decision_intent_schema,
    validate_pa_feitian_run_manifest_schema,
    validate_pa_feitian_snapshot_v1_schema,
)


SRC_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC_ROOT.parent
BUILDER = SRC_ROOT / "scripts" / "build_pa_feitian_review_artifacts.py"
SCORECARD_FIXTURE = SRC_ROOT / "tests" / "fixtures" / "pa_feitian_scorecard_v1.json"
COMMIT = "d" * 40


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


def _run_builder(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BUILDER), *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )


def _artifact_paths(source_dir: Path, dashboard_dir: Path) -> dict[str, Path]:
    return {
        "dashboard_decision_intent": dashboard_dir / "pa_feitian_decision_intent_v1.json",
        "dashboard_manifest": dashboard_dir / "pa_feitian_run_manifest_v1.json",
        "dashboard_snapshot": dashboard_dir / "pa_feitian_snapshot_v1.json",
        "source_decision_intent": source_dir / "pa_feitian_decision_intent_v1.json",
        "source_manifest": source_dir / "pa_feitian_run_manifest_v1.json",
        "source_review_manifest": source_dir
        / "pa_feitian_run_manifest_with_decision_intent_v1.json",
        "source_snapshot": source_dir / "pa_feitian_snapshot_v1.json",
    }


def _read_outputs(paths: dict[str, Path]) -> dict[str, str]:
    return {name: path.read_text(encoding="utf-8") for name, path in paths.items()}


def test_review_artifact_builder_writes_stable_dashboard_review_set(tmp_path: Path):
    scorecard_path = tmp_path / "score_today.json"
    source_dir = tmp_path / "source-fixtures"
    dashboard_dir = tmp_path / "dashboard-fixtures"
    scorecard_path.write_text(json.dumps(_score_today_artifact()), encoding="utf-8")

    command_args = [
        "--score-today-artifact",
        str(scorecard_path),
        "--source-fixture-dir",
        str(source_dir),
        "--dashboard-fixture-dir",
        str(dashboard_dir),
        "--source-commit",
        COMMIT,
        "--generated-at-utc",
        "2026-07-07T00:00:00Z",
    ]
    result = _run_builder(*command_args)
    paths = _artifact_paths(source_dir, dashboard_dir)
    first_outputs = _read_outputs(paths)

    _run_builder(*command_args)
    assert _read_outputs(paths) == first_outputs
    assert json.loads(result.stdout) == {
        name: path.as_posix() for name, path in sorted(paths.items())
    }

    snapshot = load_snapshot_v1(paths["source_snapshot"])
    sidecar = load_decision_intent(paths["dashboard_decision_intent"])
    source_manifest = load_run_manifest(paths["source_review_manifest"])
    dashboard_manifest_payload = json.loads(paths["dashboard_manifest"].read_text(encoding="utf-8"))
    dashboard_manifest = load_run_manifest(paths["dashboard_manifest"])

    validate_pa_feitian_snapshot_v1_schema(json.loads(first_outputs["source_snapshot"]))
    validate_pa_feitian_decision_intent_schema(
        json.loads(first_outputs["dashboard_decision_intent"])
    )
    validate_pa_feitian_run_manifest_schema(dashboard_manifest_payload)

    assert snapshot.run_config["mode"] == "scorecard"
    assert sidecar.intents[0].decision_state == "trade_ready"
    assert dashboard_manifest.data_access.status == "real_data_available"
    assert dashboard_manifest.scorecard_artifact.path == scorecard_path.as_posix()
    assert dashboard_manifest.scorecard_artifact.sha256 == sha256_file(scorecard_path)
    assert dashboard_manifest.snapshot_artifact.path == paths["source_snapshot"].as_posix()
    assert dashboard_manifest.snapshot_artifact.sha256 == sha256_file(paths["source_snapshot"])
    assert dashboard_manifest.frontend_copy_path == paths["dashboard_snapshot"].as_posix()
    assert dashboard_manifest.output_hashes["frontend_copy"] == sha256_file(
        paths["dashboard_snapshot"]
    )
    assert dashboard_manifest.decision_intent_artifact is not None
    assert (
        dashboard_manifest.decision_intent_artifact.path
        == paths["dashboard_decision_intent"].as_posix()
    )
    assert dashboard_manifest.output_hashes["decision_intent_artifact"] == sha256_file(
        paths["dashboard_decision_intent"]
    )
    assert dashboard_manifest.output_hashes["frontend_decision_intent_copy"] == sha256_file(
        paths["dashboard_decision_intent"]
    )
    assert source_manifest.decision_intent_artifact is not None
    assert (
        source_manifest.decision_intent_artifact.path == paths["source_decision_intent"].as_posix()
    )
    assert (
        paths["dashboard_snapshot"].read_text(encoding="utf-8") == first_outputs["source_snapshot"]
    )
    assert (
        paths["dashboard_decision_intent"].read_text(encoding="utf-8")
        == first_outputs["source_decision_intent"]
    )

    render_script = f"""
        import {{ readFile }} from "node:fs/promises";
        const snapshot = JSON.parse(await readFile(process.argv[1], "utf8"));
        const manifest = JSON.parse(await readFile(process.argv[2], "utf8"));
        const decisionIntent = JSON.parse(await readFile(process.argv[3], "utf8"));
        const {{ renderDashboard }} = await import("{(REPO_ROOT / "frontend" / "pa-feitian-dashboard" / "app.mjs").as_uri()}");
        const html = renderDashboard(snapshot, {{ manifest, decisionIntent }});
        if (!html.includes('data-testid="decision-intent-review"')) process.exit(31);
        if (!html.includes("trade_ready")) process.exit(32);
        if (!html.includes("Generated snapshot")) process.exit(33);
    """
    subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            render_script,
            str(paths["dashboard_snapshot"]),
            str(paths["dashboard_manifest"]),
            str(paths["dashboard_decision_intent"]),
        ],
        cwd=REPO_ROOT,
        check=True,
    )


def test_review_artifact_builder_uses_deterministic_fixture_fallback(tmp_path: Path):
    source_dir = tmp_path / "source-fixtures"
    dashboard_dir = tmp_path / "dashboard-fixtures"

    _run_builder(
        "--source-fixture-dir",
        str(source_dir),
        "--dashboard-fixture-dir",
        str(dashboard_dir),
        "--source-commit",
        COMMIT,
        "--generated-at-utc",
        "2026-07-07T00:00:00Z",
        "--scorecard-fixture",
        str(SCORECARD_FIXTURE),
    )

    paths = _artifact_paths(source_dir, dashboard_dir)
    manifest = load_run_manifest(paths["dashboard_manifest"])
    sidecar = load_decision_intent(paths["dashboard_decision_intent"])

    assert manifest.data_access.status == "fixture_fallback"
    assert manifest.data_access.source == "src/tests/fixtures/pa_feitian_scorecard_v1.json"
    assert manifest.scorecard_artifact.sha256 == sha256_file(SCORECARD_FIXTURE)
    assert [intent.decision_state for intent in sidecar.intents] == [
        "armed_watch",
        "trade_ready",
        "watch",
    ]
