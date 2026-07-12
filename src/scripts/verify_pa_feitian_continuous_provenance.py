"""Build or verify the M6 continuous causal-provenance evidence manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.continuous_provenance import build_manifest, verify_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--quant-repo", type=Path, required=True)
    parser.add_argument("--paired-repo", type=Path, required=True)
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    if args.build:
        protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
        payload = build_manifest(
            protocol=protocol,
            protocol_path=args.protocol,
            raw_root=args.raw_root,
            quant_repo=args.quant_repo,
            paired_repo=args.paired_repo,
            quant_commit="804f48915767abbdb848fc54be52f1e85d076567",
            paired_commit="af813b8c06f002433299bf86cc94a73a0c71a511",
        )
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = verify_manifest(
        payload,
        raw_root=args.raw_root,
        quant_repo=args.quant_repo,
        paired_repo=args.paired_repo,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
