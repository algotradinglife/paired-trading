"""Materialize explicit, finalized-vintage PA alerts from a bound corpus.

Only literal ``PASignal`` emissions from the frozen ``PABottomDetector`` are
alerts.  The descriptive diagnostics carried beside each daily bar are never
read by this module.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from engine.divergence.pa_detector import PABottomDetector
from engine.pa_feitian.manifest import sha256_file
from engine.pa_feitian.underlying_corpus import LEVELS
from engine.pa_feitian.underlying_corpus import load_contract as load_underlying_contract
from engine.pa_feitian.underlying_corpus import validate_corpus


CONTRACT_VERSION = "pa_feitian_m6_explicit_pa_alert_materialization_contract_v1"
ARTIFACT_VERSION = "pa_feitian_m6_explicit_pa_alert_corpus_v1"
TASK_ID = "t_1bf2484e"
RULE_ID = "pa_h2_bottom_daily_au_ag_v1"
PRODUCTS = ("au", "ag")
_STRATEGY_REVISION = "792cb9a0c47cd6cb20c5da4340008481e7a7bd1f"
_SOURCE_BINDINGS = (
    (
        "src/engine/divergence/pa_detector.py",
        "sha256:9e234a39c4f3eb7239066460ad8d0ccb28d3bb06bfd9e82b9af4792d0b004717",
        "797f8b9e8a62e3d24e3907703993b2ec6c4e92ee",
    ),
    (
        "src/engine/features/pa_features.py",
        "sha256:e9af8e9ddd9e3e36f28ecbf2ce995d487395d779cf99edda21c4d260b07b3585",
        "d36be8eec177faff9471ba1521a2b58693ffe8a8",
    ),
)
_INPUT_PATH = "doc/repro/pa-feitian-m6-underlying-corpus-2026-07-12/underlying_signal_corpus_v1.json"
_INPUT_SHA = "sha256:cb3407910dd15f4327a2465da3a00d6797f81fd9124066695887ddb53d3bf080"
_UNDERLYING_CONTRACT_PATH = "docs/research/pa-feitian-m6-underlying-corpus-contract-v1.json"
_UNDERLYING_CONTRACT_SHA = "sha256:e35d4567792a386270989b47af31d4e2e23d76b632eff92cabc6188f8ba37c34"
_ALERT_FIELDS = {
    "alert_id",
    "strategy_rule_id",
    "source_record_id",
    "product",
    "trading_date",
    "decision_ts_utc",
    "bar_timestamp_utc",
    "cadence",
    "pattern",
    "pa_direction",
    "strategy_direction",
}
_FORBIDDEN_KEYS = {
    "option",
    "premium",
    "contract_symbol",
    "delta",
    "greeks",
    "dte",
    "expiry",
    "bid",
    "ask",
    "modeled_price",
    "dd_line",
    "feitian_confirmation",
    "outcome",
    "performance",
    "pnl",
    "win_rate",
    "execution",
}


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def load_materialization_contract(path: str | Path) -> dict[str, Any]:
    contract = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_materialization_contract(contract)
    return contract


def validate_materialization_contract(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != CONTRACT_VERSION:
        raise ValueError("unsupported explicit PA alert contract")
    if contract.get("hermes_task") != TASK_ID:
        raise ValueError("wrong Hermes task")
    if contract.get("frozen_before_historical_scan") is not True:
        raise ValueError("contract was not frozen before historical scan")
    if contract.get("research_mode") != "retrospective_finalized":
        raise ValueError("research mode must remain retrospective_finalized")
    strategy = contract.get("authoritative_strategy", {})
    if (
        strategy.get("revision") != _STRATEGY_REVISION
        or strategy.get("rule_identifier") != RULE_ID
        or strategy.get("strategy_class")
        != "engine.divergence.pa_detector.PABottomDetector"
        or strategy.get("emitted_type") != "engine.divergence.pa_detector.PASignal"
        or strategy.get("constructor")
        != {
            "min_h_legs": 2,
            "min_quality": 0.3,
            "ema_threshold": 0.0,
            "min_gap": 10,
            "h_lookback": 8,
            "require_climax": False,
            "climax_lookback": 5,
            "climax_threshold": 0.4,
            "require_trend": None,
        }
        or strategy.get("scan_arguments")
        != {
            "bars": "ordered daily OHLCV assembled only from bound corpus records",
            "h_bars": None,
            "swing_context": None,
        }
    ):
        raise ValueError("authoritative strategy definition drifted")
    if [
        (row.get("path"), row.get("sha256"), row.get("git_blob"))
        for row in strategy.get("source_files", [])
    ] != list(_SOURCE_BINDINGS):
        raise ValueError("authoritative source bindings drifted")
    binding = contract.get("input_binding", {})
    if (
        binding.get("path") != _INPUT_PATH
        or binding.get("sha256") != _INPUT_SHA
        or binding.get("schema_version")
        != "pa_feitian_m6_underlying_signal_corpus_v1"
        or binding.get("required_research_mode") != "retrospective_finalized"
        or binding.get("contract", {}).get("path") != _UNDERLYING_CONTRACT_PATH
        or binding.get("contract", {}).get("sha256") != _UNDERLYING_CONTRACT_SHA
    ):
        raise ValueError("input binding drifted")
    universe = contract.get("universe_and_cadence", {})
    if (
        universe.get("products") != list(PRODUCTS)
        or universe.get("cadence") != "D"
        or universe.get("decision_time_utc") != "07:00:00Z"
    ):
        raise ValueError("universe or cadence drifted")
    identity = contract.get("alert_identity_and_direction", {})
    if (
        identity.get("strategy_rule_id") != RULE_ID
        or identity.get("pattern") != "h2_bottom"
        or identity.get("pa_direction") != "bottom"
        or identity.get("strategy_direction") != "long"
    ):
        raise ValueError("alert identity or direction drifted")
    output = contract.get("output_contract", {})
    if (
        output.get("schema_version") != ARTIFACT_VERSION
        or set(output.get("alert_fields", [])) != _ALERT_FIELDS
        or output.get("diagnostic_fields") is not False
        or output.get("performance_fields") is not False
        or output.get("public_safe") is not True
    ):
        raise ValueError("output boundary drifted")
    guards = contract.get("guardrails", {})
    required_true = {
        "explicit_strategy_emission_only",
        "strict_decision_time_cutoff",
        "retrospective_finalized_label_preserved",
        "deterministic_rerun_required",
        "future_row_invariance_required",
    }
    required_false = {
        "diagnostic_inference",
        "proxy_or_imputation",
        "option_or_premium_path_reading",
        "contract_membership",
        "feitian_or_dd_line_confirmation",
        "greeks_or_delta",
        "expiry_or_dte",
        "bid_or_ask",
        "modeled_prices",
        "outcomes_or_performance",
        "threshold_tuning",
        "m7",
        "m8",
        "execution",
    }
    if any(guards.get(key) is not True for key in required_true) or any(
        guards.get(key) is not False for key in required_false
    ):
        raise ValueError("guardrails were weakened")


def _verify_sha(path: Path, expected: str, label: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f"{label} hash mismatch: expected {expected}, got {actual}")


def verify_bound_files(*, repo_root: Path, contract: dict[str, Any]) -> None:
    binding = contract["input_binding"]
    _verify_sha(repo_root / binding["path"], binding["sha256"], "input corpus")
    _verify_sha(
        repo_root / binding["contract"]["path"],
        binding["contract"]["sha256"],
        "underlying corpus contract",
    )
    for source in contract["authoritative_strategy"]["source_files"]:
        _verify_sha(repo_root / source["path"], source["sha256"], source["path"])


def _timestamp(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return ts.tz_convert("UTC")


def _iso_utc(value: Any) -> str:
    return _timestamp(value).isoformat().replace("+00:00", "Z")


def _nested_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _nested_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _nested_keys(item)}
    return set()


def extract_daily_bars(
    corpus: dict[str, Any], *, contract: dict[str, Any]
) -> dict[str, tuple[pd.DataFrame, list[dict[str, Any]]]]:
    """Extract only bound daily OHLCV fields; never inspect diagnostics."""

    if corpus.get("schema_version") != contract["input_binding"]["schema_version"]:
        raise ValueError("input corpus schema drifted")
    if corpus.get("research_mode") != "retrospective_finalized":
        raise ValueError("input corpus is not retrospective_finalized")
    start = contract["universe_and_cadence"]["first_trading_date"]
    end = contract["universe_and_cadence"]["last_trading_date"]
    rows: dict[str, list[dict[str, Any]]] = {product: [] for product in PRODUCTS}
    refs: dict[str, list[dict[str, Any]]] = {product: [] for product in PRODUCTS}
    seen: set[tuple[str, str]] = set()
    previous_by_product: dict[str, pd.Timestamp] = {}
    for record in corpus.get("records", []):
        product = record.get("product")
        if product not in rows:
            raise ValueError("input record contains a product outside the frozen universe")
        decision = _timestamp(record.get("decision_ts_utc"))
        decision_iso = _iso_utc(decision)
        key = (product, decision_iso)
        if key in seen:
            raise ValueError("duplicate product/decision key")
        seen.add(key)
        if product in previous_by_product and decision <= previous_by_product[product]:
            raise ValueError("non-monotonic product/decision key")
        previous_by_product[product] = decision
        trading_date = str(record.get("trading_date"))
        if not start <= trading_date <= end:
            raise ValueError("record lies outside the frozen date range")
        if decision.hour != 7 or decision.minute or decision.second:
            raise ValueError("decision timestamp is outside the frozen cadence")
        if trading_date != decision.date().isoformat():
            raise ValueError("trading date does not match decision timestamp")
        if _timestamp(record.get("max_source_timestamp_utc")) > decision:
            raise ValueError("post-cutoff source row")
        daily = record["levels"]["D"]
        bar_timestamp = _timestamp(daily["last_bar_timestamp_utc"])
        if bar_timestamp > decision:
            raise ValueError("post-cutoff daily bar")
        bar = daily["bar"]
        numeric = {name: float(bar[name]) for name in ("open", "high", "low", "close", "volume")}
        if not all(math.isfinite(value) for value in numeric.values()):
            raise ValueError("non-finite OHLCV")
        if (
            numeric["high"] < max(numeric["open"], numeric["low"], numeric["close"])
            or numeric["low"] > min(numeric["open"], numeric["high"], numeric["close"])
            or numeric["volume"] < 0
        ):
            raise ValueError("invalid OHLCV")
        rows[product].append({"timestamp": bar_timestamp, **numeric})
        refs[product].append(
            {
                "source_record_id": record["record_id"],
                "trading_date": trading_date,
                "decision_ts_utc": decision_iso,
                "bar_timestamp_utc": _iso_utc(bar_timestamp),
            }
        )
    return {
        product: (pd.DataFrame(rows[product]), refs[product]) for product in PRODUCTS
    }


def scan_explicit_alerts(
    extracted: dict[str, tuple[pd.DataFrame, list[dict[str, Any]]]],
    *,
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    params = contract["authoritative_strategy"]["constructor"]
    detector = PABottomDetector(**params)
    alerts: list[dict[str, Any]] = []
    for product in PRODUCTS:
        bars, refs = extracted[product]
        if len(bars) < 31:
            continue
        for signal in detector.scan(bars, h_bars=None, swing_context=None):
            if signal.pattern != "h2_bottom" or signal.direction != "long":
                raise ValueError("authoritative strategy emitted an unsupported alert")
            ref = refs[signal.bar_idx]
            if _iso_utc(signal.timestamp) != ref["bar_timestamp_utc"]:
                raise ValueError("strategy alert timestamp drifted from its source bar")
            compact = (
                datetime.fromisoformat(ref["decision_ts_utc"].replace("Z", "+00:00"))
                .astimezone(UTC)
                .strftime("%Y%m%dT%H%M%SZ")
            )
            alerts.append(
                {
                    "alert_id": f"pa_h2_bottom_daily_v1:{product}:{compact}",
                    "strategy_rule_id": RULE_ID,
                    "source_record_id": ref["source_record_id"],
                    "product": product,
                    "trading_date": ref["trading_date"],
                    "decision_ts_utc": ref["decision_ts_utc"],
                    "bar_timestamp_utc": ref["bar_timestamp_utc"],
                    "cadence": "D",
                    "pattern": signal.pattern,
                    "pa_direction": "bottom",
                    "strategy_direction": signal.direction,
                }
            )
    alerts.sort(key=lambda row: (row["decision_ts_utc"], row["product"], row["alert_id"]))
    if len({row["alert_id"] for row in alerts}) != len(alerts):
        raise ValueError("duplicate alert identity")
    return alerts


def build_alert_corpus(
    *,
    contract: dict[str, Any],
    contract_path: Path,
    corpus: dict[str, Any],
    corpus_path: Path,
    underlying_contract: dict[str, Any],
) -> dict[str, Any]:
    validate_materialization_contract(contract)
    # The committed JSON uses canonical sort_keys encoding, while the upstream
    # validator also asserts the builder's semantic level order. Restore that
    # order in a validation-only view without changing or reserializing input.
    validation_view = {
        **corpus,
        "records": [
            {
                **record,
                "levels": {level: record["levels"][level] for level in LEVELS},
            }
            for record in corpus.get("records", [])
        ],
    }
    validate_corpus(validation_view, contract=underlying_contract)
    extracted = extract_daily_bars(corpus, contract=contract)
    alerts = scan_explicit_alerts(extracted, contract=contract)
    input_counts = {product: len(extracted[product][0]) for product in PRODUCTS}
    alert_counts = Counter(row["product"] for row in alerts)
    artifact = {
        "schema_version": ARTIFACT_VERSION,
        "hermes_task": TASK_ID,
        "research_mode": "retrospective_finalized",
        "contract": {"path": contract_path.as_posix(), "sha256": sha256_file(contract_path)},
        "input": {
            "path": corpus_path.as_posix(),
            "sha256": sha256_file(corpus_path),
            "schema_version": corpus["schema_version"],
        },
        "strategy": {
            "rule_identifier": RULE_ID,
            "repository_revision": contract["authoritative_strategy"]["revision"],
            "source_files": contract["authoritative_strategy"]["source_files"],
            "constructor": contract["authoritative_strategy"]["constructor"],
        },
        "guardrails": contract["guardrails"],
        "limitations": contract["limitations"],
        "coverage": {
            "input_records": sum(input_counts.values()),
            "input_records_by_product": input_counts,
            "alerts": len(alerts),
            "alerts_by_product": {product: alert_counts[product] for product in PRODUCTS},
            "cadence": "D",
            "first_trading_date": contract["universe_and_cadence"]["first_trading_date"],
            "last_trading_date": contract["universe_and_cadence"]["last_trading_date"],
        },
        "alerts": alerts,
    }
    validate_alert_corpus(artifact, contract=contract)
    return artifact


def validate_alert_corpus(artifact: dict[str, Any], *, contract: dict[str, Any]) -> None:
    validate_materialization_contract(contract)
    if set(artifact) != set(contract["output_contract"]["top_level_fields"]):
        raise ValueError("artifact top-level fields drifted")
    if artifact.get("schema_version") != ARTIFACT_VERSION:
        raise ValueError("unsupported explicit PA alert artifact")
    if artifact.get("hermes_task") != TASK_ID:
        raise ValueError("wrong artifact Hermes task")
    if artifact.get("research_mode") != "retrospective_finalized":
        raise ValueError("artifact lost retrospective_finalized label")
    if artifact.get("guardrails") != contract["guardrails"]:
        raise ValueError("artifact guardrails drifted")
    if artifact.get("limitations") != contract["limitations"]:
        raise ValueError("artifact limitations drifted")
    alerts = artifact.get("alerts", [])
    previous: tuple[str, str, str] | None = None
    identities: set[str] = set()
    for alert in alerts:
        if set(alert) != _ALERT_FIELDS:
            raise ValueError("alert fields drifted")
        if _nested_keys(alert) & _FORBIDDEN_KEYS:
            raise ValueError("alert crossed the bare-K or performance boundary")
        if (
            alert["strategy_rule_id"] != RULE_ID
            or alert["product"] not in PRODUCTS
            or alert["cadence"] != "D"
            or alert["pattern"] != "h2_bottom"
            or alert["pa_direction"] != "bottom"
            or alert["strategy_direction"] != "long"
        ):
            raise ValueError("alert identity or direction drifted")
        if _timestamp(alert["bar_timestamp_utc"]) > _timestamp(alert["decision_ts_utc"]):
            raise ValueError("alert contains a post-cutoff bar")
        expected_id = "pa_h2_bottom_daily_v1:{}:{}".format(
            alert["product"],
            _timestamp(alert["decision_ts_utc"]).strftime("%Y%m%dT%H%M%SZ"),
        )
        if alert["alert_id"] != expected_id or expected_id in identities:
            raise ValueError("duplicate or malformed alert identity")
        identities.add(expected_id)
        order = (alert["decision_ts_utc"], alert["product"], alert["alert_id"])
        if previous is not None and order < previous:
            raise ValueError("alerts are not deterministically ordered")
        previous = order
    coverage = artifact.get("coverage", {})
    if coverage.get("alerts") != len(alerts) or coverage.get("alerts_by_product") != {
        product: sum(row["product"] == product for row in alerts) for product in PRODUCTS
    }:
        raise ValueError("alert coverage mismatch")


def build_from_bound_files(*, repo_root: Path, contract_path: Path) -> dict[str, Any]:
    contract = load_materialization_contract(contract_path)
    verify_bound_files(repo_root=repo_root, contract=contract)
    corpus_path = repo_root / contract["input_binding"]["path"]
    underlying_contract_path = repo_root / contract["input_binding"]["contract"]["path"]
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    underlying_contract = load_underlying_contract(underlying_contract_path)
    return build_alert_corpus(
        contract=contract,
        contract_path=contract_path.relative_to(repo_root),
        corpus=corpus,
        corpus_path=corpus_path.relative_to(repo_root),
        underlying_contract=underlying_contract,
    )


def artifact_sha256(value: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical_json_bytes(value)).hexdigest()}"
