"""CLI entrypoint for `build_analysis_output` — the canonical consumer API.

Usage:
  uv run python scripts/analyze.py SPY                           # default: topology A, us_equity
  uv run python scripts/analyze.py SPY --topology B              # options strategy
  uv run python scripts/analyze.py kq_m_cffex_if \\
      --topology B --instrument-class cn_futures                 # CN futures
  uv run python scripts/analyze.py SPY --pretty -o out.json      # write to file
  uv run python scripts/analyze.py SPY --bars-dir /tmp/snapshots # custom data dir

Resolves bar snapshots from `<bars_dir>/<symbol_lower>_{daily,60,15,weekly}.json`
(matches fetch_polygon / fetch_akshare / fetch_tqsdk output convention).

Topology A requires daily + 60 + weekly snapshots.
Topology B requires daily + 60 + 15 snapshots.

Outputs the AnalysisOutput envelope (schema v1.2) as JSON. Use --pretty for
indented output suitable for human reading; default is compact (one-line)
suitable for piping into another tool.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from data import bar_loader
from engine.output.build import build_analysis_output

DEFAULT_BARS_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

# Topology → required level_id → snapshot filename suffix
TOPOLOGY_FILES = {
    "A": {"D": "daily", "1h": "60", "W": "weekly"},
    "B": {"D": "daily", "1h": "60", "15m": "15"},
}


def _load_bars(symbol: str, suffix: str, args) -> pd.DataFrame | None:
    """Load bars preferring BarStore when --quant-data-root is given."""
    if args.quant_data_root is not None:
        exchange = getattr(args, "exchange", None) or bar_loader.infer_exchange_mic(symbol)
        if exchange is not None:
            barstore_level = bar_loader.FILENAME_SUFFIX_TO_BARSTORE_LEVEL.get(suffix)
            if barstore_level is not None:
                try:
                    return bar_loader.load_bars_quant(
                        symbol.upper(), exchange, barstore_level, args.quant_data_root
                    )
                except Exception as e:
                    print(f"quant load {symbol}/{suffix}: {e} — falling back to JSON",
                          file=sys.stderr)
    path = args.bars_dir / f"{symbol.lower()}_{suffix}.json"
    if not path.exists():
        return None
    return bar_loader.load_bars_json(path)


def main() -> int:
    p = argparse.ArgumentParser(
        prog="analyze",
        description="Run the macd-momentum engine and emit AnalysisOutput JSON",
    )
    p.add_argument("symbol",
                   help="symbol stem matching <bars_dir>/<symbol_lower>_<resolution>.json "
                        "(e.g. SPY, kq_m_cffex_if)")
    p.add_argument("--topology", choices=["A", "B"], default="A",
                   help="context topology: A=D+1h+W (stock, default), B=D+15m+1h (options)")
    p.add_argument("--instrument-class", choices=["us_equity", "cn_futures"],
                   default="us_equity", dest="instrument_class",
                   help="calibration table: us_equity (default) or cn_futures")
    p.add_argument("--bars-dir", type=Path, default=DEFAULT_BARS_DIR,
                   help=f"directory containing snapshot JSON files (default: {DEFAULT_BARS_DIR})")
    p.add_argument("--quant-data-root", type=Path, default=bar_loader.DEFAULT_QUANT_ROOT, dest="quant_data_root",
                   help="quant-data Parquet root (default: data/quant/)")
    p.add_argument("--exchange", default=None,
                   help="override MIC exchange (e.g. XNYS, XNAQ, XCFE); inferred by default")
    p.add_argument("--pretty", action="store_true",
                   help="indent output JSON (default: compact one-line)")
    p.add_argument("-o", "--output", type=Path,
                   help="write JSON to this file (default: stdout)")
    args = p.parse_args()

    requirements = TOPOLOGY_FILES[args.topology]
    bars_per_level: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for level_id, resolution_suffix in requirements.items():
        df = _load_bars(args.symbol, resolution_suffix, args)
        if df is None:
            missing.append(f"{args.symbol.lower()}_{resolution_suffix}")
            continue
        bars_per_level[level_id] = df

    if missing:
        print(f"ERROR: topology {args.topology} requires {list(requirements)} levels.",
              file=sys.stderr)
        for m in missing:
            print(f"  missing: {m}", file=sys.stderr)
        hint = ("fetch_quant.py" if args.quant_data_root else
                "fetch_polygon / fetch_akshare / fetch_tqsdk")
        print(f"\nRun {hint} first, or pass --bars-dir.", file=sys.stderr)
        return 2

    output = build_analysis_output(
        symbol=args.symbol,
        bars_per_level=bars_per_level,
        context_topology=args.topology,
        instrument_class=args.instrument_class,
    )

    json_str = output.model_dump_json(indent=2 if args.pretty else None)
    if args.output:
        args.output.write_text(json_str + "\n")
        print(f"Wrote {len(json_str)} bytes to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(json_str)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
