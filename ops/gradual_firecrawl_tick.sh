#!/usr/bin/env bash
set -euo pipefail

STATE_DIR=/root/infohub/.state
OPS_DIR=/root/infohub/ops
LOG_DIR=/root/infohub/logs
LOCK_FILE=/tmp/infohub-gradual-firecrawl.lock
STATE_FILE="$STATE_DIR/newdocument_ingest.env"
RUN_LOG="$LOG_DIR/gradual_firecrawl.log"
PY_SCRIPT="$OPS_DIR/firecrawl_one_page_batch.py"

SPECIES=NewDocument
MAX_PAGE=258
DOC_BATCH=8
JITTER_MAX_SECONDS=180

mkdir -p "$STATE_DIR" "$OPS_DIR" "$LOG_DIR"
exec 9>"$LOCK_FILE"
flock -n 9 || exit 0

if [ ! -f "$STATE_FILE" ]; then
  cat > "$STATE_FILE" <<EOF
PAGE=1
OFFSET=0
EOF
fi

# shellcheck disable=SC1090
source "$STATE_FILE"
PAGE=${PAGE:-1}
OFFSET=${OFFSET:-0}

if [ "$PAGE" -gt "$MAX_PAGE" ]; then
  echo "$(date -u +%FT%TZ) DONE species=$SPECIES page=$PAGE" >> "$RUN_LOG"
  exit 0
fi

sleep $((RANDOM % JITTER_MAX_SECONDS))

echo "$(date -u +%FT%TZ) START species=$SPECIES page=$PAGE offset=$OFFSET batch=$DOC_BATCH" >> "$RUN_LOG"

docker exec infohub-backend sh -lc 'mkdir -p /app/logs' >/dev/null 2>&1 || true

if ! output=$(docker exec -i infohub-backend python - "$SPECIES" "$PAGE" "$OFFSET" "$DOC_BATCH" < "$PY_SCRIPT" 2>&1); then
  echo "$output" >> "$RUN_LOG"
  echo "$(date -u +%FT%TZ) ERROR species=$SPECIES page=$PAGE offset=$OFFSET" >> "$RUN_LOG"
  exit 1
fi

echo "$output" >> "$RUN_LOG"
result_line=$(printf '%s\n' "$output" | grep 'RESULT_JSON=' | tail -n 1 || true)
if [ -z "$result_line" ]; then
  echo "$(date -u +%FT%TZ) ERROR missing RESULT_JSON species=$SPECIES page=$PAGE offset=$OFFSET" >> "$RUN_LOG"
  exit 1
fi
result_json=${result_line#RESULT_JSON=}

read -r attempted total_links < <(python3 - <<'PY' "$result_json"
import json, sys
obj = json.loads(sys.argv[1])
print(obj['attempted'], obj['total_links'])
PY
)

if [ "$attempted" -eq 0 ] || [ $((OFFSET + attempted)) -ge "$total_links" ]; then
  PAGE=$((PAGE + 1))
  OFFSET=0
else
  OFFSET=$((OFFSET + attempted))
fi

cat > "$STATE_FILE" <<EOF
PAGE=$PAGE
OFFSET=$OFFSET
EOF

echo "$(date -u +%FT%TZ) END species=$SPECIES next_page=$PAGE next_offset=$OFFSET attempted=$attempted total_links=$total_links" >> "$RUN_LOG"
