#!/usr/bin/env bash

# Safe, fast-forward-only production deployment for /root/infohub.

set -Eeuo pipefail

REPO_DIR="${INFOHUB_REPO_DIR:-/root/infohub}"
PUBLIC_HEALTH_URL="${INFOHUB_HEALTH_URL:-https://tax-advisor.ge/api/v1/public/health}"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this script as root so it can install operational configuration." >&2
    exit 1
fi

cd "$REPO_DIR"

CURRENT_BRANCH="$(git branch --show-current)"
if [[ "$CURRENT_BRANCH" != "main" ]]; then
    echo "Refusing deployment from branch '$CURRENT_BRANCH'; expected 'main'." >&2
    exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Refusing deployment: tracked or staged server changes are present." >&2
    git status --short >&2
    exit 1
fi

RUNNING_COMMIT="$(git rev-parse --short=12 HEAD)"
OLD_COMMIT="${INFOHUB_DEPLOY_FROM_COMMIT:-$RUNNING_COMMIT}"
git fetch origin main
git merge --ff-only origin/main
NEW_COMMIT="$(git rev-parse --short=12 HEAD)"

# A deploy can update this script while Bash is already reading the previous
# file. Re-exec the checked-out version before any build or runtime mutation so
# newly added safety gates take effect in the same deployment. Preserve the
# original commit for rollback tags and the final deployment report.
if [[ "${INFOHUB_DEPLOY_REEXECED:-0}" != "1" ]] && \
    [[ "$RUNNING_COMMIT" != "$NEW_COMMIT" ]] && \
    ! git diff --quiet "$RUNNING_COMMIT" "$NEW_COMMIT" -- scripts/deploy_production.sh; then
    export INFOHUB_DEPLOY_REEXECED=1
    export INFOHUB_DEPLOY_FROM_COMMIT="$OLD_COMMIT"
    exec "$REPO_DIR/scripts/deploy_production.sh"
fi

chmod 600 .env
install -d -m 0755 certbot/www
install -m 0644 ops/logrotate-infohub /etc/logrotate.d/infohub
install -d -m 0755 /etc/letsencrypt/renewal-hooks/deploy
install -m 0755 ops/reload-nginx-after-certificate.sh \
    /etc/letsencrypt/renewal-hooks/deploy/reload-infohub-nginx

docker compose config --quiet

BACKEND_IMAGE="$(docker inspect --format '{{.Image}}' infohub-backend 2>/dev/null || true)"
FRONTEND_IMAGE="$(docker inspect --format '{{.Image}}' infohub-frontend 2>/dev/null || true)"
if [[ -n "$BACKEND_IMAGE" ]]; then
    docker image tag "$BACKEND_IMAGE" "infohub/backend:rollback-$OLD_COMMIT"
fi
if [[ -n "$FRONTEND_IMAGE" ]]; then
    docker image tag "$FRONTEND_IMAGE" "infohub/frontend:rollback-$OLD_COMMIT"
fi

# Use a dedicated docker-container builder so InfoHub cannot grow or prune the
# host-wide BuildKit cache shared with unrelated projects. The helper loads the
# two explicit Compose images into Docker and enforces only this builder's
# bounded cache policy before any running container can be replaced.
python3 scripts/manage_infohub_buildkit.py build \
    --compose-file docker-compose.yml

# Validate the new backend image, production policy, CPU runtime, complete local
# embedding snapshot, deterministic multilingual probes and DB reachability
# before the image is allowed to replace the running container.
docker compose run --rm --no-deps backend \
    python scripts/audit_production_readiness.py --commit "$NEW_COMMIT"

# Install only the reviewed additive Temporal Legal Engine foundation.  The
# exact contract pin prevents an unreviewed model/trigger change from mutating
# production.  The following audit is read-only and must pass before runtime
# containers can be replaced.  This release creates no historical backfill and
# does not route public answers through the new tables.
LEGAL_TEMPORAL_SCHEMA_CONTRACT_SHA256="b69e7bcc73da12c5b80a69ec6fc436758842a11b838895d02241dcde0af07e98"
docker compose run --rm --no-deps backend \
    python scripts/install_legal_temporal_schema.py \
        --apply \
        --expected-contract-sha256 "$LEGAL_TEMPORAL_SCHEMA_CONTRACT_SHA256"
docker compose run --rm --no-deps backend \
    python scripts/audit_legal_temporal_schema.py \
        --execute \
        --expected-contract-sha256 "$LEGAL_TEMPORAL_SCHEMA_CONTRACT_SHA256"

# Additive and idempotent. The first run preserves every existing account by
# marking it verified before the new verification policy can become active.
docker compose run --rm --no-deps backend python scripts/add_auth_recovery.py

# Test the exact Nginx config and mounted certificate before touching ingress.
docker compose run --rm --no-deps nginx nginx -t

docker compose up -d --wait --no-deps backend frontend

# Nginx uses a single-file bind mount. Recreate it so a git replacement of the
# config file cannot leave the container attached to the previous inode.
docker compose up -d --force-recreate --no-deps nginx

for attempt in {1..12}; do
    if curl --fail --silent --show-error --max-time 15 "$PUBLIC_HEALTH_URL" >/dev/null; then
        echo "Deployment $OLD_COMMIT -> $NEW_COMMIT is healthy."
        exit 0
    fi
    sleep 5
done

echo "Deployment completed, but public health did not recover in 60 seconds." >&2
echo "Rollback images: infohub/backend:rollback-$OLD_COMMIT and infohub/frontend:rollback-$OLD_COMMIT" >&2
exit 1
