#!/usr/bin/env bash
set -euo pipefail

LOG_DIR=/root/infohub/logs
PIPE_LOG="$LOG_DIR/full-refresh-v2.log"
STATE_FILE=/root/infohub/state/full-refresh-v2-state.json
REPARSE_SCRIPT=/root/infohub/corpus-tools/scripts/reparse_all_from_raw.py
CONTAINER=infohub-backend
PY_PATH='PYTHONPATH=/app:/app/corpus-tools/scripts:/app/corpus-tools/export_pipeline'
INDEX_SCRIPT='/app/corpus-tools/scripts/scripts/index_export_corpus.py'
STAGE=/app/corpus-reindex-v2

mkdir -p "$LOG_DIR" /root/infohub/state
: > "$PIPE_LOG"

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() {
  echo "[$(ts)] $*" | tee -a "$PIPE_LOG"
}
state_raw() {
  printf '%s\n' "$1" > "$STATE_FILE"
}

db_counts() {
  docker exec "$CONTAINER" sh -lc "$PY_PATH python - <<'PY' 2>/dev/null | tail -n 1
import json, logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.CRITICAL)
from sqlalchemy import text
from core.database import engine
with engine.connect() as conn:
    docs=conn.execute(text('SELECT COUNT(*) FROM documents')).scalar()
    chunks=conn.execute(text('SELECT COUNT(*) FROM document_chunks')).scalar()
    emb=conn.execute(text('SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL')).scalar()
    print(json.dumps({'documents':docs,'chunks':chunks,'embedded_chunks':emb}))
PY"
}

log "start full refresh v2"
state_raw '{"status":"starting"}'

log "stop residual targeted pipeline if still running"
pkill -f reexport_calibrated_residuals.py || true
pkill -f '/app/corpus-tools/scripts/scripts/index_export_corpus.py --corpus-dir /app/corpus-residual-fix' || true
state_raw '{"status":"running","phase":"stopped_residual_pipeline"}'

log "run full reparse from raw corpus"
python3 "$REPARSE_SCRIPT" 2>&1 | tee -a "$PIPE_LOG"
state_raw '{"status":"running","phase":"after_reparse"}'

log "capture DB counts before full reindex"
BEFORE_JSON=$(db_counts)
log "before_counts $BEFORE_JSON"
state_raw "{\"status\":\"running\",\"phase\":\"before_full_reindex\",\"before\":$BEFORE_JSON}"

log "prepare container stage dir"
docker exec "$CONTAINER" sh -lc "rm -rf '$STAGE' && mkdir -p '$STAGE/live-native-legislative-news/normalized' '$STAGE/live-native-newdocument/normalized'"

log "copy legislative normalized corpus into container"
docker cp /root/infohub/corpus/live-native-legislative-news/normalized/. "$CONTAINER":"$STAGE/live-native-legislative-news/normalized/"

log "copy newdocument normalized corpus into container"
docker cp /root/infohub/corpus/live-native-newdocument/normalized/. "$CONTAINER":"$STAGE/live-native-newdocument/normalized/"

log "full reindex legislative corpus"
docker exec "$CONTAINER" sh -lc "$PY_PATH python $INDEX_SCRIPT --corpus-dir $STAGE/live-native-legislative-news --write-db --embed --force" 2>&1 | tee -a "$PIPE_LOG"
state_raw "{\"status\":\"running\",\"phase\":\"after_legislative\",\"before\":$BEFORE_JSON}"

log "full reindex newdocument corpus"
docker exec "$CONTAINER" sh -lc "$PY_PATH python $INDEX_SCRIPT --corpus-dir $STAGE/live-native-newdocument --write-db --embed --force" 2>&1 | tee -a "$PIPE_LOG"
state_raw "{\"status\":\"running\",\"phase\":\"after_newdocument\",\"before\":$BEFORE_JSON}"

AFTER_JSON=$(db_counts)
log "after_counts $AFTER_JSON"
state_raw "{\"status\":\"finished\",\"before\":$BEFORE_JSON,\"after\":$AFTER_JSON}"
log "full refresh v2 finished"
