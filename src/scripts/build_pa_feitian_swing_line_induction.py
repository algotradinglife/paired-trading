#!/usr/bin/env python3
"""Build the public-safe M6 exploratory causal swing-line atlas."""

from __future__ import annotations

import argparse
from pathlib import Path

from engine.pa_feitian.swing_induction import canonical_json_bytes
from engine.pa_feitian.swing_line_induction import build_from_data_root
from engine.pa_feitian.swing_line_induction import validate_atlas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    protocol = args.protocol if args.protocol.is_absolute() else repo_root / args.protocol
    artifact = build_from_data_root(
        repo_root=repo_root,
        data_root=args.data_root,
        protocol_path=protocol,
    )
    validate_atlas(artifact)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(canonical_json_bytes(artifact))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
