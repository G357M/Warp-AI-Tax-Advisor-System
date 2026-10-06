#!/usr/bin/env bash

# Restore drill for the nightly production database backup.
#
# Proves a dump written by ops/backup-infohub-db.sh can actually be restored,
# not just listed: checks the sha256, restores the archive into a throwaway
# Postgres container built from the same image as production, and compares
# what came back with the live database (row counts per table, schema object
# counts, invalid indexes, a pgvector nearest-neighbour query).
#
# Production is only read: the drill container has no network, mounts the
# backup directory read-only, runs under CPU/memory limits and is removed
# together with its volume on exit, whatever the outcome.
#
# Usage: restore-drill-infohub-db.sh [path/to/infohub_ai-*.dump]
#        (default: the newest dump in $BACKUP_DIR)

set -Eeuo pipefail

BACKUP_DIR="${INFOHUB_DB_BACKUP_DIR:-/root/backups/infohub}"
CONTAINER="${INFOHUB_DB_CONTAINER:-infohub-postgres}"
DB_USER="${INFOHUB_DB_USER:-infohub_user}"
DB_NAME="${INFOHUB_DB_NAME:-infohub_ai}"
# Shares the backup lock so a drill never overlaps the nightly dump.
LOCK_FILE="${INFOHUB_DB_BACKUP_LOCK:-/run/lock/infohub-db-backup.lock}"
CPUS="${INFOHUB_RESTORE_DRILL_CPUS:-1}"
MEMORY="${INFOHUB_RESTORE_DRILL_MEMORY:-2g}"
# Docker's default 64 MB /dev/shm is too small for the dynamic shared memory
# that parallel index builds allocate during pg_restore.
SHM_SIZE="${INFOHUB_RESTORE_DRILL_SHM_SIZE:-1g}"
JOBS="${INFOHUB_RESTORE_DRILL_JOBS:-2}"
# Production keeps changing after the dump, so core tables may only have
# grown or shrunk by a bounded amount (percent of the live row count).
MIN_PERCENT="${INFOHUB_RESTORE_DRILL_MIN_PERCENT:-90}"
READY_TIMEOUT="${INFOHUB_RESTORE_DRILL_READY_TIMEOUT:-120}"
CORE_TABLES=(documents document_chunks users decision_facts)

log() { echo "[restore-drill $(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
fail() {
    log "FAILED: $*" >&2
    printf 'failed %s %s\n' "${dump_name:-?}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" 2>/dev/null > "$BACKUP_DIR/restore-drill-last.txt" || true
    exit 1
}

for value in "$CPUS" "$JOBS" "$MIN_PERCENT" "$READY_TIMEOUT"; do
    if ! [[ "$value" =~ ^[1-9][0-9]*$ ]]; then
        log "numeric settings must be positive integers, got '$value'" >&2
        exit 2
    fi
done

dump="${1:-}"
if [[ -z "$dump" ]]; then
    dump="$(ls -1t "$BACKUP_DIR"/infohub_ai-*.dump 2>/dev/null | head -n 1 || true)"
    [[ -n "$dump" ]] || fail "no infohub_ai-*.dump in $BACKUP_DIR"
fi
[[ -f "$dump" ]] || fail "dump not found: $dump"
dump_dir="$(cd "$(dirname "$dump")" && pwd)"
dump_name="$(basename "$dump")"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    log "a backup or another drill is running; try again later" >&2
    exit 75
fi

log "dump $dump_dir/$dump_name ($(stat -c %s "$dump") bytes)"
[[ -f "$dump_dir/$dump_name.sha256" ]] || fail "missing checksum $dump_name.sha256"
(cd "$dump_dir" && sha256sum --check --quiet "$dump_name.sha256") || fail "sha256 mismatch for $dump_name"
log "checksum ok"

live_psql() { docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -XAtq -v ON_ERROR_STOP=1 -c "$1"; }

image="$(docker inspect --format '{{.Config.Image}}' "$CONTAINER")" || fail "cannot inspect $CONTAINER"
live_bytes="$(live_psql "SELECT pg_database_size(current_database())")"
docker_root="$(docker info --format '{{.DockerRootDir}}')"
need_kb=$(( live_bytes / 1024 * 12 / 10 ))
free_kb="$(df --output=avail -k "$docker_root" | tail -n 1 | tr -d ' ')"
if (( free_kb < need_kb )); then
    fail "not enough free space under $docker_root: ${free_kb} KiB available, ${need_kb} KiB needed"
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
drill="infohub-restore-drill-$stamp"
restore_log="$(mktemp)"
cleanup() {
    docker rm -f "$drill" >/dev/null 2>&1 || true
    docker volume rm "$drill" >/dev/null 2>&1 || true
    rm -f "$restore_log"
}
trap cleanup EXIT

started=$SECONDS
log "starting $drill from $image (cpus=$CPUS memory=$MEMORY shm=$SHM_SIZE, no network)"
docker volume create "$drill" >/dev/null
docker run -d --name "$drill" \
    --network none \
    --cpus "$CPUS" --memory "$MEMORY" --shm-size "$SHM_SIZE" \
    -e POSTGRES_USER="$DB_USER" \
    -e POSTGRES_PASSWORD="drill-$stamp" \
    -e POSTGRES_DB="$DB_NAME" \
    -v "$drill:/var/lib/postgresql/data" \
    -v "$dump_dir:/backups:ro" \
    "$image" >/dev/null

# The image's init phase runs a socket-only server; TCP on loopback answers
# only once the final server is up.
deadline=$(( SECONDS + READY_TIMEOUT ))
until docker exec "$drill" pg_isready -q -h 127.0.0.1 -U "$DB_USER" -d "$DB_NAME"; do
    (( SECONDS < deadline )) || fail "drill postgres not ready after ${READY_TIMEOUT}s"
    sleep 2
done

drill_psql() { docker exec "$drill" psql -h 127.0.0.1 -U "$DB_USER" -d "$DB_NAME" -XAtq -v ON_ERROR_STOP=1 -c "$1"; }

log "restoring with pg_restore -j $JOBS"
if ! docker exec "$drill" pg_restore -h 127.0.0.1 -U "$DB_USER" -d "$DB_NAME" -j "$JOBS" "/backups/$dump_name" >"$restore_log" 2>&1; then
    grep -m 40 -E "error|ERROR|Command was" "$restore_log" >&2 || tail -n 20 "$restore_log" >&2
    fail "pg_restore reported errors"
fi
log "restore finished in $(( SECONDS - started ))s"

problems=0

table_sql="SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
mapfile -t tables < <(drill_psql "$table_sql")
(( ${#tables[@]} > 0 )) || fail "restored database has no tables"
mapfile -t live_tables < <(live_psql "$table_sql")
missing="$(comm -13 <(printf '%s\n' "${tables[@]}" | LC_ALL=C sort) <(printf '%s\n' "${live_tables[@]}" | LC_ALL=C sort) | tr '\n' ' ')"
[[ -z "$missing" ]] || log "note: tables created after the dump: $missing"

printf '%-36s %12s %12s\n' table restored live
for table in "${tables[@]}"; do
    restored="$(drill_psql "SELECT count(*) FROM public.\"$table\"")"
    live="$(live_psql "SELECT count(*) FROM public.\"$table\"" 2>/dev/null || echo "-")"
    mark=""
    for core in "${CORE_TABLES[@]}"; do
        [[ "$table" == "$core" ]] || continue
        if (( restored == 0 )); then
            mark="  <- EMPTY"; problems=$(( problems + 1 ))
        elif [[ "$live" =~ ^[0-9]+$ ]] && (( restored * 100 < live * MIN_PERCENT || live * 100 < restored * MIN_PERCENT )); then
            mark="  <- differs from live by more than $(( 100 - MIN_PERCENT ))%"; problems=$(( problems + 1 ))
        fi
    done
    printf '%-36s %12s %12s%s\n' "$table" "$restored" "$live" "$mark"
done
for core in "${CORE_TABLES[@]}"; do
    found=0
    for table in "${tables[@]}"; do [[ "$table" == "$core" ]] && found=1; done
    (( found )) || { log "core table '$core' missing from restore" >&2; problems=$(( problems + 1 )); }
done

objects_sql="SELECT c.relkind || ':' || count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind IN ('r','i','S','v','m') GROUP BY c.relkind ORDER BY 1"
restored_objects="$(drill_psql "$objects_sql" | tr '\n' ' ')"
live_objects="$(live_psql "$objects_sql" | tr '\n' ' ')"
log "schema objects (r=tables i=indexes S=sequences v=views m=matviews): restored [$restored_objects] live [$live_objects]"
[[ "$restored_objects" == "$live_objects" ]] || log "note: schema object counts differ (expected only after a migration since the dump)"

invalid="$(drill_psql "SELECT count(*) FROM pg_index WHERE NOT indisvalid")"
if (( invalid > 0 )); then
    log "$invalid invalid index(es) after restore" >&2; problems=$(( problems + 1 ))
fi

extensions="$(drill_psql "SELECT string_agg(extname || ' ' || extversion, ', ' ORDER BY extname) FROM pg_extension")"
log "extensions: $extensions"

with_vectors="$(drill_psql "SELECT count(*) FROM document_chunks WHERE embedding IS NOT NULL")"
if (( with_vectors == 0 )); then
    log "no document_chunks.embedding vectors restored" >&2; problems=$(( problems + 1 ))
else
    neighbours="$(drill_psql "SELECT count(*) FROM (SELECT id FROM document_chunks WHERE embedding IS NOT NULL ORDER BY embedding <=> (SELECT embedding FROM document_chunks WHERE embedding IS NOT NULL LIMIT 1) LIMIT 5) s")"
    (( neighbours == 5 )) || { log "pgvector nearest-neighbour query returned $neighbours rows" >&2; problems=$(( problems + 1 )); }
    log "pgvector ok: $with_vectors chunks with embeddings, nearest-neighbour query returned $neighbours rows"
fi

duration=$(( SECONDS - started ))
(( problems == 0 )) || fail "$problems check(s) failed for $dump_name after ${duration}s"

printf 'ok %s %s %ss\n' "$dump_name" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$duration" > "$BACKUP_DIR/restore-drill-last.txt"
log "ok $dump_name restored and verified in ${duration}s"
