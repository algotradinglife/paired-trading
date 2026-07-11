"""Build artifact-only PA / Feitian M6 dashboard copies from explicit evidence."""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.manifest import (  # noqa: E402
    PaFeitianArtifactRef,
    load_run_manifest,
    sha256_file,
    write_run_manifest,
)


SRC_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC_ROOT.parent
SCRIPT_PATH = SRC_ROOT / "scripts" / "build_pa_feitian_m6_dashboard_artifacts.py"


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _ref(kind: str, path: Path, schema_version: str) -> PaFeitianArtifactRef:
    return PaFeitianArtifactRef(
        kind=kind,
        path=_relative(path),
        sha256=sha256_file(path),
        schema_version=schema_version,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--decision-intent", type=Path, required=True)
    parser.add_argument("--premium-outcome", type=Path, required=True)
    parser.add_argument("--evaluation-dataset", type=Path, required=True)
    parser.add_argument("--evaluation-aggregate", type=Path, required=True)
    parser.add_argument("--failure-mode-report", type=Path)
    parser.add_argument("--screening-report", type=Path)
    parser.add_argument("--dashboard-dir", type=Path, required=True)
    parser.add_argument("--manifest-out", type=Path, required=True)
    parser.add_argument("--generated-at-utc", type=_parse_utc, required=True)
    args = parser.parse_args(argv)

    dashboard_dir = args.dashboard_dir.resolve()
    copied = {
        "snapshot": dashboard_dir / "pa_feitian_snapshot_v1.json",
        "decision_intent": dashboard_dir / "pa_feitian_decision_intent_v1.json",
        "premium_outcome": dashboard_dir / args.premium_outcome.name,
        "evaluation_dataset": dashboard_dir / args.evaluation_dataset.name,
        "evaluation_aggregate": dashboard_dir / args.evaluation_aggregate.name,
    }
    sources = {
        "snapshot": args.snapshot.resolve(),
        "decision_intent": args.decision_intent.resolve(),
        "premium_outcome": args.premium_outcome.resolve(),
        "evaluation_dataset": args.evaluation_dataset.resolve(),
        "evaluation_aggregate": args.evaluation_aggregate.resolve(),
    }
    for key, source in sources.items():
        _copy(source, copied[key])
    if args.failure_mode_report is not None:
        copied["failure_mode_report"] = dashboard_dir / args.failure_mode_report.name
        _copy(args.failure_mode_report.resolve(), copied["failure_mode_report"])
    if args.screening_report is not None:
        copied["screening_report"] = dashboard_dir / args.screening_report.name
        _copy(args.screening_report.resolve(), copied["screening_report"])

    manifest = load_run_manifest(args.source_manifest)
    manifest.generated_at_utc = args.generated_at_utc
    manifest.snapshot_artifact = _ref("snapshot", copied["snapshot"], "pa_feitian_snapshot_v1")
    manifest.decision_intent_artifact = _ref(
        "decision_intent", copied["decision_intent"], "pa_feitian_decision_intent_v1"
    )
    manifest.premium_outcome_artifact = _ref(
        "premium_outcome", copied["premium_outcome"], "pa_feitian_premium_outcome_v1"
    )
    manifest.evaluation_dataset_artifact = _ref(
        "evaluation_dataset", copied["evaluation_dataset"], "pa_feitian_evaluation_dataset_v1"
    )
    manifest.evaluation_aggregate_result_artifact = _ref(
        "evaluation_aggregate_result",
        copied["evaluation_aggregate"],
        "pa_feitian_evaluation_aggregate_result_v1",
    )
    manifest.evaluation_failure_mode_report_artifact = (
        _ref(
            "evaluation_failure_mode_report",
            copied["failure_mode_report"],
            "pa_feitian_evaluation_failure_mode_report_v1",
        )
        if "failure_mode_report" in copied
        else None
    )
    manifest.evaluation_screening_report_artifact = (
        _ref(
            "evaluation_screening_report",
            copied["screening_report"],
            "pa_feitian_evaluation_screening_report_v1",
        )
        if "screening_report" in copied
        else None
    )
    manifest.frontend_copy_path = _relative(copied["snapshot"])
    manifest.cli_args = [
        _relative(SCRIPT_PATH),
        "--source-manifest",
        _relative(args.source_manifest.resolve()),
    ]
    manifest.run_config = {
        **manifest.run_config,
        "mode": "m6_candidate_dashboard_artifact_builder",
        "dashboard_artifact_only": True,
        "source_m5_manifest": _relative(args.source_manifest.resolve()),
    }
    manifest.input_hashes["source_m5_manifest"] = sha256_file(args.source_manifest)
    manifest.output_hashes.update(
        {
            "snapshot_artifact": manifest.snapshot_artifact.sha256,
            "decision_intent_artifact": manifest.decision_intent_artifact.sha256,
            "premium_outcome_artifact": manifest.premium_outcome_artifact.sha256,
            "evaluation_dataset_artifact": manifest.evaluation_dataset_artifact.sha256,
            "evaluation_aggregate_result_artifact": manifest.evaluation_aggregate_result_artifact.sha256,
            "frontend_copy": manifest.snapshot_artifact.sha256,
            "frontend_decision_intent_copy": manifest.decision_intent_artifact.sha256,
            "frontend_premium_outcome_copy": manifest.premium_outcome_artifact.sha256,
            "frontend_evaluation_dataset_copy": manifest.evaluation_dataset_artifact.sha256,
            "frontend_evaluation_aggregate_result_copy": manifest.evaluation_aggregate_result_artifact.sha256,
        }
    )
    for name, artifact in (
        ("evaluation_failure_mode_report", manifest.evaluation_failure_mode_report_artifact),
        ("evaluation_screening_report", manifest.evaluation_screening_report_artifact),
    ):
        if artifact is None:
            manifest.output_hashes.pop(f"{name}_artifact", None)
            manifest.output_hashes.pop(f"frontend_{name}_copy", None)
        else:
            manifest.output_hashes[f"{name}_artifact"] = artifact.sha256
            manifest.output_hashes[f"frontend_{name}_copy"] = artifact.sha256
    write_run_manifest(manifest, args.manifest_out)
    print(_relative(args.manifest_out.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
