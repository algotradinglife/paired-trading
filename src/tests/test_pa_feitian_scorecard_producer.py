from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.contract import (  # noqa: E402
    load_snapshot,
    snapshot_from_scorecard,
    write_snapshot,
)


SRC_ROOT = Path(__file__).resolve().parents[1]
COMMIT = "a" * 40


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
