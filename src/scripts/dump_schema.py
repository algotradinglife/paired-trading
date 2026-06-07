"""Dump JSON Schema for AnalysisOutput to doc/.

Run after schema changes:
  uv run python scripts/dump_schema.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.output.envelope import SCHEMA_VERSION, AnalysisOutput

OUT_DIR = Path(__file__).resolve().parents[2] / "doc" / "schemas"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    schema = AnalysisOutput.model_json_schema()
    path = OUT_DIR / f"analysis-output-{SCHEMA_VERSION}.schema.json"
    path.write_text(json.dumps(schema, indent=2))
    print(f"Wrote schema to {path} ({len(json.dumps(schema))} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
