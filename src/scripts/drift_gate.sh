#!/usr/bin/env bash
# Baseline drift gate — run `validate_baselines.py --full` and alert only on a
# real runtime DRIFT_DETECTED. Known STALE / PENDING lanes are NOT treated as
# drift (they are accepted states), so this won't cry wolf every week.
#
# Intended to run from cron weekly. Requires: the external Parquet drive mounted
# and (on macOS, under cron) Full Disk Access granted to cron. If the drive is
# not mounted the full_stack run fails and is logged — no false DRIFT alert.
#
# Logs: <repo>/logs/drift-gate/drift_<ts>.log ; alerts appended to ALERTS.log.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
SRC="$REPO/src"
LOG_DIR="$REPO/logs/drift-gate"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d_%H%M)"
LOG="$LOG_DIR/drift_$TS.log"

# cron runs with a minimal env (no profile). Mirror the project's data env so
# paths resolve the same as an interactive run; keep any value already exported.
export DERIVED_ROOT="${DERIVED_ROOT:-/Volumes/Data Drive/derived}"
export MARKET_DATA="${MARKET_DATA:-/Volumes/Data Drive/data}"

cd "$SRC" || { echo "drift_gate: cannot cd $SRC" >&2; exit 2; }
if [ ! -x .venv/bin/python ]; then
  echo "drift_gate: .venv/bin/python not found in $SRC" | tee -a "$LOG" >&2
  exit 2
fi

.venv/bin/python scripts/validate_baselines.py --full >"$LOG" 2>&1
status=$?

# Alert when EITHER:
#  - a row's STATUS is drift ([DRFT] icon) — a real, non-masked drift on a
#    healthy lane (the known-broken STALE climax lane prints "DRIFT_DETECTED" in
#    its repro line but stays [STAL], so matching the icon avoids crying wolf); OR
#  - full_stack produced no per-lane data (FULL_STACK_UNAVAILABLE) — a zero-trade
#    collapse or data outage that would otherwise pass silently.
if grep -qF '[DRFT]' "$LOG" || grep -q 'FULL_STACK_UNAVAILABLE' "$LOG"; then
  echo "$(date '+%F %T')  DRIFT/UNAVAILABLE — see $LOG" >>"$LOG_DIR/ALERTS.log"
  /usr/bin/osascript -e 'display notification "Baseline drift gate fired — see logs/drift-gate/ALERTS.log" with title "paired-trading drift gate"' 2>/dev/null || true
fi

# retain only the 12 most-recent run logs (portable: no GNU-only `xargs -r`,
# which BSD/macOS xargs rejects — the documented cron environment)
ls -1t "$LOG_DIR"/drift_*.log 2>/dev/null | tail -n +13 | while IFS= read -r f; do
  rm -f "$f"
done

exit "$status"
