#!/usr/bin/env python3
"""Open the Issue #64 sealed reveal after complete blind annotations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.pa_feitian.historical_bare_k_episode_pack import (
    atomic_write,
    pretty_json_bytes,
    reveal_with_annotations,
    strict_json_loads,
    validate_reveal_output_path,
)


def _load_object(path: Path) -> dict:
    value = strict_json_loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("input must be a JSON object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sealed-reveal", type=Path, required=True)
    parser.add_argument("--blind-annotations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--acknowledge-first-pass-complete",
        action="store_true",
        required=True,
    )
    args = parser.parse_args()

    resolved_output = validate_reveal_output_path(
        output=args.output,
        sealed_reveal=args.sealed_reveal,
        blind_annotations=args.blind_annotations,
        repository_root=Path(__file__).resolve().parents[2],
    )
    payload = reveal_with_annotations(
        sealed=_load_object(args.sealed_reveal),
        annotations=_load_object(args.blind_annotations),
        acknowledge_first_pass_complete=args.acknowledge_first_pass_complete,
    )
    atomic_write(resolved_output, pretty_json_bytes(payload))
    print(
        json.dumps(
            {
                "ok": True,
                "episodes": payload["episode_count"],
                "output": str(resolved_output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
