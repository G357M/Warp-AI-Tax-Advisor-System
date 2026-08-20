#!/usr/bin/env bash

# Rotate the production PostgreSQL role password without printing either value.

set -Eeuo pipefail
set +x

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"
PUBLIC_HEALTH_URL="${INFOHUB_HEALTH_URL:-https://tax-advisor.ge/api/v1/public/health}"
DB_ROLE="infohub_user"
DB_NAME="infohub_ai"
CHECK_ONLY=0

case "${1:-}" in
    "") ;;
    --check) CHECK_ONLY=1 ;;
    *)
        echo "Usage: $0 [--check]" >&2
        exit 2
        ;;
esac

for command_name in docker openssl curl grep git date mktemp; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "Required command is missing: $command_name" >&2
        exit 1
    fi
done

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Environment file not found: $ENV_FILE" >&2
    exit 1
fi
if [[ "$(git branch --show-current)" != "main" ]]; then
    echo "Refusing database credential rotation outside the main branch." >&2
    exit 1
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Refusing database credential rotation with tracked server changes." >&2
    exit 1
fi

read_env_value() {
    local key="$1"
    local line
    line="$(grep -m1 "^${key}=" "$ENV_FILE" || true)"
    printf '%s' "${line#*=}"
}

strip_matching_quotes() {
    local value="$1"
    if [[ ${#value} -ge 2 ]]; then
        if [[ "${value:0:1}" == '"' && "${value: -1}" == '"' ]]; then
            value="${value:1:${#value}-2}"
        elif [[ "${value:0:1}" == "'" && "${value: -1}" == "'" ]]; then
            value="${value:1:${#value}-2}"
        fi
    fi
    printf '%s' "$value"
}

sql_string_literal() {
    local value="$1"
    value="${value//\'/\'\'}"
    printf "'%s'" "$value"
}

set_role_password() {
    local password_literal
    password_literal="$(sql_string_literal "$1")"
    printf 'ALTER ROLE "%s" WITH PASSWORD %s;\n' "$DB_ROLE" "$password_literal" | \
        docker compose exec -T postgres psql \
            --username "$DB_ROLE" --dbname "$DB_NAME" --set ON_ERROR_STOP=1 >/dev/null
}

current_password="$(strip_matching_quotes "$(read_env_value POSTGRES_PASSWORD)")"
if [[ -z "$current_password" ]]; then
    echo "POSTGRES_PASSWORD is missing from $ENV_FILE" >&2
    exit 1
fi

# Prove the current application connection and local administrative path before
# changing either the environment file or the database role.
docker compose exec -T backend python -c \
    "from sqlalchemy import text; from core.database import SessionLocal; db=SessionLocal(); assert db.execute(text('SELECT 1')).scalar() == 1; db.close()" >/dev/null
docker compose exec -T postgres psql \
    --username "$DB_ROLE" --dbname "$DB_NAME" --set ON_ERROR_STOP=1 \
    --tuples-only --no-align --command "SELECT current_user" | grep -qx "$DB_ROLE"

if (( CHECK_ONLY == 1 )); then
    echo "Database credential rotation preflight: ok"
    exit 0
fi

new_password="$(openssl rand -hex 32)"
backup_dir="$REPO_ROOT/.state/database-password-rotation"
backup_file="$backup_dir/.env.pre-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
cp -p "$ENV_FILE" "$backup_file"
chmod 600 "$backup_file"

write_new_env() {
    local temp_file
    local found=0
    temp_file="$(mktemp "${ENV_FILE}.database.XXXXXX")"
    chmod 600 "$temp_file"

    while IFS= read -r line || [[ -n "$line" ]]; do
        case "$line" in
            POSTGRES_PASSWORD=*)
                printf 'POSTGRES_PASSWORD=%s\n' "$new_password" >>"$temp_file"
                found=1
                ;;
            *)
                printf '%s\n' "$line" >>"$temp_file"
                ;;
        esac
    done <"$ENV_FILE"

    (( found == 1 )) || printf 'POSTGRES_PASSWORD=%s\n' "$new_password" >>"$temp_file"
    mv -f "$temp_file" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
}

restore_previous_state() {
    echo "Database credential verification failed; restoring the previous credential." >&2
    set +e
    set_role_password "$current_password"
    cp -p "$backup_file" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    docker compose up -d --wait --no-deps --force-recreate backend
    set -e
}

write_new_env
if ! docker compose config --quiet; then
    cp -p "$backup_file" "$ENV_FILE"
    exit 1
fi

if ! set_role_password "$new_password" || \
    ! docker compose up -d --wait --no-deps --force-recreate backend || \
    ! docker compose exec -T backend python -c \
        "from sqlalchemy import text; from core.database import SessionLocal; db=SessionLocal(); assert db.execute(text('SELECT 1')).scalar() == 1; db.close()" >/dev/null || \
    ! curl --fail --silent --show-error --max-time 15 "$PUBLIC_HEALTH_URL" >/dev/null; then
    restore_previous_state
    exit 1
fi

echo "PostgreSQL application password rotation completed."
echo "Backend connection and public health: ok"
echo "Rollback environment: $backup_file"
