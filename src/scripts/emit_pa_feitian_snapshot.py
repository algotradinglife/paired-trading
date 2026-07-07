"""Emit a PA / Feitian snapshot contract artifact.

By default this writes the deterministic contract fixture. With ``--scorecard``
it consumes an existing score_today JSON output and converts the emitted ag/au
option suggestions into pa_feitian_snapshot_v0. This script does not scan raw
market data itself.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.options.iv_regime import DEFAULT_MAX_RANK, DEFAULT_WARMUP
from engine.pa_feitian.contract import (
    example_snapshot,
    snapshot_from_scorecard_file,
    write_snapshot,
)


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
    parser.add_argument(
        "--scorecard",
        type=Path,
        default=None,
        help="Existing score_today JSON output to convert into a real PA/Feitian snapshot.",
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
    args = parser.parse_args(argv)

    source_commit = args.source_commit or _source_commit()
    generated_at_utc = _parse_generated_at(args.generated_at_utc)
    if args.scorecard is not None:
        snapshot = snapshot_from_scorecard_file(
            args.scorecard,
            source_commit=source_commit,
            generated_at_utc=generated_at_utc,
            max_signals=args.max_signals,
            iv_warmup=args.iv_warmup,
            iv_max_rank=args.iv_max_rank,
        )
    else:
        snapshot = example_snapshot(
            source_commit=source_commit,
            generated_at_utc=generated_at_utc,
        )
    write_snapshot(snapshot, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
