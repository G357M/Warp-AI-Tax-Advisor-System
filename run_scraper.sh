#!/bin/bash
# Daily scraper runner for InfoHub vector database

set -e

# Configuration
MAX_DOCS=200
LOG_DIR="/root/infohub/logs"
CONTAINER_NAME="infohub-backend"
OPTIONAL_FAILURES=()

run_optional() {
    local label="$1"
    local tail_lines="$2"
    shift 2

    local output
    local exit_code
    set +e
    output="$("$@" 2>&1)"
    exit_code=$?
    set -e

    # Preserve the complete diagnostic in the per-run log, but keep cron output
    # concise so routine successful runs do not flood logs/alerts.
    printf '%s\n' "$output" >> "$LOG_FILE"
    printf '%s\n' "$output" | tail -n "$tail_lines"
    if [ "$exit_code" -ne 0 ]; then
        OPTIONAL_FAILURES+=("${label} (exit ${exit_code})")
        echo "[nightly] WARN: ${label} failed with exit ${exit_code}." | tee -a "$LOG_FILE"
    fi
}

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
bash "$(dirname "$0")/scraper_alert.sh" "$EXIT_CODE" "$NEW_DOCS" 2>&1 | tee -a "$LOG_FILE" || true

# Extract structured facts from newly ingested dispute decisions (incremental;
# --new-only keeps the nightly run off the v1->v2 upgrade backlog, which is a
# separate manual backfill). Non-fatal on error.
echo "Extracting decision facts for new court decisions..." | tee -a "$LOG_FILE"
run_optional "decision fact extraction" 5 \
    docker exec "$CONTAINER_NAME" python /app/scripts/extract_decision_facts.py --limit 500 --new-only

# Classify news subtypes for newly ingested documents the ingest rules could
# not place (LLM fallback; incremental). Non-fatal.
echo "Classifying news subtypes..." | tee -a "$LOG_FILE"
run_optional "news subtype classification" 5 \
    docker exec "$CONTAINER_NAME" python /app/scripts/classify_news_subtypes.py --llm --limit 200

# Re-link appeal chains when new decision facts arrived. Deterministic, cheap.
echo "Linking appeal chains..." | tee -a "$LOG_FILE"
run_optional "appeal chain linking" 5 \
    docker exec "$CONTAINER_NAME" python /app/scripts/link_decision_chains.py --apply

# Extract law-amendment facts for the change timeline (incremental). Non-fatal.
echo "Extracting law amendments..." | tee -a "$LOG_FILE"
run_optional "law amendment extraction" 5 \
    docker exec "$CONTAINER_NAME" python /app/scripts/extract_law_amendments.py --limit 200
# Retry target-law resolution for older rows (no LLM; heals once missing law
# texts get ingested).
run_optional "law amendment re-resolution" 3 \
    docker exec "$CONTAINER_NAME" python /app/scripts/extract_law_amendments.py --reresolve

# Translate new amendment summaries to ka/en for the timeline. Non-fatal.
echo "Translating amendment summaries..." | tee -a "$LOG_FILE"
run_optional "amendment translation" 5 \
    docker exec "$CONTAINER_NAME" python /app/scripts/translate_amendments.py --limit 300

if [ "${#OPTIONAL_FAILURES[@]}" -gt 0 ]; then
    OPTIONAL_DETAILS="$(IFS=', '; echo "${OPTIONAL_FAILURES[*]}")"
    bash "$(dirname "$0")/scraper_alert.sh" 1 "$NEW_DOCS" "$OPTIONAL_DETAILS" \
        2>&1 | tee -a "$LOG_FILE" || true
fi

# Nightly RAG canary: 10 known-answer questions through the real pipeline.
# Alerts to Telegram when below threshold (>1 failure). Non-fatal.
echo "Running RAG canary..." | tee -a "$LOG_FILE"
CANARY_EXIT=0
CANARY_OUT="$(docker exec "$CONTAINER_NAME" python /app/scripts/canary_eval.py 2>>"$LOG_FILE")" || CANARY_EXIT=$?
echo "$CANARY_OUT" | tee -a "$LOG_FILE"
bash "$(dirname "$0")/canary_alert.sh" "$CANARY_EXIT" "$(echo "$CANARY_OUT" | grep '^CANARY:' | tail -1)" 2>&1 | tee -a "$LOG_FILE" || true

# Keep only last 30 days of logs
find "$LOG_DIR" -name "scraper_*.log" -mtime +30 -delete

exit $EXIT_CODE
