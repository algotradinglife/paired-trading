#!/usr/bin/env python3
"""Build the Issue #53 public-safe exploratory historical swing views."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.exploratory_swing_views import (  # noqa: E402
    build_exploratory_swing_views,
    load_contract,
    pretty_json_bytes,
)


def validate_output_path(
    *,
    output: Path,
    data_root: Path,
    contract: Path,
    candidate_audit: Path,
) -> Path:
    resolved_output = output.expanduser().resolve()
    resolved_root = data_root.expanduser().resolve()
    protected_inputs = {
        contract.expanduser().resolve(),
        candidate_audit.expanduser().resolve(),
    }
    if resolved_output in protected_inputs:
        raise ValueError("output must not overwrite a contract or candidate audit")
    if resolved_output == resolved_root or resolved_root in resolved_output.parents:
        raise ValueError("output must be outside the read-only data root")
    return resolved_output


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--candidate-audit", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    output = validate_output_path(
        output=args.output,
        data_root=args.data_root,
        contract=args.contract,
        candidate_audit=args.candidate_audit,
    )
    contract = load_contract(args.contract)
    candidate_audit = json.loads(args.candidate_audit.read_text(encoding="utf-8"))
    artifact = build_exploratory_swing_views(
        contract=contract,
        contract_path=args.contract,
        candidate_audit=candidate_audit,
        candidate_audit_path=args.candidate_audit,
        data_root=args.data_root,
        workers=args.workers,
    )
    atomic_write(output, pretty_json_bytes(artifact))
    print(
        json.dumps(
            {
                "ok": True,
                "families": len(artifact["family_window_summaries"]),
                "representative_views": len(artifact["representative_swing_views"]),
                "output": str(output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
