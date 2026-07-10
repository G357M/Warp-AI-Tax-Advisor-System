#!/bin/bash
# Daily scraper runner for InfoHub vector database

set -e

# Configuration
MAX_DOCS=200
LOG_DIR="/root/infohub/logs"
CONTAINER_NAME="infohub-backend"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Log file for this run
LOG_FILE="$LOG_DIR/scraper_$(date +%Y%m%d_%H%M%S).log"

echo "========================================" | tee -a "$LOG_FILE"
echo "Starting scraper at $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# Run scraper inside backend container (direct JSON API; incremental)
docker exec "$CONTAINER_NAME" python /app/scripts/scrape_infohub_api.py \
    --max-docs $MAX_DOCS \
    2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=${PIPESTATUS[0]}

echo "========================================" | tee -a "$LOG_FILE"
echo "Scraper finished at $(date)" | tee -a "$LOG_FILE"
echo "Exit code: $EXIT_CODE" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# How many new docs were ingested (from the scraper summary line, e.g. "+0 new docs").
# "?" means the line was missing -> scraper_alert.sh treats it as a failure.
NEW_DOCS="$(grep -oE '\+[0-9]+ new docs' "$LOG_FILE" | tail -1 | grep -oE '[0-9]+' || true)"
NEW_DOCS="${NEW_DOCS:-?}"

# Alert (Telegram) on failure, or on too many consecutive 0-new runs.
"$(dirname "$0")/scraper_alert.sh" "$EXIT_CODE" "$NEW_DOCS" 2>&1 | tee -a "$LOG_FILE" || true

# Extract structured facts from newly ingested dispute decisions (incremental;
# --new-only keeps the nightly run off the v1->v2 upgrade backlog, which is a
# separate manual backfill). Non-fatal on error.
echo "Extracting decision facts for new court decisions..." | tee -a "$LOG_FILE"
docker exec "$CONTAINER_NAME" python /app/scripts/extract_decision_facts.py --limit 500 --new-only \
    2>&1 | tail -5 | tee -a "$LOG_FILE" || true

# Classify news subtypes for newly ingested documents the ingest rules could
# not place (LLM fallback; incremental). Non-fatal.
echo "Classifying news subtypes..." | tee -a "$LOG_FILE"
docker exec "$CONTAINER_NAME" python /app/scripts/classify_news_subtypes.py --llm --limit 200 \
    2>&1 | tail -3 | tee -a "$LOG_FILE" || true

# Re-link appeal chains when new decision facts arrived. Deterministic, cheap.
echo "Linking appeal chains..." | tee -a "$LOG_FILE"
docker exec "$CONTAINER_NAME" python /app/scripts/link_decision_chains.py --apply \
    2>&1 | tail -3 | tee -a "$LOG_FILE" || true

# Extract law-amendment facts for the change timeline (incremental). Non-fatal.
echo "Extracting law amendments..." | tee -a "$LOG_FILE"
docker exec "$CONTAINER_NAME" python /app/scripts/extract_law_amendments.py --limit 200 \
    2>&1 | tail -5 | tee -a "$LOG_FILE" || true
# Retry target-law resolution for older rows (no LLM; heals once missing law
# texts get ingested).
docker exec "$CONTAINER_NAME" python /app/scripts/extract_law_amendments.py --reresolve \
    2>&1 | tail -2 | tee -a "$LOG_FILE" || true

# Translate new amendment summaries to ka/en for the timeline. Non-fatal.
echo "Translating amendment summaries..." | tee -a "$LOG_FILE"
docker exec "$CONTAINER_NAME" python /app/scripts/translate_amendments.py --limit 300 \
    2>&1 | tail -3 | tee -a "$LOG_FILE" || true

# Keep only last 30 days of logs
find "$LOG_DIR" -name "scraper_*.log" -mtime +30 -delete

exit $EXIT_CODE
