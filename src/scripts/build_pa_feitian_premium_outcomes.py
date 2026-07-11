"""Build PA / Feitian M5 premium outcome sidecars from explicit M4 artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.manifest import (  # noqa: E402
    build_run_manifest,
    load_run_manifest,
    sha256_file,
    write_run_manifest,
)
from engine.pa_feitian.premium_outcome import (  # noqa: E402
    load_premium_outcome,
    premium_outcome_to_jsonable,
    write_premium_outcome,
)
from engine.pa_feitian.premium_outcome_harness import (  # noqa: E402
    DEFAULT_GENERATED_AT_UTC,
    DEFAULT_MAX_HOLDING_BARS,
    DEFAULT_POLICY_ID,
    DEFAULT_POLICY_VERSION,
    DEFAULT_SLIPPAGE_TICKS,
    DEFAULT_STOP_FRACTION_OF_ENTRY,
    DEFAULT_TARGET_MULTIPLES_OF_ENTRY,
    PremiumOutcomeHarnessConfig,
    build_premium_outcome_sidecar_from_files,
)
from engine.pa_feitian.schema_validation import (  # noqa: E402
    validate_pa_feitian_premium_outcome_schema,
    validate_pa_feitian_run_manifest_schema,
)


SRC_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC_ROOT.parent
SCRIPT_PATH = SRC_ROOT / "scripts" / "build_pa_feitian_premium_outcomes.py"


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
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
        return "5a6e2c9"


def _repo_path(path: str | Path) -> Path:
    raw = Path(path)
    return raw if raw.is_absolute() else REPO_ROOT / raw


def _repo_relative(path: str | Path) -> str:
    raw = Path(path)
    try:
        return raw.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return raw.as_posix()


def _copy_artifact(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)


def _manifest_ref_path(path: str | Path) -> str:
    return _repo_relative(_repo_path(path))


def _recorded_cli_args(raw_argv: list[str], quant_data_root_label: str | None) -> list[str]:
    recorded = [_repo_relative(SCRIPT_PATH), *raw_argv]
    if quant_data_root_label is None:
        return recorded

    for index, value in enumerate(recorded):
        if value == "--quant-data-root" and index + 1 < len(recorded):
            recorded[index + 1] = quant_data_root_label
            break
        if value.startswith("--quant-data-root="):
            recorded[index] = f"--quant-data-root={quant_data_root_label}"
            break
    return recorded


def _m5_data_access(
    source_m4_manifest,
    quant_data_root: Path,
    recorded_quant_data_root: str,
) -> dict[str, object]:
    daily_dir = quant_data_root / "daily"
    source_status = source_m4_manifest.data_access.status
    source_notes = list(source_m4_manifest.data_access.notes)
    if not daily_dir.is_dir():
        return {
            "status": "data_blocked",
            "source": recorded_quant_data_root,
            "notes": [
                *source_notes,
                "OptionStore daily directory is unavailable for M5 premium outcome traversal",
            ],
        }
    if source_status in {"fixture_fallback", "data_blocked", "unknown"}:
        return {
            "status": source_status,
            "source": recorded_quant_data_root,
            "notes": [
                *source_notes,
                "M5 preserved source M4 data-access classification",
                f"OptionStore daily root available: {recorded_quant_data_root}",
            ],
        }
    return {
        "status": "real_data_available",
        "source": recorded_quant_data_root,
        "notes": [
            *source_notes,
            "M5 consumed explicit M4 artifacts and OptionStore daily bars only",
            "M5 did not scan score_today and did not select or reselect contracts",
        ],
    }


def _write_m5_manifest(
    *,
    manifest_out: Path,
    source_m4_manifest_path: Path,
    premium_outcome_path: Path,
    frontend_outcome_copy: Path | None,
    cli_args: list[str],
    source_commit: str,
    generated_at_utc: datetime,
    quant_data_root: Path,
    recorded_quant_data_root: str,
    policy_declared_at_utc: datetime,
    traversal_started_at_utc: datetime,
    policy_config: PremiumOutcomeHarnessConfig,
) -> None:
    source_m4_manifest = load_run_manifest(source_m4_manifest_path)
    outcome_sidecar = load_premium_outcome(premium_outcome_path)
    snapshot_frontend_copy_path = (
        _manifest_ref_path(source_m4_manifest.frontend_copy_path)
        if source_m4_manifest.frontend_copy_path is not None
        else None
    )
    manifest = build_run_manifest(
        scorecard_path=_manifest_ref_path(source_m4_manifest.scorecard_artifact.path),
        snapshot_path=_manifest_ref_path(source_m4_manifest.snapshot_artifact.path),
        source_commit=source_commit,
        cli_args=cli_args,
        run_config={
            "contract": "pa_feitian_premium_outcome_v1",
            "mode": "premium_outcome_harness",
            "producer": _repo_relative(SCRIPT_PATH),
            "source_m4_manifest": _repo_relative(source_m4_manifest_path),
            "quant_data_root": recorded_quant_data_root,
            "policy_id": policy_config.policy_id,
            "policy_version": policy_config.policy_version,
            "slippage_ticks": policy_config.slippage_ticks,
            "stop_fraction_of_entry": policy_config.stop_fraction_of_entry,
            "target_multiples_of_entry": list(policy_config.target_multiples_of_entry),
            "max_holding_bars": policy_config.max_holding_bars,
            "policy_declared_at_utc": policy_declared_at_utc.isoformat().replace("+00:00", "Z"),
            "traversal_started_at_utc": traversal_started_at_utc.isoformat().replace(
                "+00:00", "Z"
            ),
            "observation_only": True,
            "no_contract_reselection": True,
        },
        generated_at_utc=generated_at_utc,
        frontend_copy_path=snapshot_frontend_copy_path,
        decision_intent_path=(
            _manifest_ref_path(source_m4_manifest.decision_intent_artifact.path)
            if source_m4_manifest.decision_intent_artifact is not None
            else None
        ),
        premium_outcome_path=_repo_relative(premium_outcome_path),
        data_access=_m5_data_access(
            source_m4_manifest,
            quant_data_root,
            recorded_quant_data_root,
        ),
    )
    manifest.input_hashes.update(outcome_sidecar.provenance.input_hashes)
    manifest.input_hashes["source_m4_manifest"] = outcome_sidecar.provenance.input_hashes[
        "source_manifest"
    ]
    if frontend_outcome_copy is not None:
        manifest.output_hashes["frontend_premium_outcome_copy"] = sha256_file(
            frontend_outcome_copy
        )
    write_run_manifest(manifest, manifest_out)
    validate_pa_feitian_run_manifest_schema(json.loads(manifest_out.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        description="Build deterministic M5 PA/Feitian premium outcome sidecar and manifest."
    )
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--decision-intent", type=Path, required=True)
    parser.add_argument("--source-m4-manifest", type=Path, required=True)
    parser.add_argument("--quant-data-root", type=Path, required=True)
    parser.add_argument(
        "--quant-data-root-label",
        default=None,
        help="Stable public label recorded in artifacts instead of the runtime filesystem root.",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest-out", type=Path, required=True)
    parser.add_argument(
        "--frontend-outcome-copy",
        type=Path,
        default=None,
        help="Optional frontend/dashboard copy of the generated premium outcome sidecar.",
    )
    parser.add_argument(
        "--generated-at-utc",
        default=DEFAULT_GENERATED_AT_UTC.isoformat().replace("+00:00", "Z"),
    )
    parser.add_argument(
        "--policy-declared-at-utc",
        default=None,
        help="Fixed retrospective policy declaration timestamp. Defaults to generated-at.",
    )
    parser.add_argument(
        "--traversal-started-at-utc",
        default=None,
        help="Fixed traversal timestamp. Defaults to policy-declared-at + one minute.",
    )
    parser.add_argument("--policy-id", default=DEFAULT_POLICY_ID)
    parser.add_argument("--policy-version", default=DEFAULT_POLICY_VERSION)
    parser.add_argument("--slippage-ticks", type=float, default=DEFAULT_SLIPPAGE_TICKS)
    parser.add_argument(
        "--stop-fraction-of-entry", type=float, default=DEFAULT_STOP_FRACTION_OF_ENTRY
    )
    parser.add_argument(
        "--target-multiple-of-entry",
        type=float,
        action="append",
        default=None,
        help="Repeatable entry-relative target multiple; defaults to the v1 policy target.",
    )
    parser.add_argument("--max-holding-bars", type=int, default=DEFAULT_MAX_HOLDING_BARS)
    parser.add_argument("--source-commit", default=None)
    args = parser.parse_args(raw_argv)

    snapshot_path = _repo_path(args.snapshot)
    decision_intent_path = _repo_path(args.decision_intent)
    source_manifest_path = _repo_path(args.source_m4_manifest)
    quant_data_root = _repo_path(args.quant_data_root)
    out_path = _repo_path(args.out)
    manifest_out = _repo_path(args.manifest_out)
    frontend_copy = (
        _repo_path(args.frontend_outcome_copy) if args.frontend_outcome_copy is not None else None
    )
    generated_at_utc = _parse_utc(args.generated_at_utc)
    policy_declared_at_utc = (
        _parse_utc(args.policy_declared_at_utc)
        if args.policy_declared_at_utc is not None
        else generated_at_utc
    )
    traversal_started_at_utc = (
        _parse_utc(args.traversal_started_at_utc)
        if args.traversal_started_at_utc is not None
        else policy_declared_at_utc + timedelta(minutes=1)
    )
    source_commit = args.source_commit or _git_head()
    recorded_quant_data_root = args.quant_data_root_label or _repo_relative(quant_data_root)
    cli_args = _recorded_cli_args(raw_argv, args.quant_data_root_label)

    config = PremiumOutcomeHarnessConfig(
        source_commit=source_commit,
        generated_at_utc=generated_at_utc,
        policy_declared_at_utc=policy_declared_at_utc,
        traversal_started_at_utc=traversal_started_at_utc,
        policy_id=args.policy_id,
        policy_version=args.policy_version,
        slippage_ticks=args.slippage_ticks,
        stop_fraction_of_entry=args.stop_fraction_of_entry,
        target_multiples_of_entry=tuple(
            args.target_multiple_of_entry or DEFAULT_TARGET_MULTIPLES_OF_ENTRY
        ),
        max_holding_bars=args.max_holding_bars,
        cli_args=tuple(cli_args),
        recorded_quant_data_root=recorded_quant_data_root,
    )
    sidecar = build_premium_outcome_sidecar_from_files(
        snapshot_path=snapshot_path,
        decision_intent_path=decision_intent_path,
        source_manifest_path=source_manifest_path,
        quant_data_root=quant_data_root,
        config=config,
        path_formatter=_repo_relative,
    )
    write_premium_outcome(sidecar, out_path)
    loaded = load_premium_outcome(out_path)
    validate_pa_feitian_premium_outcome_schema(premium_outcome_to_jsonable(loaded))

    if frontend_copy is not None:
        _copy_artifact(out_path, frontend_copy)

    _write_m5_manifest(
        manifest_out=manifest_out,
        source_m4_manifest_path=source_manifest_path,
        premium_outcome_path=out_path,
        frontend_outcome_copy=frontend_copy,
        cli_args=cli_args,
        source_commit=source_commit,
        generated_at_utc=generated_at_utc,
        quant_data_root=quant_data_root,
        recorded_quant_data_root=recorded_quant_data_root,
        policy_declared_at_utc=policy_declared_at_utc,
        traversal_started_at_utc=traversal_started_at_utc,
        policy_config=config,
    )
    print(
        json.dumps(
            {
                "premium_outcome": _repo_relative(out_path),
                "manifest": _repo_relative(manifest_out),
                "frontend_outcome_copy": (
                    _repo_relative(frontend_copy) if frontend_copy is not None else None
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
