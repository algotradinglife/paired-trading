from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.contract import (  # noqa: E402
    PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION,
    write_decision_intent,
    write_snapshot,
)
from engine.pa_feitian.decision_intent_adapter import (  # noqa: E402
    build_decision_intent_sidecar,
)
from engine.pa_feitian.manifest import (  # noqa: E402
    build_run_manifest,
    load_run_manifest,
    sha256_file,
    write_run_manifest,
)
from engine.pa_feitian.premium_outcome import load_premium_outcome  # noqa: E402
from engine.pa_feitian.premium_outcome_harness import (  # noqa: E402
    PremiumOutcomeHarnessConfig,
    build_premium_outcome_sidecar_from_files,
    canonical_policy_digest,
)
from engine.pa_feitian.schema_validation import (  # noqa: E402
    validate_pa_feitian_premium_outcome_schema,
    validate_pa_feitian_run_manifest_schema,
)
from engine.pa_feitian.scorecard_producer import snapshot_from_scorecard  # noqa: E402


SRC_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC_ROOT.parent
SCRIPT = SRC_ROOT / "scripts" / "build_pa_feitian_premium_outcomes.py"
PYTHON = Path(sys.executable)
COMMIT = "5a6e2c9"
GENERATED_AT = datetime(2026, 7, 10, tzinfo=UTC)


def _bar(date: str, open_: float, high: float, low: float, close: float) -> dict:
    return {
        "datetime": datetime.fromisoformat(date),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 10.0,
        "turnover": close * 10.0,
        "open_interest": 5.0,
    }


def _write_contract(root: Path, name: str, bars: list[dict]) -> None:
    daily = root / "daily"
    daily.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(bars).to_parquet(daily / f"{name}.parquet", index=False)


def _ten_bars(start: str = "2026-06-30", *, open_: float = 10.0, close: float = 11.0):
    first = datetime.fromisoformat(start)
    return [
        _bar(
            (first + timedelta(days=i)).date().isoformat(),
            open_ if i == 0 else close,
            max(open_, close) + 1.0,
            min(open_, close) - 1.0,
            close,
        )
        for i in range(10)
    ]


def _record(
    date: str = "2026-06-29",
    *,
    contract_sym: str = "au2608c880",
    strike: float = 880,
    expiry_month: str = "2608",
    expiry_date: str = "2026-08-17",
    option_price: float = 10.0,
    price_source: str = "store",
    model_dominated: bool = False,
    iv_rank: float = 0.1,
    extra_calls: list[dict] | None = None,
) -> dict:
    calls = [
        {
            "rank": 1,
            "strike": strike,
            "otm_pct": 2.33,
            "expiry_month": expiry_month,
            "expiry_date": expiry_date,
            "contract_sym": contract_sym,
            "days_to_expiry": 45,
            "is_mm_strike": False,
            "option_price": option_price,
            "price_source": price_source,
            "model_dominated": model_dominated,
            "iv": 10.0,
            "iv_rank": iv_rank,
        }
    ]
    if extra_calls:
        calls.extend(extra_calls)
    return {
        "symbol": "kq_m_shfe_au",
        "date": date,
        "direction": "bottom",
        "level": "pa_h2",
        "subtype": "pa_h2",
        "confidence": 0.75,
        "score": 4,
        "policy_rule": "pa-h2-cn-metal-tr-phase",
        "policy_weight": 0.75,
        "underlying_price": 860.0,
        "options_calls": calls,
        "premium_stop": {
            "status": "clear",
            "source": "swing_low_premium",
            "stop_premium": option_price * 0.9,
            "asof_ts_utc": f"{date}T00:00:00Z",
        },
        "premium_confirmation": {
            "status": "confirmed",
            "source": "premium_macd",
            "confirmed_at_utc": f"{date}T00:00:00Z",
        },
        "liquidity": {
            "quote_count": 18,
            "last_quote_age_seconds": 15,
            "recovery_required": False,
        },
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


def _bundle(tmp_path: Path, records: list[dict]):
    source = tmp_path / "source"
    dashboard = tmp_path / "dashboard"
    source.mkdir(parents=True)
    dashboard.mkdir(parents=True)
    scorecard_path = source / "scorecard.json"
    snapshot_path = source / "pa_feitian_snapshot_v1.json"
    frontend_snapshot_path = dashboard / "pa_feitian_snapshot_v1.json"
    decision_path = source / "pa_feitian_decision_intent_v1.json"
    manifest_path = source / "pa_feitian_run_manifest_with_decision_intent_v1.json"
    scorecard = _scorecard(records)
    scorecard_path.write_text(json.dumps(scorecard), encoding="utf-8")
    snapshot = snapshot_from_scorecard(
        scorecard,
        source_commit=COMMIT,
        generated_at_utc=GENERATED_AT,
        iv_warmup=1,
        contract_version=PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION,
    )
    write_snapshot(snapshot, snapshot_path)
    frontend_snapshot_path.write_text(snapshot_path.read_text(encoding="utf-8"), encoding="utf-8")
    decision = build_decision_intent_sidecar(
        snapshot,
        source_commit=COMMIT,
        source_manifest_path=manifest_path,
        snapshot_artifact_path=snapshot_path,
        generated_at_utc=GENERATED_AT,
        source_manifest_generated_at_utc=GENERATED_AT,
        scorecard=scorecard,
    )
    write_decision_intent(decision, decision_path)
    manifest = build_run_manifest(
        scorecard_path=scorecard_path,
        snapshot_path=snapshot_path,
        source_commit=COMMIT,
        cli_args=["m4-fixture"],
        run_config=snapshot.run_config,
        generated_at_utc=GENERATED_AT,
        frontend_copy_path=frontend_snapshot_path,
        decision_intent_path=decision_path,
        data_access={"status": "fixture_fallback", "source": str(scorecard_path), "notes": []},
    )
    write_run_manifest(manifest, manifest_path)
    return {
        "scorecard": scorecard_path,
        "snapshot": snapshot_path,
        "frontend_snapshot": frontend_snapshot_path,
        "decision": decision_path,
        "manifest": manifest_path,
    }


def _sidecar(
    tmp_path: Path,
    bars: list[dict] | None,
    record: dict | None = None,
    config: PremiumOutcomeHarnessConfig | None = None,
):
    paths = _bundle(tmp_path, [record or _record()])
    quant = tmp_path / "quant"
    if bars is not None:
        _write_contract(quant, "SHFE.au2608C880", bars)
    harness_config = config or PremiumOutcomeHarnessConfig(
        source_commit=COMMIT,
        generated_at_utc=GENERATED_AT,
        policy_declared_at_utc=GENERATED_AT,
        traversal_started_at_utc=GENERATED_AT + timedelta(minutes=1),
        cli_args=("test-harness",),
    )
    sidecar = build_premium_outcome_sidecar_from_files(
        snapshot_path=paths["snapshot"],
        decision_intent_path=paths["decision"],
        source_manifest_path=paths["manifest"],
        quant_data_root=quant,
        config=harness_config,
    )
    return sidecar, paths, quant


def test_m5_harness_observes_target_with_premium_r_math_and_policy_digest(tmp_path: Path):
    sidecar, _, _ = _sidecar(
        tmp_path,
        [
            _bar("2026-06-30", 10.0, 12.0, 9.0, 10.5),
            _bar("2026-07-01", 10.5, 21.0, 10.0, 20.0),
            *_ten_bars("2026-07-02")[:8],
        ],
    )
    outcome = sidecar.outcomes[0]

    assert outcome.evaluation_status == "observed"
    assert outcome.exit_reason == "premium_target"
    assert outcome.entry_fill.fill_premium == pytest.approx(10.04)
    assert outcome.exit_fill.fill_premium == pytest.approx(20.04)
    assert outcome.underlying_context is None
    notes = " ".join(outcome.data_quality.notes)
    assert "observation-only" in notes
    assert "daily bar-envelope excursions through the exit bar" in notes
    assert "premium-unit normalization only" in " ".join(outcome.cost_model.notes)
    assert outcome.premium_metrics.premium_multiple == pytest.approx(20.04 / 10.04)
    assert outcome.premium_metrics.premium_r == pytest.approx((20.04 - 10.04) / 5.06)
    assert outcome.premium_metrics.premium_mfe == pytest.approx((21.0 - 10.04) / 10.04)
    assert outcome.premium_metrics.premium_mae == pytest.approx((9.0 - 10.04) / 10.04)
    assert (
        sidecar.provenance.policy_hashes[outcome.policy.provenance_hash_key]
        == outcome.policy.digest
    )
    assert outcome.policy.digest == canonical_policy_digest(
        policy_id=outcome.policy.policy_id,
        policy_version=outcome.policy.policy_version,
        declared_at_utc=outcome.policy.declared_at_utc,
        traversal_started_at_utc=outcome.policy.traversal_started_at_utc,
        params=outcome.policy.params,
    )
    assert f"selected_option_bars:{outcome.outcome_id}" in sidecar.provenance.input_hashes


def test_m5_harness_normalizes_unsorted_target_multiples_and_exits_nearest_target(
    tmp_path: Path,
):
    sidecar, _, _ = _sidecar(
        tmp_path,
        [
            _bar("2026-06-30", 10.0, 12.0, 9.0, 10.5),
            _bar("2026-07-01", 10.5, 25.0, 10.0, 24.0),
            *_ten_bars("2026-07-02")[:8],
        ],
        config=PremiumOutcomeHarnessConfig(
            source_commit=COMMIT,
            generated_at_utc=GENERATED_AT,
            policy_declared_at_utc=GENERATED_AT,
            traversal_started_at_utc=GENERATED_AT + timedelta(minutes=1),
            target_multiples_of_entry=(3.0, 2.0, 2.0),
            cli_args=("test-unsorted-targets",),
        ),
    )
    outcome = sidecar.outcomes[0]

    assert outcome.evaluation_status == "observed"
    assert outcome.exit_reason == "premium_target"
    assert outcome.policy.params.target_multiples_of_entry == [2.0, 3.0]
    assert outcome.exit_fill.fill_premium == pytest.approx(20.04)
    assert "nearest declared target" in " ".join(outcome.data_quality.notes)


def test_m5_harness_observes_stop_and_gap_open_stop(tmp_path: Path):
    stop, _, _ = _sidecar(
        tmp_path / "stop",
        [
            _bar("2026-06-30", 10.0, 11.0, 9.0, 10.5),
            _bar("2026-07-01", 10.5, 11.0, 4.9, 5.1),
            *_ten_bars("2026-07-02")[:8],
        ],
    )
    gap, _, _ = _sidecar(
        tmp_path / "gap",
        [
            _bar("2026-06-30", 10.0, 11.0, 9.0, 10.5),
            _bar("2026-07-01", 4.0, 4.5, 3.8, 4.2),
            *_ten_bars("2026-07-02")[:8],
        ],
    )

    stopped = stop.outcomes[0]
    assert stopped.exit_reason == "premium_stop"
    assert stopped.exit_fill.fill_rule == "at_level"
    assert stopped.exit_fill.fill_premium == pytest.approx(4.98)
    assert stopped.premium_metrics.premium_r == pytest.approx(-1.0)

    gapped = gap.outcomes[0]
    assert gapped.exit_reason == "premium_stop"
    assert gapped.exit_fill.fill_rule == "gap_open"
    assert gapped.exit_fill.fill_premium == pytest.approx(3.96)
    assert gapped.premium_metrics.premium_r < -1.0


def test_m5_harness_observes_gap_open_target_and_time_exit(tmp_path: Path):
    gap, _, _ = _sidecar(
        tmp_path / "gap_target",
        [
            _bar("2026-06-30", 10.0, 11.0, 9.0, 10.5),
            _bar("2026-07-01", 21.0, 22.0, 20.5, 21.5),
            *_ten_bars("2026-07-02")[:8],
        ],
    )
    timed, _, _ = _sidecar(
        tmp_path / "time",
        _ten_bars(close=12.0),
    )

    gap_outcome = gap.outcomes[0]
    assert gap_outcome.exit_reason == "premium_target"
    assert gap_outcome.exit_fill.fill_rule == "gap_open"
    assert gap_outcome.exit_fill.fill_premium == pytest.approx(20.96)

    time_outcome = timed.outcomes[0]
    assert time_outcome.exit_reason == "time_exit"
    assert time_outcome.exit_fill.ts_utc.isoformat().startswith("2026-07-09")
    assert time_outcome.exit_fill.fill_premium == pytest.approx(11.96)


def test_m5_harness_marks_same_bar_ambiguity_and_data_blockers(tmp_path: Path):
    ambiguous, _, _ = _sidecar(
        tmp_path / "ambiguous",
        [
            _bar("2026-06-30", 10.0, 21.0, 4.9, 10.5),
            *_ten_bars("2026-07-01")[:9],
        ],
    )
    missing_contract, _, _ = _sidecar(tmp_path / "missing_contract", None)
    invalid, _, _ = _sidecar(
        tmp_path / "invalid",
        [
            _bar("2026-06-30", 0.0, 11.0, 0.0, 10.5),
            *_ten_bars("2026-07-01")[:9],
        ],
    )
    early, _, _ = _sidecar(
        tmp_path / "early",
        [_bar("2026-06-30", 10.0, 11.0, 9.0, 10.5)],
    )

    assert ambiguous.outcomes[0].evaluation_status == "ambiguous"
    assert ambiguous.outcomes[0].exit_reason == "unresolved"
    assert ambiguous.outcomes[0].data_quality.ambiguity.kind == "same_bar_stop_target"

    assert missing_contract.outcomes[0].evaluation_status == "data_blocked"
    assert missing_contract.outcomes[0].data_quality.data_gap.kind == "missing_contract"

    assert invalid.outcomes[0].evaluation_status == "data_blocked"
    assert invalid.outcomes[0].data_quality.data_gap.kind == "missing_entry"

    assert early.outcomes[0].evaluation_status == "data_blocked"
    assert early.outcomes[0].data_quality.data_gap.kind == "early_termination"


def test_m5_harness_keeps_model_derived_rejection_not_evaluable(tmp_path: Path):
    record = _record(price_source="model", model_dominated=True, iv_rank=1.0)
    sidecar, _, _ = _sidecar(tmp_path, _ten_bars(), record)
    outcome = sidecar.outcomes[0]

    assert outcome.evaluation_status == "not_evaluable"
    assert outcome.exit_reason == "not_evaluable"
    assert outcome.data_quality.premium_price_source_type == "model_derived"
    assert outcome.entry_fill is None
    assert outcome.premium_metrics is None


def test_m5_harness_uses_snapshot_selected_contract_without_reselection(tmp_path: Path):
    other_call = {
        "rank": 2,
        "strike": 900,
        "otm_pct": 4.0,
        "expiry_month": "2608",
        "expiry_date": "2026-08-17",
        "contract_sym": "au2608c900",
        "days_to_expiry": 45,
        "is_mm_strike": False,
        "option_price": 8.0,
        "price_source": "store",
        "model_dominated": False,
        "iv": 10.0,
        "iv_rank": 0.1,
    }
    paths = _bundle(tmp_path, [_record(extra_calls=[other_call])])
    quant = tmp_path / "quant"
    _write_contract(quant, "SHFE.au2608C880", _ten_bars(close=12.0))
    _write_contract(
        quant,
        "SHFE.au2608C900",
        [
            _bar("2026-06-30", 8.0, 40.0, 7.5, 35.0),
            *_ten_bars("2026-07-01")[:9],
        ],
    )
    sidecar = build_premium_outcome_sidecar_from_files(
        snapshot_path=paths["snapshot"],
        decision_intent_path=paths["decision"],
        source_manifest_path=paths["manifest"],
        quant_data_root=quant,
        config=PremiumOutcomeHarnessConfig(
            source_commit=COMMIT,
            generated_at_utc=GENERATED_AT,
            policy_declared_at_utc=GENERATED_AT,
            traversal_started_at_utc=GENERATED_AT + timedelta(minutes=1),
            cli_args=("test",),
        ),
    )

    outcome = sidecar.outcomes[0]
    assert outcome.selected_contract.contract_symbol == "au2608c880"
    assert outcome.exit_reason == "time_exit"


def test_m5_cli_is_deterministic_and_links_manifest_without_mutating_sources(tmp_path: Path):
    paths = _bundle(tmp_path, [_record()])
    quant = tmp_path / "quant"
    _write_contract(quant, "SHFE.au2608C880", _ten_bars(close=12.0))
    source_hashes_before = {name: sha256_file(path) for name, path in paths.items()}
    out = tmp_path / "m5" / "pa_feitian_premium_outcome_v1.json"
    manifest_out = tmp_path / "m5" / "pa_feitian_run_manifest_m5_v1.json"
    frontend_copy = tmp_path / "frontend" / "pa_feitian_premium_outcome_v1.json"
    command = [
        str(PYTHON),
        str(SCRIPT),
        "--snapshot",
        str(paths["snapshot"]),
        "--decision-intent",
        str(paths["decision"]),
        "--source-m4-manifest",
        str(paths["manifest"]),
        "--quant-data-root",
        str(quant),
        "--out",
        str(out),
        "--manifest-out",
        str(manifest_out),
        "--frontend-outcome-copy",
        str(frontend_copy),
        "--generated-at-utc",
        "2026-07-10T00:00:00Z",
        "--policy-declared-at-utc",
        "2026-07-10T00:00:00Z",
        "--traversal-started-at-utc",
        "2026-07-10T00:01:00Z",
        "--source-commit",
        COMMIT,
    ]
    env = {**os.environ, "PYTHONPATH": str(SRC_ROOT)}

    subprocess.run(command, cwd=REPO_ROOT, env=env, check=True, capture_output=True, text=True)
    first_sidecar = out.read_bytes()
    first_manifest = manifest_out.read_bytes()
    subprocess.run(command, cwd=REPO_ROOT, env=env, check=True, capture_output=True, text=True)

    assert out.read_bytes() == first_sidecar
    assert manifest_out.read_bytes() == first_manifest
    assert frontend_copy.read_bytes() == first_sidecar
    assert {name: sha256_file(path) for name, path in paths.items()} == source_hashes_before

    sidecar = load_premium_outcome(out)
    manifest = load_run_manifest(manifest_out)
    validate_pa_feitian_premium_outcome_schema(sidecar.model_dump(mode="json"))
    validate_pa_feitian_run_manifest_schema(manifest.model_dump(mode="json", exclude_none=False))
    assert manifest.premium_outcome_artifact.sha256 == sha256_file(out)
    assert manifest.output_hashes["premium_outcome_artifact"] == sha256_file(out)
    assert manifest.frontend_copy_path == str(paths["frontend_snapshot"])
    assert manifest.output_hashes["frontend_copy"] == sha256_file(paths["frontend_snapshot"])
    assert manifest.output_hashes["frontend_premium_outcome_copy"] == sha256_file(frontend_copy)
    assert manifest.output_hashes["frontend_premium_outcome_copy"] != manifest.output_hashes[
        "frontend_copy"
    ]
    assert manifest.input_hashes["source_m4_manifest"] == sha256_file(paths["manifest"])
    assert manifest.data_access.status == "fixture_fallback"
    for key, digest in sidecar.provenance.input_hashes.items():
        assert manifest.input_hashes[key] == digest

    selected_bar_keys = [
        key for key in sidecar.provenance.input_hashes if key.startswith("selected_option_bars:")
    ]
    assert selected_bar_keys
    for key in selected_bar_keys:
        assert manifest.input_hashes[key] == sidecar.provenance.input_hashes[key]


def test_m5_cli_classifies_unavailable_option_store_data_blocked(tmp_path: Path):
    paths = _bundle(tmp_path, [_record()])
    missing_quant_root = tmp_path / "missing_quant_root"
    out = tmp_path / "m5_missing" / "pa_feitian_premium_outcome_v1.json"
    manifest_out = tmp_path / "m5_missing" / "pa_feitian_run_manifest_m5_v1.json"
    command = [
        str(PYTHON),
        str(SCRIPT),
        "--snapshot",
        str(paths["snapshot"]),
        "--decision-intent",
        str(paths["decision"]),
        "--source-m4-manifest",
        str(paths["manifest"]),
        "--quant-data-root",
        str(missing_quant_root),
        "--out",
        str(out),
        "--manifest-out",
        str(manifest_out),
        "--generated-at-utc",
        "2026-07-10T00:00:00Z",
        "--policy-declared-at-utc",
        "2026-07-10T00:00:00Z",
        "--traversal-started-at-utc",
        "2026-07-10T00:01:00Z",
        "--source-commit",
        COMMIT,
    ]
    env = {**os.environ, "PYTHONPATH": str(SRC_ROOT)}

    subprocess.run(command, cwd=REPO_ROOT, env=env, check=True, capture_output=True, text=True)

    sidecar = load_premium_outcome(out)
    manifest = load_run_manifest(manifest_out)
    validate_pa_feitian_premium_outcome_schema(sidecar.model_dump(mode="json"))
    validate_pa_feitian_run_manifest_schema(manifest.model_dump(mode="json", exclude_none=False))
    assert manifest.data_access.status == "data_blocked"
    assert manifest.frontend_copy_path == str(paths["frontend_snapshot"])
    assert manifest.output_hashes["frontend_copy"] == sha256_file(paths["frontend_snapshot"])
    assert "frontend_premium_outcome_copy" not in manifest.output_hashes
    assert [outcome.evaluation_status for outcome in sidecar.outcomes] == ["data_blocked"]
    for key, digest in sidecar.provenance.input_hashes.items():
        assert manifest.input_hashes[key] == digest


def test_m5_harness_supports_empty_no_signal_sidecar(tmp_path: Path):
    paths = _bundle(tmp_path, [_record()])
    snapshot_path = paths["snapshot"]
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["signals"] = []
    snapshot["summary"]["signals_total"] = 0
    snapshot["summary"]["by_status"] = {}
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    manifest = build_run_manifest(
        scorecard_path=paths["scorecard"],
        snapshot_path=snapshot_path,
        source_commit=COMMIT,
        cli_args=["m4-empty-fixture"],
        run_config=snapshot["run_config"],
        generated_at_utc=GENERATED_AT,
        decision_intent_path=paths["decision"],
        data_access={"status": "fixture_fallback", "source": str(paths["scorecard"]), "notes": []},
    )
    write_run_manifest(manifest, paths["manifest"])

    sidecar = build_premium_outcome_sidecar_from_files(
        snapshot_path=snapshot_path,
        decision_intent_path=paths["decision"],
        source_manifest_path=paths["manifest"],
        quant_data_root=tmp_path / "quant",
        config=PremiumOutcomeHarnessConfig(
            source_commit=COMMIT,
            generated_at_utc=GENERATED_AT,
            policy_declared_at_utc=GENERATED_AT,
            traversal_started_at_utc=GENERATED_AT + timedelta(minutes=1),
            cli_args=("test-empty",),
        ),
    )

    assert sidecar.outcomes == []
    assert sidecar.provenance.policy_hashes == {}
