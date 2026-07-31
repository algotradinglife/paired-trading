#!/usr/bin/env python3
"""Build the deterministic Issue #64 blind/sealed-reveal episode packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.pa_feitian.historical_bare_k_episode_pack import (
    build_episode_pack,
    load_contract,
    validate_output_directory,
    write_episode_pack,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    output = validate_output_directory(
        output_directory=args.output_directory,
        data_root=args.data_root,
        contract_path=args.contract,
    )
    contract = load_contract(args.contract)
    artifacts = build_episode_pack(
        contract=contract,
        contract_path=args.contract,
        data_root=args.data_root,
        workers=args.workers,
    )
    write_episode_pack(output, artifacts)
    print(
        json.dumps(
            {
                "ok": True,
                "episodes": artifacts["blind"]["episode_count"],
                "families": len(artifacts["coverage"]["family_coverage"]),
                "exchanges": len(artifacts["coverage"]["exchange_coverage"]),
                "output_directory": str(output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
