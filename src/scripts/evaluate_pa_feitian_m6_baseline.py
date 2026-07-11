"""Emit deterministic PA / Feitian M6-B baseline evaluation artifacts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.baseline_evaluator import (  # noqa: E402
    BaselineEvaluationConfig,
    build_aggregate_result,
    build_evaluation_dataset,
    canonical_config_sha256,
)
from engine.pa_feitian.contract import load_decision_intent  # noqa: E402
from engine.pa_feitian.evaluation import (  # noqa: E402
    evaluation_aggregate_result_to_jsonable,
    evaluation_dataset_to_jsonable,
    load_evaluation_aggregate_result,
    load_evaluation_dataset,
    write_evaluation_aggregate_result,
    write_evaluation_dataset,
)
from engine.pa_feitian.manifest import (  # noqa: E402
    build_run_manifest,
    load_run_manifest,
    sha256_file,
    write_run_manifest,
)
from engine.pa_feitian.premium_outcome import load_premium_outcome  # noqa: E402
from engine.pa_feitian.schema_validation import (  # noqa: E402
    validate_pa_feitian_evaluation_aggregate_result_schema,
    validate_pa_feitian_evaluation_dataset_schema,
    validate_pa_feitian_run_manifest_schema,
)


SRC_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC_ROOT.parent


def _repo_relative(path: str | Path) -> str:
    raw = Path(path)
    try:
        return raw.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return raw.as_posix()


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _resolve_and_validate_paths(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    input_names = ("m5_manifest", "premium_outcome", "decision_intent")
    output_names = ("dataset_out", "aggregate_out", "manifest_out")
    resolved_inputs = {name: getattr(args, name).resolve() for name in input_names}
    resolved_outputs = {name: getattr(args, name).resolve() for name in output_names}
    input_paths = {path: name for name, path in resolved_inputs.items()}
    for name, path in resolved_outputs.items():
        if path in input_paths:
            parser.error(f"--{name.replace('_', '-')} must not collide with --{input_paths[path].replace('_', '-')}")
    seen_outputs: dict[Path, str] = {}
    for name, path in resolved_outputs.items():
        if path in seen_outputs:
            parser.error(f"--{name.replace('_', '-')} must not collide with --{seen_outputs[path].replace('_', '-')}")
        seen_outputs[path] = name
    for name, path in {**resolved_inputs, **resolved_outputs}.items():
        setattr(args, name, path)


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate explicit M5 artifacts only. This command never reruns score_today, scans "
            "markets, reselects contracts, trades, or executes orders."
        )
    )
    parser.add_argument("--m5-manifest", type=Path, required=True)
    parser.add_argument("--premium-outcome", type=Path, required=True)
    parser.add_argument("--decision-intent", type=Path, required=True)
    parser.add_argument("--dataset-out", type=Path, required=True)
    parser.add_argument("--aggregate-out", type=Path, required=True)
    parser.add_argument("--manifest-out", type=Path, required=True)
    parser.add_argument("--generated-at-utc", type=_parse_utc, required=True)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--bootstrap-replicates", type=int, default=1000)
    parser.add_argument("--lower-quantile", type=float, default=0.05)
    parser.add_argument("--minimum-effective-samples", type=int, default=3)
    parser.add_argument("--folds", type=int, default=2)
    parser.add_argument("--minimum-train-events", type=int, default=1)
    parser.add_argument("--timezone", default="UTC")
    parser.add_argument("--trading-calendar", default="unknown")
    args = parser.parse_args(raw_argv)
    _resolve_and_validate_paths(args, parser)
    os.chdir(REPO_ROOT)

    config = BaselineEvaluationConfig(
        random_seed=args.seed,
        bootstrap_replicates=args.bootstrap_replicates,
        lower_quantile=args.lower_quantile,
        minimum_effective_samples=args.minimum_effective_samples,
        folds=args.folds,
        minimum_train_events=args.minimum_train_events,
        timezone=args.timezone,
        trading_calendar=args.trading_calendar,
    )
    manifest = load_run_manifest(args.m5_manifest)
    premium_outcome = load_premium_outcome(args.premium_outcome)
    decision_intent = load_decision_intent(args.decision_intent)
    recorded_args = [_repo_relative(Path(__file__)), *raw_argv]
    m5_manifest_ref = _repo_relative(args.m5_manifest)
    premium_outcome_ref = _repo_relative(args.premium_outcome)
    decision_intent_ref = _repo_relative(args.decision_intent)
    dataset_out_ref = _repo_relative(args.dataset_out)
    aggregate_out_ref = _repo_relative(args.aggregate_out)
    dataset = build_evaluation_dataset(
        manifest=manifest,
        manifest_path=m5_manifest_ref,
        premium_outcome=premium_outcome,
        premium_outcome_path=premium_outcome_ref,
        decision_intent=decision_intent,
        decision_intent_path=decision_intent_ref,
        config=config,
        generated_at_utc=args.generated_at_utc,
        cli_args=recorded_args,
    )
    write_evaluation_dataset(dataset, args.dataset_out)
    loaded_dataset = load_evaluation_dataset(args.dataset_out)
    validate_pa_feitian_evaluation_dataset_schema(evaluation_dataset_to_jsonable(loaded_dataset))

    aggregate = build_aggregate_result(
        dataset=loaded_dataset,
        dataset_path=dataset_out_ref,
        config=config,
        generated_at_utc=args.generated_at_utc,
    )
    write_evaluation_aggregate_result(aggregate, args.aggregate_out)
    loaded_aggregate = load_evaluation_aggregate_result(args.aggregate_out)
    validate_pa_feitian_evaluation_aggregate_result_schema(
        evaluation_aggregate_result_to_jsonable(loaded_aggregate)
    )

    evaluation_manifest = build_run_manifest(
        scorecard_path=manifest.scorecard_artifact.path,
        snapshot_path=manifest.snapshot_artifact.path,
        source_commit=manifest.source_commit,
        cli_args=recorded_args,
        run_config={
            "contract": "pa_feitian_evaluation_dataset_v1",
            "mode": "m6_baseline_evaluator",
            "source_m5_manifest": m5_manifest_ref,
            "baseline_only": True,
            "no_score_today_rerun": True,
            "no_market_scan": True,
            "no_contract_reselection": True,
            "no_live_trading_or_execution": True,
            "evaluation_config": config.canonical_payload(),
        },
        generated_at_utc=args.generated_at_utc,
        decision_intent_path=decision_intent_ref,
        premium_outcome_path=premium_outcome_ref,
        evaluation_dataset_path=dataset_out_ref,
        evaluation_aggregate_result_path=aggregate_out_ref,
        data_access=manifest.data_access,
    )
    evaluation_manifest.input_hashes.update(
        {
            "source_m5_manifest": sha256_file(args.m5_manifest),
            "decision_intent_artifact": sha256_file(args.decision_intent),
            "premium_outcome_artifact": sha256_file(args.premium_outcome),
            "policy_config": canonical_config_sha256(config),
        }
    )
    write_run_manifest(evaluation_manifest, args.manifest_out)
    validate_pa_feitian_run_manifest_schema(json.loads(args.manifest_out.read_text(encoding="utf-8")))
    print(
        json.dumps(
            {
                "aggregate_result": str(args.aggregate_out),
                "dataset": str(args.dataset_out),
                "manifest": str(args.manifest_out),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
