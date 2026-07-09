"""Focused v0.2 PA / Feitian decision-intent strategy adapter."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.pa_feitian.contract import (
    PA_FEITIAN_DECISION_INTENT_SCHEMA_VERSION,
    ConfirmationIntent,
    DecisionIntentProvenance,
    DecisionIntentSignal,
    LiquidityIntent,
    NoLookaheadInputRef,
    PaFeitianDecisionIntentSidecar,
    PaFeitianSignal,
    PaFeitianSnapshot,
    PaFeitianSnapshotV1,
    PremiumStopIntent,
    ProductDirectionTier,
)
from engine.pa_feitian.manifest import sha256_file
from engine.pa_feitian.scorecard_producer import (
    _optional_float,
    _optional_int,
    _parse_record_ts,
    _scorecard_record_digest,
    _scorecard_records,
    _select_option_leg,
)


AU_CALL_STOP_GATE_MIN_PCT = 4.0
AU_CALL_STOP_GATE_MAX_PCT = 12.0
STALE_QUOTE_AGE_SECONDS = 300
THIN_QUOTE_COUNT = 5

_STOP_SOURCES = {
    "swing_low_premium",
    "recent_36bar_low",
    "half_loss_fixed",
    "manual",
    "unavailable",
    "not_applicable",
}
_CONFIRMATION_SOURCES = {
    "premium_macd",
    "premium_breakout",
    "underlying_only",
    "manual",
    "unavailable",
    "not_applicable",
}
_LIQUIDITY_STATUSES = {
    "adequate",
    "thin",
    "stale",
    "thin_and_stale",
    "unknown",
    "not_applicable",
}
_PRODUCT_DIRECTION_TIERS = {
    "aligned_trade_candidate",
    "conditional_watch",
    "observation_only",
    "direction_blocked",
    "unknown",
}


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        default=str,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _signal_decision_digest(signal: PaFeitianSignal) -> str:
    payload = signal.model_dump(
        mode="json",
        exclude={
            "underlying_r_outcome",
            "premium_r_outcome",
            "option_runner_outcome",
            "proxy_outcome",
        },
    )
    return _canonical_digest(payload)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware UTC")
    return value.astimezone(UTC)


def _parse_optional_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _utc(value)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _decision_time_ts(value: Any, decision_ts_utc: datetime, *, label: str) -> datetime | None:
    parsed = _parse_optional_ts(value)
    if parsed is None:
        return None
    if parsed > decision_ts_utc:
        raise ValueError(f"{label} must not be after decision_ts_utc")
    return parsed


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _nested_mapping(*owners: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    for owner in owners:
        value = owner.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _first_value(configs: Sequence[Mapping[str, Any]], *keys: str) -> Any:
    for config in configs:
        for key in keys:
            if key in config and config[key] is not None:
                return config[key]
    return None


def _first_str(configs: Sequence[Mapping[str, Any]], *keys: str) -> str | None:
    value = _first_value(configs, *keys)
    if value is None:
        return None
    return str(value)


def _first_bool(configs: Sequence[Mapping[str, Any]], *keys: str) -> bool | None:
    value = _first_value(configs, *keys)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        folded = value.strip().lower()
        if folded in {"1", "true", "yes", "y"}:
            return True
        if folded in {"0", "false", "no", "n"}:
            return False
    return bool(value)


def _normalize_choice(value: str | None, allowed: set[str], default: str) -> str:
    if value is None:
        return default
    normalized = value.strip().lower().replace("-", "_")
    return normalized if normalized in allowed else default


def _add_reason(reason_codes: list[str], code: str) -> None:
    if code not in reason_codes:
        reason_codes.append(code)


def _candidate_records(
    scorecard: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
) -> dict[int, dict[str, Any]]:
    if scorecard is None:
        return {}
    records = _scorecard_records(scorecard)
    candidates = [record for record in records if record.get("options_calls")]
    candidates.sort(
        key=lambda record: (
            _parse_record_ts(record),
            str(record.get("symbol") or ""),
            str(record.get("level") or ""),
            str(record.get("subtype") or ""),
        )
    )
    return {index: record for index, record in enumerate(candidates, start=1)}


def _selected_option(
    signal: PaFeitianSignal,
    record: Mapping[str, Any],
) -> Mapping[str, Any]:
    calls = record.get("options_calls") or signal.features_det.get("options_calls") or []
    if not isinstance(calls, Sequence) or isinstance(calls, (str, bytes)):
        calls = []
    selected_contract = signal.features_det.get("selected_option_contract")
    if selected_contract is not None:
        for call in calls:
            call_mapping = _mapping(call)
            if str(call_mapping.get("contract_sym")) == str(selected_contract):
                return call_mapping
    selected = _select_option_leg([_mapping(call) for call in calls])
    return selected if selected is not None else {}


def _is_au_call(signal: PaFeitianSignal) -> bool:
    return signal.instrument.lower() == "shfe.au" and signal.option_leg.side == "call"


def _premium_stop_intent(
    signal: PaFeitianSignal,
    record: Mapping[str, Any],
    selected: Mapping[str, Any],
    *,
    evidence_ref: str,
    reason_codes: list[str],
) -> PremiumStopIntent:
    stop_cfg = _nested_mapping(selected, record, key="premium_stop")
    configs = [stop_cfg, selected, record]
    entry_premium = _optional_float(
        _first_value(configs, "entry_premium", "premium_entry", "option_price")
    )
    stop_premium = _optional_float(
        _first_value(configs, "stop_premium", "premium_stop_price", "stop_price")
    )
    source_raw = _first_str(
        configs,
        "source",
        "premium_stop_source",
        "stop_source",
        "premium_stop_mode",
        "stop_mode",
    )
    if (
        _first_bool(configs, "half_loss_fixed", "half_loss_stop") is True
        or source_raw in {"half_loss", "half_loss_fixed"}
    ):
        source = "half_loss_fixed"
    else:
        default_source = "recent_36bar_low" if stop_premium is not None else "unavailable"
        source = _normalize_choice(source_raw, _STOP_SOURCES, default_source)

    if source == "half_loss_fixed" and entry_premium is not None and stop_premium is None:
        stop_premium = entry_premium * 0.5

    stop_distance_pct = _optional_float(
        _first_value(configs, "stop_distance_pct", "premium_stop_distance_pct")
    )
    if stop_distance_pct is None and entry_premium is not None and stop_premium is not None:
        raw_distance = (entry_premium - stop_premium) / entry_premium * 100.0
        stop_distance_pct = max(0.0, raw_distance)
        if raw_distance < 0:
            _add_reason(reason_codes, "STOP_PREMIUM_NOT_BELOW_ENTRY")

    soft_gate_min_pct = _optional_float(_first_value(configs, "soft_gate_min_pct"))
    soft_gate_max_pct = _optional_float(_first_value(configs, "soft_gate_max_pct"))
    if _is_au_call(signal):
        soft_gate_min_pct = soft_gate_min_pct or AU_CALL_STOP_GATE_MIN_PCT
        soft_gate_max_pct = soft_gate_max_pct or AU_CALL_STOP_GATE_MAX_PCT

    provided_status = _normalize_choice(
        _first_str(configs, "status", "premium_stop_status", "stop_status"),
        {"clear", "unclear", "blocked", "not_applicable"},
        "clear",
    )
    if entry_premium is None:
        status = "blocked"
        _add_reason(reason_codes, "PREMIUM_ENTRY_UNAVAILABLE")
    elif source in {"unavailable", "not_applicable"}:
        status = "blocked" if source == "unavailable" else "not_applicable"
        _add_reason(reason_codes, "PREMIUM_STOP_UNAVAILABLE")
    elif stop_premium is None or stop_distance_pct is None:
        status = "blocked"
        _add_reason(reason_codes, "PREMIUM_STOP_UNAVAILABLE")
    elif source == "half_loss_fixed":
        status = "unclear"
        _add_reason(reason_codes, "HALF_LOSS_FIXED_DOWNGRADE")
    elif provided_status in {"blocked", "unclear", "not_applicable"}:
        status = provided_status
        if provided_status == "unclear":
            _add_reason(reason_codes, "PREMIUM_STOP_UNCLEAR")
        elif provided_status == "blocked":
            _add_reason(reason_codes, "PREMIUM_STOP_BLOCKED")
    elif (
        _is_au_call(signal)
        and soft_gate_min_pct is not None
        and soft_gate_max_pct is not None
        and not soft_gate_min_pct <= stop_distance_pct <= soft_gate_max_pct
    ):
        status = "unclear"
        _add_reason(reason_codes, "STOP_DISTANCE_OUTSIDE_SOFT_GATE")
    else:
        status = "clear"
        _add_reason(reason_codes, "PREMIUM_STOP_CLEAR")

    if provided_status == "clear" and status != "clear":
        _add_reason(reason_codes, "STOP_CLEAR_DOWNGRADED")

    asof_ts_utc = _decision_time_ts(
        _first_value(configs, "asof_ts_utc", "premium_stop_asof_ts_utc", "stop_asof_ts_utc"),
        signal.ts_utc,
        label="premium_stop.asof_ts_utc",
    )

    return PremiumStopIntent(
        status=status,  # type: ignore[arg-type]
        source=source,  # type: ignore[arg-type]
        entry_premium=entry_premium,
        stop_premium=stop_premium,
        stop_distance_pct=stop_distance_pct,
        soft_gate_min_pct=soft_gate_min_pct,
        soft_gate_max_pct=soft_gate_max_pct,
        asof_ts_utc=asof_ts_utc or signal.ts_utc,
        evidence_ref=evidence_ref,
    )


def _confirmation_intent(
    signal: PaFeitianSignal,
    record: Mapping[str, Any],
    selected: Mapping[str, Any],
    *,
    evidence_ref: str,
    reason_codes: list[str],
) -> ConfirmationIntent:
    confirmation_cfg = _nested_mapping(selected, record, key="premium_confirmation")
    if not confirmation_cfg:
        confirmation_cfg = _nested_mapping(selected, record, key="confirmation")
    configs = [confirmation_cfg, selected, record]
    alert_only = _first_bool(
        configs,
        "macd_alert_only",
        "premium_macd_alert_only",
        "confirmation_alert_only",
    )
    confirmed = _first_bool(
        configs,
        "premium_macd_confirmed",
        "premium_confirmation_confirmed",
        "confirmed",
    )
    source = _normalize_choice(
        _first_str(
            configs,
            "source",
            "premium_confirmation_source",
            "confirmation_source",
        ),
        _CONFIRMATION_SOURCES,
        "unavailable",
    )
    raw_status = _first_str(configs, "status", "premium_confirmation_status", "confirmation_status")
    status = "pending"
    confirmed_at_utc = None

    if alert_only is True or source == "underlying_only":
        status = "pending"
        source = "underlying_only"
        _add_reason(reason_codes, "MACD_ALERT_ONLY")
        _add_reason(reason_codes, "PREMIUM_CONFIRMATION_PENDING")
    elif raw_status == "failed":
        status = "failed"
        _add_reason(reason_codes, "PREMIUM_CONFIRMATION_FAILED")
    elif raw_status == "confirmed" or confirmed is True:
        status = "confirmed"
        if source in {"unavailable", "not_applicable", "underlying_only"}:
            source = "premium_macd"
        confirmed_at_utc = _decision_time_ts(
            _first_value(
                configs,
                "confirmed_at_utc",
                "premium_confirmed_at_utc",
                "premium_macd_confirmed_at_utc",
            ),
            signal.ts_utc,
            label="confirmation.confirmed_at_utc",
        ) or signal.ts_utc
        _add_reason(reason_codes, "PREMIUM_CONFIRMATION_CONFIRMED")
    else:
        _add_reason(reason_codes, "PREMIUM_CONFIRMATION_PENDING")

    return ConfirmationIntent(
        status=status,  # type: ignore[arg-type]
        source=source,  # type: ignore[arg-type]
        confirmed_at_utc=confirmed_at_utc,
        evidence_ref=evidence_ref,
    )


def _liquidity_intent(
    signal: PaFeitianSignal,
    record: Mapping[str, Any],
    selected: Mapping[str, Any],
    *,
    evidence_ref: str,
    reason_codes: list[str],
) -> LiquidityIntent:
    liquidity_cfg = _nested_mapping(selected, record, key="liquidity")
    configs = [liquidity_cfg, selected, record]
    quote_count = _optional_int(
        _first_value(configs, "quote_count", "bid_ask_quote_count", "quotes_seen")
    )
    last_quote_age_seconds = _optional_int(
        _first_value(configs, "last_quote_age_seconds", "quote_age_seconds", "quote_age_sec")
    )
    status_raw = _first_str(configs, "status", "liquidity_status")
    if selected.get("model_dominated") is True or selected.get("price_source") == "model":
        status = "unknown"
    else:
        status = _normalize_choice(status_raw, _LIQUIDITY_STATUSES, "unknown")

    if status == "unknown" and (quote_count is not None or last_quote_age_seconds is not None):
        thin = quote_count is not None and quote_count < THIN_QUOTE_COUNT
        stale = (
            last_quote_age_seconds is not None
            and last_quote_age_seconds > STALE_QUOTE_AGE_SECONDS
        )
        if thin and stale:
            status = "thin_and_stale"
        elif thin:
            status = "thin"
        elif stale:
            status = "stale"
        else:
            status = "adequate"

    explicit_recovery = _first_bool(configs, "recovery_required", "liquidity_recovery_required")
    recovery_required = explicit_recovery if explicit_recovery is not None else status != "adequate"
    if status == "adequate" and not recovery_required:
        _add_reason(reason_codes, "LIQUIDITY_OK")
    elif status in {"thin", "stale", "thin_and_stale"}:
        _add_reason(reason_codes, "LIQUIDITY_THIN_OR_STALE")
    else:
        _add_reason(reason_codes, "LIQ_RECOVERY_REQUIRED")

    return LiquidityIntent(
        status=status,  # type: ignore[arg-type]
        quote_count=quote_count,
        last_quote_age_seconds=last_quote_age_seconds,
        recovery_required=recovery_required,
        evidence_ref=evidence_ref,
    )


def _product_direction_tier(
    signal: PaFeitianSignal,
    record: Mapping[str, Any],
    selected: Mapping[str, Any],
    *,
    reason_codes: list[str],
) -> ProductDirectionTier:
    explicit = _normalize_choice(
        _first_str([selected, record], "product_direction_tier", "direction_tier"),
        _PRODUCT_DIRECTION_TIERS,
        "unknown",
    )
    if explicit != "unknown":
        if explicit == "aligned_trade_candidate":
            _add_reason(reason_codes, "PRODUCT_DIRECTION_ALIGNED")
        elif explicit == "direction_blocked":
            _add_reason(reason_codes, "PRODUCT_DIRECTION_BLOCKED")
        return explicit  # type: ignore[return-value]

    direction = str(signal.underlying_signal.get("direction") or "").lower()
    side = signal.option_leg.side
    bullish = direction in {"bottom", "long", "call", "bull", "bullish"}
    bearish = direction in {"top", "short", "put", "bear", "bearish"}
    if (bullish and side == "call") or (bearish and side == "put"):
        _add_reason(reason_codes, "PRODUCT_DIRECTION_ALIGNED")
        return "aligned_trade_candidate"
    if (bullish and side == "put") or (bearish and side == "call"):
        _add_reason(reason_codes, "PRODUCT_DIRECTION_BLOCKED")
        return "direction_blocked"
    _add_reason(reason_codes, "PRODUCT_DIRECTION_UNKNOWN")
    return "unknown"


def _has_right_tail_observation(record: Mapping[str, Any], selected: Mapping[str, Any]) -> bool:
    explicit = _first_bool(
        [selected, record],
        "right_tail_observation",
        "right_tail_watch",
        "observe_right_tail",
    )
    if explicit is not None:
        return explicit
    return bool(record.get("right_tail") or selected.get("right_tail"))


def _decision_state(
    signal: PaFeitianSignal,
    *,
    product_direction_tier: ProductDirectionTier,
    premium_stop: PremiumStopIntent,
    confirmation: ConfirmationIntent,
    liquidity: LiquidityIntent,
    right_tail_observation: bool,
    reason_codes: list[str],
) -> str:
    if signal.status == "drop":
        _add_reason(reason_codes, "SOURCE_STATUS_DROP")
        return "reject"
    if product_direction_tier == "direction_blocked":
        return "reject"
    if signal.status == "model_dominated":
        _add_reason(reason_codes, "MODEL_DOMINATED_PREMIUM")
        return "watch"
    if liquidity.status in {"thin", "stale", "thin_and_stale"} and right_tail_observation:
        _add_reason(reason_codes, "THIN_STALE_RIGHT_TAIL_OBSERVATION")
        return "observation_runner"
    if (
        product_direction_tier == "aligned_trade_candidate"
        and premium_stop.status == "clear"
        and confirmation.status == "confirmed"
        and liquidity.status == "adequate"
        and not liquidity.recovery_required
    ):
        _add_reason(reason_codes, "TRADE_READY_PREMIUM_CONFIRMED")
        return "trade_ready"
    if (
        product_direction_tier == "aligned_trade_candidate"
        and signal.status == "keep"
        and premium_stop.status in {"clear", "unclear"}
        and liquidity.status == "adequate"
        and not liquidity.recovery_required
    ):
        _add_reason(reason_codes, "ARMED_WATCH_READINESS_PENDING")
        return "armed_watch"
    if signal.status == "data_blocked":
        _add_reason(reason_codes, "SOURCE_STATUS_DATA_BLOCKED")
    return "watch"


def _no_lookahead_inputs(
    signal: PaFeitianSignal,
    record: Mapping[str, Any],
    *,
    source_record_index: int | None,
    evidence_ref: str,
    scorecard_source: str,
) -> list[NoLookaheadInputRef]:
    refs: list[NoLookaheadInputRef] = []
    if record:
        record_asof = _decision_time_ts(
            record.get("decision_context_asof_ts_utc") or record.get("asof_ts_utc"),
            signal.ts_utc,
            label="scorecard_record.asof_ts_utc",
        ) or signal.ts_utc
        refs.append(
            NoLookaheadInputRef(
                id=evidence_ref,
                kind="scorecard_record",
                source=scorecard_source,
                record_index=source_record_index,
                asof_ts_utc=record_asof,
                digest=_scorecard_record_digest(record),
            )
        )
    refs.append(
        NoLookaheadInputRef(
            id=f"snapshot_signal:{signal.id}",
            kind="snapshot_signal",
            source="pa_feitian_snapshot_v1.decision_fields",
            record_index=source_record_index,
            asof_ts_utc=signal.ts_utc,
            digest=_signal_decision_digest(signal),
        )
    )
    return refs


def _intent_for_signal(
    signal: PaFeitianSignal,
    *,
    record: Mapping[str, Any],
    source_record_index: int | None,
    scorecard_source: str,
) -> DecisionIntentSignal:
    evidence_ref = (
        f"scorecard_record:{source_record_index}"
        if source_record_index is not None
        else f"snapshot_signal:{signal.id}"
    )
    selected = _selected_option(signal, record)
    reason_codes: list[str] = []
    premium_stop = _premium_stop_intent(
        signal,
        record,
        selected,
        evidence_ref=evidence_ref,
        reason_codes=reason_codes,
    )
    confirmation = _confirmation_intent(
        signal,
        record,
        selected,
        evidence_ref=evidence_ref,
        reason_codes=reason_codes,
    )
    liquidity = _liquidity_intent(
        signal,
        record,
        selected,
        evidence_ref=evidence_ref,
        reason_codes=reason_codes,
    )
    product_direction_tier = _product_direction_tier(
        signal,
        record,
        selected,
        reason_codes=reason_codes,
    )
    right_tail_observation = _has_right_tail_observation(record, selected)
    decision_state = _decision_state(
        signal,
        product_direction_tier=product_direction_tier,
        premium_stop=premium_stop,
        confirmation=confirmation,
        liquidity=liquidity,
        right_tail_observation=right_tail_observation,
        reason_codes=reason_codes,
    )
    if not reason_codes:
        _add_reason(reason_codes, "READINESS_REVIEW_REQUIRED")

    return DecisionIntentSignal(
        signal_id=signal.id,
        instrument=signal.instrument,
        contract=signal.contract,
        interval=signal.interval,
        decision_ts_utc=signal.ts_utc,
        decision_state=decision_state,  # type: ignore[arg-type]
        execution_allowed=decision_state == "trade_ready",
        product_direction_tier=product_direction_tier,
        premium_stop=premium_stop,
        confirmation=confirmation,
        liquidity=liquidity,
        reason_codes=reason_codes,
        no_lookahead_inputs=_no_lookahead_inputs(
            signal,
            record,
            source_record_index=source_record_index,
            evidence_ref=evidence_ref,
            scorecard_source=scorecard_source,
        ),
    )


def build_decision_intent_sidecar(
    snapshot: PaFeitianSnapshot | PaFeitianSnapshotV1,
    *,
    source_commit: str,
    source_manifest_path: str | Path,
    snapshot_artifact_path: str | Path,
    generated_at_utc: datetime,
    source_manifest_generated_at_utc: datetime | None = None,
    scorecard: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    scorecard_source: str = "score_today_json",
) -> PaFeitianDecisionIntentSidecar:
    """Build the manifest-referenced v0.2 decision-intent sidecar.

    The adapter only consumes already-emitted scorecard/snapshot artifacts. It
    does not read market stores and it does not place or stage orders.
    """
    candidate_records = _candidate_records(scorecard)
    intents: list[DecisionIntentSignal] = []
    for signal in snapshot.signals:
        raw_index = signal.features_det.get("source_record_index")
        source_record_index = _optional_int(raw_index)
        record = candidate_records.get(source_record_index, {}) if source_record_index else {}
        intents.append(
            _intent_for_signal(
                signal,
                record=record,
                source_record_index=source_record_index,
                scorecard_source=scorecard_source,
            )
        )

    return PaFeitianDecisionIntentSidecar(
        schema_version=PA_FEITIAN_DECISION_INTENT_SCHEMA_VERSION,
        generated_at_utc=generated_at_utc,
        source_commit=source_commit,
        provenance=DecisionIntentProvenance(
            role="manifest_referenced_decision_intent_sidecar",
            source_manifest_path=str(source_manifest_path),
            source_manifest_schema_version="pa_feitian_run_manifest_v1",
            source_manifest_generated_at_utc=source_manifest_generated_at_utc,
            snapshot_artifact_path=str(snapshot_artifact_path),
            snapshot_artifact_sha256=sha256_file(snapshot_artifact_path),
            snapshot_schema_version=snapshot.schema_version,  # type: ignore[arg-type]
            producer="engine.pa_feitian.decision_intent_adapter.v0_2",
            notes=[
                "focused v0.2 strategy adapter sidecar; snapshot v0/v1 semantics unchanged",
                "execution_allowed remains false unless explicit premium stop, confirmation, "
                "and liquidity gates pass at decision time",
            ],
        ),
        intents=intents,
        warnings=[
            "decision intent sidecar is readiness metadata only; it does not execute orders",
            "missing premium stop, confirmation, or liquidity inputs are downgraded instead of "
            "being inferred from outcomes",
        ],
    )


def build_decision_intent_sidecar_from_scorecard_file(
    snapshot: PaFeitianSnapshot | PaFeitianSnapshotV1,
    *,
    scorecard_path: str | Path,
    source_commit: str,
    source_manifest_path: str | Path,
    snapshot_artifact_path: str | Path,
    generated_at_utc: datetime,
    source_manifest_generated_at_utc: datetime | None = None,
) -> PaFeitianDecisionIntentSidecar:
    with Path(scorecard_path).open(encoding="utf-8") as f:
        scorecard = json.load(f)
    return build_decision_intent_sidecar(
        snapshot,
        source_commit=source_commit,
        source_manifest_path=source_manifest_path,
        snapshot_artifact_path=snapshot_artifact_path,
        generated_at_utc=generated_at_utc,
        source_manifest_generated_at_utc=source_manifest_generated_at_utc,
        scorecard=scorecard,
        scorecard_source="score_today_json",
    )


__all__ = [
    "AU_CALL_STOP_GATE_MAX_PCT",
    "AU_CALL_STOP_GATE_MIN_PCT",
    "build_decision_intent_sidecar",
    "build_decision_intent_sidecar_from_scorecard_file",
]
