"""Frozen, artifact-driven PA / Feitian historical cohort research gate."""

from __future__ import annotations

import json
import statistics
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from data.option_store import ExplicitContractOptionStore
from engine.pa_feitian.contract import load_decision_intent, load_snapshot_v1
from engine.pa_feitian.manifest import load_run_manifest, sha256_file
from engine.pa_feitian.premium_outcome import (
    PaFeitianPremiumOutcomeSidecar,
    write_premium_outcome,
)
from engine.pa_feitian.premium_outcome_harness import (
    HarnessInputPaths,
    PremiumOutcomeHarnessConfig,
    build_premium_outcome_sidecar,
)


PROTOCOL_VERSION = "pa_feitian_historical_cohort_protocol_v1"
AUDIT_VERSION = "pa_feitian_historical_cohort_coverage_audit_v1"
REPORT_VERSION = "pa_feitian_historical_cohort_report_v1"
PUBLIC_DATA_ROOT = "external://optionstore/quant-data"


def _write_json(payload: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc


def load_frozen_protocol(path: str | Path) -> dict[str, Any]:
    """Load and enforce the research protocol invariants used by this gate."""

    protocol_path = Path(path)
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol.get("schema_version") != PROTOCOL_VERSION:
        raise ValueError(f"protocol schema_version must be {PROTOCOL_VERSION!r}")
    interpretation = protocol.get("interpretation", {})
    if interpretation.get("evaluated_track", {}).get("faithful_feitian_hypothesis") is not False:
        raise ValueError("protocol must label the evaluated track as non-faithful Feitian")
    if (
        interpretation.get("faithful_hypothesis_track", {}).get("status")
        != "coverage_gap_not_evaluated"
    ):
        raise ValueError("protocol must retain the faithful Feitian track as an unevaluated gap")
    upstream = protocol.get("upstream_research", {})
    if upstream.get("role") != "independent_non_transferable_research_input":
        raise ValueError("upstream research must be marked non-transferable")
    if upstream.get("performance_metrics_imported") is not False:
        raise ValueError("upstream performance metrics must not be imported")
    bounds = protocol.get("bounds", {})
    start = _parse_date(bounds.get("decision_date_start"), "decision_date_start")
    end = _parse_date(bounds.get("decision_date_end"), "decision_date_end")
    if start > end:
        raise ValueError("protocol decision-date bounds are reversed")
    if bounds.get("cadence", {}).get("kind") != "immutable_artifact_event":
        raise ValueError("historical cohort cadence must be immutable_artifact_event")
    if bounds.get("cadence", {}).get("calendar_backfill") is not False:
        raise ValueError("historical cohort protocol must prohibit calendar backfill")
    windows = bounds.get("oos_windows", [])
    previous_end: date | None = None
    for window in windows:
        window_start = _parse_date(window.get("decision_date_start"), "OOS window start")
        window_end = _parse_date(window.get("decision_date_end"), "OOS window end")
        if window_start > window_end or window_start < start or window_end > end:
            raise ValueError("OOS windows must be ordered within frozen decision bounds")
        if previous_end is not None and window_start <= previous_end:
            raise ValueError("OOS windows must not overlap")
        previous_end = window_end
    universe = bounds.get("universe")
    if not isinstance(universe, list) or not universe:
        raise ValueError("historical cohort protocol requires a non-empty universe")
    no_lookahead = protocol.get("no_lookahead", {})
    required_guards = (
        "artifact_driven_only",
        "reselect_contract",
        "future_contract_selection",
        "outcome_dependent_reselection",
        "mutate_decision_intent",
        "policy_fixed_before_traversal",
    )
    expected = {
        "artifact_driven_only": True,
        "reselect_contract": False,
        "future_contract_selection": False,
        "outcome_dependent_reselection": False,
        "mutate_decision_intent": False,
        "policy_fixed_before_traversal": True,
    }
    for guard in required_guards:
        if no_lookahead.get(guard) is not expected[guard]:
            raise ValueError(f"protocol no-lookahead guard {guard!r} is not frozen safely")
    policies = protocol.get("policies", {})
    if policies.get("identical_eligible_events_required") is not True:
        raise ValueError("protocol must require identical eligible policy events")
    if policies.get("baseline", {}).get("stop_fraction_of_entry") != 0.5:
        raise ValueError("baseline stop must be frozen at 50%")
    if policies.get("candidate", {}).get("stop_fraction_of_entry") != 0.3:
        raise ValueError("candidate stop must be frozen at 30%")
    thresholds = protocol.get("sample_thresholds", {})
    for name in (
        "pooled_inference_minimum",
        "grouped_result_minimum_per_group",
        "oos_minimum_windows",
        "oos_minimum_events_per_window",
        "screening_minimum_effective_events",
    ):
        if not isinstance(thresholds.get(name), int) or thresholds[name] <= 0:
            raise ValueError(f"sample threshold {name!r} must be a positive integer")
    for name, artifact in protocol.get("inputs", {}).items():
        if name == "runtime_option_store_label":
            continue
        if not isinstance(artifact, dict) or not artifact.get("path") or not str(
            artifact.get("sha256", "")
        ).startswith("sha256:"):
            raise ValueError(f"protocol input {name!r} must pin path and SHA-256")
    return protocol


def _verify_protocol_inputs(protocol: dict[str, Any], repo_root: Path) -> dict[str, Path]:
    resolved: dict[str, Path] = {}
    for name, artifact in protocol["inputs"].items():
        if name == "runtime_option_store_label":
            continue
        path = (repo_root / artifact["path"]).resolve()
        actual = sha256_file(path)
        if actual != artifact["sha256"]:
            raise ValueError(
                f"protocol input hash mismatch for {name}: expected {artifact['sha256']}, "
                f"got {actual}"
            )
        resolved[name] = path
    return resolved


def _universe(protocol: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (str(member["exchange"]).upper(), str(member["product"]).lower())
        for member in protocol["bounds"]["universe"]
    }


def _symbol_market(symbol: str) -> tuple[str, str]:
    parts = symbol.lower().split("_")
    if len(parts) >= 4 and parts[0:2] == ["kq", "m"]:
        return parts[-2].upper(), parts[-1]
    return "UNKNOWN", "unknown"


def _valid_daily_bars(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    bars = pd.read_parquet(path)
    required = {"datetime", "open", "high", "low", "close"}
    if not required.issubset(bars.columns):
        return pd.DataFrame()
    bars = bars.copy()
    bars["date"] = pd.to_datetime(bars["datetime"], errors="coerce").dt.date
    finite = bars[["open", "high", "low", "close"]].notna().all(axis=1)
    coherent = (
        (bars["open"] >= 0)
        & (bars["high"] >= bars[["open", "close", "low"]].max(axis=1))
        & (bars["low"] <= bars[["open", "close", "high"]].min(axis=1))
    )
    return (
        bars[bars["date"].notna() & finite & coherent]
        .sort_values("date")
        .drop_duplicates("date", keep="last")
        .reset_index(drop=True)
    )


def build_coverage_audit(
    *,
    protocol: dict[str, Any],
    protocol_path: str | Path,
    repo_root: str | Path,
    quant_data_root: str | Path,
    generated_at_utc: datetime,
) -> tuple[dict[str, Any], list[str], list[str]]:
    """Audit every source scorecard row and return eligible selected contracts."""

    root = Path(repo_root)
    inputs = _verify_protocol_inputs(protocol, root)
    scorecard = json.loads(inputs["scorecard"].read_text(encoding="utf-8"))
    snapshot = load_snapshot_v1(inputs["snapshot"])
    decision_intent = load_decision_intent(inputs["decision_intent"])
    load_run_manifest(inputs["source_manifest"])
    snapshot_by_key = {
        (str(signal.underlying_signal.get("symbol", "")), signal.ts_utc.date()): signal
        for signal in snapshot.signals
    }
    intents = {intent.signal_id: intent for intent in decision_intent.intents}
    start = _parse_date(protocol["bounds"]["decision_date_start"], "decision_date_start")
    end = _parse_date(protocol["bounds"]["decision_date_end"], "decision_date_end")
    allowed = _universe(protocol)
    rows: list[dict[str, Any]] = []
    eligible_contracts: list[str] = []

    for index, source in enumerate(scorecard.get("scored", [])):
        symbol = str(source.get("symbol", ""))
        decision_date = _parse_date(source.get("date"), f"scorecard row {index} date")
        exchange, product = _symbol_market(symbol)
        result: dict[str, Any] = {
            "source_row_index": index,
            "symbol": symbol,
            "decision_date": decision_date.isoformat(),
            "exchange": exchange,
            "product": product,
            "eligible": False,
            "exclusion_reason": None,
            "signal_id": None,
            "selected_contract": None,
            "coverage": None,
        }
        if not start <= decision_date <= end:
            result["exclusion_reason"] = "outside_frozen_date_range"
        elif (exchange, product) not in allowed:
            result["exclusion_reason"] = "outside_frozen_universe"
        else:
            signal = snapshot_by_key.get((symbol, decision_date))
            calls = source.get("options_calls") or []
            selected = signal.features_det.get("selected_option_contract") if signal else None
            if not calls:
                result["exclusion_reason"] = "missing_rank1_selected_option_contract"
            elif signal is None or signal.id not in intents:
                result["exclusion_reason"] = "missing_immutable_decision_artifacts"
            elif not selected:
                result["exclusion_reason"] = "missing_rank1_selected_option_contract"
            elif selected != calls[0].get("contract_sym"):
                result["exclusion_reason"] = "rank1_contract_mismatch"
            else:
                explicit = ExplicitContractOptionStore(quant_data_root, [str(selected)])
                contract = explicit.explicit_contract(str(selected))
                assert contract is not None
                bars = _valid_daily_bars(contract.path)
                before = bars[bars["date"] <= decision_date]
                after = bars[bars["date"] > decision_date]
                result.update(
                    {
                        "signal_id": signal.id,
                        "selected_contract": selected,
                        "coverage": {
                            "source": PUBLIC_DATA_ROOT,
                            "file": contract.path.name,
                            "valid_daily_bars": len(bars),
                            "first_date": bars["date"].iloc[0].isoformat()
                            if not bars.empty
                            else None,
                            "last_date": bars["date"].iloc[-1].isoformat()
                            if not bars.empty
                            else None,
                            "bars_on_or_before_decision": len(before),
                            "bars_strictly_after_decision": len(after),
                        },
                    }
                )
                if bars.empty:
                    result["exclusion_reason"] = "selected_contract_missing_or_invalid_daily_bars"
                elif before.empty:
                    result["exclusion_reason"] = "contract_not_evidenced_listed_by_decision"
                elif after.empty:
                    result["exclusion_reason"] = "missing_post_decision_entry_bar"
                else:
                    result["eligible"] = True
                    eligible_contracts.append(str(selected))
        rows.append(result)

    reasons = Counter(
        row["exclusion_reason"] for row in rows if row["exclusion_reason"] is not None
    )
    eligible_ids = [row["signal_id"] for row in rows if row["eligible"]]
    audit = {
        "schema_version": AUDIT_VERSION,
        "protocol_id": protocol["protocol_id"],
        "generated_at_utc": generated_at_utc.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "protocol_path": Path(protocol_path).as_posix(),
        "protocol_sha256": sha256_file(protocol_path),
        "data_source": PUBLIC_DATA_ROOT,
        "bounded_contract_count": len(set(eligible_contracts)),
        "funnel": {
            "source_rows": len(rows),
            "eligible_rows": len(eligible_ids),
            "excluded_rows": len(rows) - len(eligible_ids),
            "exclusions_by_reason": dict(sorted(reasons.items())),
        },
        "eligible_signal_ids": eligible_ids,
        "rows": rows,
        "guardrails": {
            "contract_discovery": "explicit_artifact_selected_contracts_only",
            "raw_directory_glob": False,
            "score_today_rerun": False,
            "contract_reselection": False,
        },
    }
    return audit, sorted(set(eligible_contracts)), eligible_ids


def _policy_sidecar(
    *,
    protocol: dict[str, Any],
    inputs: dict[str, Path],
    quant_data_root: Path,
    eligible_contracts: list[str],
    eligible_signal_ids: list[str],
    source_commit: str,
    generated_at_utc: datetime,
    policy_name: str,
) -> PaFeitianPremiumOutcomeSidecar:
    policy = protocol["policies"][policy_name]
    common = protocol["policies"]["common"]
    snapshot = load_snapshot_v1(inputs["snapshot"])
    intent = load_decision_intent(inputs["decision_intent"])
    manifest = load_run_manifest(inputs["source_manifest"])
    eligible_set = set(eligible_signal_ids)
    filtered_signals = [
        signal
        for signal in snapshot.signals
        if signal.id in eligible_set
    ]
    if len(filtered_signals) != len(eligible_set):
        raise ValueError("eligible signal IDs do not map one-to-one to snapshot signals")
    snapshot = snapshot.model_copy(update={"signals": filtered_signals})
    declared = generated_at_utc
    traversal = generated_at_utc + timedelta(seconds=1)
    config = PremiumOutcomeHarnessConfig(
        source_commit=source_commit,
        generated_at_utc=generated_at_utc,
        policy_declared_at_utc=declared,
        traversal_started_at_utc=traversal,
        policy_id=policy["policy_id"],
        policy_version=("v1.default" if policy_name == "baseline" else "v1.m6_hist_001"),
        slippage_ticks=float(common["slippage_ticks"]),
        stop_fraction_of_entry=float(policy["stop_fraction_of_entry"]),
        target_multiples_of_entry=tuple(common["target_multiples_of_entry"]),
        max_holding_bars=int(common["maximum_holding_daily_bars"]),
        cli_args=(
            "src/scripts/build_pa_feitian_historical_cohort.py",
            f"--protocol={protocol['protocol_id']}",
            f"--policy={policy_name}",
            f"--quant-data-root={PUBLIC_DATA_ROOT}",
        ),
        recorded_quant_data_root=PUBLIC_DATA_ROOT,
    )
    return build_premium_outcome_sidecar(
        snapshot=snapshot,
        decision_intent=intent,
        source_manifest=manifest,
        input_paths=HarnessInputPaths(
            source_manifest_path=protocol["inputs"]["source_manifest"]["path"],
            snapshot_path=protocol["inputs"]["snapshot"]["path"],
            decision_intent_path=protocol["inputs"]["decision_intent"]["path"],
        ),
        quant_data_root=quant_data_root,
        config=config,
        store=ExplicitContractOptionStore(quant_data_root, eligible_contracts),
    )


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def build_research_report(
    *,
    protocol: dict[str, Any],
    protocol_path: Path,
    coverage_audit: dict[str, Any],
    coverage_audit_path: Path,
    baseline: PaFeitianPremiumOutcomeSidecar,
    baseline_path: Path,
    candidate: PaFeitianPremiumOutcomeSidecar,
    candidate_path: Path,
    generated_at_utc: datetime,
) -> dict[str, Any]:
    baseline_by_signal = {row.source_signal_id: row for row in baseline.outcomes}
    candidate_by_signal = {row.source_signal_id: row for row in candidate.outcomes}
    if set(baseline_by_signal) != set(candidate_by_signal):
        raise ValueError("baseline and candidate must use identical eligible signal IDs")
    paired: list[dict[str, Any]] = []
    comparable_differences: list[float] = []
    baseline_r: list[float] = []
    candidate_r: list[float] = []
    grouped_values: dict[str, list[float]] = {}
    oos_values: dict[str, list[float]] = {
        window["id"]: [] for window in protocol["bounds"].get("oos_windows", [])
    }
    for signal_id in sorted(baseline_by_signal):
        base = baseline_by_signal[signal_id]
        cand = candidate_by_signal[signal_id]
        base_contract = base.selected_contract.contract_symbol if base.selected_contract else None
        cand_contract = cand.selected_contract.contract_symbol if cand.selected_contract else None
        if base_contract != cand_contract:
            raise ValueError(f"policy contract mismatch for {signal_id}")
        base_value = base.premium_metrics.premium_r if base.premium_metrics else None
        cand_value = cand.premium_metrics.premium_r if cand.premium_metrics else None
        difference = None
        if base_value is not None and cand_value is not None:
            difference = cand_value - base_value
            baseline_r.append(base_value)
            candidate_r.append(cand_value)
            comparable_differences.append(difference)
            product = "unknown"
            if base.selected_contract is not None:
                product = base.selected_contract.product
            grouped_values.setdefault(product, []).append(difference)
            decision_date = base.decision_ts_utc.date()
            for window in protocol["bounds"].get("oos_windows", []):
                if (
                    _parse_date(window["decision_date_start"], "OOS window start")
                    <= decision_date
                    <= _parse_date(window["decision_date_end"], "OOS window end")
                ):
                    oos_values[window["id"]].append(difference)
        paired.append(
            {
                "signal_id": signal_id,
                "decision_ts_utc": base.decision_ts_utc.isoformat().replace("+00:00", "Z"),
                "contract": base_contract,
                "baseline_status": base.evaluation_status,
                "candidate_status": cand.evaluation_status,
                "baseline_exit_reason": base.exit_reason,
                "candidate_exit_reason": cand.exit_reason,
                "baseline_premium_r": base_value,
                "candidate_premium_r": cand_value,
                "candidate_minus_baseline_premium_r": difference,
            }
        )
    thresholds = protocol["sample_thresholds"]
    comparable_n = len(comparable_differences)
    inference_met = comparable_n >= thresholds["pooled_inference_minimum"]
    grouped_met = bool(grouped_values) and all(
        len(values) >= thresholds["grouped_result_minimum_per_group"]
        for values in grouped_values.values()
    )
    oos_met = (
        len(oos_values) >= thresholds["oos_minimum_windows"]
        and all(
            len(values) >= thresholds["oos_minimum_events_per_window"]
            for values in oos_values.values()
        )
    )
    gate = (
        "research_thresholds_met"
        if inference_met
        and grouped_met
        and oos_met
        and comparable_n >= thresholds["screening_minimum_effective_events"]
        else "insufficient_sample"
    )
    return {
        "schema_version": REPORT_VERSION,
        "protocol_id": protocol["protocol_id"],
        "generated_at_utc": generated_at_utc.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "research_mode": protocol["research_mode"],
        "research_interpretation": {
            "evaluated_track": protocol["interpretation"]["evaluated_track"],
            "faithful_hypothesis_track": protocol["interpretation"][
                "faithful_hypothesis_track"
            ],
            "upstream_research": protocol["upstream_research"],
            "independently_reproduced_here": [
                "bounded explicit-contract coverage for the four pinned M4 decisions",
                "legacy M5 integration-control replay for 50% and 30% premium stops on identical events",
                "insufficient-sample suppression of grouped, OOS, strategy, and M7 conclusions",
            ],
            "prior_evidence_not_reproduced_here": [
                "faithful delta/DTE selection effects",
                "causal IV-rank or low-IV/range regime effects",
                "runner superiority over fixed targets",
                "DD-line structural-stop behavior or bid/ask-aware tight-stop execution",
            ],
            "upstream_performance_metrics_imported": False,
        },
        "artifact_hashes": {
            "protocol": sha256_file(protocol_path),
            "coverage_audit": sha256_file(coverage_audit_path),
            "baseline_premium_outcome": sha256_file(baseline_path),
            "candidate_premium_outcome": sha256_file(candidate_path),
        },
        "coverage_funnel": coverage_audit["funnel"],
        "policy_status_counts": {
            "baseline": dict(sorted(Counter(row.evaluation_status for row in baseline.outcomes).items())),
            "candidate": dict(sorted(Counter(row.evaluation_status for row in candidate.outcomes).items())),
        },
        "paired_events": paired,
        "pooled_descriptive": {
            "comparable_event_count": comparable_n,
            "baseline_mean_premium_r": _mean(baseline_r),
            "candidate_mean_premium_r": _mean(candidate_r),
            "mean_paired_difference": _mean(comparable_differences),
            "median_paired_difference": statistics.median(comparable_differences)
            if comparable_differences
            else None,
            "baseline_win_rate_r_gt_zero": _mean([float(value > 0) for value in baseline_r]),
            "candidate_win_rate_r_gt_zero": _mean([float(value > 0) for value in candidate_r]),
            "inferential_use_allowed": inference_met,
        },
        "threshold_gates": {
            "sample_thresholds": thresholds,
            "grouped_results": {
                "emitted": grouped_met,
                "reason": None if grouped_met else "grouped_result_minimum_not_met",
                "sample_counts": {
                    group: len(values) for group, values in sorted(grouped_values.items())
                },
                "results": (
                    {
                        group: {
                            "paired_event_count": len(values),
                            "mean_paired_difference": _mean(values),
                            "median_paired_difference": statistics.median(values),
                        }
                        for group, values in sorted(grouped_values.items())
                    }
                    if grouped_met
                    else None
                ),
            },
            "oos_results": {
                "emitted": oos_met,
                "reason": None if oos_met else "oos_window_sample_minimum_not_met",
                "window_sample_counts": {
                    window: len(values) for window, values in oos_values.items()
                },
                "results": (
                    {
                        window: {
                            "paired_event_count": len(values),
                            "mean_paired_difference": _mean(values),
                        }
                        for window, values in oos_values.items()
                    }
                    if oos_met
                    else None
                ),
            },
            "screening": {
                "classification": gate,
                "strategy_inference_allowed": gate != "insufficient_sample",
                "advance_m7": False,
            },
        },
        "limitations": [
            "Only one immutable historical score_today artifact is available; this gate cannot construct a broader calendar cohort without a separately produced no-lookahead artifact series.",
            "score_today currently filters relative to date.today() and scans full loaded series, so it is not used as a historical as-of replay engine here.",
            "Daily option OHLC cannot identify intraday event ordering or executable bid/ask fills.",
            "The candidate is retrospective exploratory evidence and cannot mutate decision intent, production policy, or execution permission.",
            "Both evaluated policies are legacy M5 integration controls, not faithful Feitian hypotheses; this packet does not test or refute the faithful track.",
            "Grouped and OOS results are suppressed unless their frozen sample thresholds are met.",
        ],
        "guardrails": {
            "artifact_driven_only": True,
            "bounded_explicit_contract_reads": True,
            "identical_policy_event_ids": True,
            "decision_intent_mutated": False,
            "live_trading_or_execution": False,
            "m7_work": False,
        },
    }


def run_historical_cohort(
    *,
    protocol_path: str | Path,
    repo_root: str | Path,
    quant_data_root: str | Path,
    audit_out: str | Path,
    baseline_out: str | Path,
    candidate_out: str | Path,
    report_out: str | Path,
    generated_at_utc: datetime,
    source_commit: str,
) -> dict[str, Any]:
    protocol_path = Path(protocol_path)
    root = Path(repo_root)
    protocol = load_frozen_protocol(protocol_path)
    inputs = _verify_protocol_inputs(protocol, root)
    audit, contracts, eligible_signal_ids = build_coverage_audit(
        protocol=protocol,
        protocol_path=protocol_path,
        repo_root=root,
        quant_data_root=quant_data_root,
        generated_at_utc=generated_at_utc,
    )
    audit_path = Path(audit_out)
    _write_json(audit, audit_path)
    baseline = _policy_sidecar(
        protocol=protocol,
        inputs=inputs,
        quant_data_root=Path(quant_data_root),
        eligible_contracts=contracts,
        eligible_signal_ids=eligible_signal_ids,
        source_commit=source_commit,
        generated_at_utc=generated_at_utc,
        policy_name="baseline",
    )
    candidate = _policy_sidecar(
        protocol=protocol,
        inputs=inputs,
        quant_data_root=Path(quant_data_root),
        eligible_contracts=contracts,
        eligible_signal_ids=eligible_signal_ids,
        source_commit=source_commit,
        generated_at_utc=generated_at_utc,
        policy_name="candidate",
    )
    baseline_path = Path(baseline_out)
    candidate_path = Path(candidate_out)
    write_premium_outcome(baseline, baseline_path)
    write_premium_outcome(candidate, candidate_path)
    report = build_research_report(
        protocol=protocol,
        protocol_path=protocol_path,
        coverage_audit=audit,
        coverage_audit_path=audit_path,
        baseline=baseline,
        baseline_path=baseline_path,
        candidate=candidate,
        candidate_path=candidate_path,
        generated_at_utc=generated_at_utc,
    )
    _write_json(report, report_out)
    return report
