"""Build the frozen M6 historical option-input capability audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pa_feitian.option_input_audit import build_audit, load_contract


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--quant-data-root", type=Path, required=True)
    parser.add_argument("--quant-repo", type=Path, required=True)
    parser.add_argument("--paired-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = load_contract(args.contract)
    artifact = build_audit(
        contract=contract,
        contract_path=args.contract,
        data_root=args.quant_data_root,
        quant_repo=args.quant_repo,
        paired_repo=args.paired_repo,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(args.output)}))


if __name__ == "__main__":
    main()
