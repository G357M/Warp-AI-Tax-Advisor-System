#!/bin/bash
# Daily scraper runner for InfoHub vector database

set -e

# Configuration
MAX_DOCS=200
LOG_DIR="/root/infohub/logs"
CONTAINER_NAME="infohub-backend"
QUALITY_STATE_DIR="/root/infohub/.state"
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

run_quality_gate() {
    local label="$1"
    local summary_prefix="$2"
    local container_report="$3"
    local host_report="$4"
    local container_baseline="$5"
    local host_baseline="$6"
    shift 6

    local output=""
    local summary=""
    local exit_code=0
    local artifact_error=0
    local host_artifact

    # Retain one recoverable prior generation, but never leave it at the
    # current path where operators could mistake it for this run's result.
    for host_artifact in "$host_report" "$host_baseline"; do
        if [ -f "$host_artifact" ]; then
            if ! mv -f "$host_artifact" "${host_artifact}.previous" || \
                    ! chmod 0600 "${host_artifact}.previous"; then
                artifact_error=1
            fi
        fi
    done

    # Prevent an interrupted evaluator from making yesterday's artifact look
    # like the result of the current run.
    if ! docker exec "$CONTAINER_NAME" rm -f \
            "$container_report" "$container_baseline" >>"$LOG_FILE" 2>&1; then
        artifact_error=1
    fi

    set +e
    output="$("$@" 2>>"$LOG_FILE")"
    exit_code=$?
    set -e
    printf '%s\n' "$output" | tee -a "$LOG_FILE"

    if docker exec "$CONTAINER_NAME" test -s "$container_report"; then
        if ! docker cp "$CONTAINER_NAME:$container_report" "$host_report" \
                >>"$LOG_FILE" 2>&1; then
            artifact_error=1
        fi
    else
        artifact_error=1
    fi
    if docker exec "$CONTAINER_NAME" test -s "$container_baseline"; then
        if ! docker cp "$CONTAINER_NAME:$container_baseline" "$host_baseline" \
                >>"$LOG_FILE" 2>&1; then
            artifact_error=1
        fi
    else
        artifact_error=1
    fi

    if [ "$artifact_error" -eq 0 ] && \
            ! chmod 0600 "$host_report" "$host_baseline"; then
        artifact_error=1
    fi
    if [ "$artifact_error" -ne 0 ]; then
        exit_code=1
        echo "[nightly] WARN: ${label} artifacts were incomplete." | tee -a "$LOG_FILE"
    fi

    summary="$(printf '%s\n' "$output" | grep "^${summary_prefix}" | tail -1 || true)"
    if [ -z "$summary" ]; then
        exit_code=1
    fi
    echo "[nightly] ${label} exit=${exit_code}." | tee -a "$LOG_FILE"
    bash "$(dirname "$0")/quality_gate_alert.sh" \
        "$exit_code" "$label" "$summary" 2>&1 | tee -a "$LOG_FILE" || true
}

# Ensure log directory exists
mkdir -p "$LOG_DIR"
install -d -m 0700 "$QUALITY_STATE_DIR"

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

# Deterministic post-ingest quality gates. Both use SELECT-only retrieval,
# prohibit LLM calls and keep document-level reports server-side at mode 0600.
DEPLOYED_COMMIT="$(git -C /root/infohub rev-parse HEAD)"

echo "Running deterministic live-corpus quality gate..." | tee -a "$LOG_FILE"
run_quality_gate \
    "RAG v2 live-corpus gate" \
    "RAG_V2_LIVE_CORPUS_EVAL=" \
    "/tmp/rag_v2_live_corpus_nightly_report.json" \
    "$QUALITY_STATE_DIR/rag_v2_live_corpus_nightly_report.json" \
    "/tmp/rag_v2_live_corpus_nightly_baseline.json" \
    "$QUALITY_STATE_DIR/rag_v2_live_corpus_nightly_baseline.json" \
    docker exec "$CONTAINER_NAME" python /app/scripts/evaluate_rag_v2_live_corpus.py \
        --commit "$DEPLOYED_COMMIT" \
        --output /tmp/rag_v2_live_corpus_nightly_report.json \
        --baseline-output /tmp/rag_v2_live_corpus_nightly_baseline.json

echo "Running decision-facts quality gate..." | tee -a "$LOG_FILE"
run_quality_gate \
    "decision-facts quality gate" \
    "DECISION_FACTS_QUALITY_EVAL=" \
    "/tmp/decision_facts_quality_nightly_report.json" \
    "$QUALITY_STATE_DIR/decision_facts_quality_nightly_report.json" \
    "/tmp/decision_facts_quality_nightly_baseline.json" \
    "$QUALITY_STATE_DIR/decision_facts_quality_nightly_baseline.json" \
    docker exec "$CONTAINER_NAME" python /app/scripts/evaluate_decision_facts_quality.py \
        --execute \
        --commit "$DEPLOYED_COMMIT" \
        --output /tmp/decision_facts_quality_nightly_report.json \
        --baseline-output /tmp/decision_facts_quality_nightly_baseline.json

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
