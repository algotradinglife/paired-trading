#!/usr/bin/env python3
"""Verify and deterministically regenerate the explicit PA alert corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.pa_feitian.explicit_pa_alerts import (
    build_from_bound_files,
    canonical_json_bytes,
    load_materialization_contract,
    validate_alert_corpus,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    contract_path = args.contract if args.contract.is_absolute() else repo_root / args.contract
    artifact_path = args.artifact if args.artifact.is_absolute() else repo_root / args.artifact
    contract = load_materialization_contract(contract_path)
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    validate_alert_corpus(artifact, contract=contract)
    regenerated = build_from_bound_files(repo_root=repo_root, contract_path=contract_path)
    if canonical_json_bytes(artifact) != canonical_json_bytes(regenerated):
        raise SystemExit("explicit PA alert artifact is not deterministic")
    print(
        "verified explicit PA alerts: "
        f"records={artifact['coverage']['input_records']} alerts={artifact['coverage']['alerts']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
