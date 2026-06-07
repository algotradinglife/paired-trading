"""Daily ag options near-ATM refresh — designed for launchd automation.

Reads latest ag futures close, computes near-ATM OTM strikes (same logic
as cn_ag_selector), then refreshes ag2607+ag2608 options via TqSdk.

Runs in ~30s for 6 contracts (3 strikes × C/P × current month).
Add next month (--next-months 2) to cover both ag2607 and ag2608.

Auth: TQ_USERNAME + TQ_PASSWORD from env (source ~/.zshrc first).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
BARS_FILE = SRC_DIR / "data" / "raw" / "kq_m_shfe_ag_daily.json"

# OTM strike offsets matching cn_ag_selector
_OTM_OFFSETS = [0.0171, 0.0293, 0.0414]
_STRIKE_STEP = 100


def _latest_ag_close() -> float:
    data = json.loads(BARS_FILE.read_text())
    bars = [b for b in data["bars"] if b.get("close", 0) > 0]
    if not bars:
        raise RuntimeError(f"No bars in {BARS_FILE}")
    return float(bars[-1]["close"])


def _compute_strikes(price: float) -> list[int]:
    return [round(price * (1 + o) / _STRIKE_STEP) * _STRIKE_STEP for o in _OTM_OFFSETS]


def _active_months(n: int) -> list[str]:
    """Return next n monthly contract months in YYMM format starting from today."""
    today = date.today()
    months = []
    m, y = today.month, today.year
    for _ in range(n):
        months.append(f"{str(y)[2:]}{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def main() -> int:
    ap = argparse.ArgumentParser(description="Daily ag options near-ATM refresh")
    ap.add_argument("--next-months", type=int, default=1,
                    help="Number of active months to refresh (default: 1 = current only)")
    ap.add_argument("--extra-strikes", nargs="*", type=int, default=[],
                    help="Additional strike prices to include")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print command without executing")
    args = ap.parse_args()

    if not os.environ.get("TQ_USERNAME") or not os.environ.get("TQ_PASSWORD"):
        print("ERROR: TQ_USERNAME + TQ_PASSWORD required. Run via: zsh -c 'source ~/.zshrc && ...'",
              file=sys.stderr)
        return 2

    price = _latest_ag_close()
    strikes = _compute_strikes(price) + list(args.extra_strikes)
    months = _active_months(args.next_months)

    print(f"ag latest close: {price:.0f}")
    print(f"Computed strikes: {strikes}")
    print(f"Months: {months}")

    cmd = [
        sys.executable,
        str(SRC_DIR / "scripts" / "backfill_ag_options_tqsdk.py"),
        "--months", *months,
        "--strikes", *[str(s) for s in strikes],
        "--overwrite",
    ]

    if args.dry_run:
        print("DRY RUN:", " ".join(cmd))
        return 0

    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    sys.exit(main())
