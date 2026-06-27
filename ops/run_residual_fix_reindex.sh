#!/usr/bin/env bash
set -euo pipefail

LOG_DIR=/root/infohub/logs
PIPE_LOG="$LOG_DIR/residual-fix-pipeline.log"
STATE_FILE=/root/infohub/state/residual-fix-pipeline-state.json
PY_SCRIPT=/root/infohub/corpus-tools/scripts/reexport_calibrated_residuals.py
REEXPORT_STDOUT="$LOG_DIR/reexport-residual.stdout.log"
CONTAINER=infohub-backend
PY_PATH='PYTHONPATH=/app:/app/corpus-tools/scripts:/app/corpus-tools/export_pipeline'
INDEX_SCRIPT='/app/corpus-tools/scripts/scripts/index_export_corpus.py'
SELECTED_DIR=/root/infohub/state/residual-selected-json
STAGE=/app/corpus-residual-fix

mkdir -p "$LOG_DIR" /root/infohub/state
: > "$PIPE_LOG"
: > "$REEXPORT_STDOUT"

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() {
  echo "[$(ts)] $*" | tee -a "$PIPE_LOG"
}
state_raw() {
  printf '%s\n' "$1" > "$STATE_FILE"
}

db_counts() {
  docker exec "$CONTAINER" sh -lc "$PY_PATH python - <<'PY' 2>/dev/null | tail -n 1
import json
from sqlalchemy import text
from core.database import engine
with engine.connect() as conn:
    docs=conn.execute(text('SELECT COUNT(*) FROM documents')).scalar()
    chunks=conn.execute(text('SELECT COUNT(*) FROM document_chunks')).scalar()
    emb=conn.execute(text('SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL')).scalar()
    print(json.dumps({'documents':docs,'chunks':chunks,'embedded_chunks':emb}))
PY"
}

log "start residual-fix pipeline"
state_raw '{"status":"starting"}'

BEFORE_JSON=$(db_counts)
log "before_counts $BEFORE_JSON"
state_raw "{\"status\":\"running\",\"phase\":\"before_counts\",\"before\":$BEFORE_JSON}"

log "run calibrated residual re-export"
python3 "$PY_SCRIPT" 2>&1 | tee -a "$REEXPORT_STDOUT"
state_raw "{\"status\":\"running\",\"phase\":\"after_reexport\",\"before\":$BEFORE_JSON}"

log "prepare container stage dir"
docker exec "$CONTAINER" sh -lc "rm -rf '$STAGE' && mkdir -p '$STAGE/live-native-legislative-news/normalized' '$STAGE/live-native-newdocument/normalized'"

log "copy normalized corpus into container for selected reindex"
docker cp /root/infohub/corpus/live-native-legislative-news/normalized/. "$CONTAINER":"$STAGE/live-native-legislative-news/normalized/"
docker cp /root/infohub/corpus/live-native-newdocument/normalized/. "$CONTAINER":"$STAGE/live-native-newdocument/normalized/"

if [ -s "$SELECTED_DIR/live-native-legislative-news.json" ]; then
  log "copy legislative selected-json"
  docker cp "$SELECTED_DIR/live-native-legislative-news.json" "$CONTAINER":"$STAGE/live-native-legislative-news-selected.json"
  log "reindex legislative residual set"
  docker exec "$CONTAINER" sh -lc "$PY_PATH python $INDEX_SCRIPT --corpus-dir $STAGE/live-native-legislative-news --selected-json $STAGE/live-native-legislative-news-selected.json --write-db --embed --force" 2>&1 | tee -a "$PIPE_LOG"
fi

if [ -s "$SELECTED_DIR/live-native-newdocument.json" ]; then
  log "copy newdocument selected-json"
  docker cp "$SELECTED_DIR/live-native-newdocument.json" "$CONTAINER":"$STAGE/live-native-newdocument-selected.json"
  log "reindex newdocument residual set"
  docker exec "$CONTAINER" sh -lc "$PY_PATH python $INDEX_SCRIPT --corpus-dir $STAGE/live-native-newdocument --selected-json $STAGE/live-native-newdocument-selected.json --write-db --embed --force" 2>&1 | tee -a "$PIPE_LOG"
fi

AFTER_JSON=$(db_counts)
log "after_counts $AFTER_JSON"
state_raw "{\"status\":\"finished\",\"before\":$BEFORE_JSON,\"after\":$AFTER_JSON}"
log "residual-fix pipeline finished"
