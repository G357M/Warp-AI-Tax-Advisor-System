#!/usr/bin/env bash
set -euo pipefail

LOG_DIR=/root/infohub/logs
LOG_FILE="$LOG_DIR/reindex-full.log"
STATE_FILE=/root/infohub/state/reindex-full-state.json
CONTAINER=infohub-backend
PY_PATH='PYTHONPATH=/app:/app/corpus-tools/scripts:/app/corpus-tools/export_pipeline'
INDEX_SCRIPT='/app/corpus-tools/scripts/scripts/index_export_corpus.py'

mkdir -p "$LOG_DIR" /root/infohub/state

: > "$LOG_FILE"

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() {
  echo "[$(ts)] $*" | tee -a "$LOG_FILE"
}
state_raw() {
  printf '%s\n' "$1" > "$STATE_FILE"
}

log "start full reindex"
state_raw '{"status":"starting"}'

log "prepare container stage dir"
docker exec "$CONTAINER" sh -lc 'rm -rf /app/corpus-reindex && mkdir -p /app/corpus-reindex/live-native-legislative-news/normalized /app/corpus-reindex/live-native-newdocument/normalized'

log "copy legislative normalized corpus into container"
docker cp /root/infohub/corpus/live-native-legislative-news/normalized/. "$CONTAINER":/app/corpus-reindex/live-native-legislative-news/normalized/

log "copy newdocument normalized corpus into container"
docker cp /root/infohub/corpus/live-native-newdocument/normalized/. "$CONTAINER":/app/corpus-reindex/live-native-newdocument/normalized/

log "capture DB counts before"
BEFORE_JSON=$(docker exec "$CONTAINER" sh -lc "$PY_PATH python - <<'PY' 2>/dev/null | tail -n 1
import json
from sqlalchemy import text
from core.database import engine
with engine.connect() as conn:
    docs=conn.execute(text('SELECT COUNT(*) FROM documents')).scalar()
    chunks=conn.execute(text('SELECT COUNT(*) FROM document_chunks')).scalar()
    emb=conn.execute(text('SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL')).scalar()
    print(json.dumps({'documents':docs,'chunks':chunks,'embedded_chunks':emb}))
PY")
log "before_counts $BEFORE_JSON"
state_raw "{\"status\":\"running\",\"phase\":\"before_counts\",\"before\":$BEFORE_JSON}"

log "reindex legislative corpus"
docker exec "$CONTAINER" sh -lc "$PY_PATH python $INDEX_SCRIPT --corpus-dir /app/corpus-reindex/live-native-legislative-news --write-db --embed --force" 2>&1 | tee -a "$LOG_FILE"
state_raw "{\"status\":\"running\",\"phase\":\"after_legislative\",\"before\":$BEFORE_JSON}"

log "reindex newdocument corpus"
docker exec "$CONTAINER" sh -lc "$PY_PATH python $INDEX_SCRIPT --corpus-dir /app/corpus-reindex/live-native-newdocument --write-db --embed --force" 2>&1 | tee -a "$LOG_FILE"
state_raw "{\"status\":\"running\",\"phase\":\"after_newdocument\",\"before\":$BEFORE_JSON}"

log "capture DB counts after"
AFTER_JSON=$(docker exec "$CONTAINER" sh -lc "$PY_PATH python - <<'PY' 2>/dev/null | tail -n 1
import json
from sqlalchemy import text
from core.database import engine
with engine.connect() as conn:
    docs=conn.execute(text('SELECT COUNT(*) FROM documents')).scalar()
    chunks=conn.execute(text('SELECT COUNT(*) FROM document_chunks')).scalar()
    emb=conn.execute(text('SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL')).scalar()
    print(json.dumps({'documents':docs,'chunks':chunks,'embedded_chunks':emb}))
PY")
log "after_counts $AFTER_JSON"
state_raw "{\"status\":\"finished\",\"before\":$BEFORE_JSON,\"after\":$AFTER_JSON}"

log "full reindex finished"
