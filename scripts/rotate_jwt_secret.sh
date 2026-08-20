#!/usr/bin/env bash
set -Eeuo pipefail
set +x

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"
GRACE_MINUTES="${1:-35}"

if [[ ! "$GRACE_MINUTES" =~ ^[0-9]+$ ]] || (( GRACE_MINUTES < 5 || GRACE_MINUTES > 1440 )); then
    echo "Usage: $0 [grace-minutes between 5 and 1440]" >&2
    exit 2
fi

for command_name in docker openssl curl date; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "Required command is missing: $command_name" >&2
        exit 1
    fi
done

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Environment file not found: $ENV_FILE" >&2
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

current_secret="$(strip_matching_quotes "$(read_env_value JWT_SECRET_KEY)")"
if [[ -z "$current_secret" ]]; then
    echo "JWT_SECRET_KEY is missing from $ENV_FILE" >&2
    exit 1
fi

access_minutes="$(strip_matching_quotes "$(read_env_value ACCESS_TOKEN_EXPIRE_MINUTES)")"
access_minutes="${access_minutes:-30}"
if [[ ! "$access_minutes" =~ ^[0-9]+$ ]]; then
    echo "ACCESS_TOKEN_EXPIRE_MINUTES must be an integer" >&2
    exit 1
fi
if (( GRACE_MINUTES < access_minutes + 5 )); then
    echo "Grace window must be at least ACCESS_TOKEN_EXPIRE_MINUTES + 5 (${access_minutes} + 5)." >&2
    exit 1
fi

existing_until="$(strip_matching_quotes "$(read_env_value JWT_PREVIOUS_SECRET_ACCEPT_UNTIL)")"
if [[ -n "$existing_until" ]]; then
    existing_epoch="$(date -u -d "$existing_until" +%s 2>/dev/null || true)"
    if [[ -n "$existing_epoch" ]] && (( existing_epoch > $(date -u +%s) )); then
        echo "An earlier JWT rotation window is still active until $existing_until; refusing to rotate again." >&2
        exit 1
    fi
fi

if ! docker compose exec -T backend python -c \
    "from core.config import settings; assert hasattr(settings, 'JWT_PREVIOUS_SECRET_ACCEPT_UNTIL')"; then
    echo "The running backend does not support grace-period JWT rotation yet." >&2
    exit 1
fi

probe_token="$(docker compose exec -T backend python -c \
    "from core.database import SessionLocal; from core.security import create_access_token; from models import User; db=SessionLocal(); user=db.query(User).filter(User.is_active.is_(True)).first(); print(create_access_token({'sub': user.username, 'role': user.role}) if user else '')")"
if [[ -z "$probe_token" ]]; then
    echo "No active user is available for the session-continuity probe; rotation was not started." >&2
    exit 1
fi

new_secret="$(openssl rand -hex 32)"
accept_until="$(date -u -d "+${GRACE_MINUTES} minutes" +%Y-%m-%dT%H:%M:%SZ)"
backup_dir="$REPO_ROOT/.state/jwt-rotation"
backup_file="$backup_dir/.env.pre-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
cp -p "$ENV_FILE" "$backup_file"
chmod 600 "$backup_file"

write_rotated_env() {
    local temp_file
    local found_current=0
    local found_previous=0
    local found_until=0
    temp_file="$(mktemp "${ENV_FILE}.jwt.XXXXXX")"
    chmod 600 "$temp_file"

    while IFS= read -r line || [[ -n "$line" ]]; do
        case "$line" in
            JWT_SECRET_KEY=*)
                printf 'JWT_SECRET_KEY=%s\n' "$new_secret" >>"$temp_file"
                found_current=1
                ;;
            JWT_PREVIOUS_SECRET_KEYS=*)
                printf 'JWT_PREVIOUS_SECRET_KEYS=%s\n' "$current_secret" >>"$temp_file"
                found_previous=1
                ;;
            JWT_PREVIOUS_SECRET_ACCEPT_UNTIL=*)
                printf 'JWT_PREVIOUS_SECRET_ACCEPT_UNTIL=%s\n' "$accept_until" >>"$temp_file"
                found_until=1
                ;;
            *)
                printf '%s\n' "$line" >>"$temp_file"
                ;;
        esac
    done <"$ENV_FILE"

    (( found_current == 1 )) || printf 'JWT_SECRET_KEY=%s\n' "$new_secret" >>"$temp_file"
    (( found_previous == 1 )) || printf 'JWT_PREVIOUS_SECRET_KEYS=%s\n' "$current_secret" >>"$temp_file"
    (( found_until == 1 )) || printf 'JWT_PREVIOUS_SECRET_ACCEPT_UNTIL=%s\n' "$accept_until" >>"$temp_file"
    mv -f "$temp_file" "$ENV_FILE"
}

restore_previous_env() {
    echo "JWT rotation verification failed; restoring the previous environment." >&2
    cp -p "$backup_file" "$ENV_FILE"
    docker compose up -d --wait --no-deps --force-recreate backend
}

write_rotated_env

if ! docker compose config >/dev/null; then
    restore_previous_env
    exit 1
fi

if ! docker compose up -d --wait --no-deps --force-recreate backend; then
    restore_previous_env
    exit 1
fi

old_status="$(printf 'Authorization: Bearer %s\n' "$probe_token" | \
    curl -sS -o /dev/null -w '%{http_code}' -H @- https://tax-advisor.ge/api/v1/auth/me)"
new_token="$(docker compose exec -T backend python -c \
    "from core.database import SessionLocal; from core.security import create_access_token; from models import User; db=SessionLocal(); user=db.query(User).filter(User.is_active.is_(True)).first(); print(create_access_token({'sub': user.username, 'role': user.role}))")"
new_status="$(printf 'Authorization: Bearer %s\n' "$new_token" | \
    curl -sS -o /dev/null -w '%{http_code}' -H @- https://tax-advisor.ge/api/v1/auth/me)"

if [[ "$old_status" != "200" || "$new_status" != "200" ]] || \
    ! curl -fsS https://tax-advisor.ge/api/v1/public/health >/dev/null; then
    restore_previous_env
    exit 1
fi

echo "JWT secret rotation completed."
echo "Previous sessions are accepted until: $accept_until"
echo "Old-token probe: HTTP $old_status"
echo "New-token probe: HTTP $new_status"
echo "Rollback environment: $backup_file"
