#!/usr/bin/env python3
"""Validate the frozen PA/Feitian Phase 1 v2 hypothesis registry."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[1]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from engine.pa_feitian.hypothesis_registry_v2 import (  # noqa: E402
    validate_registry_v2_files,
)


DEFAULT_REGISTRY = "docs/research/pa-feitian-phase1-hypothesis-registry-v2.json"
DEFAULT_LOCK = "docs/research/pa-feitian-phase1-hypothesis-registry-v2.lock.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    parser.add_argument("--registry", default=DEFAULT_REGISTRY)
    parser.add_argument("--lock", default=DEFAULT_LOCK)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    result = validate_registry_v2_files(
        registry_path=repo_root / args.registry,
        lock_path=repo_root / args.lock,
        repo_root=repo_root,
    )
    print(
        "PA/Feitian Phase 1 hypothesis registry v2 verification passed "
        f"({result['registry_sha256']}, "
        f"{result['selected_experiment_design_sha256']})"
    )


if __name__ == "__main__":
    main()
