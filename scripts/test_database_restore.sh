#!/usr/bin/env bash

# Restore one pinned InfoHub backup into an isolated ephemeral PostgreSQL.
# Dry-run is the default. The production database, containers, networks and
# volumes are never referenced by this script.

set -Eeuo pipefail
umask 077

BACKUP_FILE=""
EVIDENCE_FILE=""
EXPECTED_SHA256=""
POSTGRES_IMAGE="pgvector/pgvector:pg15"
MAX_AGE_DAYS=14
MIN_DOCUMENTS=1
MIN_CHUNKS=1
MIN_FACTS=1
EXECUTE=0
CONTAINER_CREATED=0
CONTAINER_NAME=""
EVIDENCE_TEMP=""

usage() {
    cat <<'EOF'
Usage:
  ./scripts/test_database_restore.sh --backup PATH [--max-age-days N]
  ./scripts/test_database_restore.sh --backup PATH --execute \
    --expected-sha256 HEX --evidence PATH [options]

Options:
  --backup PATH          Plain SQL, gzip-compressed dump, or PostgreSQL custom dump.
  --execute              Perform the isolated restore; default is read-only planning.
  --expected-sha256 HEX  Exact lowercase/uppercase SHA-256 emitted by the dry run.
  --evidence PATH        New JSON evidence file; existing files are never overwritten.
  --image IMAGE          Existing local PostgreSQL image (default pgvector/pgvector:pg15).
  --max-age-days N       Freshness ceiling used for RPO evidence (default 14).
  --min-documents N      Minimum restored documents (default 1).
  --min-chunks N         Minimum restored document chunks (default 1).
  --min-facts N          Minimum restored decision facts (default 1).

The execute path creates one uniquely named, network-disabled container with no
published ports and no mounted volumes. It is removed on every exit.
EOF
}

die() {
    echo "Restore drill refused: $*" >&2
    exit 2
}

require_uint() {
    local label="$1" value="$2"
    [[ "$value" =~ ^[0-9]+$ ]] || die "$label must be a non-negative integer"
}

while (( $# > 0 )); do
    case "$1" in
        --backup)
            (( $# >= 2 )) || die "--backup requires a path"
            BACKUP_FILE="$2"
            shift 2
            ;;
        --evidence)
            (( $# >= 2 )) || die "--evidence requires a path"
            EVIDENCE_FILE="$2"
            shift 2
            ;;
        --expected-sha256)
            (( $# >= 2 )) || die "--expected-sha256 requires a value"
            EXPECTED_SHA256="${2,,}"
            shift 2
            ;;
        --image)
            (( $# >= 2 )) || die "--image requires a value"
            POSTGRES_IMAGE="$2"
            shift 2
            ;;
        --max-age-days)
            (( $# >= 2 )) || die "--max-age-days requires a value"
            MAX_AGE_DAYS="$2"
            shift 2
            ;;
        --min-documents)
            (( $# >= 2 )) || die "--min-documents requires a value"
            MIN_DOCUMENTS="$2"
            shift 2
            ;;
        --min-chunks)
            (( $# >= 2 )) || die "--min-chunks requires a value"
            MIN_CHUNKS="$2"
            shift 2
            ;;
        --min-facts)
            (( $# >= 2 )) || die "--min-facts requires a value"
            MIN_FACTS="$2"
            shift 2
            ;;
        --execute)
            EXECUTE=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            die "unknown argument: $1"
            ;;
    esac
done

[[ -n "$BACKUP_FILE" ]] || die "--backup is required"
require_uint "--max-age-days" "$MAX_AGE_DAYS"
require_uint "--min-documents" "$MIN_DOCUMENTS"
require_uint "--min-chunks" "$MIN_CHUNKS"
require_uint "--min-facts" "$MIN_FACTS"
(( MAX_AGE_DAYS > 0 )) || die "--max-age-days must be positive"
[[ "$POSTGRES_IMAGE" =~ ^[A-Za-z0-9._/:@-]+$ ]] || die "--image contains unsafe characters"

for command_name in realpath sha256sum stat date basename dirname dd od tr cut; do
    command -v "$command_name" >/dev/null 2>&1 || die "missing command: $command_name"
done

[[ ! -L "$BACKUP_FILE" ]] || die "backup symlinks are not accepted"
[[ -f "$BACKUP_FILE" ]] || die "backup must be an existing regular file"
BACKUP_PATH="$(realpath -- "$BACKUP_FILE")"
BACKUP_NAME="$(basename -- "$BACKUP_PATH")"
[[ "$BACKUP_NAME" =~ ^[A-Za-z0-9._-]+$ ]] || die "backup filename contains unsafe characters"

BACKUP_SIZE="$(stat -c %s -- "$BACKUP_PATH")"
(( BACKUP_SIZE > 0 )) || die "backup file is empty"
BACKUP_MTIME="$(stat -c %Y -- "$BACKUP_PATH")"
NOW_EPOCH="$(date -u +%s)"
BACKUP_AGE_SECONDS="$((NOW_EPOCH - BACKUP_MTIME))"
(( BACKUP_AGE_SECONDS >= 0 )) || BACKUP_AGE_SECONDS=0
MAX_AGE_SECONDS="$((MAX_AGE_DAYS * 86400))"
BACKUP_MODIFIED_UTC="$(date -u -d "@$BACKUP_MTIME" +%Y-%m-%dT%H:%M:%SZ)"
BACKUP_SHA256="$(sha256sum -- "$BACKUP_PATH" | tr '[:upper:]' '[:lower:]' | tr -d '\n' | cut -d ' ' -f 1)"
MAGIC="$(dd if="$BACKUP_PATH" bs=5 count=1 status=none | od -An -tx1 | tr -d ' \n')"

case "$MAGIC" in
    1f8b*)
        command -v gzip >/dev/null 2>&1 || die "gzip is required for this backup"
        gzip -t -- "$BACKUP_PATH" || die "gzip integrity check failed"
        BACKUP_FORMAT="gzip"
        ;;
    5047444d50)
        BACKUP_FORMAT="postgres_custom"
        ;;
    *)
        BACKUP_FORMAT="plain_sql"
        ;;
esac

FRESH=true
if (( BACKUP_AGE_SECONDS > MAX_AGE_SECONDS )); then
    FRESH=false
fi

printf 'DATABASE_RESTORE_DRILL_PLAN={"backup_name":"%s","bytes":%s,"format":"%s","modified_at_utc":"%s","age_seconds":%s,"max_age_days":%s,"fresh":%s,"sha256":"%s","execute":%s}\n' \
    "$BACKUP_NAME" "$BACKUP_SIZE" "$BACKUP_FORMAT" "$BACKUP_MODIFIED_UTC" \
    "$BACKUP_AGE_SECONDS" "$MAX_AGE_DAYS" "$FRESH" "$BACKUP_SHA256" \
    "$([[ "$EXECUTE" == 1 ]] && echo true || echo false)"

[[ "$FRESH" == true ]] || die "backup is older than --max-age-days"
if (( EXECUTE == 0 )); then
    exit 0
fi

[[ "$EXPECTED_SHA256" =~ ^[0-9a-f]{64}$ ]] || die "execute requires --expected-sha256 from the dry run"
[[ "$EXPECTED_SHA256" == "$BACKUP_SHA256" ]] || die "backup SHA-256 changed after dry run"
[[ -n "$EVIDENCE_FILE" ]] || die "execute requires --evidence"
[[ ! -e "$EVIDENCE_FILE" && ! -L "$EVIDENCE_FILE" ]] || die "evidence target already exists"

EVIDENCE_PATH="$(realpath -m -- "$EVIDENCE_FILE")"
EVIDENCE_PARENT="$(dirname -- "$EVIDENCE_PATH")"
EVIDENCE_NAME="$(basename -- "$EVIDENCE_PATH")"
[[ "$EVIDENCE_NAME" =~ ^[A-Za-z0-9._-]+$ ]] || die "evidence filename contains unsafe characters"
[[ -d "$EVIDENCE_PARENT" ]] || die "evidence parent directory must already exist"
EVIDENCE_TEMP="${EVIDENCE_PATH}.tmp.$$"
[[ ! -e "$EVIDENCE_TEMP" && ! -L "$EVIDENCE_TEMP" ]] || die "temporary evidence target exists"

for command_name in docker sleep seq install mv chmod rm; do
    command -v "$command_name" >/dev/null 2>&1 || die "missing execute command: $command_name"
done
docker info >/dev/null 2>&1 || die "Docker daemon is unavailable"
docker image inspect "$POSTGRES_IMAGE" >/dev/null 2>&1 || \
    die "image is not local; review and pull it explicitly: $POSTGRES_IMAGE"

cleanup() {
    if [[ -n "$EVIDENCE_TEMP" && -f "$EVIDENCE_TEMP" ]]; then
        rm -f -- "$EVIDENCE_TEMP"
    fi
    if (( CONTAINER_CREATED == 1 )); then
        [[ "$CONTAINER_NAME" == infohub-restore-drill-* ]] || return
        docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

STARTED_EPOCH="$(date -u +%s)"
STARTED_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
CONTAINER_NAME="infohub-restore-drill-$(date -u +%Y%m%d%H%M%S)-$$"
RESTORE_PASSWORD="restore-drill-$RANDOM-$RANDOM"
POSTGRES_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$POSTGRES_IMAGE")"

docker run --detach \
    --name "$CONTAINER_NAME" \
    --network none \
    --label infohub.restore-drill=true \
    --env POSTGRES_USER=infohub_user \
    --env POSTGRES_PASSWORD="$RESTORE_PASSWORD" \
    --env POSTGRES_DB=infohub_ai \
    "$POSTGRES_IMAGE" >/dev/null
CONTAINER_CREATED=1

READY=0
for _attempt in $(seq 1 60); do
    if docker exec "$CONTAINER_NAME" pg_isready \
        -U infohub_user -d infohub_ai >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 1
done
(( READY == 1 )) || die "isolated PostgreSQL did not become ready in 60 seconds"

docker cp "$BACKUP_PATH" "$CONTAINER_NAME:/tmp/infohub-backup.input"

case "$BACKUP_FORMAT" in
    postgres_custom)
        docker exec "$CONTAINER_NAME" pg_restore \
            --list /tmp/infohub-backup.input >/dev/null
        docker exec "$CONTAINER_NAME" pg_restore \
            --exit-on-error --no-owner --no-privileges \
            -U infohub_user -d infohub_ai /tmp/infohub-backup.input >/dev/null
        ;;
    plain_sql)
        docker exec "$CONTAINER_NAME" psql \
            -X -v ON_ERROR_STOP=1 -U infohub_user -d infohub_ai \
            -f /tmp/infohub-backup.input >/dev/null
        ;;
    gzip)
        docker exec "$CONTAINER_NAME" bash -ceu '
            gzip -t /tmp/infohub-backup.input
            gzip -dc /tmp/infohub-backup.input > /tmp/infohub-backup.unpacked
            if [ "$(dd if=/tmp/infohub-backup.unpacked bs=5 count=1 status=none | od -An -tx1 | tr -d " \n")" = "5047444d50" ]; then
                pg_restore --list /tmp/infohub-backup.unpacked >/dev/null
                pg_restore --exit-on-error --no-owner --no-privileges \
                    -U infohub_user -d infohub_ai /tmp/infohub-backup.unpacked >/dev/null
            else
                psql -X -v ON_ERROR_STOP=1 -U infohub_user -d infohub_ai \
                    -f /tmp/infohub-backup.unpacked >/dev/null
            fi
        '
        ;;
esac

MISSING_TABLES="$(docker exec "$CONTAINER_NAME" psql \
    -X -v ON_ERROR_STOP=1 -U infohub_user -d infohub_ai -At \
    -c "SELECT coalesce(string_agg(name, ',' ORDER BY name), '') FROM (VALUES ('documents'),('document_chunks'),('document_relations'),('decision_facts'),('decision_links'),('law_amendments'),('users'),('subscriptions'),('payments'),('feedback'),('conversations'),('messages')) required(name) WHERE to_regclass('public.' || name) IS NULL;")"
[[ -z "$MISSING_TABLES" ]] || die "restored database is missing tables: $MISSING_TABLES"

COUNTS="$(docker exec "$CONTAINER_NAME" psql \
    -X -v ON_ERROR_STOP=1 -U infohub_user -d infohub_ai -At -F '|' \
    -c "SELECT (SELECT count(*) FROM documents), (SELECT count(*) FROM document_chunks), (SELECT count(*) FROM decision_facts), (SELECT count(*) FROM decision_links), (SELECT count(*) FROM users), (SELECT count(*) FROM conversations), (SELECT count(*) FROM document_chunks c LEFT JOIN documents d ON d.id=c.document_id WHERE d.id IS NULL), (SELECT count(*) FROM decision_facts f LEFT JOIN documents d ON d.id=f.document_id WHERE d.id IS NULL), (SELECT count(*) FROM decision_links l LEFT JOIN decision_facts hi ON hi.id=l.from_facts_id LEFT JOIN decision_facts lo ON lo.id=l.to_facts_id WHERE hi.id IS NULL OR lo.id IS NULL), (SELECT count(*) FROM pg_constraint WHERE contype='f' AND NOT convalidated), (SELECT count(*) FROM pg_extension WHERE extname='vector');")"
IFS='|' read -r DOCUMENTS CHUNKS FACTS LINKS USERS CONVERSATIONS \
    ORPHAN_CHUNKS ORPHAN_FACTS ORPHAN_LINKS UNVALIDATED_FKS VECTOR_EXTENSIONS \
    <<< "$COUNTS"

(( DOCUMENTS >= MIN_DOCUMENTS )) || die "restored documents below minimum: $DOCUMENTS"
(( CHUNKS >= MIN_CHUNKS )) || die "restored chunks below minimum: $CHUNKS"
(( FACTS >= MIN_FACTS )) || die "restored decision facts below minimum: $FACTS"
(( ORPHAN_CHUNKS == 0 )) || die "restored database has orphan chunks: $ORPHAN_CHUNKS"
(( ORPHAN_FACTS == 0 )) || die "restored database has orphan decision facts: $ORPHAN_FACTS"
(( ORPHAN_LINKS == 0 )) || die "restored database has orphan decision links: $ORPHAN_LINKS"
(( UNVALIDATED_FKS == 0 )) || die "restored database has unvalidated foreign keys"
(( VECTOR_EXTENSIONS == 1 )) || die "restored database is missing the vector extension"

COMPLETED_EPOCH="$(date -u +%s)"
COMPLETED_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RTO_SECONDS="$((COMPLETED_EPOCH - STARTED_EPOCH))"

install -m 0600 /dev/null "$EVIDENCE_TEMP"
printf '{\n  "schema_version": 1,\n  "result": "passed",\n  "started_at_utc": "%s",\n  "completed_at_utc": "%s",\n  "rpo_seconds": %s,\n  "rto_seconds": %s,\n  "backup": {"name": "%s", "bytes": %s, "format": "%s", "modified_at_utc": "%s", "sha256": "%s"},\n  "isolation": {"image": "%s", "image_id": "%s", "network": "none", "published_ports": false, "mounted_volumes": false},\n  "counts": {"documents": %s, "document_chunks": %s, "decision_facts": %s, "decision_links": %s, "users": %s, "conversations": %s},\n  "integrity": {"missing_critical_tables": 0, "orphan_chunks": %s, "orphan_decision_facts": %s, "orphan_decision_links": %s, "unvalidated_foreign_keys": %s, "vector_extension": true}\n}\n' \
    "$STARTED_UTC" "$COMPLETED_UTC" "$BACKUP_AGE_SECONDS" "$RTO_SECONDS" \
    "$BACKUP_NAME" "$BACKUP_SIZE" "$BACKUP_FORMAT" "$BACKUP_MODIFIED_UTC" \
    "$BACKUP_SHA256" "$POSTGRES_IMAGE" "$POSTGRES_IMAGE_ID" \
    "$DOCUMENTS" "$CHUNKS" "$FACTS" "$LINKS" "$USERS" "$CONVERSATIONS" \
    "$ORPHAN_CHUNKS" "$ORPHAN_FACTS" "$ORPHAN_LINKS" "$UNVALIDATED_FKS" \
    > "$EVIDENCE_TEMP"
mv -- "$EVIDENCE_TEMP" "$EVIDENCE_PATH"
EVIDENCE_TEMP=""
chmod 0600 "$EVIDENCE_PATH"

printf 'DATABASE_RESTORE_DRILL_RESULT={"result":"passed","evidence":"%s","rpo_seconds":%s,"rto_seconds":%s,"documents":%s,"document_chunks":%s,"decision_facts":%s}\n' \
    "$EVIDENCE_NAME" "$BACKUP_AGE_SECONDS" "$RTO_SECONDS" \
    "$DOCUMENTS" "$CHUNKS" "$FACTS"
