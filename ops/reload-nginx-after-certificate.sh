#!/usr/bin/env bash

set -Eeuo pipefail

if docker ps --format '{{.Names}}' | grep -qx 'infohub-nginx'; then
    docker exec infohub-nginx nginx -t
    docker exec infohub-nginx nginx -s reload
fi
