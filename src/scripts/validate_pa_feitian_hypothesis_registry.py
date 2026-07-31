#!/usr/bin/env python3
"""Validate the frozen PA/Feitian Phase 1 hypothesis registry."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[1]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from engine.pa_feitian.hypothesis_registry import validate_registry_files  # noqa: E402


DEFAULT_REGISTRY = "docs/research/pa-feitian-phase1-hypothesis-registry-v1.json"
DEFAULT_LOCK = "docs/research/pa-feitian-phase1-hypothesis-registry-v1.lock.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--registry", default=DEFAULT_REGISTRY)
    parser.add_argument("--lock", default=DEFAULT_LOCK)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    result = validate_registry_files(
        registry_path=repo_root / args.registry,
        lock_path=repo_root / args.lock,
        repo_root=repo_root,
    )
    print(
        "PA/Feitian Phase 1 hypothesis registry verification passed "
        f"({result['registry_sha256']}, "
        f"{result['selected_experiment_design_sha256']})"
    )


if __name__ == "__main__":
    main()
