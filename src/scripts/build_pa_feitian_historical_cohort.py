"""Build the frozen, bounded PA / Feitian historical cohort research gate."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.historical_cohort import run_historical_cohort  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Replay only frozen M4 decision artifacts through bounded M5 premium mechanics. "
            "This command never runs score_today, discovers contracts, trades, or executes."
        )
    )
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--quant-data-root", type=Path, required=True)
    parser.add_argument("--audit-out", type=Path, required=True)
    parser.add_argument("--baseline-out", type=Path, required=True)
    parser.add_argument("--candidate-out", type=Path, required=True)
    parser.add_argument("--report-out", type=Path, required=True)
    parser.add_argument("--generated-at-utc", type=_utc, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args(argv)
    outputs = [
        args.audit_out.resolve(),
        args.baseline_out.resolve(),
        args.candidate_out.resolve(),
        args.report_out.resolve(),
    ]
    if len(set(outputs)) != len(outputs):
        parser.error("output paths must be distinct")
    report = run_historical_cohort(
        protocol_path=args.protocol,
        repo_root=REPO_ROOT,
        quant_data_root=args.quant_data_root,
        audit_out=args.audit_out,
        baseline_out=args.baseline_out,
        candidate_out=args.candidate_out,
        report_out=args.report_out,
        generated_at_utc=args.generated_at_utc,
        source_commit=args.source_commit,
    )
    print(
        json.dumps(
            {
                "gate": report["threshold_gates"]["screening"]["classification"],
                "eligible": report["coverage_funnel"]["eligible_rows"],
                "excluded": report["coverage_funnel"]["excluded_rows"],
                "paired": report["pooled_descriptive"]["comparable_event_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
