#!/usr/bin/env bash

# RAG canary: 10 known-answer questions through the real answer pipeline, then
# the Telegram alert and the admin status file (ops-status/canary.json).
# Called by the nightly run_scraper.sh with its log file, and by the ops
# dispatcher for a manual run (no argument: the canary writes its own log).
# Exits with the canary's own exit code.

set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
CONTAINER_NAME="${INFOHUB_BACKEND_CONTAINER:-infohub-backend}"
ALERT="${INFOHUB_CANARY_ALERT:-$ROOT/canary_alert.sh}"
STATUS_WRITER="${INFOHUB_OPS_STATUS_WRITER:-$SCRIPT_DIR/write_job_status.py}"
LOG_DIR="${INFOHUB_LOG_DIR:-/root/infohub/logs}"

LOG_FILE="${1:-}"
if [[ -z "$LOG_FILE" ]]; then
    mkdir -p "$LOG_DIR"
    find "$LOG_DIR" -name "canary_*.log" -mtime +30 -delete
    LOG_FILE="$LOG_DIR/canary_$(date -u +%Y%m%d_%H%M%S).log"
    touch "$LOG_FILE"
    chmod 0600 "$LOG_FILE"
fi

STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
CANARY_EXIT=0
CANARY_OUT="$(docker exec "$CONTAINER_NAME" python /app/scripts/canary_eval.py 2>>"$LOG_FILE")" || CANARY_EXIT=$?
echo "$CANARY_OUT" | tee -a "$LOG_FILE"
CANARY_LINE="$(echo "$CANARY_OUT" | grep '^CANARY:' | tail -1 || true)"
bash "$ALERT" "$CANARY_EXIT" "$CANARY_LINE" 2>&1 | tee -a "$LOG_FILE" || true
python3 "$STATUS_WRITER" canary "$STARTED_AT" "$CANARY_EXIT" "$CANARY_LINE" "$LOG_FILE" || true
exit "$CANARY_EXIT"
