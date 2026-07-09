"""Deterministic intake for existing score_today JSON artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.pa_feitian.manifest import DataAccessStatus


DEFAULT_SCORE_TODAY_ARTIFACT_GLOB = "*.json"


@dataclass(frozen=True)
class ScoreTodayArtifactIntake:
    scorecard_path: Path | None
    status: DataAccessStatus
    source: str | None
    notes: tuple[str, ...]
    used_fixture_fallback: bool = False

    def data_access(self) -> dict[str, Any]:
        return {"status": self.status, "source": self.source, "notes": list(self.notes)}


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _validation_error(path: Path) -> str | None:
    if not path.exists():
        return f"score_today artifact not found: {path}"
    if not path.is_file():
        return f"score_today artifact path is not a file: {path}"
    try:
        with path.open(encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as exc:
        return f"score_today artifact is not valid JSON: {path}: {exc.msg}"
    if not isinstance(payload, Mapping):
        return f"score_today artifact must be a JSON object: {path}"

    scored = payload.get("scored")
    active_rules = payload.get("active_rules")
    required = ("pool", "instrument_class", "window_days", "active_rules", "scored")
    missing = [key for key in required if key not in payload]
    if missing:
        return f"score_today artifact is missing required key(s) {missing}: {path}"
    if not _is_sequence(active_rules):
        return f"score_today artifact active_rules must be a list: {path}"
    if not _is_sequence(scored):
        return f"score_today artifact scored must be a list: {path}"
    return None


def is_score_today_artifact(path: str | Path) -> bool:
    return _validation_error(Path(path)) is None


def _same_file(left: Path, right: Path | None) -> bool:
    if right is None:
        return False
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left == right


def _fixture_fallback(fixture_path: Path) -> ScoreTodayArtifactIntake:
    error = _validation_error(fixture_path)
    if error is not None:
        return ScoreTodayArtifactIntake(
            scorecard_path=None,
            status="data_blocked",
            source=fixture_path.as_posix(),
            notes=(error,),
        )
    return ScoreTodayArtifactIntake(
        scorecard_path=fixture_path,
        status="fixture_fallback",
        source=fixture_path.as_posix(),
        notes=("deterministic scorecard fixture fallback; no live score_today run was invoked",),
        used_fixture_fallback=True,
    )


def resolve_score_today_artifact(
    *,
    explicit_path: str | Path | None = None,
    artifact_dirs: Sequence[str | Path] = (),
    artifact_glob: str = DEFAULT_SCORE_TODAY_ARTIFACT_GLOB,
    fixture_path: str | Path | None = None,
    allow_fixture_fallback: bool = False,
) -> ScoreTodayArtifactIntake:
    """Resolve one score_today scorecard without touching raw market stores.

    Directory intake is deliberately limited to caller-provided artifact
    directories. Candidate selection is deterministic: valid score_today JSON
    files are sorted by path text and the last path is selected.
    """

    fixture = Path(fixture_path) if fixture_path is not None else None
    if explicit_path is not None:
        path = Path(explicit_path)
        error = _validation_error(path)
        if error is not None:
            return ScoreTodayArtifactIntake(
                scorecard_path=None,
                status="data_blocked",
                source=path.as_posix(),
                notes=(error,),
            )
        status: DataAccessStatus = (
            "fixture_fallback" if _same_file(path, fixture) else "real_data_available"
        )
        notes = (
            "consumed existing score_today JSON artifact; producer did not read raw data stores",
        )
        if status == "fixture_fallback":
            notes = (
                "deterministic scorecard fixture fallback; no live score_today run was invoked",
            )
        return ScoreTodayArtifactIntake(
            scorecard_path=path,
            status=status,
            source=path.as_posix(),
            notes=notes,
            used_fixture_fallback=status == "fixture_fallback",
        )

    valid_candidates: list[Path] = []
    invalid_count = 0
    searched: list[str] = []
    for directory in artifact_dirs:
        root = Path(directory)
        searched.append(root.as_posix())
        if not root.exists() or not root.is_dir():
            invalid_count += 1
            continue
        for candidate in sorted(root.glob(artifact_glob), key=lambda path: path.as_posix()):
            if not candidate.is_file():
                continue
            if _validation_error(candidate) is None:
                valid_candidates.append(candidate)
            else:
                invalid_count += 1

    if valid_candidates:
        unique_candidates = sorted(
            {path.resolve(): path for path in valid_candidates}.values(),
            key=lambda path: path.as_posix(),
        )
        selected = unique_candidates[-1]
        notes = [
            "located existing score_today JSON artifact; producer did not read raw data stores",
            f"selected lexicographically last path from {len(unique_candidates)} valid candidate(s)",
        ]
        if invalid_count:
            notes.append(f"ignored {invalid_count} non-score_today artifact candidate(s)")
        return ScoreTodayArtifactIntake(
            scorecard_path=selected,
            status="real_data_available",
            source=selected.as_posix(),
            notes=tuple(notes),
        )

    if allow_fixture_fallback and fixture is not None:
        return _fixture_fallback(fixture)

    if artifact_dirs:
        searched_text = ", ".join(searched) if searched else "(none)"
        return ScoreTodayArtifactIntake(
            scorecard_path=None,
            status="data_blocked",
            source=None,
            notes=(
                "no valid score_today JSON artifact found in configured artifact directories",
                f"searched: {searched_text}",
            ),
        )

    return ScoreTodayArtifactIntake(
        scorecard_path=None,
        status="unknown",
        source=None,
        notes=("no score_today artifact selector supplied",),
    )
