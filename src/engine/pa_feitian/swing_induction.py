"""Causal, outcome-free daily bare-K swing induction for M6 exploration."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any, Iterable

import pandas as pd


PROTOCOL_VERSION = "pa_feitian_m6_historical_swing_induction_protocol_v1"
ATLAS_VERSION = "pa_feitian_m6_historical_swing_atlas_v1"
PRODUCTS = ("AU", "AG")
TRAIN_END = date(2025, 12, 31)
HOLDOUT_START = date(2026, 1, 1)
HOLDOUT_END = date(2026, 6, 30)
MIN_PREFIX_BARS = 60
WINDOW_BARS = 20
MAX_PUBLIC_SPECIMENS_PER_PRODUCT_SPLIT = 32
DEFAULT_SERIES_PER_PRODUCT = 4
MIN_HOLDOUT_VALID_BARS = 20
_FILENAME_RE = re.compile(r"^SHFE\.(au|ag)\d{4}[CP]\d+\.parquet$", re.IGNORECASE)
_PUBLIC_FORBIDDEN_KEYS = {
    "open",
    "high",
    "low",
    "close",
    "raw_bar",
    "price",
    "chart",
    "future_return",
    "outcome",
    "pnl",
    "premium",
    "bid",
    "ask",
    "delta",
    "greeks",
    "dte",
    "execution",
}


@dataclass(frozen=True)
class DailyBar:
    trading_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class SourceSeries:
    product: str
    public_file_alias: str
    bars: tuple[DailyBar, ...]


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256_hex(value: str | bytes) -> str:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def public_file_alias(filename: str) -> str:
    return "sha256:" + sha256_hex("pa-feitian-m6-swing-source-v1|" + filename)


def discover_option_daily_files(data_root: Path) -> list[tuple[str, Path]]:
    daily_root = data_root / "daily"
    if not daily_root.is_dir():
        raise ValueError("caller-provided data root has no daily directory")
    discovered: list[tuple[str, Path]] = []
    for path in daily_root.iterdir():
        if path.is_symlink() or not path.is_file():
            continue
        match = _FILENAME_RE.fullmatch(path.name)
        if match is None:
            continue
        discovered.append((match.group(1).upper(), path))
    return sorted(discovered, key=lambda item: (item[0], public_file_alias(item[1].name)))


def inventory_digest(discovered: Iterable[tuple[str, Path]]) -> str:
    aliases = [
        {"product": product, "public_file_alias": public_file_alias(path.name)}
        for product, path in discovered
    ]
    return "sha256:" + sha256_hex(canonical_json_bytes(aliases))


def select_corpus_files(
    discovered: Iterable[tuple[str, Path]], *, max_series_per_product: int
) -> list[tuple[str, Path]]:
    if max_series_per_product <= 0:
        raise ValueError("max series per product must be positive")
    selected: list[tuple[str, Path]] = []
    for product in PRODUCTS:
        product_files = [item for item in discovered if item[0] == product]
        selected.extend(product_files[:max_series_per_product])
    if {product for product, _ in selected} != set(PRODUCTS):
        raise ValueError("inventory has no selectable files for one or more products")
    return selected


def select_coverage_qualified_series(
    discovered: Iterable[tuple[str, Path]], *, max_series_per_product: int
) -> tuple[list[SourceSeries], dict[str, int]]:
    """Select the first non-outcome coverage-qualified files for each product."""

    if max_series_per_product <= 0:
        raise ValueError("max series per product must be positive")
    ordered = list(discovered)
    selected: list[SourceSeries] = []
    scanned: dict[str, int] = {product: 0 for product in PRODUCTS}
    for product in PRODUCTS:
        product_selected: list[SourceSeries] = []
        for _, path in (item for item in ordered if item[0] == product):
            scanned[product] += 1
            series = load_source_series(product, path)
            training_count = sum(bar.trading_date <= TRAIN_END for bar in series.bars)
            holdout_count = sum(
                HOLDOUT_START <= bar.trading_date <= HOLDOUT_END for bar in series.bars
            )
            if training_count < MIN_PREFIX_BARS or holdout_count < MIN_HOLDOUT_VALID_BARS:
                continue
            product_selected.append(series)
            if len(product_selected) == max_series_per_product:
                break
        if len(product_selected) != max_series_per_product:
            raise ValueError(f"insufficient non-outcome coverage-qualified series for {product}")
        selected.extend(product_selected)
    return selected, scanned


def _as_finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _valid_bar(bar: DailyBar) -> bool:
    values = (bar.open, bar.high, bar.low, bar.close, bar.volume)
    if any(not math.isfinite(value) or value <= 0 for value in values):
        return False
    return (
        bar.high >= bar.low
        and bar.high >= max(bar.open, bar.close)
        and bar.low <= min(bar.open, bar.close)
    )


def load_source_series(product: str, path: Path) -> SourceSeries:
    required = ["datetime", "open", "high", "low", "close", "volume"]
    frame = pd.read_parquet(path, columns=required)
    if tuple(frame.columns) != tuple(required):
        raise ValueError("daily source schema order drifted")
    bars: list[DailyBar] = []
    previous: date | None = None
    for row in frame.itertuples(index=False):
        timestamp = pd.Timestamp(row.datetime)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_localize(None)
        trading_date = timestamp.date()
        values = [_as_finite_float(value) for value in row[1:]]
        if any(value is None for value in values):
            continue
        bar = DailyBar(trading_date, *values)  # type: ignore[arg-type]
        if not _valid_bar(bar):
            continue
        if previous is not None and trading_date <= previous:
            raise ValueError("valid daily bars are not strictly chronological")
        previous = trading_date
        bars.append(bar)
    return SourceSeries(product=product, public_file_alias=public_file_alias(path.name), bars=tuple(bars))


def split_for_date(trading_date: date) -> str | None:
    if trading_date <= TRAIN_END:
        return "training"
    if HOLDOUT_START <= trading_date <= HOLDOUT_END:
        return "holdout"
    return None


def _bar_direction(bar: DailyBar) -> str:
    if bar.close > bar.open:
        return "up"
    if bar.close < bar.open:
        return "down"
    return "flat"


def _body_position(bar: DailyBar) -> str:
    if bar.close == bar.open or bar.high == bar.low:
        return "doji"
    fraction = (bar.close - bar.low) / (bar.high - bar.low)
    if fraction >= 2 / 3:
        return "upper"
    if fraction <= 1 / 3:
        return "lower"
    return "middle"


def _range_bucket(prefix: tuple[DailyBar, ...]) -> str:
    current = prefix[-1].high - prefix[-1].low
    sample = [bar.high - bar.low for bar in prefix[-WINDOW_BARS:]]
    base = median(sample)
    if base <= 0 or current <= base * 0.6:
        return "compressed"
    if current >= base * 1.5:
        return "expanded"
    return "typical"


def _causal_turn(prefix: tuple[DailyBar, ...]) -> str:
    current, prior = prefix[-1], prefix[-2]
    if current.high >= prior.high and current.low <= prior.low:
        return "outside"
    if current.high <= prior.high and current.low >= prior.low:
        return "inside"
    if current.high > prior.high and current.low >= prior.low:
        return "higher_high"
    if current.low < prior.low and current.high <= prior.high:
        return "lower_low"
    return "none"


def _three_bar_shape(prefix: tuple[DailyBar, ...]) -> str:
    directions = tuple(_bar_direction(bar) for bar in prefix[-3:])
    if directions == ("up", "up", "up"):
        return "rising"
    if directions == ("down", "down", "down"):
        return "falling"
    if directions == ("down", "down", "up"):
        return "reversal_up"
    if directions == ("up", "up", "down"):
        return "reversal_down"
    return "mixed"


def trace_classification(prefix: tuple[DailyBar, ...]) -> dict[str, str]:
    if len(prefix) < MIN_PREFIX_BARS:
        raise ValueError("trace requires the frozen completed-bar prefix")
    return {
        "bar_direction": _bar_direction(prefix[-1]),
        "body_position": _body_position(prefix[-1]),
        "range_bucket_relative_to_prefix_median": _range_bucket(prefix),
        "causal_turn": _causal_turn(prefix),
        "three_bar_directional_shape": _three_bar_shape(prefix),
    }


def _trace_key(trace: dict[str, str]) -> str:
    return "|".join(f"{key}={trace[key]}" for key in sorted(trace))


def _specimen_identity(product: str, file_alias: str, decision_date: date) -> str:
    return "sha256:" + sha256_hex(
        canonical_json_bytes(
            {
                "product": product,
                "public_file_alias": file_alias,
                "decision_date": decision_date.isoformat(),
            }
        )
    )


def _assert_public_safe(value: Any) -> None:
    if isinstance(value, dict):
        forbidden = set(value) & _PUBLIC_FORBIDDEN_KEYS
        if forbidden:
            raise ValueError(f"public artifact contains forbidden fields: {sorted(forbidden)}")
        for nested in value.values():
            _assert_public_safe(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_public_safe(nested)


def build_swing_atlas(
    series: Iterable[SourceSeries],
    *,
    protocol_sha256: str,
    selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ordered = sorted(series, key=lambda item: (item.product, item.public_file_alias))
    if {item.product for item in ordered} != set(PRODUCTS):
        raise ValueError("both AU and AG source series are required")
    files_by_product = Counter(item.product for item in ordered)
    valid_files_by_product: Counter[str] = Counter()
    candidate_counts: Counter[tuple[str, str]] = Counter()
    trace_counts: dict[str, Counter[str]] = {"training": Counter(), "holdout": Counter()}
    traces_by_product: dict[str, dict[str, Counter[str]]] = {
        "AU": {"training": Counter(), "holdout": Counter()},
        "AG": {"training": Counter(), "holdout": Counter()},
    }
    specimens: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for item in ordered:
        training_seen = False
        holdout_seen = False
        for index in range(MIN_PREFIX_BARS - 1, len(item.bars)):
            decision = item.bars[index]
            split = split_for_date(decision.trading_date)
            if split is None:
                continue
            prefix = item.bars[: index + 1]
            trace = trace_classification(prefix)
            trace_key = _trace_key(trace)
            candidate_counts[(item.product, split)] += 1
            trace_counts[split][trace_key] += 1
            traces_by_product[item.product][split][trace_key] += 1
            training_seen = training_seen or split == "training"
            holdout_seen = holdout_seen or split == "holdout"
            specimen = {
                "hashed_specimen_identity": _specimen_identity(
                    item.product, item.public_file_alias, decision.trading_date
                ),
                "product": item.product,
                "decision_date": decision.trading_date.isoformat(),
                "split": split,
                "trace_classification": trace,
            }
            specimens[(item.product, split)].append(specimen)
        if training_seen or holdout_seen:
            valid_files_by_product[item.product] += 1

    if not candidate_counts[("AU", "training")] or not candidate_counts[("AG", "training")]:
        raise ValueError("training coverage is insufficient for one or more products")
    if not candidate_counts[("AU", "holdout")] or not candidate_counts[("AG", "holdout")]:
        raise ValueError("holdout coverage is insufficient for one or more products")

    public_specimens: list[dict[str, Any]] = []
    for key in sorted(specimens):
        selected = sorted(specimens[key], key=lambda row: row["hashed_specimen_identity"])[
            :MAX_PUBLIC_SPECIMENS_PER_PRODUCT_SPLIT
        ]
        public_specimens.extend(selected)
    shared_training_classes = sorted(
        set(traces_by_product["AU"]["training"])
        & set(traces_by_product["AG"]["training"])
    )
    induced_definition = {
        "rule_id": "empirical_bare_k_trace_family_v1",
        "labels": ["empirically_induced_not_authentic", "training_only"],
        "clauses": [
            {
                "id": "IND-001",
                "labels": ["empirically_induced_not_authentic", "training_only"],
                "definition": "A trace is evaluated only at the close of a valid daily bar with at least 60 valid completed same-file bars in its causal prefix.",
            },
            {
                "id": "IND-002",
                "labels": ["empirically_induced_not_authentic", "training_only"],
                "definition": "A trace classification is the fixed tuple of bar direction, body position, range bucket relative to the completed-prefix median, causal two-bar turn, and three-bar directional shape.",
            },
            {
                "id": "IND-003",
                "labels": ["empirically_induced_not_authentic", "training_only"],
                "definition": "The candidate structural family is the set of fixed trace classes observed in both AU and AG training coverage; it has no action, prediction, or outcome meaning.",
            },
        ],
        "shared_training_trace_class_count": len(shared_training_classes),
        "shared_training_trace_class_sha256": "sha256:"
        + sha256_hex(canonical_json_bytes(shared_training_classes)),
    }
    artifact = {
        "schema_version": ATLAS_VERSION,
        "study_label": "empirical_operationalization_exploratory_only",
        "protocol": {
            "path": "docs/research/pa-feitian-m6-historical-swing-induction-protocol-v1.json",
            "sha256": protocol_sha256,
        },
        "source_inventory": {
            "public_source_alias": "external://quant-data/daily/SHFE.au-ag-option-ohlc",
            "selected_series_by_product": {
                product: files_by_product[product] for product in PRODUCTS
            },
            "valid_prefix_files_by_product": {
                product: valid_files_by_product[product] for product in PRODUCTS
            },
            "inventory_alias_digest": "sha256:"
            + sha256_hex(
                canonical_json_bytes(
                    [
                        {"product": item.product, "public_file_alias": item.public_file_alias}
                        for item in ordered
                    ]
                )
            ),
            "series_selection": selection
            or {
                "method": "synthetic_test_input",
                "selected_files_by_product": {product: files_by_product[product] for product in PRODUCTS},
            },
        },
        "coverage": {
            "candidate_windows_by_product_and_split": {
                product: {
                    split: candidate_counts[(product, split)]
                    for split in ("training", "holdout")
                }
                for product in PRODUCTS
            },
            "trace_class_counts": {
                split: {
                    "total": sum(trace_counts[split].values()),
                    "distinct": len(trace_counts[split]),
                    "sha256": "sha256:"
                    + sha256_hex(canonical_json_bytes(sorted(trace_counts[split].items()))),
                }
                for split in ("training", "holdout")
            },
        },
        "induced_definition": induced_definition,
        "representative_specimens": public_specimens,
        "holdout_result": {
            "role": "structural_trace_coverage_and_reproducibility_only",
            "candidate_definition_frozen_before_holdout_application": True,
            "performance_metrics_present": False,
            "outcome_fields_present": False,
        },
        "limitations": [
            "This atlas does not recover an authentic Feitian or DD-line rule.",
            "Trace families are empirical K-bar descriptions, not trade signals.",
            "No future-return, outcome, PnL, contract ranking, or execution evidence is used.",
            "A structural trace class may be present without carrying any economic meaning.",
        ],
    }
    _assert_public_safe(artifact)
    return artifact


def build_from_data_root(
    *,
    data_root: Path,
    protocol_sha256: str,
    max_series_per_product: int = DEFAULT_SERIES_PER_PRODUCT,
) -> dict[str, Any]:
    discovered = discover_option_daily_files(data_root)
    if not discovered:
        raise ValueError("no direct AU/AG daily option files found")
    series, scanned = select_coverage_qualified_series(
        discovered, max_series_per_product=max_series_per_product
    )
    artifact = build_swing_atlas(
        series,
        protocol_sha256=protocol_sha256,
        selection={
            "method": "first_public_file_aliases_per_product_with_non_outcome_coverage",
            "max_series_per_product": max_series_per_product,
            "minimum_training_valid_bars": MIN_PREFIX_BARS,
            "minimum_holdout_valid_bars": MIN_HOLDOUT_VALID_BARS,
            "files_scanned_by_product": scanned,
            "selected_files_by_product": {product: max_series_per_product for product in PRODUCTS},
            "selection_uses_outcomes_or_performance": False,
        },
    )
    artifact["source_inventory"]["discovery_inventory_digest"] = inventory_digest(discovered)
    artifact["source_inventory"]["discovered_files_by_product"] = {
        product: sum(1 for discovered_product, _ in discovered if discovered_product == product)
        for product in PRODUCTS
    }
    _assert_public_safe(artifact)
    return artifact


def validate_atlas(artifact: dict[str, Any]) -> None:
    if artifact.get("schema_version") != ATLAS_VERSION:
        raise ValueError("unsupported swing atlas schema")
    if artifact.get("study_label") != "empirical_operationalization_exploratory_only":
        raise ValueError("study label drifted")
    protocol = artifact.get("protocol", {})
    if protocol.get("path") != "docs/research/pa-feitian-m6-historical-swing-induction-protocol-v1.json":
        raise ValueError("wrong protocol binding")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", protocol.get("sha256", "")):
        raise ValueError("invalid protocol hash")
    selection = artifact.get("source_inventory", {}).get("series_selection", {})
    if selection.get("selection_uses_outcomes_or_performance") is True:
        raise ValueError("source selection used outcomes or performance")
    definition = artifact.get("induced_definition", {})
    if definition.get("labels") != ["empirically_induced_not_authentic", "training_only"]:
        raise ValueError("induced definition labels drifted")
    for clause in definition.get("clauses", []):
        if clause.get("labels") != ["empirically_induced_not_authentic", "training_only"]:
            raise ValueError("induced clause labels drifted")
    for specimen in artifact.get("representative_specimens", []):
        if specimen.get("split") not in {"training", "holdout"}:
            raise ValueError("invalid specimen split")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", specimen.get("hashed_specimen_identity", "")):
            raise ValueError("invalid specimen identity")
        if specimen.get("product") not in PRODUCTS:
            raise ValueError("invalid specimen product")
    holdout = artifact.get("holdout_result", {})
    if holdout.get("candidate_definition_frozen_before_holdout_application") is not True:
        raise ValueError("holdout was not kept untouched")
    if holdout.get("performance_metrics_present") is not False or holdout.get("outcome_fields_present") is not False:
        raise ValueError("outcome boundary drifted")
    _assert_public_safe(artifact)
