#!/usr/bin/env bash

# Drops the leftover table public.document_chunks_backup_20260630.
#
# It was a manual safety copy taken before the 2026-06-30 re-chunking; no code
# reads it, yet every nightly dump and restore drill carries its ~48k rows.
# Dry run by default: prints what would be dropped. With --apply it drops the
# table, but only when a checksummed nightly dump younger than
# $MAX_BACKUP_AGE_HOURS exists, so the data is still recoverable from backup.
#
# Usage: drop-stale-chunks-backup.sh [--apply]

set -Eeuo pipefail

TABLE="document_chunks_backup_20260630"
BACKUP_DIR="${INFOHUB_DB_BACKUP_DIR:-/root/backups/infohub}"
CONTAINER="${INFOHUB_DB_CONTAINER:-infohub-postgres}"
DB_USER="${INFOHUB_DB_USER:-infohub_user}"
DB_NAME="${INFOHUB_DB_NAME:-infohub_ai}"
MAX_BACKUP_AGE_HOURS="${INFOHUB_MAX_BACKUP_AGE_HOURS:-36}"

apply=0
case "${1:-}" in
    "") ;;
    --apply) apply=1 ;;
    *) echo "usage: $0 [--apply]" >&2; exit 2 ;;
esac

psql_live() {
    docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -XAtq -v ON_ERROR_STOP=1 -c "$1"
}

if [[ "$(psql_live "SELECT to_regclass('public.$TABLE') IS NOT NULL")" != "t" ]]; then
    echo "public.$TABLE does not exist; nothing to do."
    exit 0
fi

rows="$(psql_live "SELECT count(*) FROM public.$TABLE")"
size="$(psql_live "SELECT pg_size_pretty(pg_total_relation_size('public.$TABLE'))")"
echo "public.$TABLE: $rows rows, $size"

latest="$(find "$BACKUP_DIR" -maxdepth 1 -name 'infohub_ai-*.dump' -mmin "-$(( MAX_BACKUP_AGE_HOURS * 60 ))" -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -n 1 | cut -d' ' -f2- || true)"
if [[ -z "$latest" || ! -f "$latest.sha256" ]]; then
    echo "refusing: no checksummed dump younger than ${MAX_BACKUP_AGE_HOURS}h in $BACKUP_DIR" >&2
    exit 1
fi
echo "recoverable from $(basename "$latest") (and the weekly off-site copies)"

if (( ! apply )); then
    echo "dry run; rerun with --apply to drop it."
    exit 0
fi

psql_live "DROP TABLE public.$TABLE"
echo "dropped public.$TABLE"
