#!/usr/bin/env python3
"""Build a public-safe exploratory daily swing atlas from one data root."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from engine.pa_feitian.swing_induction import build_from_data_root, canonical_json_bytes


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-series-per-product", type=int, default=4)
    args = parser.parse_args()
    artifact = build_from_data_root(
        data_root=args.data_root,
        protocol_sha256=sha256_file(args.protocol),
        max_series_per_product=args.max_series_per_product,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(canonical_json_bytes(artifact))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
