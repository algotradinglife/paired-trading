from __future__ import annotations

import copy
import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pandas as pd
import pytest

from engine.pa_feitian.underlying_corpus import (
    LEVELS,
    aggregate_at_decision,
    build_corpus,
    canonical_json_bytes,
    describe_latest,
    load_contract,
    validate_contract,
    validate_corpus,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = (
    REPO_ROOT / "docs/research/pa-feitian-m6-underlying-corpus-contract-v1.json"
)


def _business_dates(start: date, end: date) -> list[date]:
    dates = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            dates.append(day)
        day += timedelta(days=1)
    return dates


def _source_frame(sessions: list[date], *, future_extreme: bool = False) -> pd.DataFrame:
    rows = []
    for index, day in enumerate(sessions):
        value = 100.0 + index
        previous = day - timedelta(days=1)
        for stamp, shift in (
            (datetime.combine(previous, time(21, 5)), 0.0),
            (datetime.combine(day, time(9, 5)), 0.5),
            (datetime.combine(day, time(15, 0)), 1.0),
        ):
            price = value + shift
            rows.append(
                {
                    "datetime": stamp,
                    "open": price,
                    "high": price + 1.0,
                    "low": price - 1.0,
                    "close": price + 0.25,
                    "volume": 10.0,
                    "turnover": 100.0,
                    "open_interest": 1000.0 + index,
                    # Deliberately wrong and ignored by the corpus.
                    "main_month": "999999",
                    "is_roll": True,
                }
            )
    if future_extreme:
        rows.append(
            {
                "datetime": datetime(2026, 7, 1, 15, 0),
                "open": 1e12,
                "high": 1e12 + 1,
                "low": 1e12 - 1,
                "close": 1e12,
                "volume": 1e12,
                "turnover": 1e12,
                "open_interest": 1e12,
                "main_month": "000000",
                "is_roll": False,
            }
        )
    return pd.DataFrame(rows)


def _fixtures(future_extreme: bool = False):
    sessions = _business_dates(date(2024, 4, 1), date(2025, 1, 10))
    frames = {
        product: _source_frame(sessions, future_extreme=future_extreme)
        for product in ("au", "ag")
    }
    schedules = {}
    for product in ("au", "ag"):
        schedule = {day: "202506" for day in sessions}
        schedule[date(2025, 1, 6)] = "202508"
        for day in sessions:
            if day > date(2025, 1, 6):
                schedule[day] = "202508"
        if future_extreme:
            schedule[date(2026, 7, 1)] = "999999"
        schedules[product] = schedule
    return frames, schedules


def _build(*, future_extreme: bool = False):
    contract = load_contract(CONTRACT_PATH)
    frames, schedules = _fixtures(future_extreme=future_extreme)
    artifact = build_corpus(
        contract=contract,
        contract_path=CONTRACT_PATH,
        predecessor_refs=contract["predecessors"],
        frames=frames,
        schedules=schedules,
    )
    return contract, artifact


def test_contract_freezes_scope_and_rejects_widening() -> None:
    contract = load_contract(CONTRACT_PATH)
    assert contract["aggregation"]["levels"] == list(LEVELS)
    assert contract["promotion"] and not any(contract["promotion"].values())
    widened = copy.deepcopy(contract)
    widened["guardrails"]["future_rows_allowed"] = True
    with pytest.raises(ValueError, match="guardrails"):
        validate_contract(widened)


def test_aggregate_filters_future_before_mapping_and_resample() -> None:
    frames, schedules = _fixtures()
    cutoff = datetime(2025, 1, 10, 7, tzinfo=UTC)
    base, base_count, base_max = aggregate_at_decision(
        frames["au"],
        decision_ts_utc=cutoff,
        causal_sessions=list(schedules["au"]),
        lookback_calendar_days=260,
    )
    tainted_frames, _ = _fixtures(future_extreme=True)
    tainted, count, maximum = aggregate_at_decision(
        tainted_frames["au"],
        decision_ts_utc=cutoff,
        causal_sessions=list(schedules["au"]),
        lookback_calendar_days=260,
    )
    assert (base_count, base_max) == (count, maximum)
    for level in LEVELS:
        pd.testing.assert_frame_equal(base[level], tainted[level])
        assert base[level]["timestamp"].max() <= pd.Timestamp(cutoff)


def test_prior_20_baseline_strictly_excludes_current_bar() -> None:
    timestamps = pd.date_range("2025-01-01", periods=21, freq="1D", tz="UTC")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [10.0] * 20 + [100.0],
            "high": [12.0] * 20 + [1000.0],
            "low": [8.0] * 20 + [0.0],
            "close": [11.0] * 20 + [900.0],
            "volume": [1.0] * 21,
            "open_interest": [1.0] * 21,
            "constituent_count": [1] * 21,
        }
    )
    result = describe_latest(frame)
    assert result is not None
    assert result["diagnostics"]["prior_20_high"] == 12.0
    assert result["diagnostics"]["prior_20_low"] == 8.0
    assert result["signals"]["breakout_20"] == "up"


def test_corpus_is_deterministic_future_invariant_and_ignores_embedded_rolls() -> None:
    contract, first = _build()
    _, second = _build()
    _, tainted = _build(future_extreme=True)
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert canonical_json_bytes(first) == canonical_json_bytes(tainted)
    assert "generated_at" not in canonical_json_bytes(first).decode()
    assert first["records"]
    roll = next(
        row
        for row in first["records"]
        if row["product"] == "au" and row["trading_date"] == "2025-01-06"
    )
    assert roll["causal_main_month"] == "202508"
    assert roll["causal_roll_session"] is True
    validate_corpus(first, contract=contract)


def test_corpus_builder_does_not_use_directory_discovery_or_current_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_glob(*_args, **_kwargs):
        raise AssertionError("corpus must not discover source files")

    monkeypatch.setattr(Path, "glob", reject_glob)
    _, artifact = _build()
    serialized = json.dumps(artifact, sort_keys=True)
    assert "date.today" not in serialized
    assert "datetime.now" not in serialized
    assert artifact["guardrails"]["implicit_current_time"] is False
    implementation = (
        REPO_ROOT / "src/engine/pa_feitian/underlying_corpus.py"
    ).read_text(encoding="utf-8")
    assert "date.today(" not in implementation
    assert "datetime.now(" not in implementation


def test_validator_rejects_future_derived_timestamp() -> None:
    contract, artifact = _build()
    damaged = copy.deepcopy(artifact)
    damaged["records"][0]["levels"]["D"]["last_bar_timestamp_utc"] = (
        "2030-01-01T00:00:00Z"
    )
    with pytest.raises(ValueError, match="future bar"):
        validate_corpus(damaged, contract=contract)
