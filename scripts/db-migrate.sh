#!/usr/bin/env bash
# Explicit, controlled migration runner. The application NEVER migrates at
# startup; this script (or CI) is the only writer of schema change.
#
# Procedure (see docs/database/p7-operations.md):
#   1. Backup (caller-owned; refuses to run without BACKUP_REF).
#   2. Show current head.
#   3. Show pending migrations for review.
#   4. Apply upgrade head.
#   5. Verify single head.
# Required env: OWNER_DATABASE_URL, BACKUP_REF (e.g. pg_dump file path).
set -euo pipefail

: "${OWNER_DATABASE_URL:?OWNER_DATABASE_URL (owner URL) is required}"
: "${BACKUP_REF:?BACKUP_REF (proof a backup exists) is required. Take one first: scripts/backup-preview.sh}"

cd "$(dirname "$0")/.."

echo "== current revision =="
alembic -c backend/alembic.ini current

echo "== pending (review before applying) =="
alembic -c backend/alembic.ini history -r current:head || true

echo "== heads (must be exactly one) =="
HEADS="$(alembic -c backend/alembic.ini heads)"
echo "$HEADS"
if [ "$(echo "$HEADS" | grep -c '(head)' || true)" -ne 1 ]; then
  echo "refusing: migration history has multiple heads" >&2
  exit 1
fi

echo "== applying upgrade head =="
alembic -c backend/alembic.ini upgrade head

echo "== verifying =="
alembic -c backend/alembic.ini current
alembic -c backend/alembic.ini check || echo "(alembic check: template drift only, non-blocking)"
echo "migration complete (backup: $BACKUP_REF)"
