"""Deterministic PA / Feitian premium-space outcome harness."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from data.option_store import OptionContract, OptionStore
from engine.pa_feitian.contract import (
    PaFeitianDecisionIntentSidecar,
    PaFeitianSnapshotV1,
    load_decision_intent,
    load_snapshot_v1,
)
from engine.pa_feitian.manifest import PaFeitianRunManifest, load_run_manifest, sha256_file
from engine.pa_feitian.premium_outcome import (
    PA_FEITIAN_PREMIUM_OUTCOME_SCHEMA_VERSION,
    PaFeitianPremiumOutcomeSidecar,
    PremiumFill,
    PremiumOutcomeAmbiguity,
    PremiumOutcomeCostModel,
    PremiumOutcomeDataGap,
    PremiumOutcomeDataQuality,
    PremiumOutcomeMetrics,
    PremiumOutcomeNoLookaheadInputRef,
    PremiumOutcomePolicy,
    PremiumOutcomePolicyParams,
    PremiumOutcomeProvenance,
    PremiumOutcomeRecord,
    PremiumRiskBasis,
    SelectedOptionContract,
    premium_outcome_to_jsonable,
    validate_premium_outcome,
)


DEFAULT_GENERATED_AT_UTC = datetime(2026, 7, 10, tzinfo=UTC)
DEFAULT_POLICY_DECLARED_AT_UTC = DEFAULT_GENERATED_AT_UTC
DEFAULT_TRAVERSAL_STARTED_AT_UTC = DEFAULT_POLICY_DECLARED_AT_UTC + timedelta(minutes=1)
DEFAULT_TICK_SIZES: dict[str, float] = {"ag": 0.5, "au": 0.02}
DEFAULT_SLIPPAGE_TICKS = 2.0
DEFAULT_STOP_FRACTION_OF_ENTRY = 0.5
DEFAULT_TARGET_MULTIPLES_OF_ENTRY = (2.0,)
DEFAULT_MAX_HOLDING_BARS = 10
DEFAULT_POLICY_ID = "pa_feitian_m5_daily_long_option_stop_target"
DEFAULT_POLICY_VERSION = "v1.default"
PRODUCER_ID = "engine.pa_feitian.premium_outcome_harness.v1"


@dataclass(frozen=True)
class PremiumOutcomeHarnessConfig:
    source_commit: str
    generated_at_utc: datetime = DEFAULT_GENERATED_AT_UTC
    policy_declared_at_utc: datetime = DEFAULT_POLICY_DECLARED_AT_UTC
    traversal_started_at_utc: datetime = DEFAULT_TRAVERSAL_STARTED_AT_UTC
    policy_id: str = DEFAULT_POLICY_ID
    policy_version: str = DEFAULT_POLICY_VERSION
    slippage_ticks: float = DEFAULT_SLIPPAGE_TICKS
    stop_fraction_of_entry: float = DEFAULT_STOP_FRACTION_OF_ENTRY
    target_multiples_of_entry: tuple[float, ...] = DEFAULT_TARGET_MULTIPLES_OF_ENTRY
    max_holding_bars: int = DEFAULT_MAX_HOLDING_BARS
    tick_sizes: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_TICK_SIZES))
    cli_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class HarnessInputPaths:
    source_manifest_path: str
    snapshot_path: str
    decision_intent_path: str


@dataclass(frozen=True)
class _SelectedLeg:
    source_contract_id: str
    selection_source_ref: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class _Evaluation:
    record: PremiumOutcomeRecord
    selected_bar_digest: str | None = None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _utc_iso(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def _date_ts_utc(value: Any) -> datetime:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        return parsed.to_pydatetime().replace(tzinfo=UTC)
    return parsed.tz_convert("UTC").to_pydatetime()


def _canonical_digest(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
        default=str,
    )
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def canonical_policy_digest(
    *,
    policy_id: str,
    policy_version: str,
    declared_at_utc: datetime,
    traversal_started_at_utc: datetime,
    params: PremiumOutcomePolicyParams,
) -> str:
    """Digest the policy declaration excluding outcome-local provenance keys."""

    return _canonical_digest(
        {
            "policy_id": policy_id,
            "policy_version": policy_version,
            "origin": "retrospective_fixed",
            "declared_at_utc": _utc_iso(declared_at_utc),
            "fixed_before_traversal": True,
            "traversal_started_at_utc": _utc_iso(traversal_started_at_utc),
            "params": params.model_dump(mode="json", exclude_none=False),
        }
    )


def selected_option_bar_digest(bars: list[dict[str, Any]]) -> str:
    return _canonical_digest({"bar_granularity": "daily", "bars": bars})


def _round(value: float | None, digits: int = 10) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value):
        return value
    return round(float(value), digits)


def _safe_id(value: str) -> str:
    safe = re.sub(r"[^a-z0-9_:-]+", "_", value.lower())
    return safe.strip("_") or "unknown"


def _product_from_signal(signal: Any) -> str:
    instrument = str(signal.instrument or "")
    if "." in instrument:
        return instrument.split(".")[-1]
    contract = str(signal.contract or "")
    if contract.startswith("kq_m_"):
        return contract.split("_")[-1]
    selected = str(signal.features_det.get("selected_option_contract") or "")
    match = re.match(r"([a-zA-Z]+)", selected)
    return match.group(1) if match else ""


def _exchange_from_signal(signal: Any) -> str:
    instrument = str(signal.instrument or "")
    if "." in instrument:
        return instrument.split(".")[0]
    return "UNKNOWN"


def _selected_leg(signal: Any) -> _SelectedLeg | None:
    selected_symbol = signal.features_det.get("selected_option_contract")
    if not selected_symbol:
        return None

    source_record_index = signal.features_det.get("source_record_index")
    selection_source_ref = (
        f"scorecard_record:{source_record_index}"
        if source_record_index is not None
        else f"snapshot_signal:{signal.id}"
    )
    options_calls = signal.features_det.get("options_calls") or []
    for index, call in enumerate(options_calls):
        if str(call.get("contract_sym")) == str(selected_symbol):
            return _SelectedLeg(
                source_contract_id=f"{selection_source_ref}:options_calls:{index}",
                selection_source_ref=selection_source_ref,
                payload=dict(call),
            )
    return None


def _is_model_derived(leg: _SelectedLeg | None, signal: Any) -> bool:
    if leg is None:
        return False
    return (
        leg.payload.get("model_dominated") is True
        or leg.payload.get("price_source") == "model"
        or signal.status == "model_dominated"
    )


def _option_type(signal: Any, selected_symbol: str) -> str:
    side = getattr(signal.option_leg, "side", None)
    if side in {"call", "put"}:
        return side
    stem = selected_symbol.rstrip("0123456789").lower()
    if stem.endswith("c"):
        return "call"
    if stem.endswith("p"):
        return "put"
    return "unknown"


def _resolve_contract(store: OptionStore, product: str, selected_symbol: str) -> OptionContract | None:
    for contract in store.catalog(product):
        if contract.contract_sym.lower() == selected_symbol.lower():
            return contract
    return None


def _build_selected_contract(
    *,
    signal: Any,
    intent: Any,
    leg: _SelectedLeg,
    store_contract: OptionContract | None,
) -> SelectedOptionContract | None:
    selected_symbol = str(signal.features_det.get("selected_option_contract"))
    product = _product_from_signal(signal)
    exchange = _exchange_from_signal(signal)
    strike = leg.payload.get("strike")
    expiry = leg.payload.get("expiry_date") or leg.payload.get("expiry")
    dte = leg.payload.get("days_to_expiry")

    if strike is None and store_contract is not None:
        strike = store_contract.strike
    if expiry is None and store_contract is not None and store_contract.expiry is not None:
        expiry = store_contract.expiry.isoformat()
    if dte is None:
        dte = getattr(signal.option_leg, "dte", None)
    if product == "" and store_contract is not None:
        product = store_contract.product

    if strike is None or expiry is None or dte is None or product == "":
        return None

    option_type = _option_type(signal, selected_symbol)
    if option_type not in {"call", "put"}:
        return None

    return SelectedOptionContract(
        source_contract_id=leg.source_contract_id,
        option_type=option_type,
        exchange=exchange,
        product=product,
        contract_symbol=selected_symbol,
        strike=float(strike),
        expiry=str(expiry),
        dte_at_decision=int(dte),
        contract_selection_asof_utc=intent.decision_ts_utc,
        selection_source_ref=leg.selection_source_ref,
    )


def _policy_params(tick_size: float | None, config: PremiumOutcomeHarnessConfig):
    return PremiumOutcomePolicyParams(
        entry_rule="first_valid_daily_option_store_bar_strictly_after_decision_open",
        price_level_mode="entry_relative",
        stop_premium=None,
        target_premiums=[],
        stop_fraction_of_entry=config.stop_fraction_of_entry,
        target_multiples_of_entry=list(config.target_multiples_of_entry),
        max_holding_bars=config.max_holding_bars,
        max_holding_days=None,
        stop_fill_rule="at_level",
        target_fill_rule="at_level",
        time_exit_fill_rule="bar_close",
        missing_bar_policy="data_blocked",
        same_bar_resolution="ambiguous",
        slippage_ticks=config.slippage_ticks,
        tick_size=tick_size,
    )


def _policy(
    *,
    params: PremiumOutcomePolicyParams,
    outcome_id: str,
    config: PremiumOutcomeHarnessConfig,
) -> PremiumOutcomePolicy:
    digest = canonical_policy_digest(
        policy_id=config.policy_id,
        policy_version=config.policy_version,
        declared_at_utc=config.policy_declared_at_utc,
        traversal_started_at_utc=config.traversal_started_at_utc,
        params=params,
    )
    return PremiumOutcomePolicy(
        policy_id=config.policy_id,
        policy_version=config.policy_version,
        origin="retrospective_fixed",
        declared_at_utc=config.policy_declared_at_utc,
        fixed_before_traversal=True,
        traversal_started_at_utc=config.traversal_started_at_utc,
        digest=digest,
        provenance_hash_key=f"{outcome_id}:policy",
        params=params,
    )


def _cost_model(tick_size: float | None, config: PremiumOutcomeHarnessConfig) -> PremiumOutcomeCostModel:
    return PremiumOutcomeCostModel(
        model_id="m5_default_slippage_only_long_option",
        currency="CNY",
        commission_per_contract=0.0,
        fees_per_contract=0.0,
        slippage_ticks=config.slippage_ticks,
        tick_size=tick_size,
        tick_value=1.0 if tick_size is not None else None,
        entry_cost_premium=0.0,
        exit_cost_premium=0.0,
        notes=[
            "entry fill = daily open + slippage_ticks * tick_size for a long option buy",
            "exit fill = raw exit level/open/close - slippage_ticks * tick_size, floored at zero",
            "cost_premium excludes slippage; default commissions and fees are zero",
        ],
    )


def _copied_no_lookahead_inputs(intent: Any) -> list[PremiumOutcomeNoLookaheadInputRef]:
    return [
        PremiumOutcomeNoLookaheadInputRef.model_validate(input_ref.model_dump(mode="python"))
        for input_ref in intent.no_lookahead_inputs
    ]


def _base_quality(
    *,
    source_type: str,
    required: bool,
    first_ts: datetime | None = None,
    last_ts: datetime | None = None,
    ambiguity: PremiumOutcomeAmbiguity | None = None,
    data_gap: PremiumOutcomeDataGap | None = None,
    notes: list[str] | None = None,
) -> PremiumOutcomeDataQuality:
    return PremiumOutcomeDataQuality(
        premium_price_source_type=source_type,
        bar_granularity="daily",
        required_premium_bars_available=required,
        first_premium_observation_ts_utc=first_ts,
        last_premium_observation_ts_utc=last_ts,
        ambiguity=ambiguity,
        data_gap=data_gap,
        notes=notes or [],
    )


def _blocked_record(
    *,
    signal: Any,
    intent: Any,
    outcome_id: str,
    source_contract_id: str | None,
    selected_contract: SelectedOptionContract | None,
    policy: PremiumOutcomePolicy,
    cost_model: PremiumOutcomeCostModel,
    gap: PremiumOutcomeDataGap,
    first_ts: datetime | None = None,
    last_ts: datetime | None = None,
    entry_fill: PremiumFill | None = None,
    source_type: str = "unavailable",
    notes: list[str] | None = None,
) -> PremiumOutcomeRecord:
    return PremiumOutcomeRecord(
        outcome_id=outcome_id,
        source_signal_id=signal.id,
        decision_intent_signal_id=intent.signal_id,
        source_contract_id=source_contract_id,
        decision_ts_utc=intent.decision_ts_utc,
        first_eligible_entry_ts_utc=entry_fill.ts_utc if entry_fill is not None else None,
        selected_contract=selected_contract,
        policy=policy,
        cost_model=cost_model,
        evaluation_status="data_blocked",
        exit_reason="data_gap",
        entry_fill=entry_fill,
        exit_fill=None,
        premium_metrics=None,
        underlying_context=None,
        data_quality=_base_quality(
            source_type=source_type,
            required=False,
            first_ts=first_ts,
            last_ts=last_ts,
            data_gap=gap,
            notes=notes
            or ["missing or invalid required option premium data is data_blocked"],
        ),
        no_lookahead_inputs=_copied_no_lookahead_inputs(intent),
    )


def _not_evaluable_record(
    *,
    signal: Any,
    intent: Any,
    outcome_id: str,
    source_contract_id: str | None,
    selected_contract: SelectedOptionContract | None,
    policy: PremiumOutcomePolicy,
    cost_model: PremiumOutcomeCostModel,
) -> PremiumOutcomeRecord:
    return PremiumOutcomeRecord(
        outcome_id=outcome_id,
        source_signal_id=signal.id,
        decision_intent_signal_id=intent.signal_id,
        source_contract_id=source_contract_id,
        decision_ts_utc=intent.decision_ts_utc,
        first_eligible_entry_ts_utc=None,
        selected_contract=selected_contract,
        policy=policy,
        cost_model=cost_model,
        evaluation_status="not_evaluable",
        exit_reason="not_evaluable",
        entry_fill=None,
        exit_fill=None,
        premium_metrics=None,
        underlying_context=None,
        data_quality=_base_quality(
            source_type="model_derived",
            required=False,
            notes=[
                "selected decision-time premium was model-derived and is not evaluable "
                "as an observed OptionStore premium path"
            ],
        ),
        no_lookahead_inputs=_copied_no_lookahead_inputs(intent),
    )


def _bar_to_digest_row(row: pd.Series) -> dict[str, Any]:
    return {
        "ts_utc": _utc_iso(_date_ts_utc(row["date"])),
        "open": _round(float(row["open"])),
        "high": _round(float(row["high"])),
        "low": _round(float(row["low"])),
        "close": _round(float(row["close"])),
    }


def _valid_ohlc(row: pd.Series) -> bool:
    values = [float(row[key]) for key in ("open", "high", "low", "close")]
    if any(not math.isfinite(value) or value <= 0 for value in values):
        return False
    open_, high, low, close = values
    return low <= min(open_, close) and high >= max(open_, close) and high >= low


def _after_decision_bars(df: pd.DataFrame, decision_ts: datetime) -> pd.DataFrame:
    bars = df.copy()
    bars["date"] = pd.to_datetime(bars["date"])
    bars["ts_utc"] = bars["date"].map(_date_ts_utc)
    return bars[bars["ts_utc"] > _utc(decision_ts)].reset_index(drop=True)


def _evaluate_path(
    *,
    signal: Any,
    intent: Any,
    outcome_id: str,
    source_contract_id: str,
    selected_contract: SelectedOptionContract,
    policy: PremiumOutcomePolicy,
    cost_model: PremiumOutcomeCostModel,
    df: pd.DataFrame,
    config: PremiumOutcomeHarnessConfig,
) -> _Evaluation:
    bars = _after_decision_bars(df, intent.decision_ts_utc)
    if bars.empty:
        gap = PremiumOutcomeDataGap(
            kind="missing_bars",
            start_ts_utc=None,
            end_ts_utc=None,
            description="OptionStore has no daily bars strictly after the decision timestamp",
        )
        return _Evaluation(
            _blocked_record(
                signal=signal,
                intent=intent,
                outcome_id=outcome_id,
                source_contract_id=source_contract_id,
                selected_contract=selected_contract,
                policy=policy,
                cost_model=cost_model,
                gap=gap,
            )
        )

    tick_size = policy.params.tick_size
    assert tick_size is not None
    slippage = config.slippage_ticks * tick_size
    target_multiple = config.target_multiples_of_entry[0]
    considered: list[dict[str, Any]] = []

    entry_row = bars.iloc[0]
    entry_ts = _date_ts_utc(entry_row["date"])
    considered.append(_bar_to_digest_row(entry_row))
    first_ts = entry_ts

    if not _valid_ohlc(entry_row):
        digest = selected_option_bar_digest(considered)
        gap = PremiumOutcomeDataGap(
            kind="missing_entry",
            start_ts_utc=entry_ts,
            end_ts_utc=entry_ts,
            description="first eligible daily OptionStore bar has invalid OHLC",
        )
        return _Evaluation(
            _blocked_record(
                signal=signal,
                intent=intent,
                outcome_id=outcome_id,
                source_contract_id=source_contract_id,
                selected_contract=selected_contract,
                policy=policy,
                cost_model=cost_model,
                gap=gap,
                first_ts=first_ts,
                last_ts=entry_ts,
                source_type="observed",
                notes=["invalid first eligible option OHLC blocks deterministic entry"],
            ),
            selected_bar_digest=digest,
        )

    entry_raw = float(entry_row["open"])
    entry_fill_price = entry_raw + slippage
    stop_level = entry_fill_price * config.stop_fraction_of_entry
    target_level = entry_fill_price * target_multiple
    stop_exit_fill = max(stop_level - slippage, 0.0)
    entry_fill = PremiumFill(
        ts_utc=entry_ts,
        fill_premium=_round(entry_fill_price),
        fill_rule="next_open",
        slippage_premium=_round(slippage),
        cost_premium=0.0,
    )

    max_bars = config.max_holding_bars
    exit_reason: str | None = None
    exit_rule = "not_applicable"
    exit_ts: datetime | None = None
    exit_raw: float | None = None
    highs: list[float] = []
    lows: list[float] = []

    for offset in range(max_bars):
        if offset >= len(bars):
            gap = PremiumOutcomeDataGap(
                kind="early_termination",
                start_ts_utc=_date_ts_utc(bars.iloc[-1]["date"]),
                end_ts_utc=None,
                description=(
                    f"OptionStore ended before the required {max_bars}-bar "
                    "time-exit window completed"
                ),
            )
            digest = selected_option_bar_digest(considered)
            return _Evaluation(
                _blocked_record(
                    signal=signal,
                    intent=intent,
                    outcome_id=outcome_id,
                    source_contract_id=source_contract_id,
                    selected_contract=selected_contract,
                    policy=policy,
                    cost_model=cost_model,
                    gap=gap,
                    first_ts=first_ts,
                    last_ts=_date_ts_utc(bars.iloc[-1]["date"]),
                    entry_fill=entry_fill,
                    source_type="observed",
                    notes=["full max-holding window is required for a time exit"],
                ),
                selected_bar_digest=digest,
            )

        row = bars.iloc[offset]
        row_ts = _date_ts_utc(row["date"])
        if offset > 0:
            considered.append(_bar_to_digest_row(row))
        if not _valid_ohlc(row):
            digest = selected_option_bar_digest(considered)
            gap = PremiumOutcomeDataGap(
                kind="missing_exit",
                start_ts_utc=row_ts,
                end_ts_utc=row_ts,
                description="required daily OptionStore bar has invalid OHLC",
            )
            return _Evaluation(
                _blocked_record(
                    signal=signal,
                    intent=intent,
                    outcome_id=outcome_id,
                    source_contract_id=source_contract_id,
                    selected_contract=selected_contract,
                    policy=policy,
                    cost_model=cost_model,
                    gap=gap,
                    first_ts=first_ts,
                    last_ts=row_ts,
                    entry_fill=entry_fill,
                    source_type="observed",
                    notes=["invalid option OHLC in the required traversal path blocks outcome"],
                ),
                selected_bar_digest=digest,
            )

        open_ = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])
        highs.append(high)
        lows.append(low)

        gap_stop = open_ <= stop_level
        gap_target = open_ >= target_level
        touches_stop = low <= stop_level
        touches_target = high >= target_level

        if gap_stop:
            exit_reason = "premium_stop"
            exit_rule = "gap_open"
            exit_ts = row_ts
            exit_raw = open_
            break
        if gap_target:
            exit_reason = "premium_target"
            exit_rule = "gap_open"
            exit_ts = row_ts
            exit_raw = open_
            break
        if touches_stop and touches_target:
            ambiguity = PremiumOutcomeAmbiguity(
                kind="same_bar_stop_target",
                bar_ts_utc=row_ts,
                conservative_resolution="ambiguous",
                description=(
                    "daily OptionStore OHLC touched the entry-relative stop and "
                    "target in the same bar; event ordering is unknowable"
                ),
            )
            digest = selected_option_bar_digest(considered)
            record = PremiumOutcomeRecord(
                outcome_id=outcome_id,
                source_signal_id=signal.id,
                decision_intent_signal_id=intent.signal_id,
                source_contract_id=source_contract_id,
                decision_ts_utc=intent.decision_ts_utc,
                first_eligible_entry_ts_utc=entry_ts,
                selected_contract=selected_contract,
                policy=policy,
                cost_model=cost_model,
                evaluation_status="ambiguous",
                exit_reason="unresolved",
                entry_fill=entry_fill,
                exit_fill=None,
                premium_metrics=None,
                underlying_context=None,
                data_quality=_base_quality(
                    source_type="observed",
                    required=True,
                    first_ts=first_ts,
                    last_ts=row_ts,
                    ambiguity=ambiguity,
                    notes=[
                        "daily option OHLC is observation-only and cannot prove "
                        "same-bar stop/target ordering"
                    ],
                ),
                no_lookahead_inputs=_copied_no_lookahead_inputs(intent),
            )
            return _Evaluation(record, selected_bar_digest=digest)
        if touches_stop:
            exit_reason = "premium_stop"
            exit_rule = "at_level"
            exit_ts = row_ts
            exit_raw = stop_level
            break
        if touches_target:
            exit_reason = "premium_target"
            exit_rule = "at_level"
            exit_ts = row_ts
            exit_raw = target_level
            break

    if exit_reason is None:
        row = bars.iloc[max_bars - 1]
        exit_reason = "time_exit"
        exit_rule = "bar_close"
        exit_ts = _date_ts_utc(row["date"])
        exit_raw = float(row["close"])

    assert exit_ts is not None and exit_raw is not None
    exit_fill_price = max(exit_raw - slippage, 0.0)
    exit_fill = PremiumFill(
        ts_utc=exit_ts,
        fill_premium=_round(exit_fill_price),
        fill_rule=exit_rule,
        slippage_premium=_round(slippage),
        cost_premium=0.0,
    )
    risk = PremiumRiskBasis(
        entry_premium=_round(entry_fill_price),
        stop_premium=_round(stop_exit_fill),
        entry_cost_premium=0.0,
        exit_cost_premium=0.0,
        declared_risk_premium=_round(entry_fill_price - stop_exit_fill),
        denominator_label="declared_premium_risk_after_costs",
    )
    net_pnl = exit_fill_price - entry_fill_price
    metrics = PremiumOutcomeMetrics(
        gross_premium_return=_round((exit_fill_price - entry_fill_price) / entry_fill_price),
        net_premium_return=_round(net_pnl / entry_fill_price),
        premium_multiple=_round(exit_fill_price / entry_fill_price),
        premium_r=_round(net_pnl / risk.declared_risk_premium),
        premium_mfe=_round((max(highs) - entry_fill_price) / entry_fill_price),
        premium_mae=_round((min(lows) - entry_fill_price) / entry_fill_price),
        risk=risk,
    )
    digest = selected_option_bar_digest(considered)
    record = PremiumOutcomeRecord(
        outcome_id=outcome_id,
        source_signal_id=signal.id,
        decision_intent_signal_id=intent.signal_id,
        source_contract_id=source_contract_id,
        decision_ts_utc=intent.decision_ts_utc,
        first_eligible_entry_ts_utc=entry_ts,
        selected_contract=selected_contract,
        policy=policy,
        cost_model=cost_model,
        evaluation_status="observed",
        exit_reason=exit_reason,
        entry_fill=entry_fill,
        exit_fill=exit_fill,
        premium_metrics=metrics,
        underlying_context=None,
        data_quality=_base_quality(
            source_type="observed",
            required=True,
            first_ts=first_ts,
            last_ts=exit_ts,
            notes=[
                "daily OptionStore OHLC is observation-only evidence, not exact "
                "tick-level execution proof",
                "gap opens through stop/target fill at that bar open with adverse "
                "exit slippage",
            ],
        ),
        no_lookahead_inputs=_copied_no_lookahead_inputs(intent),
    )
    return _Evaluation(record, selected_bar_digest=digest)


def evaluate_premium_outcome_signal(
    *,
    signal: Any,
    intent: Any,
    store: OptionStore,
    config: PremiumOutcomeHarnessConfig,
    outcome_index: int,
) -> _Evaluation:
    outcome_id = f"paft_premium_outcome_{outcome_index:04d}_{_safe_id(signal.id)}_daily_v1"
    product = _product_from_signal(signal)
    tick_size = config.tick_sizes.get(product)
    leg = _selected_leg(signal)
    selected_symbol = signal.features_det.get("selected_option_contract")
    store_contract = (
        _resolve_contract(store, product, str(selected_symbol))
        if selected_symbol and product
        else None
    )
    selected_contract = (
        _build_selected_contract(
            signal=signal,
            intent=intent,
            leg=leg,
            store_contract=store_contract,
        )
        if leg is not None
        else None
    )

    params = _policy_params(tick_size, config)
    policy = _policy(params=params, outcome_id=outcome_id, config=config)
    cost_model = _cost_model(tick_size, config)

    if leg is None or selected_symbol is None:
        gap = PremiumOutcomeDataGap(
            kind="missing_contract",
            start_ts_utc=None,
            end_ts_utc=None,
            description="snapshot signal has no decision-time selected_option_contract",
        )
        return _Evaluation(
            _blocked_record(
                signal=signal,
                intent=intent,
                outcome_id=outcome_id,
                source_contract_id=None,
                selected_contract=None,
                policy=policy,
                cost_model=cost_model,
                gap=gap,
            )
        )

    if _is_model_derived(leg, signal):
        return _Evaluation(
            _not_evaluable_record(
                signal=signal,
                intent=intent,
                outcome_id=outcome_id,
                source_contract_id=leg.source_contract_id,
                selected_contract=selected_contract,
                policy=policy,
                cost_model=cost_model,
            )
        )

    if tick_size is None:
        gap = PremiumOutcomeDataGap(
            kind="other",
            start_ts_utc=None,
            end_ts_utc=None,
            description=f"no explicit M5 tick size configured for product {product!r}",
        )
        return _Evaluation(
            _blocked_record(
                signal=signal,
                intent=intent,
                outcome_id=outcome_id,
                source_contract_id=leg.source_contract_id,
                selected_contract=selected_contract,
                policy=policy,
                cost_model=cost_model,
                gap=gap,
            )
        )

    if selected_contract is None:
        gap = PremiumOutcomeDataGap(
            kind="missing_contract",
            start_ts_utc=None,
            end_ts_utc=None,
            description="selected contract lacks required decision-time metadata",
        )
        return _Evaluation(
            _blocked_record(
                signal=signal,
                intent=intent,
                outcome_id=outcome_id,
                source_contract_id=leg.source_contract_id,
                selected_contract=None,
                policy=policy,
                cost_model=cost_model,
                gap=gap,
            )
        )

    if store_contract is None:
        gap = PremiumOutcomeDataGap(
            kind="missing_contract",
            start_ts_utc=None,
            end_ts_utc=None,
            description=(
                "selected decision-time contract was not found in OptionStore; "
                "the harness does not rescan or reselect"
            ),
        )
        return _Evaluation(
            _blocked_record(
                signal=signal,
                intent=intent,
                outcome_id=outcome_id,
                source_contract_id=leg.source_contract_id,
                selected_contract=selected_contract,
                policy=policy,
                cost_model=cost_model,
                gap=gap,
            )
        )

    df = store.load_contract_daily(str(selected_symbol))
    if df is None or df.empty:
        gap = PremiumOutcomeDataGap(
            kind="missing_bars",
            start_ts_utc=None,
            end_ts_utc=None,
            description="selected OptionStore contract has no daily OHLC bars",
        )
        return _Evaluation(
            _blocked_record(
                signal=signal,
                intent=intent,
                outcome_id=outcome_id,
                source_contract_id=leg.source_contract_id,
                selected_contract=selected_contract,
                policy=policy,
                cost_model=cost_model,
                gap=gap,
            )
        )

    return _evaluate_path(
        signal=signal,
        intent=intent,
        outcome_id=outcome_id,
        source_contract_id=leg.source_contract_id,
        selected_contract=selected_contract,
        policy=policy,
        cost_model=cost_model,
        df=df,
        config=config,
    )


def _validate_source_manifest_links(
    *,
    source_manifest: PaFeitianRunManifest,
    source_manifest_path: str | Path,
    snapshot_path: str | Path,
    decision_intent_path: str | Path,
) -> None:
    snapshot_hash = sha256_file(snapshot_path)
    decision_hash = sha256_file(decision_intent_path)
    if source_manifest.snapshot_artifact.sha256 != snapshot_hash:
        raise ValueError("source M4 manifest snapshot hash does not match explicit snapshot input")
    if source_manifest.decision_intent_artifact is None:
        raise ValueError("source M4 manifest must reference a decision-intent artifact")
    if source_manifest.decision_intent_artifact.sha256 != decision_hash:
        raise ValueError(
            "source M4 manifest decision-intent hash does not match explicit decision-intent input"
        )
    if sha256_file(source_manifest_path) is None:
        raise AssertionError("unreachable")


def build_premium_outcome_sidecar(
    *,
    snapshot: PaFeitianSnapshotV1,
    decision_intent: PaFeitianDecisionIntentSidecar,
    source_manifest: PaFeitianRunManifest,
    input_paths: HarnessInputPaths,
    quant_data_root: str | Path,
    config: PremiumOutcomeHarnessConfig,
) -> PaFeitianPremiumOutcomeSidecar:
    store = OptionStore(quant_data_root)
    intents_by_id = {intent.signal_id: intent for intent in decision_intent.intents}
    outcomes: list[PremiumOutcomeRecord] = []
    bar_hashes: dict[str, str] = {}
    policy_hashes: dict[str, str] = {}

    for index, signal in enumerate(snapshot.signals, start=1):
        intent = intents_by_id.get(signal.id)
        if intent is None:
            raise ValueError(f"decision intent missing signal_id {signal.id!r}")
        evaluation = evaluate_premium_outcome_signal(
            signal=signal,
            intent=intent,
            store=store,
            config=config,
            outcome_index=index,
        )
        outcomes.append(evaluation.record)
        policy_hashes[evaluation.record.policy.provenance_hash_key] = (
            evaluation.record.policy.digest
        )
        if evaluation.selected_bar_digest is not None:
            bar_hashes[f"selected_option_bars:{evaluation.record.outcome_id}"] = (
                evaluation.selected_bar_digest
            )

    input_hashes = {
        "source_manifest": sha256_file(input_paths.source_manifest_path),
        "snapshot_artifact": sha256_file(input_paths.snapshot_path),
        "decision_intent_artifact": sha256_file(input_paths.decision_intent_path),
        **bar_hashes,
    }
    provenance = PremiumOutcomeProvenance(
        role="manifest_referenced_premium_outcome_sidecar",
        source_manifest_path=input_paths.source_manifest_path,
        source_manifest_sha256=input_hashes["source_manifest"],
        source_manifest_schema_version="pa_feitian_run_manifest_v1",
        snapshot_artifact_path=input_paths.snapshot_path,
        snapshot_artifact_sha256=input_hashes["snapshot_artifact"],
        snapshot_schema_version="pa_feitian_snapshot_v1",
        decision_intent_artifact_path=input_paths.decision_intent_path,
        decision_intent_artifact_sha256=input_hashes["decision_intent_artifact"],
        decision_intent_schema_version="pa_feitian_decision_intent_v1",
        producer=PRODUCER_ID,
        cli_args=list(config.cli_args),
        input_hashes=input_hashes,
        policy_hashes=policy_hashes,
        output_hashes={},
        notes=[
            "M5 premium outcomes are posterior observation-only sidecar records",
            "source snapshot and decision-intent artifacts are immutable inputs",
            "source M4 manifest is hashed input; the M5 manifest hashes this sidecar separately",
            f"quant_data_root={Path(quant_data_root).as_posix()}",
        ],
    )
    sidecar = PaFeitianPremiumOutcomeSidecar(
        schema_version=PA_FEITIAN_PREMIUM_OUTCOME_SCHEMA_VERSION,
        generated_at_utc=config.generated_at_utc,
        source_commit=config.source_commit,
        provenance=provenance,
        outcomes=outcomes,
        warnings=[
            "premium outcome sidecar is posterior observation metadata and must not mutate "
            "snapshot or decision-intent artifacts",
            "daily bars are observation-only evidence and cannot prove exact tick-level "
            "execution ordering",
        ],
    )
    return validate_premium_outcome(premium_outcome_to_jsonable(sidecar))


def build_premium_outcome_sidecar_from_files(
    *,
    snapshot_path: str | Path,
    decision_intent_path: str | Path,
    source_manifest_path: str | Path,
    quant_data_root: str | Path,
    config: PremiumOutcomeHarnessConfig,
    path_formatter: Any | None = None,
) -> PaFeitianPremiumOutcomeSidecar:
    snapshot = load_snapshot_v1(snapshot_path)
    decision_intent = load_decision_intent(decision_intent_path)
    source_manifest = load_run_manifest(source_manifest_path)
    _validate_source_manifest_links(
        source_manifest=source_manifest,
        source_manifest_path=source_manifest_path,
        snapshot_path=snapshot_path,
        decision_intent_path=decision_intent_path,
    )

    def fmt(path: str | Path) -> str:
        if path_formatter is not None:
            return str(path_formatter(path))
        return Path(path).as_posix()

    return build_premium_outcome_sidecar(
        snapshot=snapshot,
        decision_intent=decision_intent,
        source_manifest=source_manifest,
        input_paths=HarnessInputPaths(
            source_manifest_path=fmt(source_manifest_path),
            snapshot_path=fmt(snapshot_path),
            decision_intent_path=fmt(decision_intent_path),
        ),
        quant_data_root=quant_data_root,
        config=config,
    )
