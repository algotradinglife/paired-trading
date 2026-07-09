from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.contract import load_decision_intent, load_snapshot  # noqa: E402
from engine.pa_feitian.manifest import load_run_manifest, sha256_file  # noqa: E402


SRC_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC_ROOT.parent
COMMIT = "b" * 40


def _scorecard() -> dict:
    def record(date: str, iv: float) -> dict:
        return {
            "symbol": "kq_m_shfe_au",
            "date": date,
            "direction": "bottom",
            "level": "pa_h2",
            "subtype": "pa_h2",
            "confidence": 0.75,
            "score": 4,
            "policy_rule": "pa-h2-cn-metal-tr-phase",
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
                    "option_price": 18.5,
                    "price_source": "store",
                    "iv": iv,
                }
            ],
        }

    return {
        "pool": "CN_METAL",
        "instrument_class": "cn_metal_futures",
        "window_days": 30,
        "active_rules": ["pa-h2-cn-metal"],
        "scored": [
            record("2026-06-01", 20.0),
            record("2026-06-02", 10.0),
        ],
    }


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


def test_scorecard_cli_output_renders_in_frontend(tmp_path: Path):
    scorecard_path = tmp_path / "scorecard.json"
    snapshot_path = tmp_path / "pa_feitian_snapshot_v0.json"
    scorecard_path.write_text(json.dumps(_scorecard()), encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            str(SRC_ROOT / "scripts" / "emit_pa_feitian_snapshot.py"),
            "--out",
            str(snapshot_path),
            "--scorecard",
            str(scorecard_path),
            "--source-commit",
            COMMIT,
            "--generated-at-utc",
            datetime(2026, 7, 8, tzinfo=UTC).isoformat(),
            "--iv-warmup",
            "1",
        ],
        cwd=SRC_ROOT,
        check=True,
    )

    snapshot = load_snapshot(snapshot_path)
    assert snapshot.run_config["mode"] == "scorecard"
    assert snapshot.summary["signals_total"] == 2
    assert snapshot.signals[-1].status == "keep"

    render_script = f"""
        import {{ readFile }} from "node:fs/promises";
        const snapshot = JSON.parse(await readFile(process.argv[1], "utf8"));
        const {{ renderDashboard }} = await import("{(REPO_ROOT / "frontend" / "pa-feitian-dashboard" / "app.mjs").as_uri()}");
        const html = renderDashboard(snapshot);
        if (!html.includes("Signal Table")) process.exit(11);
        if (!html.includes("paft_scorecard_")) process.exit(12);
        if (!html.includes("scorecard")) process.exit(13);
    """
    subprocess.run(
        ["node", "--input-type=module", "-e", render_script, str(snapshot_path)],
        cwd=REPO_ROOT,
        check=True,
    )


def test_scorecard_cli_v1_sidecar_manifest_renders_in_frontend(tmp_path: Path):
    scorecard_path = tmp_path / "scorecard.json"
    snapshot_path = tmp_path / "pa_feitian_snapshot_v1.json"
    sidecar_path = tmp_path / "pa_feitian_decision_intent_v1.json"
    manifest_path = tmp_path / "pa_feitian_run_manifest_v1.json"
    scorecard_path.write_text(
        json.dumps(_decision_intent_scorecard()),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            str(SRC_ROOT / "scripts" / "emit_pa_feitian_snapshot.py"),
            "--out",
            str(snapshot_path),
            "--scorecard",
            str(scorecard_path),
            "--source-commit",
            COMMIT,
            "--generated-at-utc",
            datetime(2026, 7, 8, tzinfo=UTC).isoformat(),
            "--iv-warmup",
            "1",
            "--contract-version",
            "pa_feitian_snapshot_v1",
            "--manifest-out",
            str(manifest_path),
            "--decision-intent-out",
            str(sidecar_path),
            "--data-access-status",
            "fixture_fallback",
            "--data-access-source",
            "deterministic integration scorecard fixture",
        ],
        cwd=SRC_ROOT,
        check=True,
    )

    snapshot = load_snapshot(snapshot_path)
    sidecar = load_decision_intent(sidecar_path)
    manifest = load_run_manifest(manifest_path)

    assert snapshot.schema_version == "pa_feitian_snapshot_v1"
    assert sidecar.schema_version == "pa_feitian_decision_intent_v1"
    assert sidecar.intents[0].decision_state == "trade_ready"
    assert sidecar.intents[0].execution_allowed is True
    assert manifest.decision_intent_artifact is not None
    assert manifest.decision_intent_artifact.sha256 == sha256_file(sidecar_path)
    assert manifest.output_hashes["decision_intent_artifact"] == sha256_file(
        sidecar_path
    )

    render_script = f"""
        import {{ readFile }} from "node:fs/promises";
        const snapshot = JSON.parse(await readFile(process.argv[1], "utf8"));
        const manifest = JSON.parse(await readFile(process.argv[2], "utf8"));
        const decisionIntent = JSON.parse(await readFile(process.argv[3], "utf8"));
        const {{ renderDashboard }} = await import("{(REPO_ROOT / "frontend" / "pa-feitian-dashboard" / "app.mjs").as_uri()}");
        const html = renderDashboard(snapshot, {{ manifest, decisionIntent }});
        if (!html.includes('data-testid="decision-intent-review"')) process.exit(21);
        if (!html.includes("execution_allowed: true")) process.exit(22);
        if (!html.includes("TRADE_READY_PREMIUM_CONFIRMED")) process.exit(23);
        if (!html.includes("decision_state")) process.exit(24);
    """
    subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            render_script,
            str(snapshot_path),
            str(manifest_path),
            str(sidecar_path),
        ],
        cwd=REPO_ROOT,
        check=True,
    )
