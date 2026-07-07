"""Shared PA / Feitian snapshot contract.

This module is intentionally small: strategy code produces the snapshot,
frontend code consumes it, and neither side should infer fields outside this
boundary.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION = "pa_feitian_snapshot_v0"
SIGNAL_STATUSES = ("keep", "drop", "advisory", "data_blocked", "model_dominated")

SignalStatus = Literal["keep", "drop", "advisory", "data_blocked", "model_dominated"]


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware UTC")
    value = value.astimezone(UTC)
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must be UTC")
    return value


class IvRegimeAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iv_rank: float | None = None
    keep: bool
    reason: str | None = None


class OptionLegAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    side: Literal["call", "put", "none", "unknown"]
    strike: float | None = None
    dte: int | None = None
    otm_rank: int | None = None
    delta_estimate: float | None = None
    selection_status: SignalStatus


class ExitPolicyAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["runner", "fixed_tp", "tick_stop", "none", "unknown"]
    status: SignalStatus
    reason: str | None = None


class PaFeitianSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    instrument: str
    contract: str | None = None
    interval: str
    ts_utc: datetime
    underlying_signal: dict[str, Any] = Field(default_factory=dict)
    features_det: dict[str, Any] = Field(default_factory=dict)
    decision: str | None = None
    decision_trace: str | None = None
    option_leg: OptionLegAnnotation
    iv_regime: IvRegimeAnnotation
    exit_policy: ExitPolicyAnnotation
    underlying_r_outcome: dict[str, Any] | None = None
    premium_r_outcome: dict[str, Any] | None = None
    option_runner_outcome: dict[str, Any] | None = None
    proxy_outcome: dict[str, Any] | None = None
    status: SignalStatus
    caveats: list[str] = Field(default_factory=list)

    @field_validator("ts_utc")
    @classmethod
    def _validate_ts_utc(cls, value: datetime) -> datetime:
        return _utc_datetime(value)


class PaFeitianSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["pa_feitian_snapshot_v0"] = PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION
    generated_at_utc: datetime
    source_commit: str
    run_config: dict[str, Any] = Field(default_factory=dict)
    data_quality: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    signals: list[PaFeitianSignal] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("generated_at_utc")
    @classmethod
    def _validate_generated_at_utc(cls, value: datetime) -> datetime:
        return _utc_datetime(value)


def validate_snapshot(data: dict[str, Any]) -> PaFeitianSnapshot:
    return PaFeitianSnapshot.model_validate(data)


def snapshot_to_jsonable(snapshot: PaFeitianSnapshot) -> dict[str, Any]:
    return snapshot.model_dump(mode="json", exclude_none=False)


def load_snapshot(path: str | Path) -> PaFeitianSnapshot:
    with Path(path).open(encoding="utf-8") as f:
        return validate_snapshot(json.load(f))


def write_snapshot(snapshot: PaFeitianSnapshot, path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(snapshot_to_jsonable(snapshot), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def example_snapshot(
    *,
    source_commit: str,
    generated_at_utc: datetime | None = None,
) -> PaFeitianSnapshot:
    generated_at_utc = generated_at_utc or datetime(2026, 7, 7, tzinfo=UTC)
    return PaFeitianSnapshot(
        generated_at_utc=generated_at_utc,
        source_commit=source_commit,
        run_config={
            "contract": PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION,
            "mode": "fixture",
            "producer": "src/scripts/emit_pa_feitian_snapshot.py",
        },
        data_quality={
            "raw_data_access": "not_required_for_fixture",
            "premium_space_required": True,
            "bid_ask_available": False,
        },
        summary={
            "signals_total": 2,
            "by_status": {"advisory": 1, "data_blocked": 1},
            "integration_milestone": "producer_snapshot_frontend_readonly_shell",
        },
        signals=[
            PaFeitianSignal(
                id="paft_fixture_0001",
                instrument="SHFE.au",
                contract="kq_m_shfe_au",
                interval="1h",
                ts_utc=datetime(2026, 6, 30, 2, 0, tzinfo=UTC),
                underlying_signal={
                    "family": "pa_feitian",
                    "pattern": "platform_breakout",
                    "direction": "call",
                },
                features_det={
                    "lookahead_free": True,
                    "cutoff_ts_utc": "2026-06-30T02:00:00Z",
                    "premium_space_signal": "pending",
                },
                decision="watch",
                decision_trace="fixture: underlying alert exists; option premium contract pending",
                option_leg=OptionLegAnnotation(
                    side="call",
                    strike=None,
                    dte=None,
                    otm_rank=None,
                    delta_estimate=None,
                    selection_status="advisory",
                ),
                iv_regime=IvRegimeAnnotation(iv_rank=0.42, keep=True, reason=None),
                exit_policy=ExitPolicyAnnotation(
                    mode="runner",
                    status="advisory",
                    reason="premium runner preferred; production integration pending",
                ),
                underlying_r_outcome={"available": True, "r": 0.8},
                premium_r_outcome={"available": False, "reason": "premium_path_not_emitted"},
                option_runner_outcome=None,
                proxy_outcome={"available": True, "type": "underlying_proxy"},
                status="advisory",
                caveats=[
                    "fixture only",
                    "underlying-R context is not premium-space validation",
                ],
            ),
            PaFeitianSignal(
                id="paft_fixture_0002",
                instrument="SHFE.ag",
                contract="kq_m_shfe_ag",
                interval="1h",
                ts_utc=datetime(2026, 6, 30, 3, 0, tzinfo=UTC),
                underlying_signal={
                    "family": "pa_feitian",
                    "pattern": "trendline_break",
                    "direction": "put",
                },
                features_det={
                    "lookahead_free": True,
                    "cutoff_ts_utc": "2026-06-30T03:00:00Z",
                    "premium_space_signal": "data_blocked",
                },
                decision=None,
                decision_trace=None,
                option_leg=OptionLegAnnotation(
                    side="put",
                    strike=None,
                    dte=None,
                    otm_rank=None,
                    delta_estimate=None,
                    selection_status="data_blocked",
                ),
                iv_regime=IvRegimeAnnotation(
                    iv_rank=None,
                    keep=False,
                    reason="iv_warmup(<40 prior signals)",
                ),
                exit_policy=ExitPolicyAnnotation(
                    mode="tick_stop",
                    status="data_blocked",
                    reason="tick-level premium stop requires intraday option bid/ask",
                ),
                underlying_r_outcome={"available": True, "r": -0.2},
                premium_r_outcome={"available": False, "reason": "missing_premium_bars"},
                option_runner_outcome=None,
                proxy_outcome=None,
                status="data_blocked",
                caveats=[
                    "do not infer missing option fields",
                    "put-side premium chain requires explicit validation",
                ],
            ),
        ],
        warnings=[
            "snapshot v0 is a contract fixture, not a production signal set",
            "premium-space outcomes must remain separate from underlying-R context",
        ],
    )
