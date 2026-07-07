from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.contract import load_snapshot  # noqa: E402


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
