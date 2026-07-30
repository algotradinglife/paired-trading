#!/usr/bin/env python3
"""Build the public Issue #50 historical backtest data-gate profile."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.historical_backtest_gate import (
    build_gate_profile,
    load_contract,
    pretty_json_bytes,
)


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def safe_output_path(path: Path) -> Path:
    parent = path.parent.resolve()
    if not parent.is_dir():
        raise ValueError("output parent must already exist")
    output = parent / path.name
    if output.is_symlink():
        raise ValueError("output must not be a symlink")
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    contract_path = args.contract.resolve()
    output = safe_output_path(args.output)
    contract = load_contract(contract_path)
    paths = {row["alias"]: repo_root / row["path"] for row in contract["bound_evidence"]}
    protected = {contract_path, *(path.resolve() for path in paths.values())}
    if output in protected:
        raise ValueError("output must not overwrite contract or bound evidence")
    profile = build_gate_profile(
        contract=contract,
        paths=paths,
    )
    atomic_write(output, pretty_json_bytes(profile))
    print(
        json.dumps(
            {
                "ok": True,
                "families": len(profile["candidate_interface_mapping"]),
                "output": str(output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
