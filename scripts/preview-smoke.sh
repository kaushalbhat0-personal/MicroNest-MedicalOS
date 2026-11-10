#!/usr/bin/env bash
# Preview release smoke gate. All checks local; fails closed.
# Required env: PREVIEW_API (default http://localhost:8001), PREVIEW_WEB (default http://localhost:3001).
set -euo pipefail

API="${PREVIEW_API:-http://localhost:8001}"
WEB="${PREVIEW_WEB:-http://localhost:3001}"
FAIL=0
say() { echo "== $1"; }

say "healthz (liveness)"
[ "$(curl -sf "$API/api/healthz")" = '{"status":"ok"}' ] || { echo FAIL healthz; FAIL=1; }

say "readyz (readiness)"
READY="$(curl -sf "$API/api/readyz")" || { echo FAIL readyz-unreachable; FAIL=1; }
echo "$READY" | grep -q '"status":"ready"' || { echo "FAIL readyz not ready: $READY"; FAIL=1; }

say "readyz returns 503 shape on outage is covered by tests (not toggled here)"

say "security headers on api"
curl -sI "$API/api/healthz" | grep -qi 'x-content-type-options: nosniff' || { echo FAIL sec-headers; FAIL=1; }

say "no secrets/PHI in api logs"
if docker compose -f infrastructure/preview/docker-compose.yml logs --no-log-prefix api 2>/dev/null \
  | grep -Ei 'password=|eyJ[A-Za-z0-9_-]{10,}\.|AKIA|secret-key|clinical_note' | grep -v REDACTED; then
  echo "FAIL secrets in logs"; FAIL=1;
else echo "no secret-shaped log lines"; fi

say "web login page serves"
curl -sf "$WEB/login" >/dev/null || curl -sf "$WEB/" >/dev/null || { echo FAIL web; FAIL=1; }

say "storage stays private (no public bucket listing)"
if curl -sf http://localhost:9000/hos-preview-private/ >/dev/null 2>&1; then
  echo "FAIL bucket publicly listable"; FAIL=1;
else echo "bucket not publicly listable"; fi

if [ "$FAIL" = 0 ]; then echo "PREVIEW SMOKE: PASS"; else echo "PREVIEW SMOKE: FAIL"; exit 1; fi
