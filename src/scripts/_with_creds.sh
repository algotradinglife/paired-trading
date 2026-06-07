#!/usr/bin/env bash
# Load credentials from macOS keychain into env vars, then exec the command.
#
# Each service has a fixed set of account names it expects:
#   tqsdk      → TQ_USERNAME, TQ_PASSWORD
#   polygon    → POLYGON_PROXY_KEY
#   qveris     → QVERIS_API_KEY
#   minishare  → MINISHARE_API_KEY
#
# Setup once (per service):
#   security add-generic-password -s "<service>" -a "<ACCOUNT>" -w
# Inspect what's stored:
#   security find-generic-password -s "<service>" -a "<ACCOUNT>"
#
# Usage:
#   scripts/_with_creds.sh tqsdk uv run python scripts/fetch_tqsdk.py ...
#   scripts/_with_creds.sh polygon uv run python scripts/fetch_polygon.py ...
#
# Creds never enter shell history (no -c arg) or process listing (`security`
# call is wrapped by the parent process).
set -euo pipefail

if [ $# -lt 2 ]; then
  echo "usage: $0 <service> <command> [args...]" >&2
  echo "  services: tqsdk, polygon, qveris, minishare" >&2
  exit 2
fi

SERVICE="$1"
shift

# Per-service account list
case "$SERVICE" in
  tqsdk)      ACCOUNTS=("TQ_USERNAME" "TQ_PASSWORD") ;;
  polygon)    ACCOUNTS=("POLYGON_PROXY_KEY") ;;
  qveris)     ACCOUNTS=("QVERIS_API_KEY") ;;
  minishare)  ACCOUNTS=("MINISHARE_API_KEY") ;;
  *)          echo "unknown service: $SERVICE" >&2; exit 2 ;;
esac

for ACCOUNT in "${ACCOUNTS[@]}"; do
  VAL=$(security find-generic-password -s "$SERVICE" -a "$ACCOUNT" -w 2>/dev/null || true)
  if [ -z "$VAL" ]; then
    echo "ERROR: keychain entry missing — service=$SERVICE account=$ACCOUNT" >&2
    echo "Set with: security add-generic-password -s \"$SERVICE\" -a \"$ACCOUNT\" -w" >&2
    exit 2
  fi
  export "$ACCOUNT"="$VAL"
done

exec "$@"
