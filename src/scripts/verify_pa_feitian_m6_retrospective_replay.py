"""Build or verify the M6 retrospective-finalized epistemic gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.retrospective_replay import (  # noqa: E402
    build_replay_evidence,
    verify_replay_evidence,
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--historical-audit", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--availability", type=Path, required=True)
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    values = {
        "contract": _load(args.contract),
        "contract_path": args.contract,
        "protocol": _load(args.protocol),
        "protocol_path": args.protocol,
        "historical_audit": _load(args.historical_audit),
        "historical_audit_path": args.historical_audit,
        "provenance": _load(args.provenance),
        "provenance_path": args.provenance,
        "availability": _load(args.availability),
        "availability_path": args.availability,
    }
    if args.build:
        built = build_replay_evidence(**values)
        args.artifact.parent.mkdir(parents=True, exist_ok=True)
        args.artifact.write_text(json.dumps(built, indent=2, sort_keys=True) + "\n")
    result = verify_replay_evidence(_load(args.artifact), **values)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
