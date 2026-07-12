"""Verify the committed finalized-vintage underlying corpus from pinned inputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.underlying_corpus import verify_external_corpus  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--quant-repo", type=Path, required=True)
    parser.add_argument("--paired-repo", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    args = parser.parse_args()
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
