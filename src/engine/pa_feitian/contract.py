"""Shared PA / Feitian snapshot contract.

This module is intentionally small: strategy code produces the snapshot,
frontend code consumes it, and neither side should infer fields outside this
boundary.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from engine.options.iv_regime import (
    DEFAULT_MAX_RANK,
    DEFAULT_WARMUP,
    iv_regime_decision,
    iv_regime_keep,
)


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


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_record_ts(record: Mapping[str, Any]) -> datetime:
    raw = record.get("pa_60m_timestamp") or record.get("timestamp") or record.get("ts_utc")
    if raw is None:
        raw = record.get("date")
    if raw is None:
        raise ValueError("scorecard record is missing date/timestamp")

    text = str(raw)
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        parsed = datetime.fromisoformat(text).replace(tzinfo=UTC)
    else:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _scorecard_records(scorecard: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(scorecard, Mapping):
        records = scorecard.get("scored", scorecard.get("signals", []))
    else:
        records = scorecard
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise ValueError("scorecard must contain a scored/signals list")
    out: list[dict[str, Any]] = []
    for record in records:
        if isinstance(record, Mapping):
            out.append(dict(record))
    return out


def _instrument_from_symbol(symbol: str) -> str:
    lower = symbol.lower()
    if lower.startswith("kq_m_"):
        parts = lower.split("_")
        if len(parts) >= 4:
            return f"{parts[2].upper()}.{parts[3]}"
    return symbol


def _option_side(contract_sym: str | None, direction: str | None) -> Literal["call", "put", "none", "unknown"]:
    if contract_sym:
        stem = contract_sym.rstrip("0123456789").lower()
        if stem.endswith("c"):
            return "call"
        if stem.endswith("p"):
            return "put"
    if direction == "bottom":
        return "call"
    if direction == "top":
        return "put"
    return "unknown"


def _select_option_leg(calls: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    if not calls:
        return None

    def key(call: Mapping[str, Any]) -> tuple[int, int, float]:
        is_mm = 0 if call.get("is_mm_strike") is True else 1
        rank = _optional_int(call.get("rank"))
        otm = _optional_float(call.get("otm_pct"))
        return (is_mm, rank if rank is not None else 999, otm if otm is not None else 999.0)

    return dict(sorted(calls, key=key)[0])


def _status_from_leg(selected: Mapping[str, Any] | None, iv: IvRegimeAnnotation) -> SignalStatus:
    if selected is None:
        return "data_blocked"
    price_source = selected.get("price_source")
    if selected.get("model_dominated") is True or price_source == "model":
        return "model_dominated"
    if selected.get("option_price") is None:
        return "data_blocked"
    if selected.get("iv") is None or iv.iv_rank is None:
        return "data_blocked"
    return "keep" if iv.keep else "drop"


def _decision_for_status(status: SignalStatus) -> str | None:
    if status == "keep":
        return "take"
    if status == "drop":
        return "skip"
    if status in ("advisory", "data_blocked", "model_dominated"):
        return "watch"
    return None


def _build_signal(
    record: Mapping[str, Any],
    *,
    index: int,
    ts_utc: datetime,
    selected: Mapping[str, Any] | None,
    iv: IvRegimeAnnotation,
) -> PaFeitianSignal:
    symbol = str(record.get("symbol") or record.get("instrument") or "unknown")
    instrument = _instrument_from_symbol(symbol)
    direction = str(record.get("direction") or "")
    status = _status_from_leg(selected, iv)
    option_contract = str(selected.get("contract_sym")) if selected and selected.get("contract_sym") else None
    selected_price_source = selected.get("price_source") if selected else None

    score = record.get("score")
    level = record.get("level")
    policy_rule = record.get("policy_rule")
    decision_trace = (
        f"score_today:{level or 'unknown'} score={score} policy={policy_rule or 'n/a'} "
        f"selected={option_contract or 'none'} status={status}"
    )
    if iv.reason:
        decision_trace += f" iv={iv.reason}"

    caveats: list[str] = []
    if len(str(record.get("date", ""))) == 10 and not record.get("pa_60m_timestamp"):
        caveats.append("source record is date-granular; ts_utc uses start-of-day UTC")
    if status == "data_blocked":
        caveats.append("premium entry or causal IV rank is unavailable in source scorecard")
    if status == "model_dominated":
        caveats.append("selected option leg is model-dominated; do not treat as market premium validation")

    premium_outcome: dict[str, Any] = {
        "available": False,
        "reason": "live_snapshot_no_forward_premium_outcome",
    }
    if selected is not None:
        premium_outcome.update(
            {
                "entry_price": selected.get("option_price"),
                "price_source": selected_price_source,
                "selected_contract": option_contract,
            }
        )

    return PaFeitianSignal(
        id=f"paft_scorecard_{index:04d}_{symbol.lower()}_{ts_utc.strftime('%Y%m%d%H%M%S')}",
        instrument=instrument,
        contract=str(record.get("contract") or symbol),
        interval=str(record.get("pa_timeframe") or "1d"),
        ts_utc=ts_utc,
        underlying_signal={
            "family": "pa_feitian",
            "source": "score_today",
            "symbol": symbol,
            "direction": direction,
            "level": level,
            "subtype": record.get("subtype"),
            "confidence": record.get("confidence"),
            "score": score,
            "policy_rule": policy_rule,
            "policy_weight": record.get("policy_weight"),
            "matched_sweet_spots": record.get("matched_sweet_spots", []),
            "direction_verdict": record.get("direction_verdict"),
            "direction_confidence": record.get("direction_confidence"),
            "direction_sources": record.get("direction_sources"),
            "direction_rationale": record.get("direction_rationale"),
        },
        features_det={
            "lookahead_free": True,
            "cutoff_ts_utc": ts_utc.isoformat().replace("+00:00", "Z"),
            "source_record_index": index,
            "underlying_price": record.get("underlying_price"),
            "invalidation_level": record.get("invalidation_level"),
            "position_size": record.get("position_size"),
            "pa_isolated": record.get("pa_isolated"),
            "pa_phase": record.get("pa_phase"),
            "pa_15m_confirmed": record.get("pa_15m_confirmed"),
            "signal_bar_quality": record.get("signal_bar_quality"),
            "options_calls": record.get("options_calls", []),
            "selected_option_contract": option_contract,
        },
        decision=_decision_for_status(status),
        decision_trace=decision_trace,
        option_leg=OptionLegAnnotation(
            side=_option_side(option_contract, direction),
            strike=_optional_float(selected.get("strike")) if selected else None,
            dte=_optional_int(selected.get("days_to_expiry")) if selected else None,
            otm_rank=_optional_int(selected.get("rank")) if selected else None,
            delta_estimate=_optional_float(selected.get("delta_estimate")) if selected else None,
            selection_status=status,
        ),
        iv_regime=iv,
        exit_policy=ExitPolicyAnnotation(
            mode="runner" if selected is not None else "none",
            status=status,
            reason=(
                "premium runner candidate from score_today option emission"
                if status == "keep"
                else "runner policy retained for review; final action blocked by status"
            ),
        ),
        underlying_r_outcome={
            "available": False,
            "reason": "live_snapshot_no_forward_underlying_outcome",
        },
        premium_r_outcome=premium_outcome,
        option_runner_outcome=None,
        proxy_outcome=None,
        status=status,
        caveats=caveats,
    )


def snapshot_from_scorecard(
    scorecard: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    source_commit: str,
    generated_at_utc: datetime | None = None,
    source_path: str | Path | None = None,
    max_signals: int | None = None,
    iv_warmup: int = DEFAULT_WARMUP,
    iv_max_rank: float = DEFAULT_MAX_RANK,
) -> PaFeitianSnapshot:
    """Build a PA / Feitian snapshot from an existing score_today JSON output.

    The producer is file-backed at this boundary: it consumes already-emitted
    paired-trading score records and does not read or mutate raw market data.
    """
    if iv_warmup < 1:
        raise ValueError("iv_warmup must be >= 1")
    generated_at_utc = generated_at_utc or datetime.now(UTC)
    generated_at_utc = _utc_datetime(generated_at_utc)
    records = _scorecard_records(scorecard)
    candidates = [r for r in records if r.get("options_calls")]
    candidates.sort(
        key=lambda r: (
            _parse_record_ts(r),
            str(r.get("symbol") or ""),
            str(r.get("level") or ""),
            str(r.get("subtype") or ""),
        )
    )

    prior_ivs: defaultdict[str, list[float]] = defaultdict(list)
    signals: list[PaFeitianSignal] = []
    missing_iv = 0
    missing_price = 0
    price_sources: Counter[str] = Counter()

    for index, record in enumerate(candidates, start=1):
        ts_utc = _parse_record_ts(record)
        selected = _select_option_leg(record.get("options_calls") or [])
        instrument = _instrument_from_symbol(str(record.get("symbol") or "unknown"))
        current_iv = _optional_float(selected.get("iv")) if selected else None
        if current_iv is None:
            iv_data = {"iv_rank": None, "keep": False, "reason": "missing_signal_day_iv"}
            missing_iv += 1
        elif selected and selected.get("iv_rank") is not None:
            rank = _optional_float(selected.get("iv_rank"))
            if rank is None:
                iv_data = {"iv_rank": None, "keep": False, "reason": "invalid_signal_day_iv_rank"}
                missing_iv += 1
            else:
                keep = iv_regime_keep(rank, max_rank=iv_max_rank)
                iv_data = {
                    "iv_rank": rank,
                    "keep": keep,
                    "reason": None if keep else f"iv_rank_rich({rank:.2f}>{iv_max_rank})",
                }
        else:
            iv_data = iv_regime_decision(
                current_iv,
                prior_ivs[instrument],
                warmup=iv_warmup,
                max_rank=iv_max_rank,
            )
            if iv_data["iv_rank"] is None:
                missing_iv += 1

        if selected is None or selected.get("option_price") is None:
            missing_price += 1
            price_sources["missing"] += 1
        else:
            price_sources[str(selected.get("price_source") or "unknown")] += 1

        signal = _build_signal(
            record,
            index=index,
            ts_utc=ts_utc,
            selected=selected,
            iv=IvRegimeAnnotation.model_validate(iv_data),
        )
        signals.append(signal)
        if current_iv is not None:
            prior_ivs[instrument].append(current_iv)

    if max_signals is not None and max_signals >= 0:
        signals = signals[-max_signals:] if max_signals else []

    by_status = Counter(signal.status for signal in signals)
    by_instrument = Counter(signal.instrument for signal in signals)
    warnings: list[str] = [
        "producer consumes score_today/emission output; it does not read raw data stores",
        "forward premium/underlying outcomes are intentionally absent from live snapshots",
    ]
    if not candidates:
        warnings.append("source scorecard contained no records with options_calls")
    if missing_price:
        warnings.append(f"{missing_price} selected option legs lack premium entry price")
    if missing_iv:
        warnings.append(f"{missing_iv} selected option legs lack causal IV rank")

    scorecard_meta = scorecard if isinstance(scorecard, Mapping) else {}
    return PaFeitianSnapshot(
        generated_at_utc=generated_at_utc,
        source_commit=source_commit,
        run_config={
            "contract": PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION,
            "mode": "scorecard",
            "producer": "src/scripts/emit_pa_feitian_snapshot.py",
            "source_scorecard": str(source_path) if source_path is not None else None,
            "pool": scorecard_meta.get("pool"),
            "instrument_class": scorecard_meta.get("instrument_class"),
            "window_days": scorecard_meta.get("window_days"),
            "active_rules": scorecard_meta.get("active_rules", []),
            "iv_warmup": iv_warmup,
            "iv_max_rank": iv_max_rank,
            "max_signals": max_signals,
        },
        data_quality={
            "raw_data_access": "not_used_by_pa_feitian_producer",
            "source_output_type": "score_today_json",
            "source_records_total": len(records),
            "source_records_with_options": len(candidates),
            "selected_option_price_sources": dict(sorted(price_sources.items())),
            "selected_option_missing_price": missing_price,
            "selected_option_missing_iv_or_rank": missing_iv,
        },
        summary={
            "signals_total": len(signals),
            "by_status": {status: by_status[status] for status in SIGNAL_STATUSES if by_status[status]},
            "by_instrument": dict(sorted(by_instrument.items())),
            "integration_milestone": "producer_scorecard_to_pa_feitian_snapshot",
        },
        signals=signals,
        warnings=warnings,
    )


def snapshot_from_scorecard_file(
    path: str | Path,
    *,
    source_commit: str,
    generated_at_utc: datetime | None = None,
    max_signals: int | None = None,
    iv_warmup: int = DEFAULT_WARMUP,
    iv_max_rank: float = DEFAULT_MAX_RANK,
) -> PaFeitianSnapshot:
    scorecard_path = Path(path)
    with scorecard_path.open(encoding="utf-8") as f:
        scorecard = json.load(f)
    return snapshot_from_scorecard(
        scorecard,
        source_commit=source_commit,
        generated_at_utc=generated_at_utc,
        source_path=scorecard_path,
        max_signals=max_signals,
        iv_warmup=iv_warmup,
        iv_max_rank=iv_max_rank,
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
