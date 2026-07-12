"""Build or verify the frozen M6 finalized-vintage underlying corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.underlying_corpus import (  # noqa: E402
    build_from_external_sources,
    canonical_json_bytes,
    verify_external_corpus,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--quant-repo", type=Path, required=True)
    parser.add_argument("--paired-repo", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    if args.build:
        artifact = build_from_external_sources(
            contract_path=args.contract,
            provenance_path=args.provenance,
            raw_root=args.raw_root,
            quant_repo=args.quant_repo,
            paired_repo=args.paired_repo,
        )
        args.artifact.parent.mkdir(parents=True, exist_ok=True)
        args.artifact.write_bytes(canonical_json_bytes(artifact))
    artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
    result = verify_external_corpus(
        artifact,
        contract_path=args.contract,
        provenance_path=args.provenance,
        raw_root=args.raw_root,
        quant_repo=args.quant_repo,
        paired_repo=args.paired_repo,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
