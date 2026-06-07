#!/usr/bin/env bash
# Stage D: backfill all US ETFs from alphavantage via qveris.
#
# Fetches daily (full history) + 60min + 15min (2021-05 → current month)
# for all 10 US ETFs in the exhaustion pool.  SPY was already done in
# Stage C; skipped here to avoid re-billing unless --include-spy is passed.
#
# Usage (from repo root — requires QVERIS_API_KEY in keychain):
#   scripts/_with_creds.sh qveris uv run bash scripts/backfill_stage_d.sh
#
# Estimated cost:
#   9 symbols × ~95 credits = ~855 credits
#   (1 daily call + ~62 monthly 60min calls + ~62 monthly 15min calls
#    × 1.3 qveris overhead per symbol)
#
# Writes to src/data/raw/<sym>_daily.json, _60.json, _15.json.
# Merges with any existing snapshot (incremental-safe for intraday).
# Daily always overwrites (split-adjusted correctness; see fetch_alphavantage.py).
#
# Set STAGE_D_DRY_RUN=1 to echo commands without executing.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# uv run must execute from the directory containing pyproject.toml
cd "$REPO_ROOT"

# Month range to match Stage C SPY intraday window.
# Adjust END_MONTH when running in a later month.
START_MONTH="2021-05"
END_MONTH="2026-05"

# Full 10-ETF pool. SPY was backfilled in Stage C but is included here
# so `verify_stage_d.py` works on a clean checkout. All fetches are
# idempotent (daily overwrites; intraday merges), so re-running SPY only
# costs 1 extra daily call (~1.3 credits).
# Pass --skip-spy to omit SPY when you know it is already current.
SYMBOLS=(QQQ IWM DIA GLD GDX XLF XLK TLT NVDA SPY)
if [[ "${1:-}" == "--skip-spy" ]]; then
  SYMBOLS=(QQQ IWM DIA GLD GDX XLF XLK TLT NVDA)
fi

DRY_RUN="${STAGE_D_DRY_RUN:-0}"

run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[DRY] $*"
  else
    "$@"
  fi
}

echo "=== Stage D: US ETF backfill ===" >&2
echo "  Symbols : ${SYMBOLS[*]}" >&2
echo "  Intraday: ${START_MONTH} → ${END_MONTH}" >&2
echo "  DRY_RUN : ${DRY_RUN}" >&2
echo "" >&2

for SYM in "${SYMBOLS[@]}"; do
  echo "--- ${SYM} ---" >&2

  echo "[${SYM}] daily (full)" >&2
  run uv run python "${SCRIPT_DIR}/fetch_alphavantage.py" \
    --symbol "$SYM" --tf daily

  echo "[${SYM}] 60min ${START_MONTH} → ${END_MONTH}" >&2
  run uv run python "${SCRIPT_DIR}/fetch_alphavantage.py" \
    --symbol "$SYM" --tf 60min \
    --start-month "$START_MONTH" --end-month "$END_MONTH"

  echo "[${SYM}] 15min ${START_MONTH} → ${END_MONTH}" >&2
  run uv run python "${SCRIPT_DIR}/fetch_alphavantage.py" \
    --symbol "$SYM" --tf 15min \
    --start-month "$START_MONTH" --end-month "$END_MONTH"

  echo "[${SYM}] done" >&2
  echo "" >&2
done

echo "=== Stage D backfill complete ===" >&2
echo "Next: run scripts/verify_stage_d.py to check bar counts," >&2
echo "      then rerun analyze_exhaustion_pool.py --pool US" >&2
