#!/usr/bin/env bash
set -euo pipefail

LOCK_FILE=/tmp/infohub-corpus-first-sync.lock
LOG_DIR=/root/infohub/logs/corpus-first-sync
STATE_FILE=/root/infohub/state/corpus-first-sync-state.json
RUNS_DIR=/root/infohub/logs/corpus-first-sync/runs
CORPUS_ROOT=/root/infohub/corpus
STAGING_ROOT=/root/infohub/.tmp/corpus-sync-stage
TOOLS_ROOT=/root/infohub/corpus-tools
JITTER_MAX_SECONDS=${JITTER_MAX_SECONDS:-180}

mkdir -p "$LOG_DIR" "$RUNS_DIR" "$(dirname "$STATE_FILE")" "$STAGING_ROOT"
exec 9>"$LOCK_FILE"
flock -n 9 || exit 0
sleep $((RANDOM % JITTER_MAX_SECONDS))

python3 "$TOOLS_ROOT/scripts/run_corpus_first_sync.py" \
  --state-file "$STATE_FILE" \
  --runs-dir "$RUNS_DIR" \
  --corpus-root "$CORPUS_ROOT" \
  --staging-root "$STAGING_ROOT" \
  --container infohub-backend \
  --page-size 20 \
  --count 20
