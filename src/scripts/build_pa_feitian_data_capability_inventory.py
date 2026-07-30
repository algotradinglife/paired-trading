"""Build the frozen Phase 1 public-safe data capability inventory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.data_capability_inventory import (
    build_inventory,
    load_contract,
    pretty_json_bytes,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    contract = load_contract(args.contract)
    artifact = build_inventory(
        contract=contract,
        contract_path=args.contract,
        repo_root=args.repo_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(pretty_json_bytes(artifact))
    print(
        json.dumps(
            {
                "ok": True,
                "status": artifact["decision"]["status"],
                "usable_family_count": artifact["decision"]["usable_family_count"],
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
