"""Emit a PA / Feitian snapshot contract artifact.

By default this writes the deterministic contract fixture. With ``--scorecard``
it consumes an existing score_today JSON output and converts the emitted ag/au
option suggestions into pa_feitian_snapshot_v0/v1. With ``--manifest-out`` it
also writes the M2 run manifest. This script does not scan raw market data
itself.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.options.iv_regime import DEFAULT_MAX_RANK, DEFAULT_WARMUP
from engine.pa_feitian.contract import (
    PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION,
    PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION,
    write_decision_intent,
    write_snapshot,
)
from engine.pa_feitian.decision_intent_adapter import (
    build_decision_intent_sidecar_from_scorecard_file,
)
from engine.pa_feitian.manifest import build_run_manifest, write_run_manifest
from engine.pa_feitian.scorecard_producer import example_snapshot, snapshot_from_scorecard_file
from engine.pa_feitian.score_today_intake import (
    DEFAULT_SCORE_TODAY_ARTIFACT_GLOB,
    resolve_score_today_artifact,
)

SRC_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC_ROOT.parent
DEFAULT_SCORECARD_FIXTURE = SRC_ROOT / "tests" / "fixtures" / "pa_feitian_scorecard_v1.json"
DATA_ACCESS_STATUS_CHOICES = (
    "real_data_available",
    "fixture_fallback",
    "data_blocked",
    "unknown",
)


def _source_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def _parse_generated_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _default_data_access_notes(*, used_fixture_fallback: bool) -> list[str]:
    if used_fixture_fallback:
        return ["deterministic scorecard fixture fallback; no live score_today run was invoked"]
    return ["consumed existing score_today JSON artifact; producer did not read raw data stores"]


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output JSON path for the PA/Feitian snapshot.",
    )
    parser.add_argument(
        "--contract-version",
        choices=["pa_feitian_snapshot_v0", "pa_feitian_snapshot_v1"],
        default=PA_FEITIAN_SNAPSHOT_SCHEMA_VERSION,
        help="Snapshot contract to emit. v0 remains the default; v1 is the shadow trace contract.",
    )
    parser.add_argument(
        "--source-commit",
        default=None,
        help="Source commit to embed. Defaults to git rev-parse HEAD.",
    )
    parser.add_argument(
        "--generated-at-utc",
        default="2026-07-07T00:00:00Z",
        help="UTC timestamp to embed. Default is fixed for deterministic contract tests.",
    )
    parser.add_argument(
        "--scorecard",
        type=Path,
        default=None,
        help="Existing score_today JSON output to convert into a real PA/Feitian snapshot.",
    )
    parser.add_argument(
        "--score-today-artifact",
        type=Path,
        default=None,
        help="Alias for --scorecard when wiring an existing score_today JSON artifact.",
    )
    parser.add_argument(
        "--score-today-artifact-dir",
        type=Path,
        action="append",
        default=None,
        help=(
            "Directory containing existing score_today JSON artifacts. Only explicitly "
            "provided artifact directories are searched; raw market stores are not scanned."
        ),
    )
    parser.add_argument(
        "--score-today-artifact-glob",
        default=DEFAULT_SCORE_TODAY_ARTIFACT_GLOB,
        help=(
            "Glob used within each --score-today-artifact-dir. Defaults to *.json; "
            "valid score_today artifacts are sorted by path and the last one is selected."
        ),
    )
    parser.add_argument(
        "--max-signals",
        type=int,
        default=None,
        help="Keep only the most recent N scorecard-backed PA/Feitian signals.",
    )
    parser.add_argument(
        "--iv-warmup",
        type=int,
        default=DEFAULT_WARMUP,
        help="Prior signal IV count required before causal IV rank is actionable.",
    )
    parser.add_argument(
        "--iv-max-rank",
        type=float,
        default=DEFAULT_MAX_RANK,
        help="Maximum causal IV rank to keep a premium runner candidate.",
    )
    parser.add_argument(
        "--manifest-out",
        type=Path,
        default=None,
        help="Optional output path for pa_feitian_run_manifest_v1.",
    )
    parser.add_argument(
        "--decision-intent-out",
        type=Path,
        default=None,
        help=(
            "Optional output path for pa_feitian_decision_intent_v1. Requires "
            "--manifest-out and pa_feitian_snapshot_v1."
        ),
    )
    parser.add_argument(
        "--frontend-copy",
        type=Path,
        default=None,
        help="Optional copied snapshot path for the dashboard artifact handoff.",
    )
    parser.add_argument(
        "--data-access-status",
        choices=DATA_ACCESS_STATUS_CHOICES,
        default=None,
        help="Data access classification recorded in the run manifest.",
    )
    parser.add_argument(
        "--data-access-source",
        default=None,
        help="Data access source recorded in the run manifest. Defaults to the scorecard path.",
    )
    parser.add_argument(
        "--data-access-note",
        dest="data_access_notes",
        action="append",
        default=None,
        help="Repeatable note recorded in the run manifest data_access.notes.",
    )
    args = parser.parse_args(raw_argv)

    if (
        args.manifest_out is not None
        and args.contract_version != PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION
    ):
        parser.error("--manifest-out requires --contract-version pa_feitian_snapshot_v1")
    if args.decision_intent_out is not None and args.manifest_out is None:
        parser.error("--decision-intent-out requires --manifest-out")
    if (
        args.decision_intent_out is not None
        and args.contract_version != PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION
    ):
        parser.error("--decision-intent-out requires --contract-version pa_feitian_snapshot_v1")
    if args.scorecard is not None and args.score_today_artifact is not None:
        parser.error("--scorecard and --score-today-artifact are aliases; pass only one")

    source_commit = args.source_commit or _source_commit()
    generated_at_utc = _parse_generated_at(args.generated_at_utc)
    scorecard_path = args.scorecard or args.score_today_artifact
    artifact_dirs = args.score_today_artifact_dir or []
    should_resolve_intake = (
        scorecard_path is not None or bool(artifact_dirs) or args.manifest_out is not None
    )
    intake = None
    if should_resolve_intake:
        intake = resolve_score_today_artifact(
            explicit_path=scorecard_path,
            artifact_dirs=artifact_dirs,
            artifact_glob=args.score_today_artifact_glob,
            fixture_path=DEFAULT_SCORECARD_FIXTURE,
            allow_fixture_fallback=(
                scorecard_path is None and not artifact_dirs and args.manifest_out is not None
            ),
        )
        if intake.status == "data_blocked":
            parser.error("; ".join(intake.notes))
        scorecard_path = intake.scorecard_path

    if scorecard_path is not None:
        snapshot = snapshot_from_scorecard_file(
            scorecard_path,
            source_commit=source_commit,
            generated_at_utc=generated_at_utc,
            max_signals=args.max_signals,
            iv_warmup=args.iv_warmup,
            iv_max_rank=args.iv_max_rank,
            contract_version=args.contract_version,
        )
    else:
        snapshot = example_snapshot(
            source_commit=source_commit,
            generated_at_utc=generated_at_utc,
            contract_version=args.contract_version,
        )
    write_snapshot(snapshot, args.out)

    if args.frontend_copy is not None:
        args.frontend_copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.out, args.frontend_copy)

    if args.decision_intent_out is not None:
        if scorecard_path is None:
            parser.error("--decision-intent-out requires --scorecard or manifest fixture fallback")
        decision_intent = build_decision_intent_sidecar_from_scorecard_file(
            snapshot,
            scorecard_path=scorecard_path,
            source_commit=source_commit,
            source_manifest_path=args.manifest_out,
            snapshot_artifact_path=args.out,
            generated_at_utc=generated_at_utc,
            source_manifest_generated_at_utc=generated_at_utc,
        )
        write_decision_intent(decision_intent, args.decision_intent_out)

    if args.manifest_out is not None:
        if scorecard_path is None:
            parser.error("--manifest-out requires --scorecard or the deterministic fixture fallback")
        default_data_access = (
            intake.data_access()
            if intake is not None
            else {
                "status": "real_data_available",
                "source": _repo_relative(scorecard_path),
                "notes": _default_data_access_notes(used_fixture_fallback=False),
            }
        )
        data_access_status = args.data_access_status or default_data_access["status"]
        data_access_source = args.data_access_source or _repo_relative(scorecard_path)
        data_access_notes = args.data_access_notes or default_data_access["notes"]
        manifest = build_run_manifest(
            scorecard_path=scorecard_path,
            snapshot_path=args.out,
            source_commit=source_commit,
            cli_args=[_repo_relative(Path(__file__)), *raw_argv],
            run_config=snapshot.run_config,
            generated_at_utc=generated_at_utc,
            frontend_copy_path=args.frontend_copy,
            decision_intent_path=args.decision_intent_out,
            data_access={
                "status": data_access_status,
                "source": data_access_source,
                "notes": data_access_notes,
            },
        )
        write_run_manifest(manifest, args.manifest_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
