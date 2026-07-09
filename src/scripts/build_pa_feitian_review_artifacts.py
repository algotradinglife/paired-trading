"""Build the PA / Feitian M4 dashboard review artifact set.

The command consumes an existing score_today JSON artifact, or the deterministic
scorecard fixture when no artifact selector is supplied. It writes snapshot v1,
run manifests, decision-intent sidecar, and dashboard copies. It does not scan
raw market stores and it does not invoke live trading behavior.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.options.iv_regime import DEFAULT_MAX_RANK
from engine.pa_feitian.contract import (
    PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION,
    load_decision_intent,
    load_snapshot_v1,
    write_decision_intent,
    write_snapshot,
)
from engine.pa_feitian.decision_intent_adapter import (
    build_decision_intent_sidecar_from_scorecard_file,
)
from engine.pa_feitian.manifest import (
    build_run_manifest,
    load_run_manifest,
    sha256_file,
    write_run_manifest,
)
from engine.pa_feitian.score_today_intake import (
    DEFAULT_SCORE_TODAY_ARTIFACT_GLOB,
    resolve_score_today_artifact,
)
from engine.pa_feitian.scorecard_producer import snapshot_from_scorecard_file


SRC_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC_ROOT.parent
DEFAULT_SOURCE_FIXTURE_DIR = SRC_ROOT / "tests" / "fixtures"
DEFAULT_DASHBOARD_FIXTURE_DIR = REPO_ROOT / "frontend" / "pa-feitian-dashboard" / "fixtures"
DEFAULT_SCORECARD_FIXTURE = DEFAULT_SOURCE_FIXTURE_DIR / "pa_feitian_scorecard_v1.json"
DEFAULT_GENERATED_AT_UTC = "2026-07-07T00:00:00Z"
DEFAULT_SOURCE_COMMIT = "c" * 40
SCRIPT_PATH = SRC_ROOT / "scripts" / "build_pa_feitian_review_artifacts.py"


def _parse_generated_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return DEFAULT_SOURCE_COMMIT


def _repo_path(path: str | Path) -> Path:
    raw = Path(path)
    return raw if raw.is_absolute() else REPO_ROOT / raw


def _repo_relative(path: str | Path) -> str:
    raw = Path(path)
    try:
        return raw.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return raw.as_posix()


def _manifest_path_arg(path: Path) -> str:
    return _repo_relative(path)


def _copy_artifact(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)


def _jsonable_summary(paths: Mapping[str, Path]) -> dict[str, str]:
    return {key: _repo_relative(path) for key, path in sorted(paths.items())}


def _add_copy_hashes(manifest_path: Path, *, dashboard_sidecar_path: Path) -> None:
    manifest = load_run_manifest(manifest_path)
    manifest.output_hashes["frontend_decision_intent_copy"] = sha256_file(dashboard_sidecar_path)
    write_run_manifest(manifest, manifest_path)


def _build_manifest(
    *,
    manifest_path: Path,
    scorecard_path: Path,
    snapshot_path: Path,
    source_commit: str,
    cli_args: list[str],
    run_config: Mapping[str, Any],
    generated_at_utc: datetime,
    frontend_snapshot_path: Path,
    decision_intent_path: Path | None,
    data_access: Mapping[str, Any],
) -> None:
    manifest = build_run_manifest(
        scorecard_path=_manifest_path_arg(scorecard_path),
        snapshot_path=_manifest_path_arg(snapshot_path),
        source_commit=source_commit,
        cli_args=cli_args,
        run_config=run_config,
        generated_at_utc=generated_at_utc,
        frontend_copy_path=_manifest_path_arg(frontend_snapshot_path),
        decision_intent_path=(
            _manifest_path_arg(decision_intent_path) if decision_intent_path is not None else None
        ),
        data_access=data_access,
    )
    write_run_manifest(manifest, manifest_path)


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        description="Build PA/Feitian M4 review artifacts for the dashboard."
    )
    parser.add_argument(
        "--score-today-artifact",
        type=Path,
        default=None,
        help="Existing score_today JSON output to consume.",
    )
    parser.add_argument(
        "--score-today-artifact-dir",
        type=Path,
        action="append",
        default=None,
        help="Directory containing existing score_today JSON artifacts.",
    )
    parser.add_argument(
        "--score-today-artifact-glob",
        default=DEFAULT_SCORE_TODAY_ARTIFACT_GLOB,
        help="Glob used inside each score_today artifact directory.",
    )
    parser.add_argument(
        "--scorecard-fixture",
        type=Path,
        default=DEFAULT_SCORECARD_FIXTURE,
        help="Deterministic fallback scorecard fixture.",
    )
    parser.add_argument(
        "--no-fixture-fallback",
        action="store_true",
        help="Fail when no explicit score_today artifact can be resolved.",
    )
    parser.add_argument(
        "--source-fixture-dir",
        type=Path,
        default=DEFAULT_SOURCE_FIXTURE_DIR,
        help="Directory for source-side review fixtures.",
    )
    parser.add_argument(
        "--dashboard-fixture-dir",
        type=Path,
        default=DEFAULT_DASHBOARD_FIXTURE_DIR,
        help="Directory for dashboard fixture copies.",
    )
    parser.add_argument(
        "--source-commit",
        default=DEFAULT_SOURCE_COMMIT,
        help="Source commit to embed. Defaults to the deterministic fixture commit.",
    )
    parser.add_argument(
        "--use-git-source-commit",
        action="store_true",
        help="Embed git rev-parse HEAD instead of the deterministic fixture commit.",
    )
    parser.add_argument(
        "--generated-at-utc",
        default=DEFAULT_GENERATED_AT_UTC,
        help="UTC timestamp to embed in generated artifacts.",
    )
    parser.add_argument("--max-signals", type=int, default=None)
    parser.add_argument("--iv-warmup", type=int, default=1)
    parser.add_argument("--iv-max-rank", type=float, default=DEFAULT_MAX_RANK)
    args = parser.parse_args(raw_argv)

    os.chdir(REPO_ROOT)

    source_fixture_dir = _repo_path(args.source_fixture_dir)
    dashboard_fixture_dir = _repo_path(args.dashboard_fixture_dir)
    scorecard_fixture = _repo_path(args.scorecard_fixture)
    source_commit = _git_head() if args.use_git_source_commit else args.source_commit
    generated_at_utc = _parse_generated_at(args.generated_at_utc)
    cli_args = [_repo_relative(SCRIPT_PATH), *raw_argv]

    intake = resolve_score_today_artifact(
        explicit_path=args.score_today_artifact,
        artifact_dirs=args.score_today_artifact_dir or (),
        artifact_glob=args.score_today_artifact_glob,
        fixture_path=scorecard_fixture,
        allow_fixture_fallback=not args.no_fixture_fallback,
    )
    if intake.scorecard_path is None:
        parser.error("; ".join(intake.notes))

    scorecard_path = _repo_path(intake.scorecard_path)
    data_access = intake.data_access()
    if intake.used_fixture_fallback:
        data_access["source"] = _repo_relative(scorecard_path)

    source_snapshot_path = source_fixture_dir / "pa_feitian_snapshot_v1.json"
    source_manifest_path = source_fixture_dir / "pa_feitian_run_manifest_v1.json"
    source_review_manifest_path = (
        source_fixture_dir / "pa_feitian_run_manifest_with_decision_intent_v1.json"
    )
    source_sidecar_path = source_fixture_dir / "pa_feitian_decision_intent_v1.json"
    dashboard_snapshot_path = dashboard_fixture_dir / "pa_feitian_snapshot_v1.json"
    dashboard_manifest_path = dashboard_fixture_dir / "pa_feitian_run_manifest_v1.json"
    dashboard_sidecar_path = dashboard_fixture_dir / "pa_feitian_decision_intent_v1.json"

    snapshot = snapshot_from_scorecard_file(
        _manifest_path_arg(scorecard_path),
        source_commit=source_commit,
        generated_at_utc=generated_at_utc,
        max_signals=args.max_signals,
        iv_warmup=args.iv_warmup,
        iv_max_rank=args.iv_max_rank,
        contract_version=PA_FEITIAN_SNAPSHOT_V1_SCHEMA_VERSION,
    )
    write_snapshot(snapshot, source_snapshot_path)
    load_snapshot_v1(source_snapshot_path)

    sidecar = build_decision_intent_sidecar_from_scorecard_file(
        snapshot,
        scorecard_path=scorecard_path,
        source_commit=source_commit,
        source_manifest_path=_manifest_path_arg(source_review_manifest_path),
        snapshot_artifact_path=_manifest_path_arg(source_snapshot_path),
        generated_at_utc=generated_at_utc,
        source_manifest_generated_at_utc=generated_at_utc,
    )
    write_decision_intent(sidecar, source_sidecar_path)
    load_decision_intent(source_sidecar_path)

    _copy_artifact(source_snapshot_path, dashboard_snapshot_path)
    _copy_artifact(source_sidecar_path, dashboard_sidecar_path)

    _build_manifest(
        manifest_path=source_manifest_path,
        scorecard_path=scorecard_path,
        snapshot_path=source_snapshot_path,
        source_commit=source_commit,
        cli_args=cli_args,
        run_config=snapshot.run_config,
        generated_at_utc=generated_at_utc,
        frontend_snapshot_path=dashboard_snapshot_path,
        decision_intent_path=None,
        data_access=data_access,
    )
    _build_manifest(
        manifest_path=source_review_manifest_path,
        scorecard_path=scorecard_path,
        snapshot_path=source_snapshot_path,
        source_commit=source_commit,
        cli_args=cli_args,
        run_config=snapshot.run_config,
        generated_at_utc=generated_at_utc,
        frontend_snapshot_path=dashboard_snapshot_path,
        decision_intent_path=source_sidecar_path,
        data_access=data_access,
    )
    _add_copy_hashes(
        source_review_manifest_path,
        dashboard_sidecar_path=dashboard_sidecar_path,
    )
    _build_manifest(
        manifest_path=dashboard_manifest_path,
        scorecard_path=scorecard_path,
        snapshot_path=source_snapshot_path,
        source_commit=source_commit,
        cli_args=cli_args,
        run_config=snapshot.run_config,
        generated_at_utc=generated_at_utc,
        frontend_snapshot_path=dashboard_snapshot_path,
        decision_intent_path=dashboard_sidecar_path,
        data_access=data_access,
    )
    _add_copy_hashes(
        dashboard_manifest_path,
        dashboard_sidecar_path=dashboard_sidecar_path,
    )

    outputs = {
        "dashboard_decision_intent": dashboard_sidecar_path,
        "dashboard_manifest": dashboard_manifest_path,
        "dashboard_snapshot": dashboard_snapshot_path,
        "source_decision_intent": source_sidecar_path,
        "source_manifest": source_manifest_path,
        "source_review_manifest": source_review_manifest_path,
        "source_snapshot": source_snapshot_path,
    }
    print(json.dumps(_jsonable_summary(outputs), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
