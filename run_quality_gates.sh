#!/bin/bash
# Run the deterministic production quality gates without scraper or LLM steps.

set -e

INFOHUB_DIR="/root/infohub"
LOG_DIR="$INFOHUB_DIR/logs"
CONTAINER_NAME="infohub-backend"
QUALITY_STATE_DIR="$INFOHUB_DIR/.state"
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
QUALITY_FAILURES=()

mkdir -p "$LOG_DIR"
install -d -m 0700 "$QUALITY_STATE_DIR"
LOG_FILE="${1:-$LOG_DIR/quality_gates_$(date +%Y%m%d_%H%M%S).log}"
touch "$LOG_FILE"
chmod 0600 "$LOG_FILE"

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

    # Prevent an interrupted evaluator from making yesterday's container
    # artifact look like the result of the current run.
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
        echo "[quality-gate] WARN: ${label} artifacts were incomplete." | tee -a "$LOG_FILE"
    fi

    summary="$(printf '%s\n' "$output" | grep "^${summary_prefix}" | tail -1 || true)"
    if [ -z "$summary" ]; then
        exit_code=1
    fi
    echo "[quality-gate] ${label} exit=${exit_code}." | tee -a "$LOG_FILE"
    bash "$SCRIPT_DIR/quality_gate_alert.sh" \
        "$exit_code" "$label" "$summary" 2>&1 | tee -a "$LOG_FILE" || true
    if [ "$exit_code" -ne 0 ]; then
        QUALITY_FAILURES+=("$label")
    fi
}

DEPLOYED_COMMIT="$(git -C "$INFOHUB_DIR" rev-parse HEAD)"

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

if [ "${#QUALITY_FAILURES[@]}" -ne 0 ]; then
    echo "[quality-gate] Failed gates: ${QUALITY_FAILURES[*]}" | tee -a "$LOG_FILE"
    exit 1
fi

echo "[quality-gate] All deterministic quality gates passed." | tee -a "$LOG_FILE"
exit 0
