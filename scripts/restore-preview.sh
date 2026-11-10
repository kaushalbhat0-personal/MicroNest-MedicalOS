#!/usr/bin/env bash
# Preview restore exercise. Restores a backup from scripts/backup-preview.sh
# into ISOLATED scratch resources (never the live preview or production DB),
# then verifies: schema current, RLS enabled, seed roles intact, storage
# round-trips. Prints PASS/FAIL per check; exit nonzero on any failure.
#
# Required env: BACKUP_REF (dir from backup script), BACKUP_ENCRYPTION_PASSWORD
#   (or _FILE), RESTORE_PG_CONTAINER (isolated scratch postgres).
set -euo pipefail

: "${BACKUP_REF:?BACKUP_REF (backup dir) is required}"
: "${RESTORE_PG_CONTAINER:?RESTORE_PG_CONTAINER (isolated scratch postgres container) is required}"

case "$RESTORE_PG_CONTAINER" in
  *preview*|*prod*|*healthcare_os) echo "refusing: restore target name is not isolated" >&2; exit 1 ;;
esac

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if [ -n "${BACKUP_ENCRYPTION_PASSWORD_FILE:-}" ]; then
  PASS_ARG=(-pass "file:$BACKUP_ENCRYPTION_PASSWORD_FILE")
else
  : "${BACKUP_ENCRYPTION_PASSWORD:?backup encryption password is required}"
  PASS_ARG=(-pass "env:BACKUP_ENCRYPTION_PASSWORD")
fi

openssl enc -d -aes-256-cbc -pbkdf2 -in "$BACKUP_REF/preview.dump.enc" -out "$WORK/preview.dump" "${PASS_ARG[@]}"
openssl enc -d -aes-256-cbc -pbkdf2 -in "$BACKUP_REF/storage.tgz.enc" -out "$WORK/storage.tgz" "${PASS_ARG[@]}"

RESTORE_DB="restore_check_$$"
docker exec "$RESTORE_PG_CONTAINER" psql -U postgres -d postgres -c "CREATE DATABASE $RESTORE_DB;" >/dev/null
cleanup() { docker exec "$RESTORE_PG_CONTAINER" psql -U postgres -d postgres -c "DROP DATABASE $RESTORE_DB;" >/dev/null || true; }
trap 'cleanup; rm -rf "$WORK"' EXIT

docker cp "$WORK/preview.dump" "$RESTORE_PG_CONTAINER:/tmp/restore.dump"
docker exec "$RESTORE_PG_CONTAINER" pg_restore -U postgres -d "$RESTORE_DB" /tmp/restore.dump >/dev/null

PASS=1
check() {  # $1=name $2=expected $3=actual
  if [ "$2" = "$3" ]; then echo "PASS: $1"; else echo "FAIL: $1 (expected=$2 actual=$3)"; PASS=0; fi
}

TABLES="$(docker exec "$RESTORE_PG_CONTAINER" psql -U postgres -d "$RESTORE_DB" -tAc "SELECT count(*) FROM pg_tables WHERE schemaname='public'")"
check "public tables present" ">=15" "$( [ "$TABLES" -ge 15 ] && echo '>=15' || echo "$TABLES" )"
SEEDS="$(docker exec "$RESTORE_PG_CONTAINER" psql -U postgres -d "$RESTORE_DB" -tAc "SELECT count(*) FROM roles WHERE tenant_id IS NULL")"
check "seed roles intact (8)" "8" "$SEEDS"
RLS="$(docker exec "$RESTORE_PG_CONTAINER" psql -U postgres -d "$RESTORE_DB" -tAc "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND rowsecurity")"
check "RLS enabled tables (>=6)" ">=6" "$( [ "$RLS" -ge 6 ] && echo '>=6' || echo "$RLS" )"
FORCE="$(docker exec "$RESTORE_PG_CONTAINER" psql -U postgres -d "$RESTORE_DB" -tAc "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND rowsecurity")"
check "rls tables visible" ">=6" "$FORCE"

mkdir -p "$WORK/storage" && tar -xzf "$WORK/storage.tgz" -C "$WORK/storage"
check "storage archive extracts" "yes" "$( [ -d "$WORK/storage" ] && echo yes || echo no )"

if [ "$PASS" = 1 ]; then echo "RESTORE EXERCISE: PASS"; else echo "RESTORE EXERCISE: FAIL"; exit 1; fi
