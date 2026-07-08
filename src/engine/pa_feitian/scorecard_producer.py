"""Produce PA / Feitian snapshots from score_today output."""

from __future__ import annotations

import json
import hashlib
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from engine.options.iv_regime import (
    DEFAULT_MAX_RANK,
    DEFAULT_WARMUP,
    iv_regime_decision,
    iv_regime_keep,
)
from engine.pa_feitian.contract import (
    DECISION_TRACE_V1_VERSION,
    PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION,
    PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION,
    SIGNAL_STATUSES,
    DecisionTraceSummary,
    DecisionTraceV1,
    ExitPolicyAnnotation,
    IvRegimeAnnotation,
    OptionLegAnnotation,
    PaFeitianSignal,
    PaFeitianSnapshot,
    PaFeitianSignalV1,
    PaFeitianSnapshotV1,
    SignalStatus,
    SnapshotContractVersion,
    TraceEvidence,
    TraceInputRef,
    TraceNode,
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


def _scorecard_records(
    scorecard: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
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


def _option_side(
    contract_sym: str | None, direction: str | None
) -> Literal["call", "put", "none", "unknown"]:
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


def _scorecard_record_digest(record: Mapping[str, Any]) -> str:
    payload = json.dumps(
        record, sort_keys=True, default=str, ensure_ascii=True, separators=(",", ":")
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _trace_confidence(record: Mapping[str, Any]) -> float | None:
    confidence = _optional_float(record.get("confidence"))
    if confidence is None or not 0 <= confidence <= 1:
        return None
    return confidence


def _primary_blocker(
    status: SignalStatus,
    selected: Mapping[str, Any] | None,
    iv: IvRegimeAnnotation,
) -> str | None:
    if status == "keep":
        return None
    if status == "model_dominated":
        return "model_dominated_premium"
    if status == "drop":
        return "iv_regime_rich" if iv.reason else "policy_drop"
    if status == "data_blocked":
        if selected is None:
            return "option_selection_missing"
        if selected.get("option_price") is None:
            return "premium_entry_missing"
        if selected.get("iv") is None or iv.iv_rank is None:
            return "iv_rank_missing"
        return "data_unavailable"
    if status == "advisory":
        return "advisory_only"
    return None


def _trace_headline(status: SignalStatus, primary_blocker: str | None) -> str:
    if status == "keep":
        return "premium runner candidate accepted"
    if status == "drop":
        return "candidate rejected by contract policy"
    if status == "model_dominated":
        return "underlying signal accepted; option leg model-dominated"
    if status == "data_blocked":
        if primary_blocker == "premium_entry_missing":
            return "underlying signal accepted; premium entry blocked"
        if primary_blocker == "iv_rank_missing":
            return "underlying signal accepted; causal IV rank blocked"
        return "underlying signal accepted; option selection blocked"
    return "signal retained for advisory review"


def _trace_evidence(key: str, value: Any, source_ref: str) -> TraceEvidence:
    return TraceEvidence(key=key, value=value, source_ref=source_ref)


def _build_decision_trace_v1(
    record: Mapping[str, Any],
    *,
    index: int,
    ts_utc: datetime,
    selected: Mapping[str, Any] | None,
    iv: IvRegimeAnnotation,
    signal: PaFeitianSignal,
) -> DecisionTraceV1:
    source_ref = f"scorecard_record:{index}"
    option_contract = signal.features_det.get("selected_option_contract")
    primary_blocker = _primary_blocker(signal.status, selected, iv)

    input_refs = [
        TraceInputRef(
            id=source_ref,
            kind="scorecard_record",
            source="score_today_json",
            record_index=index,
            asof_ts_utc=ts_utc,
            digest=_scorecard_record_digest(record),
        )
    ]

    policy_rule = record.get("policy_rule")
    policy_weight = record.get("policy_weight")
    nodes: list[TraceNode] = [
        TraceNode(
            id="underlying_signal",
            kind="signal",
            label="Score Today underlying signal",
            status="pass",
            decision_effect="promote",
            reason="source scorecard emitted an option candidate",
            evidence=[
                _trace_evidence("score", record.get("score"), source_ref),
                _trace_evidence("direction", record.get("direction"), source_ref),
                _trace_evidence("level", record.get("level"), source_ref),
            ],
        ),
        TraceNode(
            id="policy_rule",
            kind="policy",
            label="PA / Feitian policy rule",
            status="pass" if policy_rule else "not_applicable",
            decision_effect="promote" if policy_rule else "none",
            reason=(
                "source scorecard supplied a policy rule"
                if policy_rule
                else "source scorecard did not supply a policy rule"
            ),
            evidence=[
                _trace_evidence("policy_rule", policy_rule, source_ref),
                _trace_evidence("policy_weight", policy_weight, source_ref),
            ],
        ),
    ]

    if selected is None:
        nodes.append(
            TraceNode(
                id="option_selection",
                kind="selection",
                label="Option selection",
                status="blocked",
                decision_effect="block",
                reason="scorecard emitted no selectable option leg",
                evidence=[_trace_evidence("selected_option_contract", None, source_ref)],
            )
        )
    else:
        nodes.append(
            TraceNode(
                id="option_selection",
                kind="selection",
                label="Option selection",
                status="pass",
                decision_effect="promote",
                reason="selected best ranked scorecard option leg",
                evidence=[
                    _trace_evidence("selected_option_contract", option_contract, source_ref),
                    _trace_evidence("side", signal.option_leg.side, source_ref),
                    _trace_evidence("strike", selected.get("strike"), source_ref),
                    _trace_evidence("dte", selected.get("days_to_expiry"), source_ref),
                    _trace_evidence("otm_rank", selected.get("rank"), source_ref),
                    _trace_evidence("delta_estimate", selected.get("delta_estimate"), source_ref),
                ],
            )
        )

    if iv.iv_rank is None:
        iv_node_status = "blocked"
        iv_effect = "block"
        iv_reason = iv.reason or "causal IV rank is unavailable"
    elif iv.keep:
        iv_node_status = "pass"
        iv_effect = "promote"
        iv_reason = "causal IV rank passed"
    else:
        iv_node_status = "fail"
        iv_effect = "demote"
        iv_reason = iv.reason or "causal IV rank failed"

    nodes.append(
        TraceNode(
            id="iv_regime",
            kind="gate",
            label="Causal IV regime",
            status=iv_node_status,
            decision_effect=iv_effect,
            reason=iv_reason,
            evidence=[
                _trace_evidence("iv", selected.get("iv") if selected else None, source_ref),
                _trace_evidence("iv_rank", iv.iv_rank, source_ref),
                _trace_evidence("iv_keep", iv.keep, source_ref),
            ],
        )
    )

    if selected is None:
        premium_status = "blocked"
        premium_effect = "block"
        premium_reason = "option leg is unavailable"
    elif selected.get("model_dominated") is True or selected.get("price_source") == "model":
        premium_status = "advisory"
        premium_effect = "block"
        premium_reason = "selected option price is model-dominated"
    elif selected.get("option_price") is None:
        premium_status = "blocked"
        premium_effect = "block"
        premium_reason = "selected option leg lacks option_price"
    else:
        premium_status = "pass"
        premium_effect = "promote"
        premium_reason = "selected option leg has an entry price"

    nodes.append(
        TraceNode(
            id="premium_entry",
            kind="gate",
            label="Premium entry availability",
            status=premium_status,
            decision_effect=premium_effect,
            reason=premium_reason,
            evidence=[
                _trace_evidence(
                    "option_price", selected.get("option_price") if selected else None, source_ref
                ),
                _trace_evidence(
                    "price_source", selected.get("price_source") if selected else None, source_ref
                ),
            ],
        )
    )

    exit_status = "pass" if signal.exit_policy.status == "keep" else "advisory"
    if signal.exit_policy.status == "drop":
        exit_status = "fail"
    nodes.append(
        TraceNode(
            id="exit_policy",
            kind="policy",
            label="Exit policy",
            status=exit_status,
            decision_effect="annotate",
            reason=signal.exit_policy.reason,
            evidence=[
                _trace_evidence("exit_mode", signal.exit_policy.mode, source_ref),
                _trace_evidence("exit_status", signal.exit_policy.status, source_ref),
            ],
        )
    )

    return DecisionTraceV1(
        trace_version=DECISION_TRACE_V1_VERSION,
        action=signal.decision,
        status=signal.status,
        summary=DecisionTraceSummary(
            headline=_trace_headline(signal.status, primary_blocker),
            primary_blocker=primary_blocker,
            selected_option_contract=option_contract,
            confidence=_trace_confidence(record),
        ),
        input_refs=input_refs,
        nodes=nodes,
    )


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
    option_contract = (
        str(selected.get("contract_sym")) if selected and selected.get("contract_sym") else None
    )
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
        caveats.append(
            "selected option leg is model-dominated; do not treat as market premium validation"
        )

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
    contract_version: SnapshotContractVersion = PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION,
) -> PaFeitianSnapshot | PaFeitianSnapshotV1:
    """Build a PA / Feitian snapshot from an existing score_today JSON output.

    The producer is file-backed at this boundary: it consumes already-emitted
    paired-trading score records and does not read or mutate raw market data.
    """
    if iv_warmup < 1:
        raise ValueError("iv_warmup must be >= 1")
    if contract_version not in (
        PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION,
        PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION,
    ):
        raise ValueError(f"unsupported PA/Feitian contract_version: {contract_version}")
    generated_at_utc = generated_at_utc or datetime.now(UTC)
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
    signals: list[PaFeitianSignal | PaFeitianSignalV1] = []
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

        signal_v0 = _build_signal(
            record,
            index=index,
            ts_utc=ts_utc,
            selected=selected,
            iv=IvRegimeAnnotation.model_validate(iv_data),
        )
        if contract_version == PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION:
            trace = _build_decision_trace_v1(
                record,
                index=index,
                ts_utc=ts_utc,
                selected=selected,
                iv=signal_v0.iv_regime,
                signal=signal_v0,
            )
            signal = PaFeitianSignalV1.model_validate(
                {
                    **signal_v0.model_dump(mode="python"),
                    "decision_trace_v1": trace,
                }
            )
        else:
            signal = signal_v0
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
    snapshot_cls = (
        PaFeitianSnapshotV1
        if contract_version == PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION
        else PaFeitianSnapshot
    )
    return snapshot_cls(
        schema_version=contract_version,
        generated_at_utc=generated_at_utc,
        source_commit=source_commit,
        run_config={
            "contract": contract_version,
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
            "by_status": {
                status: by_status[status] for status in SIGNAL_STATUSES if by_status[status]
            },
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
    contract_version: SnapshotContractVersion = PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION,
) -> PaFeitianSnapshot | PaFeitianSnapshotV1:
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
        contract_version=contract_version,
    )


def _fixture_v1_scorecard() -> dict[str, Any]:
    def record(
        date: str,
        *,
        iv: float,
        option_price: float | None,
        price_source: str,
        model_dominated: bool = False,
    ) -> dict[str, Any]:
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
                    "option_price": option_price,
                    "price_source": price_source,
                    "model_dominated": model_dominated,
                    "iv": iv,
                }
            ],
            "pa_phase": "TR",
            "position_size": "half",
            "signal_bar_quality": {
                "body_frac": 0.82,
                "close_pos": 0.97,
                "double_strong": True,
            },
        }

    return {
        "pool": "CN_METAL",
        "instrument_class": "cn_metal_futures",
        "window_days": 30,
        "active_rules": ["pa-h2-cn-metal"],
        "scored": [
            record("2026-06-28", iv=20.0, option_price=18.5, price_source="store"),
            record("2026-06-29", iv=10.0, option_price=12.2, price_source="store"),
            record(
                "2026-06-30",
                iv=12.0,
                option_price=10.4,
                price_source="model",
                model_dominated=True,
            ),
        ],
    }


def example_snapshot(
    *,
    source_commit: str,
    generated_at_utc: datetime | None = None,
    contract_version: SnapshotContractVersion = PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION,
) -> PaFeitianSnapshot | PaFeitianSnapshotV1:
    generated_at_utc = generated_at_utc or datetime(2026, 7, 7, tzinfo=UTC)
    if contract_version == PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION:
        snapshot = snapshot_from_scorecard(
            _fixture_v1_scorecard(),
            source_commit=source_commit,
            generated_at_utc=generated_at_utc,
            iv_warmup=1,
            contract_version=contract_version,
        )
        snapshot.run_config["mode"] = "fixture"
        snapshot.run_config["source_scorecard"] = None
        snapshot.summary["integration_milestone"] = "producer_snapshot_v1_shadow_contract"
        snapshot.warnings.insert(0, "snapshot v1 is a shadow contract fixture")
        return snapshot
    if contract_version != PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(f"unsupported PA/Feitian contract_version: {contract_version}")
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
