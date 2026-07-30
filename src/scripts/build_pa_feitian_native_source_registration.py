#!/usr/bin/env python3
"""Build the public-safe Issue #58 real native-source registration audit."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.native_source_registration import (
    build_audit,
    load_contract_capture,
    pretty_json_bytes,
)


def atomic_write(path: Path, parent_descriptor: int, content: bytes) -> None:
    temporary_name = f".{path.name}.{secrets.token_hex(16)}.tmp"
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(temporary_name, flags, 0o600, dir_fd=parent_descriptor)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            temporary_name,
            path.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        os.fsync(parent_descriptor)
    finally:
        try:
            os.unlink(temporary_name, dir_fd=parent_descriptor)
        except FileNotFoundError:
            pass


def safe_output_path(path: Path, *, data_root: Path, contract_path: Path) -> tuple[Path, int]:
    parent = path.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError("output parent must already exist")
    output = parent / path.name
    if output.is_symlink():
        raise ValueError("output must not be a symlink")
    data_root_resolved = data_root.resolve(strict=True)
    if output == data_root_resolved or data_root_resolved in output.parents:
        raise ValueError("output must be outside the read-only data root")
    if output == contract_path:
        raise ValueError("output must not overwrite the contract")
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    parent_descriptor = os.open(parent, directory_flags)
    if not os.path.samestat(os.stat(parent, follow_symlinks=False), os.fstat(parent_descriptor)):
        os.close(parent_descriptor)
        raise ValueError("output parent changed during validation")
    return output, parent_descriptor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    contract_path = args.contract.resolve(strict=True)
    data_root = args.data_root.absolute()
    if data_root.is_symlink():
        raise ValueError("data root must not be a symlink")
    output, parent_descriptor = safe_output_path(
        args.output,
        data_root=data_root,
        contract_path=contract_path,
    )
    try:
        contract, contract_bytes = load_contract_capture(contract_path)
        audit = build_audit(
            contract=contract,
            contract_path=contract_path,
            contract_bytes=contract_bytes,
            data_root=data_root,
            workers=args.workers,
        )
        atomic_write(output, parent_descriptor, pretty_json_bytes(audit))
    finally:
        os.close(parent_descriptor)
    print(
        json.dumps(
            {
                "ok": True,
                "matrix_cells": len(audit["cells"]),
                "source_files": audit["source"]["source_file_count"],
                "verdict": audit["verdict"]["status"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
