"""Build frozen decision-time PA / Feitian input and coverage artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.continuous_source_audit import (  # noqa: E402
    run_continuous_source_audit,
)


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit the six bounded continuous candidates only. No detector run, "
            "source discovery, contract selection, outcome traversal, or execution."
        )
    )
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--quant-data-root", type=Path, required=True)
    parser.add_argument("--artifact-out", type=Path, required=True)
    parser.add_argument("--audit-out", type=Path, required=True)
    parser.add_argument("--generated-at-utc", type=_utc, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args(argv)
    if args.artifact_out.resolve() == args.audit_out.resolve():
        parser.error("artifact and audit output paths must be distinct")
    audit = run_continuous_source_audit(
        protocol_path=args.protocol,
        continuous_root=args.quant_data_root / "continuous",
        artifact_out=args.artifact_out,
        audit_out=args.audit_out,
        generated_at_utc=args.generated_at_utc,
        source_commit=args.source_commit,
    )
    print(
        json.dumps(
            {
                "sources": len(audit["source_audit"]),
                "aggregations": len(audit["aggregation_audit"]),
                "gate": audit["gate"]["classification"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
