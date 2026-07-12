#!/usr/bin/env python3
"""Build public-safe M6 AU/AG liquid-premium unit membership."""

from __future__ import annotations

import argparse
from pathlib import Path

from engine.pa_feitian.liquid_premium_membership import (
    build_membership,
    load_contract,
    write_artifact,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--eligibility-contract", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    contract = load_contract(args.contract)
    artifact = build_membership(
        contract=contract,
        contract_path=args.contract,
        eligibility_contract_path=args.eligibility_contract,
        data_root=args.data_root,
        repo_root=args.repo_root,
        workers=args.workers,
    )
    write_artifact(artifact, args.output)


if __name__ == "__main__":
    main()
