from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from engine.pa_feitian.exploratory_swing_views import (
    ExploratorySwingViewError,
    build_exploratory_swing_views,
    load_contract,
    pretty_json_bytes,
    validate_artifact,
    validate_contract,
)
from scripts.build_pa_feitian_exploratory_swing_views import (
    atomic_write,
    validate_output_path,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "docs/research/pa-feitian-m6-exploratory-swing-views-contract-v1.json"
CANDIDATE_AUDIT_PATH = (
    REPO_ROOT
    / "doc/repro/pa-feitian-phase1-data-capability-2026-07-30"
    / "candidate_interface_audit_v1.json"
)
ARTIFACT_PATH = (
    REPO_ROOT
    / "doc/repro/pa-feitian-m6-exploratory-swing-views-2026-07-30"
    / "exploratory_swing_views_v1.json"
)
FAMILIES = ["SHFE.au", "SHFE.ag", "CZCE.TA", "CZCE.MA", "SHFE.cu", "DCE.i"]


def _market_table(timestamps: list[datetime], *, messy_indices: set[int] | None = None) -> pa.Table:
    messy_indices = messy_indices or set()
    rows = len(timestamps)
    opens = [100.0 + index * 0.1 for index in range(rows)]
    closes = [value + (0.6 if index % 3 else -0.3) for index, value in enumerate(opens)]
    highs = [max(open_, close) + 1.0 for open_, close in zip(opens, closes)]
    lows = [min(open_, close) - 1.0 for open_, close in zip(opens, closes)]
    for index in messy_indices:
        highs[index] = closes[index] - 0.1
    return pa.table(
        {
            "datetime": timestamps,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [index % 4 for index in range(rows)],
            "turnover": [float(index % 5) for index in range(rows)],
            "open_interest": [10.0 for _ in range(rows)],
        }
    )


def _write_underlying(
    path: Path,
    *,
    rows: int | None = None,
    timestamps: list[datetime] | None = None,
    messy_indices: set[int] | None = None,
) -> None:
    if timestamps is None:
        assert rows is not None
        timestamps = [datetime(2026, 1, 1) + timedelta(days=index) for index in range(rows)]
    pq.write_table(
        _market_table(timestamps, messy_indices=messy_indices),
        path,
    )


def _append_future_row(path: Path) -> None:
    current = pq.read_table(path)
    future = _market_table([datetime(2026, 8, 1)])
    pq.write_table(pa.concat_tables([current, future]), path)


def _write_root(root: Path) -> None:
    daily = root / "daily"
    daily.mkdir(parents=True)
    names = {
        "SHFE.au": ("SHFE.au2608.parquet", "SHFE.au2608C100.parquet"),
        "SHFE.ag": ("SHFE.ag2608.parquet", "SHFE.ag2608C100.parquet"),
        "CZCE.TA": ("CZCE.TA608.parquet", "CZCE.TA608C100.parquet"),
        "CZCE.MA": ("CZCE.MA608.parquet", "CZCE.MA608C100.parquet"),
        "SHFE.cu": ("SHFE.cu2608.parquet", "SHFE.cu2608C100.parquet"),
        "DCE.i": ("DCE.i2608.parquet", "DCE.i2608-C-100.parquet"),
    }
    for family, (underlying_name, option_name) in names.items():
        if family == "CZCE.TA":
            _write_underlying(
                daily / underlying_name,
                rows=140,
                messy_indices={0, 20, 21, 22, 23, 24},
            )
        else:
            _write_underlying(daily / underlying_name, rows=100)
        _write_underlying(daily / option_name, rows=100)


def _interface() -> dict:
    return {
        "scanned_files": 1,
        "rows": 100,
        "coverage": {
            "minimum_observation_timestamp": "2026-01-01T00:00:00",
            "maximum_observation_timestamp": "2026-04-10T00:00:00",
        },
        "freshness": {
            "latest_observation": "2026-04-10T00:00:00",
            "calendar_lag_days": 111,
            "status": "stale",
        },
        "ohlc_quality": {
            "rows_checked": 100,
            "null_rows": 0,
            "violation_rows": 0,
        },
        "liquidity_proxy": {
            "name": "rows_with_any_observed_nonzero_activity_rate",
            "rows_with_any_nonzero_activity": 100,
            "all_rows": 100,
            "rate": 1.0,
        },
    }


def _candidate_audit() -> dict:
    roles = {
        "SHFE.au": "continuity_candidate",
        "SHFE.ag": "continuity_candidate",
        "CZCE.TA": "mainstream_candidate",
        "CZCE.MA": "mainstream_candidate",
        "SHFE.cu": "non_czce_control",
        "DCE.i": "non_czce_control",
    }
    return {
        "schema_version": "pa_feitian_phase1_candidate_interface_audit_v1",
        "issue_number": 43,
        "audit_as_of_local_date": "2026-07-30",
        "source": {
            "access": "read_only",
            "source_refresh_performed": False,
            "inventory_sha256": "sha256:" + "a" * 64,
        },
        "decision_surface": [
            {
                "instrument_family": family,
                "role": roles[family],
                "cadences": [
                    {
                        "cadence": cadence,
                        "interfaces": {
                            "underlying": _interface(),
                            "option_premium": _interface(),
                        },
                    }
                    for cadence in ("daily", "hour", "min15", "min5")
                ],
            }
            for family in FAMILIES
        ],
    }


def _build_from_root(root: Path, tmp_path: Path) -> tuple[dict, dict, dict]:
    contract = load_contract(CONTRACT_PATH)
    candidate_audit = _candidate_audit()
    audit_path = tmp_path / "candidate_audit.json"
    audit_path.write_text(json.dumps(candidate_audit), encoding="utf-8")
    artifact = build_exploratory_swing_views(
        contract=contract,
        contract_path=CONTRACT_PATH,
        candidate_audit=candidate_audit,
        candidate_audit_path=audit_path,
        data_root=root,
        workers=2,
    )
    return contract, candidate_audit, artifact


def _build(tmp_path: Path) -> tuple[dict, dict, dict]:
    root = tmp_path / "quant"
    _write_root(root)
    return _build_from_root(root, tmp_path)


def test_contract_freezes_universe_windows_and_non_outcome_boundary() -> None:
    contract = load_contract(CONTRACT_PATH)
    assert [row["instrument_family"] for row in contract["candidate_universe"]] == FAMILIES
    assert contract["window_protocol"]["completed_observations"] == 20
    assert contract["window_protocol"]["stride_observations"] == 20
    assert contract["window_protocol"]["representative_requires_daily_option_coverage"] is True
    assert (
        contract["window_protocol"]["post_audit_rows"]
        == "excluded_before_series_inventory_and_window_partitioning"
    )
    assert contract["window_protocol"]["future_only_files"] == "excluded_from_source_inventory"
    assert contract["window_protocol"]["selection_scope"] == "within_family_only"
    assert contract["window_protocol"]["selection_uses_strategy_outcomes_or_profitability"] is False
    assert contract["option_premium_overlay"]["required_distinct_dates_for_comparable_path"] == 20
    assert contract["option_premium_overlay"]["duplicate_date_series_in_path_distribution"] is False
    assert (
        contract["option_premium_overlay"]["incomplete_fragment_series_in_path_distribution"]
        is False
    )
    assert contract["output"]["atomic_same_directory_replace"] is True

    weakened = copy.deepcopy(contract)
    weakened["guardrails"]["performance_calculation"] = True
    with pytest.raises(ExploratorySwingViewError, match="weakened"):
        validate_contract(weakened)


def test_builder_is_deterministic_and_covers_six_family_regime_slices(
    tmp_path: Path,
) -> None:
    contract, candidate_audit, first = _build(tmp_path)
    root = tmp_path / "quant"
    audit_path = tmp_path / "candidate_audit.json"
    second = build_exploratory_swing_views(
        contract=contract,
        contract_path=CONTRACT_PATH,
        candidate_audit=candidate_audit,
        candidate_audit_path=audit_path,
        data_root=root,
        workers=1,
    )
    assert first == second
    validate_artifact(first, contract=contract, candidate_audit=candidate_audit)
    assert len(first["representative_swing_views"]) == 18
    for family in FAMILIES:
        views = [
            row for row in first["representative_swing_views"] if row["instrument_family"] == family
        ]
        assert [row["regime_slice"] for row in views] == ["quiet", "typical", "volatile"]
        assert all(
            row["option_premium_overlay"]["comparable_complete_path_metrics"][
                "anonymous_series_count"
            ]
            == 1
            for row in views
        )
        assert all(row["option_premium_overlay"]["selection_influence"] is False for row in views)
        assert all(len(row["normalized_ohlc_path"]) == 20 for row in views)
        assert all(row["normalized_ohlc_path"][0]["open_index"] == 100 for row in views)

    incoherent = copy.deepcopy(first)
    incoherent["representative_swing_views"][0]["normalized_ohlc_path"][0]["high_index"] = 1
    with pytest.raises(ExploratorySwingViewError, match="incoherent OHLC"):
        validate_artifact(incoherent, contract=contract, candidate_audit=candidate_audit)

    summaries = {row["instrument_family"]: row for row in first["family_window_summaries"]}
    assert summaries["CZCE.TA"]["all_complete_windows"]["quality_counts"]["clean"] == 5
    assert summaries["CZCE.TA"]["representative_eligible_clean_windows"]["window_count"] == 3
    for summary in summaries.values():
        eligible = summary["representative_eligible_clean_windows"]
        assert (
            eligible["window_count"] <= summary["all_complete_windows"]["quality_counts"]["clean"]
        )
        assert set(eligible["total_excursion_pct"]) == {"p20", "p50", "p80"}


def test_builder_exposes_real_clean_messy_invalid_and_stale_examples(
    tmp_path: Path,
) -> None:
    _, _, artifact = _build(tmp_path)
    examples = artifact["quality_examples"]
    assert set(examples) == {"clean", "messy", "invalid", "stale"}
    assert examples["messy"]["quality_status"] == "messy"
    assert examples["messy"]["quality_findings"]["invalid_observations"] == 1
    assert examples["invalid"]["quality_status"] == "invalid"
    assert examples["invalid"]["quality_findings"]["invalid_observations"] == 5
    assert examples["stale"]["quality_status"] == "clean"
    assert all(
        row["input_quality"]["status"] == "clean" for row in artifact["representative_swing_views"]
    )


def test_future_rows_and_future_only_files_are_byte_invariant(
    tmp_path: Path,
) -> None:
    root = tmp_path / "quant"
    _write_root(root)
    boundary_path = root / "daily" / "SHFE.au2707.parquet"
    _write_underlying(
        boundary_path,
        timestamps=[datetime(2026, 6, 1) + timedelta(days=index) for index in range(19)],
    )
    _, _, baseline = _build_from_root(root, tmp_path)

    _append_future_row(boundary_path)
    _append_future_row(root / "daily" / "SHFE.au2608.parquet")
    _append_future_row(root / "daily" / "SHFE.au2608C100.parquet")
    _write_underlying(
        root / "daily" / "SHFE.au2708.parquet",
        timestamps=[datetime(2026, 8, 1)],
    )
    _write_underlying(
        root / "daily" / "SHFE.au2708C100.parquet",
        timestamps=[datetime(2026, 8, 1)],
    )
    _, _, observed = _build_from_root(root, tmp_path)

    assert pretty_json_bytes(observed) == pretty_json_bytes(baseline)
    assert all(
        row["latest_window_calendar_lag_days"] >= 0 for row in observed["family_window_summaries"]
    )
    assert all(
        row["freshness"]["calendar_lag_days"] >= 0 for row in observed["representative_swing_views"]
    )


def test_option_values_cannot_change_selected_underlying_windows(
    tmp_path: Path,
) -> None:
    root = tmp_path / "quant"
    _write_root(root)
    _, _, baseline = _build_from_root(root, tmp_path)

    _write_underlying(
        root / "daily" / "SHFE.au2608C100.parquet",
        rows=100,
        messy_indices=set(range(100)),
    )
    _, _, changed = _build_from_root(root, tmp_path)

    def selections(artifact: dict) -> list[dict]:
        return [
            {
                key: row[key]
                for key in (
                    "instrument_family",
                    "regime_slice",
                    "start_date",
                    "end_date",
                    "descriptive_metrics",
                    "normalized_ohlc_path",
                )
            }
            for row in artifact["representative_swing_views"]
        ]

    assert selections(changed) == selections(baseline)
    assert changed != baseline


def test_two_point_nineteen_date_and_duplicate_option_series_do_not_enter_path_metrics(
    tmp_path: Path,
) -> None:
    root = tmp_path / "quant"
    _write_root(root)
    _, _, baseline = _build_from_root(root, tmp_path)
    quiet = next(
        row
        for row in baseline["representative_swing_views"]
        if row["instrument_family"] == "SHFE.au" and row["regime_slice"] == "quiet"
    )
    start = datetime.fromisoformat(quiet["start_date"])
    dates = [start + timedelta(days=index) for index in range(20)]
    _write_underlying(
        root / "daily" / "SHFE.au2609C100.parquet",
        timestamps=dates[:2],
    )
    _write_underlying(
        root / "daily" / "SHFE.au2610C100.parquet",
        timestamps=[*dates, dates[0]],
    )
    _write_underlying(
        root / "daily" / "SHFE.au2611C100.parquet",
        timestamps=dates[:19],
    )
    _, _, artifact = _build_from_root(root, tmp_path)
    overlay = next(
        row["option_premium_overlay"]
        for row in artifact["representative_swing_views"]
        if row["instrument_family"] == "SHFE.au" and row["regime_slice"] == "quiet"
    )

    assert overlay["distinct_date_coverage"]["two_point_fragment_series_count"] == 1
    assert overlay["distinct_date_coverage"]["incomplete_fragment_series_count"] == 2
    assert overlay["distinct_date_coverage"]["duplicate_date_series_count"] == 1
    assert overlay["comparable_complete_path_metrics"]["anonymous_series_count"] == 1


def test_unknown_candidate_metadata_cannot_enter_public_artifact(
    tmp_path: Path,
) -> None:
    root = tmp_path / "quant"
    _write_root(root)
    contract = load_contract(CONTRACT_PATH)
    candidate_audit = _candidate_audit()
    injected_token = "github" + "_pat_EXAMPLE_NOT_A_REAL_TOKEN"
    injected_path = "/home/private/SHFE.au2608.parquet"
    injected_identifier = "SHFE.au2608"
    source = candidate_audit["decision_surface"][0]["cadences"][0]["interfaces"]["underlying"]
    source["coverage"]["operator_note"] = injected_token
    source["freshness"]["debug_path"] = injected_path
    source["freshness"]["raw_contract"] = injected_identifier
    audit_path = tmp_path / "candidate_audit_with_unknown_metadata.json"
    audit_path.write_text(json.dumps(candidate_audit), encoding="utf-8")

    artifact = build_exploratory_swing_views(
        contract=contract,
        contract_path=CONTRACT_PATH,
        candidate_audit=candidate_audit,
        candidate_audit_path=audit_path,
        data_root=root,
        workers=2,
    )
    encoded = json.dumps(artifact, sort_keys=True)
    assert injected_token not in encoded
    assert injected_path not in encoded
    assert injected_identifier not in encoded
    interface = artifact["interface_availability"][0]["cadences"][0]["interfaces"]["underlying"]
    assert set(interface["coverage"]) == {
        "minimum_observation_timestamp",
        "maximum_observation_timestamp",
    }
    assert set(interface["freshness"]) == {
        "latest_observation",
        "calendar_lag_days",
        "status",
    }

    unsafe = copy.deepcopy(artifact)
    unsafe["limitations"].append(injected_token)
    with pytest.raises(ExploratorySwingViewError, match="token prefix"):
        validate_artifact(
            unsafe,
            contract=contract,
            candidate_audit=candidate_audit,
        )


def test_cli_rejects_protected_outputs_and_writes_atomically(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "quant"
    data_root.mkdir()
    contract = tmp_path / "contract.json"
    audit = tmp_path / "audit.json"
    contract.write_text("{}", encoding="utf-8")
    audit.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="read-only data root"):
        validate_output_path(
            output=data_root / "artifact.json",
            data_root=data_root,
            contract=contract,
            candidate_audit=audit,
        )
    for protected in (contract, audit):
        with pytest.raises(ValueError, match="must not overwrite"):
            validate_output_path(
                output=protected,
                data_root=data_root,
                contract=contract,
                candidate_audit=audit,
            )

    output = validate_output_path(
        output=tmp_path / "out" / "artifact.json",
        data_root=data_root,
        contract=contract,
        candidate_audit=audit,
    )
    atomic_write(output, b"first")
    atomic_write(output, b"second")
    assert output.read_bytes() == b"second"
    assert list(output.parent.glob(f".{output.name}.*.tmp")) == []


def test_public_artifact_omits_paths_files_contract_ids_rows_and_outcomes(
    tmp_path: Path,
) -> None:
    contract, candidate_audit, artifact = _build(tmp_path)
    encoded = json.dumps(artifact, sort_keys=True)
    assert str(tmp_path) not in encoded
    assert ".parquet" not in encoded
    assert "SHFE.au2608" not in encoded
    assert '"open"' not in encoded
    assert '"close"' not in encoded
    assert '"pnl"' not in encoded
    assert artifact["public_safety"]["raw_rows"] is False
    assert artifact["evidence_separation"]["preregistered_evidence"] == "not produced"

    unsafe = copy.deepcopy(artifact)
    unsafe["quality_examples"]["clean"]["source_filename"] = "private"
    with pytest.raises(ExploratorySwingViewError, match="forbidden fields"):
        validate_artifact(
            unsafe,
            contract=contract,
            candidate_audit=candidate_audit,
        )


def test_committed_exploratory_swing_artifact_is_valid() -> None:
    if not ARTIFACT_PATH.exists():
        pytest.skip("artifact is generated after the frozen builder is committed")
    contract = load_contract(CONTRACT_PATH)
    candidate_audit = json.loads(CANDIDATE_AUDIT_PATH.read_text(encoding="utf-8"))
    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    validate_artifact(
        artifact,
        contract=contract,
        candidate_audit=candidate_audit,
    )
