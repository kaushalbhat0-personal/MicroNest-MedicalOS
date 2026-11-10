#!/usr/bin/env bash
# Preview backup: Postgres custom-format dump + storage volume tarball,
# encrypted with openssl (AES-256-GCM equivalent via enc + pbkdf2).
# Never run against production; this script refuses non-preview databases.
#
# Required env: PREVIEW_OWNER_PASSWORD, BACKUP_ENCRYPTION_PASSWORD (file or
#   BACKUP_ENCRYPTION_PASSWORD_FILE), PREVIEW_PG_CONTAINER (default hos-preview-db-1),
#   PREVIEW_STORAGE_VOLUME (default hos-preview_preview-miniodata).
# Output: ./var/backups/preview-<ts>/ (gitignored).
set -euo pipefail

DB_NAME="healthcare_os_preview"
case "${PREVIEW_PG_CONTAINER:-hos-preview-db-1}" in
  *preview*) ;;
  *) echo "refusing: container name does not look like preview" >&2; exit 1 ;;
esac

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="./var/backups/preview-${TS}"
mkdir -p "$OUT"

echo "== postgres dump =="
docker exec "${PREVIEW_PG_CONTAINER:-hos-preview-db-1}" \
  pg_dump -U hos_owner -d "$DB_NAME" -Fc -f "/tmp/preview.dump"
docker cp "${PREVIEW_PG_CONTAINER:-hos-preview-db-1}:/tmp/preview.dump" "$OUT/preview.dump"

echo "== storage volume archive =="
docker run --rm \
  -v "${PREVIEW_STORAGE_VOLUME:-hos-preview_preview-miniodata}:/data:ro" \
  -v "$PWD/$OUT:/out" alpine \
  tar -czf /out/storage.tgz -C /data .

echo "== encrypting =="
if [ -n "${BACKUP_ENCRYPTION_PASSWORD_FILE:-}" ]; then
  PASS_ARG=(-pass "file:$BACKUP_ENCRYPTION_PASSWORD_FILE")
else
  : "${BACKUP_ENCRYPTION_PASSWORD:?backup encryption password is required}"
  PASS_ARG=(-pass "env:BACKUP_ENCRYPTION_PASSWORD")
fi
openssl enc -aes-256-cbc -pbkdf2 -salt \
  -in "$OUT/preview.dump" -out "$OUT/preview.dump.enc" "${PASS_ARG[@]}"
openssl enc -aes-256-cbc -pbkdf2 -salt \
  -in "$OUT/storage.tgz" -out "$OUT/storage.tgz.enc" "${PASS_ARG[@]}"
rm "$OUT/preview.dump" "$OUT/storage.tgz"

sha256sum "$OUT"/* > "$OUT/SHA256SUMS" 2>/dev/null || shasum -a 256 "$OUT"/* > "$OUT/SHA256SUMS"
echo "backup written to $OUT (BACKUP_REF=$OUT)"
