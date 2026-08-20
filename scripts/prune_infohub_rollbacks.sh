#!/usr/bin/env bash

# Bounded, dry-run-first retention for InfoHub rollback image tags.

set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEEP_ROLLBACKS="${INFOHUB_ROLLBACK_KEEP:-3}"
APPLY=0

usage() {
    cat <<'EOF'
Usage: ./scripts/prune_infohub_rollbacks.sh [--keep N] [--apply]

Keeps the N newest main-branch rollback tags for each InfoHub application
image. The default is a dry run and N=3. Only exact tags matching
infohub/backend:rollback-<12 hex> and infohub/frontend:rollback-<12 hex>
are eligible. Current :latest images and global Docker build cache are never
removed by this script.
EOF
}

while (( $# > 0 )); do
    case "$1" in
        --keep)
            if (( $# < 2 )); then
                echo "--keep requires a value." >&2
                exit 2
            fi
            KEEP_ROLLBACKS="$2"
            shift 2
            ;;
        --apply)
            APPLY=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ ! "$KEEP_ROLLBACKS" =~ ^[0-9]+$ ]]; then
    echo "Rollback retention must be an integer of at least 2." >&2
    exit 2
fi
KEEP_ROLLBACKS="$((10#$KEEP_ROLLBACKS))"
if (( KEEP_ROLLBACKS < 2 )); then
    echo "Rollback retention must be an integer of at least 2." >&2
    exit 2
fi

for command_name in docker git sort; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "Required command is missing: $command_name" >&2
        exit 1
    fi
done

cd "$REPO_ROOT"

if [[ "$(git branch --show-current)" != "main" ]]; then
    echo "Refusing retention outside the main branch." >&2
    exit 1
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Refusing retention while tracked server changes are present." >&2
    exit 1
fi

assert_active_latest() {
    local service="$1"
    local container="infohub-$service"
    local latest_ref="infohub-$service:latest"
    local active_id latest_id

    active_id="$(docker inspect --format '{{.Image}}' "$container" 2>/dev/null || true)"
    latest_id="$(docker image inspect --format '{{.Id}}' "$latest_ref" 2>/dev/null || true)"
    if [[ -z "$active_id" || -z "$latest_id" || "$active_id" != "$latest_id" ]]; then
        echo "Refusing retention: $container is not running $latest_ref." >&2
        exit 1
    fi
}

assert_active_latest backend
assert_active_latest frontend

declare -a kept_refs=()
declare -a delete_refs=()
declare -a protected_refs=()

plan_repository() {
    local repository="$1"
    local ref commit rank index
    local -a ranked=()
    local -a sorted_refs=()

    while IFS= read -r ref; do
        [[ -n "$ref" ]] || continue
        if [[ ! "$ref" =~ ^${repository}:rollback-([0-9a-f]{12})$ ]]; then
            protected_refs+=("$ref")
            continue
        fi

        commit="${BASH_REMATCH[1]}"
        if ! git cat-file -e "${commit}^{commit}" 2>/dev/null || \
            ! git merge-base --is-ancestor "$commit" HEAD; then
            protected_refs+=("$ref")
            continue
        fi

        rank="$(git rev-list --count "$commit")"
        ranked+=("${rank}|${ref}")
    done < <(docker image ls "$repository" --format '{{.Repository}}:{{.Tag}}')

    if (( ${#ranked[@]} > 0 )); then
        mapfile -t sorted_refs < <(
            printf '%s\n' "${ranked[@]}" | sort -t '|' -k1,1nr -k2,2
        )
    fi

    for index in "${!sorted_refs[@]}"; do
        ref="${sorted_refs[$index]#*|}"
        if (( index < KEEP_ROLLBACKS )); then
            kept_refs+=("$ref")
        else
            delete_refs+=("$ref")
        fi
    done
}

plan_repository infohub/backend
plan_repository infohub/frontend

echo "InfoHub rollback retention plan (keep newest $KEEP_ROLLBACKS per image):"
for ref in "${kept_refs[@]}"; do
    echo "  KEEP    $ref"
done
for ref in "${protected_refs[@]}"; do
    echo "  PROTECT $ref (not a known main-branch rollback commit)"
done
for ref in "${delete_refs[@]}"; do
    echo "  DELETE  $ref"
done

if (( ${#delete_refs[@]} == 0 )); then
    echo "No rollback tags exceed the retention limit."
    exit 0
fi

if (( APPLY == 0 )); then
    echo "Dry run only; no images were changed. Re-run with --apply to execute this exact policy."
    exit 0
fi

for ref in "${delete_refs[@]}"; do
    docker image rm "$ref"
done

echo "Rollback retention applied. Removed ${#delete_refs[@]} exact tags."
