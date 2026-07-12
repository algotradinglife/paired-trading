#!/usr/bin/env python3
"""Build the frozen explicit PA alert corpus."""

from __future__ import annotations

import argparse
from pathlib import Path

from engine.pa_feitian.explicit_pa_alerts import build_from_bound_files, canonical_json_bytes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    contract = args.contract if args.contract.is_absolute() else repo_root / args.contract
    artifact = build_from_bound_files(repo_root=repo_root, contract_path=contract)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(artifact))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
