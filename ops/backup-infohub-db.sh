#!/usr/bin/env bash

# Nightly logical backup of the production database.
#
# Writes a custom-format pg_dump to $BACKUP_DIR, proves the archive is
# readable (pg_restore --list must show data for the core tables), records a
# sha256 and keeps the newest $KEEP verified dumps. A failed or unverifiable
# dump never replaces a good one. The weekly off-server copy pulled to the
# operator workstation remains the off-site layer; this job covers the days
# in between and gives a same-host restore point without network transfer.

set -Eeuo pipefail

BACKUP_DIR="${INFOHUB_DB_BACKUP_DIR:-/root/backups/infohub}"
KEEP="${INFOHUB_DB_BACKUP_KEEP:-4}"
CONTAINER="${INFOHUB_DB_CONTAINER:-infohub-postgres}"
DB_USER="${INFOHUB_DB_USER:-infohub_user}"
DB_NAME="${INFOHUB_DB_NAME:-infohub_ai}"
LOCK_FILE="${INFOHUB_DB_BACKUP_LOCK:-/run/lock/infohub-db-backup.lock}"
REQUIRED_TABLES=(documents document_chunks users)

ALERT="${INFOHUB_OPS_ALERT:-$(dirname "${BASH_SOURCE[0]}")/ops_alert.sh}"

log() { echo "[db-backup $(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
die() {
    local code="$1"; shift
    reason="$*"
    log "$reason" >&2
    exit "$code"
}

# Any non-zero exit, explicit or from set -e, sends one Telegram alert; the
# temporary files are removed whatever the outcome.
reason=""
partial=""
toc=""
trap 'reason="${reason:-command failed: $BASH_COMMAND}"' ERR
finish() {
    local rc=$?
    rm -f ${partial:+"$partial"} ${toc:+"$toc"}
    if (( rc != 0 )); then
        bash "$ALERT" "nightly DB backup" "exit $rc: ${reason:-unknown error}
Log: /root/infohub/logs/db-backup.log" || true
    fi
}
trap finish EXIT

if ! [[ "$KEEP" =~ ^[1-9][0-9]*$ ]]; then
    die 2 "INFOHUB_DB_BACKUP_KEEP must be a positive integer, got '$KEEP'"
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    log "another backup is running; skipped"
    exit 0
fi

umask 077
install -d -m 0700 "$BACKUP_DIR"

# Refuse to start when the disk cannot hold one more dump of the newest size
# plus a 20% margin: a half-written dump on a full disk would also starve
# Postgres itself.
latest="$(ls -1t "$BACKUP_DIR"/infohub_ai-*.dump 2>/dev/null | head -n 1 || true)"
if [[ -n "$latest" ]]; then
    need_kb=$(( $(stat -c %s "$latest") / 1024 * 12 / 10 ))
    free_kb="$(df --output=avail -k "$BACKUP_DIR" | tail -n 1 | tr -d ' ')"
    if (( free_kb < need_kb )); then
        die 1 "not enough free space: ${free_kb} KiB available, ${need_kb} KiB needed"
    fi
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$BACKUP_DIR/infohub_ai-$stamp.dump"
partial="$target.partial"
toc="$(mktemp)"

log "dumping $DB_NAME from $CONTAINER"
docker exec "$CONTAINER" pg_dump -U "$DB_USER" -Fc "$DB_NAME" > "$partial"

docker exec -i "$CONTAINER" pg_restore --list < "$partial" > "$toc"
for table in "${REQUIRED_TABLES[@]}"; do
    if ! grep -qE "TABLE DATA public $table " "$toc"; then
        die 1 "verification failed: no data entry for table '$table'"
    fi
done

mv "$partial" "$target"
(cd "$BACKUP_DIR" && sha256sum "$(basename "$target")" > "$(basename "$target").sha256")
log "ok $(basename "$target") $(stat -c %s "$target") bytes, $(grep -vc '^;' "$toc") TOC entries"

# Rotation only after a verified success, newest first.
ls -1t "$BACKUP_DIR"/infohub_ai-*.dump | tail -n +"$((KEEP + 1))" | while read -r old; do
    rm -f -- "$old" "$old.sha256"
    log "rotated out $(basename "$old")"
done
