#!/usr/bin/env python3
"""Build public-safe M6 AU/AG bare-K liquidity evidence."""

from __future__ import annotations

import argparse
from pathlib import Path

from engine.pa_feitian.liquid_premium_evidence import (
    build_evidence,
    load_contract,
    write_evidence,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--quant-repo", type=Path, required=True)
    parser.add_argument("--paired-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = load_contract(args.contract)
    artifact = build_evidence(
        contract=contract,
        contract_path=args.contract,
        data_root=args.data_root,
        paired_repo=args.paired_repo,
        quant_repo=args.quant_repo,
    )
    write_evidence(artifact, args.output)


if __name__ == "__main__":
    main()
