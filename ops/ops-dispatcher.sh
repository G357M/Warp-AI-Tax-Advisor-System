#!/usr/bin/env bash

# Runs the manual job requests the admin System page leaves in ops-requests/
# (cron, every minute). One dispatcher at a time: while a job runs, later
# minutes exit at once and the requests wait. Only four fixed commands can
# run; a request chooses one by its file name and nothing from its content
# reaches a command line. Progress goes to ops-status/<job>.request.json.

set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
REQUEST_DIR="${INFOHUB_OPS_REQUEST_DIR:-$ROOT/ops-requests}"
export INFOHUB_OPS_STATUS_DIR="${INFOHUB_OPS_STATUS_DIR:-$ROOT/ops-status}"
LOCK_FILE="${INFOHUB_OPS_DISPATCHER_LOCK:-/run/lock/infohub-ops-dispatcher.lock}"
HELPER="$SCRIPT_DIR/ops_request.py"
SCRAPER_CMD="${INFOHUB_DISPATCH_SCRAPER:-$ROOT/run_scraper.sh}"
CANARY_CMD="${INFOHUB_DISPATCH_CANARY:-$SCRIPT_DIR/run_canary.sh}"
BACKUP_CMD="${INFOHUB_DISPATCH_BACKUP:-$SCRIPT_DIR/backup-infohub-db.sh}"
STATE_DIR="${INFOHUB_OPS_DISPATCH_STATE:-/var/lib/infohub/ops-dispatch}"
INTERRUPTED_AFTER_MIN="${INFOHUB_OPS_INTERRUPTED_AFTER_MIN:-360}"

log() { echo "[ops-dispatcher $(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

exec 9>"$LOCK_FILE"
flock -n 9 || exit 0

# processing/ and rejected/ live outside ops-requests/: the backend container
# can write there and could swap them for symlinks that a root mv would follow.
install -d -m 0700 "$STATE_DIR" "$STATE_DIR/processing" "$STATE_DIR/rejected" || exit 1
for dir in "$STATE_DIR" "$STATE_DIR/processing" "$STATE_DIR/rejected"; do
    if [[ -L "$dir" || ! -d "$dir" ]]; then
        log "refusing to run: $dir is a symlink or not a directory"
        exit 1
    fi
done
PROCESSING="$STATE_DIR/processing"
REJECTED="$STATE_DIR/rejected"

[[ -d "$REQUEST_DIR" ]] || exit 0

run_job() {
    case "$1" in
        scraper_ingest) INFOHUB_JOB_TRIGGER=manual bash "$SCRAPER_CMD" --ingest-only ;;
        scraper_full) INFOHUB_JOB_TRIGGER=manual INFOHUB_MANUAL_RUN=1 bash "$SCRAPER_CMD" ;;
        canary) INFOHUB_JOB_TRIGGER=manual bash "$CANARY_CMD" ;;
        backup) INFOHUB_JOB_TRIGGER=manual bash "$BACKUP_CMD" ;;
        *) return 2 ;;
    esac
}

# A request still in processing/ after 6 h belongs to a dispatcher that died
# mid-job (deploy, reboot): close it so the card leaves "running".
while IFS= read -r -d '' stuck; do
    python3 "$HELPER" interrupted "$stuck" || true
    rm -f -- "$stuck"
    log "$(basename "$stuck"): interrupted"
done < <(find "$PROCESSING" -maxdepth 1 ! -type d -mmin +"$INTERRUPTED_AFTER_MIN" -print0)

# Oldest first. Dot files are the backend's in-flight temp files.
# NUL-delimited so a hostile file name (newline) cannot forge extra entries.
while IFS= read -r -d '' request; do
    name="$(basename -- "$request")"
    [[ "$request" == "$REQUEST_DIR/$name" ]] || continue
    case "$name" in
        scraper_ingest.json|scraper_full.json|canary.json|backup.json) job="${name%.json}" ;;
        *)
            if [[ "$name" =~ ^[A-Za-z0-9_.-]+$ ]]; then
                mv -T -- "$request" "$REJECTED/$name"
                log "$name: rejected (not a known job)"
            else
                rm -f -- "$request"
                log "removed (unsafe name)"
            fi
            continue ;;
    esac
    # Move first, validate the root-owned copy: never act twice on a path the
    # backend can still change.
    taken="$PROCESSING/$name"
    mv -T -- "$request" "$taken" || continue
    if ! request_id="$(python3 "$HELPER" check "$taken")"; then
        mv -T -- "$taken" "$REJECTED/$name"
        log "$name: rejected (invalid request)"
        continue
    fi
    touch -h -- "$taken"
    started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    python3 "$HELPER" running "$taken" "$started_at" || true
    log "$name: running request $request_id"
    output="$(mktemp)"
    run_job "$job" >"$output" 2>&1
    rc=$?
    cat "$output"
    python3 "$HELPER" finish "$taken" "$started_at" "$rc" <"$output" || true
    rm -f -- "$output" "$taken"
    log "$name: finished with exit $rc"
done < <(find "$REQUEST_DIR" -maxdepth 1 ! -type d ! -name '.*' -printf '%T@ %p\0' | sort -z -n | cut -z -d' ' -f2-)
