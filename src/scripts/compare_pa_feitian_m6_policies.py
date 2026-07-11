"""Emit M6-C controlled comparison, screening, and failure-mode artifacts.

This command accepts only explicit, already-generated M6 datasets/aggregates.
It never invokes score_today, scans markets, selects contracts, trades, or
executes orders.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.evaluation import (  # noqa: E402
    evaluation_failure_mode_report_to_jsonable,
    evaluation_screening_report_to_jsonable,
    load_evaluation_aggregate_result,
    load_evaluation_dataset,
    write_evaluation_failure_mode_report,
    write_evaluation_screening_report,
)
from engine.pa_feitian.manifest import sha256_file  # noqa: E402
from engine.pa_feitian.policy_comparison import (  # noqa: E402
    CandidateArtifacts,
    build_policy_comparison_reports,
    load_policy_comparison_config,
)
from engine.pa_feitian.schema_validation import (  # noqa: E402
    validate_pa_feitian_evaluation_failure_mode_report_schema,
    validate_pa_feitian_evaluation_screening_report_schema,
    validate_pa_feitian_m6_policy_comparison_config_schema,
)


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _load_artifacts(dataset_path: Path, aggregate_path: Path) -> CandidateArtifacts:
    return CandidateArtifacts(
        dataset_path=dataset_path,
        aggregate_path=aggregate_path,
        dataset=load_evaluation_dataset(dataset_path),
        aggregate=load_evaluation_aggregate_result(aggregate_path),
    )


def _resolve_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    inputs = {
        args.baseline_dataset.resolve(),
        args.baseline_aggregate.resolve(),
        args.comparison_config.resolve(),
    }
    candidates: dict[str, tuple[Path, Path]] = {}
    for candidate_id, dataset, aggregate in args.candidate_input:
        if candidate_id in candidates:
            parser.error(f"--candidate-input repeats candidate_id {candidate_id!r}")
        dataset_path, aggregate_path = Path(dataset), Path(aggregate)
        candidates[candidate_id] = (dataset_path, aggregate_path)
        inputs.update({dataset_path.resolve(), aggregate_path.resolve()})
    if args.screening_out.resolve() in inputs:
        parser.error("--screening-out must not collide with an input artifact")
    args.candidate_input = candidates


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        description="Compare only explicit M6 evaluation artifacts under a pre-registered config."
    )
    parser.add_argument("--baseline-dataset", type=Path, required=True)
    parser.add_argument("--baseline-aggregate", type=Path, required=True)
    parser.add_argument("--comparison-config", type=Path, required=True)
    parser.add_argument("--candidate-input", nargs=3, metavar=("ID", "DATASET", "AGGREGATE"), action="append", default=[])
    parser.add_argument("--screening-out", type=Path, required=True)
    parser.add_argument("--failure-report-dir", type=Path, required=True)
    parser.add_argument("--generated-at-utc", type=_parse_utc, required=True)
    args = parser.parse_args(raw_argv)
    _resolve_args(args, parser)

    config_payload = json.loads(args.comparison_config.read_text(encoding="utf-8"))
    validate_pa_feitian_m6_policy_comparison_config_schema(config_payload)
    config = load_policy_comparison_config(args.comparison_config)
    baseline = _load_artifacts(args.baseline_dataset, args.baseline_aggregate)
    candidates = {
        candidate_id: _load_artifacts(dataset_path, aggregate_path)
        for candidate_id, (dataset_path, aggregate_path) in args.candidate_input.items()
    }
    screening, failures = build_policy_comparison_reports(
        baseline=baseline,
        candidates=candidates,
        config=config,
        config_path=args.comparison_config,
        generated_at_utc=args.generated_at_utc,
        cli_args=["src/scripts/compare_pa_feitian_m6_policies.py", *raw_argv],
    )
    write_evaluation_screening_report(screening, args.screening_out)
    validate_pa_feitian_evaluation_screening_report_schema(
        evaluation_screening_report_to_jsonable(screening)
    )
    args.failure_report_dir.mkdir(parents=True, exist_ok=True)
    failure_paths: dict[str, str] = {}
    for candidate_id, report in failures.items():
        filename = f"{candidate_id.replace(':', '_')}_failure_mode_report.json"
        output_path = args.failure_report_dir / filename
        write_evaluation_failure_mode_report(report, output_path)
        validate_pa_feitian_evaluation_failure_mode_report_schema(
            evaluation_failure_mode_report_to_jsonable(report)
        )
        failure_paths[candidate_id] = str(output_path)
    print(json.dumps({"screening_report": str(args.screening_out), "screening_sha256": sha256_file(args.screening_out), "failure_reports": failure_paths}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
