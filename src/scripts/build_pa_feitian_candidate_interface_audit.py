"""Build the Phase 1 public-safe candidate-interface audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.candidate_interface_audit import (
    build_audit,
    load_contract,
    pretty_json_bytes,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    contract = load_contract(args.contract)
    audit = build_audit(
        contract=contract,
        contract_path=args.contract,
        data_root=args.data_root,
        workers=args.workers,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(pretty_json_bytes(audit))
    print(
        json.dumps(
            {
                "ok": True,
                "families": len(audit["decision_surface"]),
                "matched_candidate_files": audit["source"]["matched_candidate_files"],
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
