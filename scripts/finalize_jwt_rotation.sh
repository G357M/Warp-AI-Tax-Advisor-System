#!/usr/bin/env bash
set -Eeuo pipefail
set +x

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"

for command_name in docker curl date; do
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
previous_secret="$(strip_matching_quotes "$(read_env_value JWT_PREVIOUS_SECRET_KEYS)")"
accept_until="$(strip_matching_quotes "$(read_env_value JWT_PREVIOUS_SECRET_ACCEPT_UNTIL)")"

if (( ${#current_secret} < 32 )); then
    echo "Current JWT_SECRET_KEY is shorter than 32 bytes; refusing to finalize." >&2
    exit 1
fi
if [[ -z "$previous_secret" && -z "$accept_until" ]]; then
    echo "JWT rotation fallback is already finalized."
    exit 0
fi
if [[ -z "$previous_secret" || -z "$accept_until" ]]; then
    echo "JWT rotation state is incomplete; refusing to change it." >&2
    exit 1
fi

accept_epoch="$(date -u -d "$accept_until" +%s 2>/dev/null || true)"
if [[ -z "$accept_epoch" ]]; then
    echo "JWT_PREVIOUS_SECRET_ACCEPT_UNTIL is not a valid UTC timestamp." >&2
    exit 1
fi
now_epoch="$(date -u +%s)"
if (( now_epoch <= accept_epoch )); then
    echo "JWT grace window remains active until $accept_until; refusing early finalization." >&2
    exit 1
fi

expired_token="$(docker compose exec -T backend python -c \
    "from datetime import datetime, timedelta, timezone; import jwt; from core.config import settings; from core.database import SessionLocal; from models import User; db=SessionLocal(); user=db.query(User).filter(User.is_active.is_(True)).first(); old=settings.JWT_PREVIOUS_SECRET_KEYS.split(',')[0]; print(jwt.encode({'sub': user.username, 'role': user.role, 'exp': datetime.now(timezone.utc)+timedelta(minutes=5)}, old, algorithm=settings.ALGORITHM) if user and old else '')")"
if [[ -z "$expired_token" ]]; then
    echo "Could not create the expired-key verification token." >&2
    exit 1
fi

before_status="$(printf 'Authorization: Bearer %s\n' "$expired_token" | \
    curl -sS -o /dev/null -w '%{http_code}' -H @- https://tax-advisor.ge/api/v1/auth/me)"
if [[ "$before_status" != "401" ]]; then
    echo "Expired previous key is still accepted (HTTP $before_status); refusing finalization." >&2
    exit 1
fi

backup_dir="$REPO_ROOT/.state/jwt-rotation"
backup_file="$backup_dir/.env.pre-finalize-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
cp -p "$ENV_FILE" "$backup_file"
chmod 600 "$backup_file"

write_finalized_env() {
    local temp_file
    temp_file="$(mktemp "${ENV_FILE}.jwt.XXXXXX")"
    chmod 600 "$temp_file"
    while IFS= read -r line || [[ -n "$line" ]]; do
        case "$line" in
            JWT_PREVIOUS_SECRET_KEYS=*)
                printf 'JWT_PREVIOUS_SECRET_KEYS=\n' >>"$temp_file"
                ;;
            JWT_PREVIOUS_SECRET_ACCEPT_UNTIL=*)
                printf 'JWT_PREVIOUS_SECRET_ACCEPT_UNTIL=\n' >>"$temp_file"
                ;;
            *)
                printf '%s\n' "$line" >>"$temp_file"
                ;;
        esac
    done <"$ENV_FILE"
    mv -f "$temp_file" "$ENV_FILE"
}

restore_rotation_env() {
    echo "JWT finalization verification failed; restoring the rotation environment." >&2
    cp -p "$backup_file" "$ENV_FILE"
    docker compose up -d --wait --no-deps --force-recreate backend
}

write_finalized_env

if ! docker compose config >/dev/null || \
    ! docker compose up -d --wait --no-deps --force-recreate backend; then
    restore_rotation_env
    exit 1
fi

after_status="$(printf 'Authorization: Bearer %s\n' "$expired_token" | \
    curl -sS -o /dev/null -w '%{http_code}' -H @- https://tax-advisor.ge/api/v1/auth/me)"
if [[ "$after_status" != "401" ]] || \
    ! docker compose exec -T backend python -c \
        "from core.config import settings; assert len(settings.JWT_SECRET_KEY.encode()) >= 32; assert not settings.JWT_PREVIOUS_SECRET_KEYS; assert not settings.JWT_PREVIOUS_SECRET_ACCEPT_UNTIL" || \
    ! curl -fsS https://tax-advisor.ge/api/v1/public/health >/dev/null; then
    restore_rotation_env
    exit 1
fi

echo "JWT rotation fallback finalized."
echo "Expired-key probe before cleanup: HTTP $before_status"
echo "Expired-key probe after cleanup: HTTP $after_status"
echo "Rollback environment: $backup_file"
