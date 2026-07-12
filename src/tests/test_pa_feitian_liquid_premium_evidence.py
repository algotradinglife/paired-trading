from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from engine.pa_feitian.liquid_premium_evidence import (
    evaluate_contract_frame,
    load_contract,
    validate_contract,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = (
    ROOT / "docs/research/pa-feitian-m6-liquid-premium-eligibility-contract-v1.json"
)


def _frame(*, cadence: str = "5min", volume: float = 10, oi: float = 600) -> pd.DataFrame:
    timestamps = pd.date_range("2025-01-02 09:00", "2025-01-02 15:00", freq=cadence)
    return pd.DataFrame(
        {
            "datetime": timestamps,
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.0,
            "volume": volume,
            "turnover": volume * 10,
            "open_interest": oi,
        }
    )


def _evaluate(frame: pd.DataFrame, cadence_minutes: int = 5) -> dict:
    return evaluate_contract_frame(
        frame,
        cadence_minutes=cadence_minutes,
        first_day=date(2025, 1, 2),
        last_day=date(2025, 1, 2),
    )[0]


def test_frozen_contract_boundary() -> None:
    contract = load_contract(CONTRACT_PATH)
    assert contract["hermes_task"] == "t_3bf64f0c"
    assert contract["boundary_correction"]["historical_bid_ask_required"] is False
    assert contract["boundary_correction"]["contract_delta_required"] is False
    assert contract["guardrails"]["strategy_performance_evaluation"] is False


def test_contract_rejects_changed_ex_ante_floor() -> None:
    contract = json.loads(CONTRACT_PATH.read_text())
    contract["quality_contract"]["liquidity_floors_at_cutoff"][
        "cumulative_session_volume_minimum"
    ] = 99
    with pytest.raises(ValueError, match="volume floor changed"):
        validate_contract(contract)


def test_eligible_unit_and_future_row_invariance() -> None:
    frame = _frame()
    baseline = _evaluate(frame)
    future = frame.iloc[[-1]].copy()
    future["datetime"] = pd.Timestamp("2025-01-02 21:00")
    future["close"] = future["high"] = future["low"] = future["open"] = 999999.0
    amended = _evaluate(pd.concat([frame, future], ignore_index=True))
    assert baseline["eligible"] is True
    assert amended["eligible"] is True
    assert {
        key: value
        for key, value in amended.items()
        if key != "source_rows_after_cutoff_excluded"
    } == {
        key: value
        for key, value in baseline.items()
        if key != "source_rows_after_cutoff_excluded"
    }
    assert amended["source_rows_after_cutoff_excluded"] == 1


def test_gate_uses_volume_turnover_oi_and_continuity() -> None:
    thin = _frame(volume=0, oi=0)
    final_hour = thin["datetime"].dt.time
    thin = thin[
        ~((final_hour >= pd.Timestamp("14:15").time()) & (final_hour <= pd.Timestamp("14:45").time()))
        & (thin["datetime"] != pd.Timestamp("2025-01-02 15:00"))
    ]
    result = _evaluate(thin)
    assert result["eligible"] is False
    assert result["failure_reasons"] == [
        "missing_exact_cutoff_bar",
        "insufficient_final_hour_grid_coverage",
        "excessive_final_hour_gap",
        "session_volume_below_100",
        "session_turnover_not_positive",
        "open_interest_below_500",
    ]


def test_min15_continuity_floor() -> None:
    result = _evaluate(_frame(cadence="15min"), cadence_minutes=15)
    assert result["eligible"] is True
