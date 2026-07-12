"""Causal, outcome-free swing-line proxies for M6 exploratory research."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Literal

from engine.pa_feitian.swing_induction import ATLAS_VERSION as EXP_011_ATLAS_VERSION
from engine.pa_feitian.swing_induction import DailyBar
from engine.pa_feitian.swing_induction import PRODUCTS
from engine.pa_feitian.swing_induction import SourceSeries
from engine.pa_feitian.swing_induction import canonical_json_bytes
from engine.pa_feitian.swing_induction import inventory_digest
from engine.pa_feitian.swing_induction import select_coverage_qualified_series
from engine.pa_feitian.swing_induction import discover_option_daily_files


PROTOCOL_VERSION = "pa_feitian_m6_causal_swing_line_induction_protocol_v1"
ATLAS_VERSION = "pa_feitian_m6_causal_swing_line_atlas_v1"
TOLERANCE_MULTIPLIER = 0.25
TOLERANCE_LOOKBACK_BARS = 20
SERIES_PER_PRODUCT = 4
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
    "future_return",
    "outcome",
    "pnl",
    "premium",
    "contract",
    "bid",
    "ask",
    "delta",
    "greeks",
    "dte",
    "execution",
}

Side = Literal["long", "short"]


@dataclass(frozen=True)
class Pivot:
    index: int
    value: float


@dataclass(frozen=True)
class ProjectedLine:
    older: Pivot
    newer: Pivot
    slope: float

    def at(self, index: int) -> float:
        return self.older.value + self.slope * (index - self.older.index)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_exp_011_bindings(*, repo_root: Path, protocol: dict[str, Any]) -> dict[str, Any]:
    if protocol.get("schema_version") != PROTOCOL_VERSION:
        raise ValueError("unsupported swing-line induction protocol")
    if protocol.get("protocol_status") != "frozen_before_external_data_access":
        raise ValueError("protocol was not frozen before external data access")
    bindings = protocol.get("m6_exp_011_bindings", {})
    for name in ("protocol", "atlas"):
        binding = bindings.get(name, {})
        path = binding.get("path")
        expected = binding.get("sha256")
        if not isinstance(path, str) or not isinstance(expected, str):
            raise ValueError(f"invalid EXP-011 {name} binding")
        actual = sha256_file(repo_root / path)
        if actual != expected:
            raise ValueError(f"EXP-011 {name} binding hash mismatch")
    atlas = load_json(repo_root / bindings["atlas"]["path"])
    if atlas.get("schema_version") != EXP_011_ATLAS_VERSION:
        raise ValueError("wrong EXP-011 atlas schema")
    if atlas.get("study_label") != "empirical_operationalization_exploratory_only":
        raise ValueError("wrong EXP-011 atlas label")
    return atlas


def causal_pivots(prefix: tuple[DailyBar, ...]) -> tuple[list[Pivot], list[Pivot]]:
    """Return pivots whose right confirmation bar is in the completed prefix."""

    highs: list[Pivot] = []
    lows: list[Pivot] = []
    for index in range(1, len(prefix) - 1):
        before, current, after = prefix[index - 1], prefix[index], prefix[index + 1]
        if before.high < current.high and current.high > after.high:
            highs.append(Pivot(index=index, value=current.high))
        if before.low > current.low and current.low < after.low:
            lows.append(Pivot(index=index, value=current.low))
    return highs, lows


def latest_monotonic_line(
    pivots: Iterable[Pivot], *, direction: Literal["ascending", "descending"]
) -> ProjectedLine | None:
    ordered = list(pivots)
    if len(ordered) < 2:
        return None
    newer = ordered[-1]
    for older in reversed(ordered[:-1]):
        if direction == "ascending" and older.value < newer.value:
            return ProjectedLine(older=older, newer=newer, slope=(newer.value - older.value) / (newer.index - older.index))
        if direction == "descending" and older.value > newer.value:
            return ProjectedLine(older=older, newer=newer, slope=(newer.value - older.value) / (newer.index - older.index))
    return None


def prior_tolerance(prefix: tuple[DailyBar, ...]) -> float | None:
    """Return the fixed unit-free tolerance without reading the decision bar."""

    if len(prefix) < TOLERANCE_LOOKBACK_BARS + 1:
        return None
    prior = prefix[-(TOLERANCE_LOOKBACK_BARS + 1) : -1]
    return TOLERANCE_MULTIPLIER * median(bar.high - bar.low for bar in prior)


def _range_intersects(value: float, tolerance: float, bar: DailyBar) -> bool:
    return bar.low <= value + tolerance and bar.high >= value - tolerance


def _side_label(
    *,
    side: Side,
    current: DailyBar,
    tolerance: float | None,
    low_line: ProjectedLine | None,
    high_line: ProjectedLine | None,
    decision_index: int,
) -> str:
    if tolerance is None or low_line is None or high_line is None:
        return f"{side}_abstain"
    low_projection = low_line.at(decision_index)
    high_projection = high_line.at(decision_index)
    if side == "long":
        if current.close < low_projection - tolerance:
            return "long_invalidation"
        if current.close > high_projection + tolerance:
            return "long_right_break"
        if _range_intersects(low_projection, tolerance, current):
            return "long_left_touch"
    else:
        if current.close > high_projection + tolerance:
            return "short_invalidation"
        if current.close < low_projection - tolerance:
            return "short_right_break"
        if _range_intersects(high_projection, tolerance, current):
            return "short_left_touch"
    return f"{side}_abstain"


def global_label(long_label: str, short_label: str) -> str:
    if long_label != "long_abstain" and short_label != "short_abstain":
        return "conflict"
    if long_label != "long_abstain":
        return long_label
    if short_label != "short_abstain":
        return short_label
    return "abstain"


def classify_prefix(prefix: tuple[DailyBar, ...]) -> dict[str, Any]:
    if len(prefix) < TOLERANCE_LOOKBACK_BARS + 1:
        raise ValueError("classification needs the frozen tolerance history")
    highs, lows = causal_pivots(prefix)
    decision_index = len(prefix) - 1
    current = prefix[-1]
    tolerance = prior_tolerance(prefix)
    long_label = _side_label(
        side="long",
        current=current,
        tolerance=tolerance,
        low_line=latest_monotonic_line(lows, direction="descending"),
        high_line=latest_monotonic_line(highs, direction="descending"),
        decision_index=decision_index,
    )
    short_label = _side_label(
        side="short",
        current=current,
        tolerance=tolerance,
        low_line=latest_monotonic_line(lows, direction="ascending"),
        high_line=latest_monotonic_line(highs, direction="ascending"),
        decision_index=decision_index,
    )
    return {
        "long_label": long_label,
        "short_label": short_label,
        "global_label": global_label(long_label, short_label),
    }


def _specimen_id(product: str, public_file_alias: str, trading_date: date) -> str:
    return sha256_json(
        {
            "product": product,
            "public_file_alias": public_file_alias,
            "decision_date": trading_date.isoformat(),
            "schema": ATLAS_VERSION,
        }
    )


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


def build_swing_line_atlas(
    series: Iterable[SourceSeries],
    *,
    protocol_sha256: str,
    exp_011_atlas_sha256: str,
    source_inventory_digest: str,
    files_scanned_by_product: dict[str, int],
) -> dict[str, Any]:
    ordered = sorted(series, key=lambda item: (item.product, item.public_file_alias))
    if {item.product for item in ordered} != set(PRODUCTS):
        raise ValueError("both AU and AG source series are required")
    if any(sum(item.product == product for item in ordered) != SERIES_PER_PRODUCT for product in PRODUCTS):
        raise ValueError("source series selection drifted")

    labels_by_product_split: dict[str, dict[str, Counter[str]]] = {
        product: {"training": Counter(), "holdout": Counter()} for product in PRODUCTS
    }
    aggregate_labels: dict[str, Counter[str]] = {"training": Counter(), "holdout": Counter()}
    specimens: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    second_touch_history: dict[tuple[str, str], list[int]] = defaultdict(list)

    for item in ordered:
        for index in range(TOLERANCE_LOOKBACK_BARS, len(item.bars)):
            current = item.bars[index]
            split = _split(current.trading_date)
            if split is None:
                continue
            prefix = item.bars[: index + 1]
            classification = classify_prefix(prefix)
            for side in ("long", "short"):
                key = (item.public_file_alias, side)
                label = classification[f"{side}_label"]
                second_touch = label == f"{side}_left_touch" and any(
                    index - prior_index <= TOLERANCE_LOOKBACK_BARS
                    for prior_index in second_touch_history[key]
                )
                classification[f"{side}_second_touch_proxy"] = second_touch
                if label == f"{side}_left_touch":
                    second_touch_history[key].append(index)
                second_touch_history[key] = [
                    prior_index
                    for prior_index in second_touch_history[key]
                    if index - prior_index <= TOLERANCE_LOOKBACK_BARS
                ]
            label = classification["global_label"]
            labels_by_product_split[item.product][split][label] += 1
            aggregate_labels[split][label] += 1
            specimens[(item.product, split)].append(
                {
                    "hashed_specimen_identity": _specimen_id(
                        item.product, item.public_file_alias, current.trading_date
                    ),
                    "product": item.product,
                    "decision_date": current.trading_date.isoformat(),
                    "split": split,
                    "structural_classification": classification,
                }
            )

    for product in PRODUCTS:
        for split in ("training", "holdout"):
            if not labels_by_product_split[product][split]:
                raise ValueError(f"insufficient {split} structural coverage for {product}")
    shared_training_labels = sorted(
        set(labels_by_product_split["AU"]["training"])
        & set(labels_by_product_split["AG"]["training"])
    )
    if not shared_training_labels:
        raise ValueError("no shared training structural labels")
    public_specimens: list[dict[str, Any]] = []
    for key in sorted(specimens):
        public_specimens.extend(
            sorted(specimens[key], key=lambda row: row["hashed_specimen_identity"])[:32]
        )
    artifact = {
        "schema_version": ATLAS_VERSION,
        "study_label": "empirical_operationalization_exploratory_only",
        "protocol": {
            "path": "docs/research/pa-feitian-m6-causal-swing-line-induction-protocol-v1.json",
            "sha256": protocol_sha256,
        },
        "m6_exp_011_atlas": {
            "path": "doc/repro/pa-feitian-m6-historical-swing-induction-2026-07-12/historical_swing_atlas_v1.json",
            "sha256": exp_011_atlas_sha256,
        },
        "source_inventory": {
            "public_source_alias": "external://quant-data/daily/SHFE.au-ag-option-ohlc",
            "discovery_inventory_digest": source_inventory_digest,
            "selected_series_by_product": {product: SERIES_PER_PRODUCT for product in PRODUCTS},
            "files_scanned_by_product": files_scanned_by_product,
            "selection_uses_outcomes_or_performance": False,
        },
        "proxy_definition": {
            "rule_id": "empirical_causal_swing_line_proxy_v1",
            "labels": ["empirically_induced_not_authentic", "training_only"],
            "clauses": [
                {
                    "id": "LINE-IND-001",
                    "labels": ["empirically_induced_not_authentic", "training_only"],
                    "definition": "Strict three-bar pivots are unavailable until their immediate right confirmation bar is completed.",
                },
                {
                    "id": "LINE-IND-002",
                    "labels": ["empirically_induced_not_authentic", "training_only"],
                    "definition": "Two-anchor descending and ascending projections classify only structural touch, break, invalidation, abstain, or conflict states.",
                },
                {
                    "id": "LINE-IND-003",
                    "labels": ["empirically_induced_not_authentic", "training_only"],
                    "definition": "A unit-free tolerance is fixed at 0.25 times the median range of the 20 completed bars before the decision bar.",
                },
                {
                    "id": "LINE-IND-004",
                    "labels": ["empirically_induced_not_authentic", "training_only"],
                    "definition": "A second-touch proxy records only a prior causal same-side touch within 20 completed decision bars and has no action meaning.",
                },
            ],
            "shared_training_global_labels": shared_training_labels,
            "shared_training_global_labels_sha256": sha256_json(shared_training_labels),
        },
        "coverage": {
            "global_label_counts": {
                split: {
                    "total": sum(aggregate_labels[split].values()),
                    "by_label": dict(sorted(aggregate_labels[split].items())),
                    "sha256": sha256_json(sorted(aggregate_labels[split].items())),
                }
                for split in ("training", "holdout")
            },
            "global_label_counts_by_product_and_split": {
                product: {
                    split: dict(sorted(labels_by_product_split[product][split].items()))
                    for split in ("training", "holdout")
                }
                for product in PRODUCTS
            },
        },
        "representative_specimens": public_specimens,
        "holdout_result": {
            "role": "mechanical_structural_coverage_and_reproducibility_only",
            "candidate_definition_frozen_before_holdout_application": True,
            "outcome_fields_present": False,
            "performance_metrics_present": False,
        },
        "limitations": [
            "This is not an authentic Feitian or DD-line reconstruction.",
            "The fixed pivot, two-anchor, and tolerance conventions are empirical proxies only.",
            "Structural labels have no signal, trade-direction, contract-selection, outcome, or execution meaning.",
            "Holdout coverage does not establish economic value or fidelity to a manual chart-reading process.",
        ],
    }
    _assert_public_safe(artifact)
    return artifact


def build_from_data_root(
    *,
    repo_root: Path,
    data_root: Path,
    protocol_path: Path,
) -> dict[str, Any]:
    protocol = load_json(protocol_path)
    exp_011_atlas = validate_exp_011_bindings(repo_root=repo_root, protocol=protocol)
    discovered = discover_option_daily_files(data_root)
    series, scanned = select_coverage_qualified_series(
        discovered, max_series_per_product=SERIES_PER_PRODUCT
    )
    artifact = build_swing_line_atlas(
        series,
        protocol_sha256=sha256_file(protocol_path),
        exp_011_atlas_sha256=protocol["m6_exp_011_bindings"]["atlas"]["sha256"],
        source_inventory_digest=inventory_digest(discovered),
        files_scanned_by_product=scanned,
    )
    if artifact["source_inventory"]["discovery_inventory_digest"] != exp_011_atlas["source_inventory"]["discovery_inventory_digest"]:
        raise ValueError("EXP-011 source inventory drifted")
    _assert_public_safe(artifact)
    return artifact


def validate_atlas(artifact: dict[str, Any]) -> None:
    _assert_public_safe(artifact)
    if artifact.get("schema_version") != ATLAS_VERSION:
        raise ValueError("unsupported swing-line atlas schema")
    if artifact.get("study_label") != "empirical_operationalization_exploratory_only":
        raise ValueError("study label drifted")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", artifact.get("protocol", {}).get("sha256", "")):
        raise ValueError("invalid protocol hash")
    source = artifact.get("source_inventory", {})
    if source.get("selected_series_by_product") != {"AU": SERIES_PER_PRODUCT, "AG": SERIES_PER_PRODUCT}:
        raise ValueError("source series selection drifted")
    if source.get("selection_uses_outcomes_or_performance") is not False:
        raise ValueError("source selection outcome boundary drifted")
    definition = artifact.get("proxy_definition", {})
    if definition.get("labels") != ["empirically_induced_not_authentic", "training_only"]:
        raise ValueError("proxy labels drifted")
    for clause in definition.get("clauses", []):
        if clause.get("labels") != ["empirically_induced_not_authentic", "training_only"]:
            raise ValueError("proxy clause labels drifted")
    holdout = artifact.get("holdout_result", {})
    if holdout.get("candidate_definition_frozen_before_holdout_application") is not True:
        raise ValueError("holdout was not kept untouched")
    if holdout.get("outcome_fields_present") is not False or holdout.get("performance_metrics_present") is not False:
        raise ValueError("outcome boundary drifted")
    expected_classification_keys = {
        "long_label",
        "short_label",
        "global_label",
        "long_second_touch_proxy",
        "short_second_touch_proxy",
    }
    for specimen in artifact.get("representative_specimens", []):
        if set(specimen) != {
            "hashed_specimen_identity",
            "product",
            "decision_date",
            "split",
            "structural_classification",
        }:
            raise ValueError("public specimen fields drifted")
        if specimen.get("product") not in PRODUCTS or specimen.get("split") not in {"training", "holdout"}:
            raise ValueError("public specimen partition drifted")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", specimen.get("hashed_specimen_identity", "")):
            raise ValueError("invalid public specimen identity")
        classification = specimen.get("structural_classification", {})
        if set(classification) != expected_classification_keys:
            raise ValueError("structural classification fields drifted")
        if not isinstance(classification["long_second_touch_proxy"], bool) or not isinstance(classification["short_second_touch_proxy"], bool):
            raise ValueError("second-touch proxy must remain boolean")
    _assert_public_safe(artifact)
