"""Emit a minimal PA / Feitian snapshot contract artifact.

This v0 producer is a file-backed contract stub. It deliberately does not read
raw data stores or implement strategy scoring; those belong to follow-up
strategy cards after the shared boundary is accepted.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.contract import example_snapshot, write_snapshot


def _source_commit() -> str:
    root = Path(__file__).resolve().parents[2]
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output JSON path for pa_feitian_snapshot_v0.",
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
    args = parser.parse_args(argv)

    snapshot = example_snapshot(
        source_commit=args.source_commit or _source_commit(),
        generated_at_utc=_parse_generated_at(args.generated_at_utc),
    )
    write_snapshot(snapshot, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
