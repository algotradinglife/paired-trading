from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from engine.pa_feitian.historical_cohort import (
    load_frozen_protocol,
    run_historical_cohort,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = REPO_ROOT / "docs/research/pa-feitian-m6-historical-cohort-protocol-v1.json"
CONTRACT_FILES = (
    "SHFE.au2606C1152.parquet",
    "SHFE.au2606C1136.parquet",
    "SHFE.ag2607C19900.parquet",
    "SHFE.ag2608C18800.parquet",
)


def _write_contracts(root: Path) -> None:
    daily = root / "daily"
    daily.mkdir(parents=True)
    dates = pd.bdate_range("2026-03-10", "2026-06-16")
    bars = pd.DataFrame(
        {
            "datetime": dates,
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 100.0,
            "volume": 1.0,
            "turnover": 100.0,
            "open_interest": 1.0,
        }
    )
    for filename in CONTRACT_FILES:
        bars.to_parquet(daily / filename, index=False)


def test_frozen_cohort_retains_exclusions_and_suppresses_small_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    quant_root = tmp_path / "quant"
    _write_contracts(quant_root)

    def reject_unbounded_glob(*_args, **_kwargs):
        raise AssertionError("historical cohort must not glob the market-data root")

    monkeypatch.setattr(Path, "glob", reject_unbounded_glob)
    output = tmp_path / "out"
    report = run_historical_cohort(
        protocol_path=PROTOCOL,
        repo_root=REPO_ROOT,
        quant_data_root=quant_root,
        audit_out=output / "audit.json",
        baseline_out=output / "baseline.json",
        candidate_out=output / "candidate.json",
        report_out=output / "report.json",
        generated_at_utc=datetime(2026, 7, 11, 13, 30, tzinfo=UTC),
        source_commit="c6225aa",
    )

    assert report["coverage_funnel"] == {
        "source_rows": 13,
        "eligible_rows": 4,
        "excluded_rows": 9,
        "exclusions_by_reason": {
            "missing_rank1_selected_option_contract": 2,
            "outside_frozen_universe": 7,
        },
    }
    assert report["pooled_descriptive"]["comparable_event_count"] == 4
    assert report["threshold_gates"]["grouped_results"]["emitted"] is False
    assert report["threshold_gates"]["oos_results"]["emitted"] is False
    assert report["threshold_gates"]["screening"] == {
        "classification": "insufficient_sample",
        "strategy_inference_allowed": False,
        "advance_m7": False,
    }
    audit = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    assert len(audit["rows"]) == 13
    assert audit["bounded_contract_count"] == 4
    assert audit["guardrails"]["raw_directory_glob"] is False


def test_protocol_rejects_non_frozen_baseline_stop(tmp_path: Path) -> None:
    payload = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    payload["policies"]["baseline"]["stop_fraction_of_entry"] = 0.4
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="baseline stop must be frozen at 50%"):
        load_frozen_protocol(path)
