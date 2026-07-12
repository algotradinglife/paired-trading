"""Build or verify the M6 raw acquisition-time availability blocker."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.raw_availability import (  # noqa: E402
    build_blocker_packet,
    verify_blocker_packet,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--paired-repo", type=Path, required=True)
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    provenance = json.loads(args.provenance.read_text(encoding="utf-8"))
    if args.build:
        packet = build_blocker_packet(
            provenance=provenance,
            provenance_path=args.provenance,
            raw_root=args.raw_root,
            paired_repo=args.paired_repo,
        )
        args.packet.parent.mkdir(parents=True, exist_ok=True)
        args.packet.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    result = verify_blocker_packet(
        packet,
        provenance=provenance,
        provenance_path=args.provenance,
        raw_root=args.raw_root,
        paired_repo=args.paired_repo,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
