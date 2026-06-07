#!/usr/bin/env bash
# CN Bond Futures backfill via qveris (ths_ifind + cn_financial_pro).
#
# Fetches daily (max history) + 60min + 15min (2021-05 → current month)
# for CFFEX treasury bond futures: T (10Y), TF (5Y), TS (2Y).
#
# Qveris THS codes:
#   T00.CFE  → kq_m_cffex_t   (10Y, history from 2018-01)
#   TF00.CFE → kq_m_cffex_tf  (5Y,  history from 2013-09)
#   TS00.CFE → kq_m_cffex_ts  (2Y,  history from 2019-01)
#
# Usage (from repo src/ dir — requires QVERIS_API_KEY in keychain):
#   scripts/_with_creds.sh qveris uv run bash scripts/backfill_cn_bonds.sh
#
# Estimated cost:
#   ~300-400 credits total (3 symbols × daily monthly chunks + intraday wide calls)
#
# Writes to src/data/raw/kq_m_cffex_{t,tf,ts}_{daily,60,15}.json.
# Daily overwrites (full correctness). Intraday: single wide call, overwrites.
#
# Set DRY_RUN=1 to echo commands without executing.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$REPO_ROOT"

START_INTRADAY="2021-05-01"
END_INTRADAY="2026-05-31"

DRY_RUN="${DRY_RUN:-0}"

run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[DRY] $*"
  else
    "$@"
  fi
}

echo "=== CN Bond Futures backfill ===" >&2
echo "  Symbols : T00.CFE TF00.CFE TS00.CFE" >&2
echo "  Intraday: ${START_INTRADAY} → ${END_INTRADAY}" >&2
echo "  DRY_RUN : ${DRY_RUN}" >&2
echo "" >&2

# --- TF00.CFE (5Y, earliest available: 2013-09) ---
echo "--- TF00.CFE (5Y treasury) ---" >&2

echo "[TF] daily 2013-09-01 → ${END_INTRADAY}" >&2
run uv run python "${SCRIPT_DIR}/fetch_qveris.py" \
    TF00.CFE --tf daily --start 2013-09-01 --end "${END_INTRADAY}"

echo "[TF] 60min ${START_INTRADAY} → ${END_INTRADAY}" >&2
run uv run python "${SCRIPT_DIR}/fetch_qveris.py" \
    TF00.CFE --tf 60min --start "${START_INTRADAY}" --end "${END_INTRADAY}"

echo "[TF] 15min ${START_INTRADAY} → ${END_INTRADAY}" >&2
run uv run python "${SCRIPT_DIR}/fetch_qveris.py" \
    TF00.CFE --tf 15min --start "${START_INTRADAY}" --end "${END_INTRADAY}"

echo "[TF] done" >&2
echo "" >&2

# --- T00.CFE (10Y, earliest available: 2018-01) ---
echo "--- T00.CFE (10Y treasury) ---" >&2

echo "[T] daily 2018-01-01 → ${END_INTRADAY}" >&2
run uv run python "${SCRIPT_DIR}/fetch_qveris.py" \
    T00.CFE --tf daily --start 2018-01-01 --end "${END_INTRADAY}"

echo "[T] 60min ${START_INTRADAY} → ${END_INTRADAY}" >&2
run uv run python "${SCRIPT_DIR}/fetch_qveris.py" \
    T00.CFE --tf 60min --start "${START_INTRADAY}" --end "${END_INTRADAY}"

echo "[T] 15min ${START_INTRADAY} → ${END_INTRADAY}" >&2
run uv run python "${SCRIPT_DIR}/fetch_qveris.py" \
    T00.CFE --tf 15min --start "${START_INTRADAY}" --end "${END_INTRADAY}"

echo "[T] done" >&2
echo "" >&2

# --- TS00.CFE (2Y, earliest available: 2019-01) ---
echo "--- TS00.CFE (2Y treasury) ---" >&2

echo "[TS] daily 2019-01-01 → ${END_INTRADAY}" >&2
run uv run python "${SCRIPT_DIR}/fetch_qveris.py" \
    TS00.CFE --tf daily --start 2019-01-01 --end "${END_INTRADAY}"

echo "[TS] 60min ${START_INTRADAY} → ${END_INTRADAY}" >&2
run uv run python "${SCRIPT_DIR}/fetch_qveris.py" \
    TS00.CFE --tf 60min --start "${START_INTRADAY}" --end "${END_INTRADAY}"

echo "[TS] 15min ${START_INTRADAY} → ${END_INTRADAY}" >&2
run uv run python "${SCRIPT_DIR}/fetch_qveris.py" \
    TS00.CFE --tf 15min --start "${START_INTRADAY}" --end "${END_INTRADAY}"

echo "[TS] done" >&2
echo "" >&2

echo "=== CN Bond Futures backfill complete ===" >&2
echo "Files written to src/data/raw/kq_m_cffex_{t,tf,ts}_{daily,60,15}.json" >&2
echo "Next: run backtest_rr_b_single_pool.py or analyze_exhaustion_pool.py --pool CN_BOND" >&2
