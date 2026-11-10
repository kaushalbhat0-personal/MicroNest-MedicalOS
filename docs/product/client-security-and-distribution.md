# Client Security and Distribution

Status: **APPROVED direction; implementation NOT started** (2026-11-08).
Companions: `multi-platform-product-architecture.md`, `application-surfaces.md`.
Sources: `backend/app/api/deps.py`, `backend/app/platform/security/{cookies,tokens}.py`,
`backend/app/main.py` (CORS), `backend/app/platform/config.py`, `apps/web/Dockerfile`,
`backend/Dockerfile`, `infrastructure/preview/*`, `.github/workflows/ci.yml`.

## 1. Trust model (APPROVED)

- All clients are untrusted, including the Windows EXE on clinic hardware and the
  Android APK on patient devices. The server re-validates identity, membership,
  permissions, tenant scope, portal linkage, and input on every request.
- No client-controlled permissions: roles/permissions resolve server-side from
  `memberships` + seed roles (`_role_by_name` pattern); specialty packs never change
  authorization; `X-Tenant` is a selector, never a claim.
- No secrets in clients: no `service-role`/`APP_ROLE_PASSWORD`/`OWNER_DATABASE_URL`/
  JWT secrets/provider keys in any shipped bundle (existing hygiene gate extended to
  Tauri/Capacitor outputs). API keys for BYO comms live encrypted server-side only.

## 2. Authentication implications for native clients (PROPOSED detail, APPROVED posture)

What exists today (`cookies.py`, `deps.py:59-78`, `tokens.py`):

- Transport accepts **both** HttpOnly cookies (`hos_access` path `/api`, 10-min;
  `hos_refresh` path `/api/v1/auth`, 30-day; `Secure`/`lax`/`domain` from settings) and
  `Authorization: Bearer` (preferred for native). Same verification, same scope —
  "Bearer fallback for future native clients" is already the documented design.
- Short-lived JWT access (`HS256`, `ACCESS_TOKEN_MINUTES=10`) + rotating opaque refresh
  (SHA-256 at rest, family id, reuse detection revokes whole family).
- `get_current_user` fail-closed (revoked/expired/inactive → `AuthError`); tenant ctx via
  `get_ctx`; portal via `portal_ctx` + `active_link`.

Native-client rules (binding):

1. APK/EXE use the **same login/refresh/logout/revoke endpoints** — no native-only
   auth route. Prefer `Authorization: Bearer` in native shells (deterministic across
   WebView cookie-jar quirks); keep cookie support as fallback.
2. Token storage: OS-guarded storage only (Android Keystore via Capacitor Preferences/
   secure-storage plugin decision at spike; Windows Credential Manager/DPAPI via Tauri
   stronghold-or-plugin decision at spike). Never `localStorage` for tokens (extends the
   existing hygiene gate, which already forbids `localStorage(session|token|...)`).
3. Refresh discipline: reuse-detection applies equally — a double-refresh from two shells
   revokes the family by design; clients must serialize refresh and handle `401` with
   single retry → re-login. Document before APK/EXE ship.
4. Deep links (APK App Links / EXE protocol handler): verification/reset/portal links are
   capability URLs — route them into the app **without logging the token** (no query in
   logs/analytics/crash reports; existing `FORBIDDEN_PORT_KEYS` + refs-only discipline
   extended to client telemetry).
5. WebView hardening: no remote-content injection, no JS-bridge exposure of tokens,
   minimum WebView versions, clear-cache on logout, no PHI in page titles/URLs pushed to
   OS history (mirrors DESIGN.md §16).

## 3. Desktop (Windows EXE) risks + mitigations (Tauri candidate)

- Risks: installer tampering, WebView XSS-to-native bridge escape, token extraction from
  clinic machines, auto-update hijack, support-staff misuse on shared PCs.
- Mitigations (spike must prove each): signed installer (cert + reproducible build note),
  signed auto-updater channel (no plain-HTTP), minimal Tauri capability set
  (no `fs`/`shell`/`process` access for the clinical UI scope; updater + dialog only),
  OS token storage, session idle-timeout + per-user OS accounts on shared PCs, audit of
  `login/logout/revoke-all`. Cloud-only v1 keeps breach blast-radius at the account
  level (no local PHI store to steal). Docker images unchanged — EXE ships from CI as a
  separate artifact, never inside the API/web images.

## 4. Mobile (Android APK) risks + mitigations (Capacitor candidate)

- Risks: APK repackaging, backup extraction (`allowBackup`), rooted-device key access,
  push-token spam, patient using APK on shared devices, sideloaded builds.
- Mitigations (spike must prove each): Play App Signing, `allowBackup=false` for app
  data, no tokens in backups/logs, root/safety detection **advisory only** (never deny
  care access — clinical-safety rule extends: reads preserved), per-build API base URL +
  certificate pinning decision at spike (pinning optional; rotation runbook required if
  adopted), push deferred until a real provider exists (no Firebase key in O1), patient-only
  route allow-list in the bundle + server-side `patient`-role backstop. iOS deferred —
  no iOS-specific mitigations evaluated.

## 5. Packaging and distribution constraints (APPROVED)

- Web/marketing: existing Docker flow untouched (`apps/web/Dockerfile`,
  `backend/Dockerfile`, `infrastructure/preview/docker-compose.yml`, CI
  `backend/web/hygiene/preview-gates` jobs). New public site reuses the same image
  pattern (separate image or route group — build decision; no Compose architecture
  change in this slice).
- EXE: Windows installer (MSIX/NSIS decision at spike) + code signing cert (procurement
  lead time tracked as a release dependency) + versioned auto-update feed. No clinical
  data migration on update (server owns state).
- APK: Play Console track (internal → closed → production), versionCode discipline,
  signing by Play, staged rollout. No side-channel APK distribution as primary.
- PWA: manifest + icons + SW ship with the web image; SW cache allow-list = shell +
  static assets only; SW must never cache API responses with PHI (binding).

## 6. Update and release architecture (PROPOSED)

- Backend/web: current train (migrate-review gate, single Alembic head, preview smoke,
  `healthz/readyz`) continues; native shells add a **compatibility floor**: each APK/EXE
  build declares `minApiVersion`; server exposes a coarse version endpoint (no
  fingerprinting) and returns a `426`-style upgrade hint (exact shape frozen at spike)
  for builds below the floor. No breaking contract change without a floor bump + dual
  support window.
- Release order per slice: backend → web → native shells (rebuild against frozen
  contracts) → store/installer rollout. Rollback: web/backend revert per existing
  runbooks; native rollback = store halt + new build (never a server downgrade that
  breaks newer shells inside the support window).

## 7. Deferred (explicit)

Offline sync, local clinical DB, iOS app, push provider, MDM/kiosk, pinning runbook,
support-bypass grants. Each needs its own threat review before scheduling.
