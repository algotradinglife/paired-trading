"""Frozen causal premium-K response matrix for M6 exploratory research."""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from engine.pa_feitian.swing_induction import PRODUCTS
from engine.pa_feitian.swing_induction import SourceSeries
from engine.pa_feitian.swing_induction import canonical_json_bytes
from engine.pa_feitian.swing_induction import discover_option_daily_files
from engine.pa_feitian.swing_induction import inventory_digest
from engine.pa_feitian.swing_induction import select_coverage_qualified_series
from engine.pa_feitian.swing_line_induction import classify_prefix


PROTOCOL_VERSION = "pa_feitian_m6_premium_k_response_protocol_v1"
ATLAS_VERSION = "pa_feitian_m6_premium_k_response_atlas_v1"
SERIES_PER_PRODUCT = 4
MINIMUM_HISTORY_BARS = 21
HORIZONS = (1, 3, 5)
MINIMUM_OBSERVATIONS = 20
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 7179
_MAPPING = {
    "long_left_touch": 1,
    "long_right_break": 1,
    "short_left_touch": -1,
    "short_right_break": -1,
    "long_invalidation": -1,
    "short_invalidation": 1,
}
_FORBIDDEN_PUBLIC_KEYS = {
    "open",
    "high",
    "low",
    "close",
    "raw_bar",
    "price",
    "chart",
    "anchor",
    "projection",
    "tolerance",
    "return",
    "response",
    "pnl",
    "premium_r",
    "contract",
    "filename",
    "bid",
    "ask",
    "delta",
    "greeks",
    "dte",
    "execution",
}


@dataclass(frozen=True)
class _Observation:
    series_identity: str
    label: str
    horizon: int
    split: str
    signed_change: float


def canonical_json(value: Any) -> bytes:
    return canonical_json_bytes(value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _split(trading_date: date) -> str | None:
    if trading_date <= date(2025, 12, 31):
        return "training"
    if date(2026, 1, 1) <= trading_date <= date(2026, 6, 30):
        return "holdout"
    return None


def _assert_public_safe(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = set(value) & _FORBIDDEN_PUBLIC_KEYS
        if forbidden:
            raise ValueError(f"public artifact contains forbidden fields: {sorted(forbidden)}")
        for nested in value.values():
            _assert_public_safe(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_public_safe(nested)


def _quantile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("quantile requires observations")
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _bootstrap_ci(observations: list[_Observation]) -> tuple[float | None, float | None]:
    if not observations:
        return None, None
    by_series: dict[str, list[float]] = defaultdict(list)
    for item in observations:
        by_series[item.series_identity].append(item.signed_change)
    identities = sorted(by_series)
    rng = random.Random(BOOTSTRAP_SEED)
    means: list[float] = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sample: list[float] = []
        for _ in identities:
            sample.extend(by_series[rng.choice(identities)])
        means.append(sum(sample) / len(sample))
    return _quantile(means, 0.025), _quantile(means, 0.975)


def _summary(observations: list[_Observation], *, label: str, horizon: int) -> dict[str, Any]:
    values = [item.signed_change for item in observations]
    if not values:
        return {
            "structural_label": label,
            "horizon_completed_daily_bars": horizon,
            "observation_count": 0,
            "mean_signed_change": None,
            "median_signed_change": None,
            "positive_signed_change_rate": None,
            "clustered_bootstrap_mean_ci_95": {"lower": None, "upper": None},
        }
    lower, upper = _bootstrap_ci(observations)
    return {
        "structural_label": label,
        "horizon_completed_daily_bars": horizon,
        "observation_count": len(values),
        "mean_signed_change": round(sum(values) / len(values), 10),
        "median_signed_change": round(median(values), 10),
        "positive_signed_change_rate": round(sum(value > 0 for value in values) / len(values), 10),
        "clustered_bootstrap_mean_ci_95": {
            "lower": round(lower, 10) if lower is not None else None,
            "upper": round(upper, 10) if upper is not None else None,
        },
    }


def _is_training_candidate(summary: dict[str, Any]) -> bool:
    lower = summary["clustered_bootstrap_mean_ci_95"]["lower"]
    return (
        summary["observation_count"] >= MINIMUM_OBSERVATIONS
        and summary["mean_signed_change"] is not None
        and summary["mean_signed_change"] > 0
        and summary["median_signed_change"] > 0
        and lower is not None
        and lower >= 0
    )


def _bindings(protocol: dict[str, Any], repo_root: Path) -> None:
    if protocol.get("schema_version") != PROTOCOL_VERSION:
        raise ValueError("unsupported premium K response protocol")
    for family in ("m6_exp_011", "m6_exp_012"):
        for name in ("protocol", "atlas"):
            binding = protocol.get("read_only_bindings", {}).get(family, {}).get(name, {})
            path = binding.get("path")
            expected = binding.get("sha256")
            if not isinstance(path, str) or not isinstance(expected, str):
                raise ValueError(f"missing {family} {name} binding")
            if sha256_file(repo_root / path) != expected:
                raise ValueError(f"{family} {name} binding hash mismatch")


def _observations(series: Iterable[SourceSeries]) -> list[_Observation]:
    output: list[_Observation] = []
    for item in sorted(series, key=lambda value: (value.product, value.public_file_alias)):
        for index in range(MINIMUM_HISTORY_BARS - 1, len(item.bars)):
            decision = item.bars[index]
            split = _split(decision.trading_date)
            if split is None or decision.close <= 0:
                continue
            classification = classify_prefix(item.bars[: index + 1])
            label = classification["global_label"]
            sign = _MAPPING.get(label)
            if sign is None:
                continue
            for horizon in HORIZONS:
                future_index = index + horizon
                if future_index >= len(item.bars):
                    continue
                future = item.bars[future_index]
                if _split(future.trading_date) != split or future.close <= 0:
                    continue
                output.append(
                    _Observation(
                        series_identity=item.public_file_alias,
                        label=label,
                        horizon=horizon,
                        split=split,
                        signed_change=sign * (future.close / decision.close - 1.0),
                    )
                )
    return output


def build_response_atlas(
    series: Iterable[SourceSeries],
    *,
    protocol_sha256: str,
    source_inventory_digest: str,
    files_scanned_by_product: dict[str, int],
) -> dict[str, Any]:
    ordered = tuple(sorted(series, key=lambda value: (value.product, value.public_file_alias)))
    if {item.product for item in ordered} != set(PRODUCTS):
        raise ValueError("both AU and AG source series are required")
    if any(sum(item.product == product for item in ordered) != SERIES_PER_PRODUCT for product in PRODUCTS):
        raise ValueError("source selection drifted")
    observations = _observations(ordered)
    grouped: dict[tuple[str, str, int], list[_Observation]] = defaultdict(list)
    for item in observations:
        grouped[(item.split, item.label, item.horizon)].append(item)
    training = [
        _summary(grouped[("training", label, horizon)], label=label, horizon=horizon)
        for label in sorted(_MAPPING)
        for horizon in HORIZONS
    ]
    candidates = [
        {"structural_label": row["structural_label"], "horizon_completed_daily_bars": row["horizon_completed_daily_bars"]}
        for row in training
        if _is_training_candidate(row)
    ]
    holdout = [
        _summary(
            grouped[
                (
                    "holdout",
                    item["structural_label"],
                    item["horizon_completed_daily_bars"],
                )
            ],
            label=item["structural_label"],
            horizon=item["horizon_completed_daily_bars"],
        )
        for item in candidates
    ]
    artifact = {
        "schema_version": ATLAS_VERSION,
        "study_labels": ["empirical", "exploratory", "non-authentic", "non-executable"],
        "protocol": {
            "path": "docs/research/pa-feitian-m6-premium-k-response-protocol-v1.json",
            "sha256": protocol_sha256,
        },
        "source_inventory": {
            "public_source_alias": "external://quant-data/daily/SHFE.au-ag-option-ohlc",
            "discovery_inventory_digest": source_inventory_digest,
            "selected_series_by_product": {product: SERIES_PER_PRODUCT for product in PRODUCTS},
            "files_scanned_by_product": files_scanned_by_product,
        },
        "response_definition": {
            "label_mapping": {label: "upward" if sign > 0 else "downward" for label, sign in sorted(_MAPPING.items())},
            "horizons_completed_daily_bars": list(HORIZONS),
            "response_unit": "signed_close_to_close_change",
            "controls": ["abstain", "conflict"],
        },
        "training_response_matrix": training,
        "training_candidate_freeze": {
            "minimum_observations": MINIMUM_OBSERVATIONS,
            "candidate_set": candidates,
            "candidate_set_sha256": sha256_json(candidates),
            "frozen_before_holdout_application": True,
        },
        "holdout_application": {
            "status": "applied_once" if candidates else "not_applied_no_training_candidates",
            "candidate_response_matrix": holdout,
            "candidate_count": len(candidates),
        },
        "limitations": [
            "This is a daily bare-option K-line response study, not an authentic Feitian reconstruction.",
            "Aggregate signed changes are not PnL, premium R, a trading signal, a recommendation, or execution evidence.",
            "The fixed label mapping is empirical and its holdout result cannot change the frozen proxy definition.",
        ],
    }
    _assert_public_safe(artifact)
    return artifact


def build_from_data_root(*, repo_root: Path, data_root: Path, protocol_path: Path) -> dict[str, Any]:
    protocol = load_json(protocol_path)
    _bindings(protocol, repo_root)
    discovered = discover_option_daily_files(data_root)
    series, scanned = select_coverage_qualified_series(discovered, max_series_per_product=SERIES_PER_PRODUCT)
    actual_digest = inventory_digest(discovered)
    expected_digest = protocol.get("source_boundary", {}).get("source_inventory_digest")
    if actual_digest != expected_digest:
        raise ValueError("source inventory digest drifted")
    artifact = build_response_atlas(
        series,
        protocol_sha256=sha256_file(protocol_path),
        source_inventory_digest=actual_digest,
        files_scanned_by_product=scanned,
    )
    validate_atlas(artifact)
    return artifact


def validate_atlas(artifact: dict[str, Any]) -> None:
    _assert_public_safe(artifact)
    if artifact.get("schema_version") != ATLAS_VERSION:
        raise ValueError("unsupported premium K response atlas")
    if artifact.get("study_labels") != ["empirical", "exploratory", "non-authentic", "non-executable"]:
        raise ValueError("study labels drifted")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", artifact.get("protocol", {}).get("sha256", "")):
        raise ValueError("invalid protocol hash")
    source = artifact.get("source_inventory", {})
    if source.get("selected_series_by_product") != {"AU": SERIES_PER_PRODUCT, "AG": SERIES_PER_PRODUCT}:
        raise ValueError("source series selection drifted")
    matrix = artifact.get("training_response_matrix")
    if not isinstance(matrix, list) or len(matrix) != len(_MAPPING) * len(HORIZONS):
        raise ValueError("training matrix shape drifted")
    for row in matrix + artifact.get("holdout_application", {}).get("candidate_response_matrix", []):
        if set(row) != {
            "structural_label",
            "horizon_completed_daily_bars",
            "observation_count",
            "mean_signed_change",
            "median_signed_change",
            "positive_signed_change_rate",
            "clustered_bootstrap_mean_ci_95",
        }:
            raise ValueError("aggregate matrix fields drifted")
        if row["structural_label"] not in _MAPPING or row["horizon_completed_daily_bars"] not in HORIZONS:
            raise ValueError("aggregate matrix semantics drifted")
    freeze = artifact.get("training_candidate_freeze", {})
    candidates = freeze.get("candidate_set", [])
    if freeze.get("candidate_set_sha256") != sha256_json(candidates):
        raise ValueError("candidate freeze digest drifted")
    if freeze.get("frozen_before_holdout_application") is not True:
        raise ValueError("holdout freeze boundary drifted")
    expected_status = "applied_once" if candidates else "not_applied_no_training_candidates"
    if artifact.get("holdout_application", {}).get("status") != expected_status:
        raise ValueError("holdout application status drifted")
