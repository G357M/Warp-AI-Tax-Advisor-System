#!/bin/bash
# Backwards-compatible entry point. The former version overwrote the current
# API ingestion runner with an obsolete HTML crawler; schedule reconciliation
# now belongs to the dry-run-first root operational script.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
REPOSITORY_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
exec "$REPOSITORY_ROOT/scripts/configure_ingestion_schedule.sh" "$@"
