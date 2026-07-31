#!/usr/bin/env python3
"""Evaluate one schema-valid Issue #50 historical data-gate request."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.historical_backtest_gate import (
    evaluate_gate_request,
    load_contract,
    pretty_json_bytes,
    strict_json_loads,
    validate_gate_decision,
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


def parse_source_snapshots(values: list[str]) -> tuple[dict[str, Path], set[Path]]:
    snapshots: dict[str, Path] = {}
    paths: set[Path] = set()
    for value in values:
        binding_id, separator, raw_path = value.partition("=")
        if not separator or not binding_id or not raw_path or binding_id in snapshots:
            raise ValueError("--source-snapshot must be a unique BINDING_ID=PATH")
        path = Path(raw_path).resolve()
        if not path.is_file():
            raise ValueError(f"source snapshot is not a file: {path}")
        snapshots[binding_id] = path
        paths.add(path)
    return snapshots, paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument(
        "--source-snapshot",
        action="append",
        default=[],
        metavar="BINDING_ID=PATH",
        help="repeat once for each formal input binding",
    )
    parser.add_argument("--exchange-session-calendar", type=Path, required=True)
    parser.add_argument("--causal-roll-ledger", type=Path, required=True)
    parser.add_argument("--native-source-version-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_snapshots, source_paths = parse_source_snapshots(args.source_snapshot)
    causal_support_artifacts = {
        "native_source_version_manifest": args.native_source_version_manifest.resolve(),
        "exchange_session_calendar": args.exchange_session_calendar.resolve(),
        "causal_roll_ledger": args.causal_roll_ledger.resolve(),
    }
    if any(not path.is_file() for path in causal_support_artifacts.values()):
        raise ValueError("causal support artifacts must be files")
    protected = {
        args.contract.resolve(),
        args.request.resolve(),
        *source_paths,
        *causal_support_artifacts.values(),
    }
    output = safe_output_path(args.output)
    if output in protected:
        raise ValueError("output must not overwrite contract or request")
    contract = load_contract(args.contract)
    request = strict_json_loads(args.request.read_text(encoding="utf-8"))
    if not isinstance(request, dict):
        raise TypeError("request must be a JSON object")
    decision = evaluate_gate_request(
        contract=contract,
        request=request,
        source_snapshots=source_snapshots,
        causal_support_artifacts=causal_support_artifacts,
    )
    validate_gate_decision(
        decision,
        contract=contract,
        request=request,
        source_snapshots=source_snapshots,
        causal_support_artifacts=causal_support_artifacts,
    )
    atomic_write(output, pretty_json_bytes(decision))
    print(
        json.dumps(
            {
                "ok": True,
                "decision": decision["decision"],
                "reason_count": len(decision["reason_codes"]),
                "output": str(output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
