# Desktop architecture decision (Phase 1.1)

## Verdict

**Recommended:** **Tauri 2 + Rust + React/Vite + `@healthcare-os/ui` + Tailwind tokens**, talking HTTPS to the existing FastAPI monolith.

**Not selected for v1:** Electron (fallback only), embedding Next.js SSR in a WebView, second backend, local clinical DB/sync.

**Constraint change vs A0:** First desktop release is **online-first**. A0 offline/SQLCipher sync is deferred; architecture must not block adding it later.

---

## 1. Evaluation against project constraints

| Criterion | Tauri 2 | Electron | Notes |
|-----------|---------|----------|-------|
| Windows compatibility | First-class WebView2 | Chromium bundle | Clinic PCs typically have WebView2 |
| Resource usage | Smaller binary / RAM | Heavier | Prefer Tauri for clinic fleets |
| Startup | Fast with WebView2 | Slower cold start | Matters for reception desk |
| Routing | React Router (SPA) | Same | **Do not** use Next App Router inside EXE |
| UI reuse | Import `@healthcare-os/ui` | Same | packages/ui has **no** Next dependency |
| Auth | Rust stores refresh; JS gets short-lived access via IPC | Same pattern harder to isolate | Prefer Rust + DPAPI |
| Secure API | HTTPS to Render/API URL | Same | No Vercel `/api` rewrite dependency |
| Native capabilities | FS, notifications, updater, DPAPI via Rust | Node native | Enough for online-first |
| Installer | NSIS/MSI via Tauri bundler | electron-builder | Both workable |
| Code signing | Authenticode required either way | Same | |
| Secure updates | Tauri updater + signed artifacts | electron-updater | Prefer signed manifest |
| Maintenance | Rust + web skill mix | Node-centric | Repo already planning Rust from A0/A2 |
| PoC evidence | DPAPI proven in Python; Tauri **not** built yet | Not spiked | Risk: Rust toolchain bootstrap |

**Electron advantage only if:** Tauri WebView2 quirks or updater gaps block clinic pilots. Default remains Tauri 2.

---

## 2. Integration architecture

```
┌─────────────────────────────────────────────┐
│ apps/desktop (Tauri 2)                      │
│  ┌───────────────┐    IPC (allowlisted)     │
│  │ React/Vite UI │◄──────────────────────►│ │
│  │ + packages/ui │     Rust commands        │ │
│  └───────┬───────┘                          │ │
│          │ HTTPS Bearer + X-Tenant          │ │
│          ▼                                  │ │
│  FastAPI /api/v1/*  (existing)              │ │
│  CredentialStore (DPAPI) — refresh only     │ │
│  Config (API base URL, env channel)         │ │
└─────────────────────────────────────────────┘

apps/web (Next.js) ── unchanged ──► same FastAPI (cookies)
portal / PWA        ── unchanged ──► same FastAPI (/portal)
```

### Monorepo shape (future implementation — not created in 1.1)

```
apps/
  web/                 # Next.js — clinic browser + patient portal
  desktop/             # Tauri 2 host + Vite SPA (clinic EXE)
packages/
  ui/                  # existing
  api-client/          # typed fetch: cookie adapter (web) | bearer adapter (desktop)
  desktop-shell/       # optional shared nav/layout helpers without Next
```

**Rule:** Clinical business logic stays on FastAPI. Desktop UI is a privileged client, not an authority.

---

## 3. Online-first runtime model

| Concern | v1 behavior |
|---------|-------------|
| Connectivity | Required; show blocking reconnect UX when offline |
| Local patient DB | **None** |
| Sync / outbox | **None** |
| Business rules | Server only |
| Caching | Optional ephemeral HTTP/memory cache for UX; never source of truth |
| Offline phase later | Introduce `EncryptedDb` + lease behind same shell without rewriting IA |

---

## 4. Authentication & tenancy (desktop)

1. Login → backend issues session (see [authentication-integration-plan.md](./authentication-integration-plan.md)).  
2. Access JWT held in memory (renderer or Rust); refresh in DPAPI/Credential Manager via Rust.  
3. Every tenant API call: `Authorization: Bearer` + `X-Tenant`.  
4. Permissions from `GET /tenants/{id}/workspace-context` (same as web shell).  
5. Logout: revoke session + clear secure store + clear memory.

Web cookie auth **unchanged**.

---

## 5. Security boundaries

| Layer | Control |
|-------|---------|
| Renderer | No raw refresh token; CSP; no Node integration |
| IPC | Explicit command allowlist; validate args |
| Network | TLS only; configurable API base; no cleartext |
| Secrets | No production secrets in repo; env/channel config |
| Logging | No PHI/tokens (align backend redaction culture) |
| Future offline | DPAPI-wrapped DEK proven in A2 PoC — reserved |

---

## 6. Risks

| Risk | Mitigation |
|------|------------|
| Rust/Tauri not yet scaffolded in repo | Phase 1.2 foundation milestone |
| WebView2 missing on old Windows | Installer dependency / bootstrapper |
| Login JSON tokens missing | Backend B0 before feature work |
| Accidental Next coupling | Lint: ban `next/*` in `apps/desktop` |
| Drift from web UI | Share `@healthcare-os/ui` + DESIGN.md; accept controlled desktop shell differences |

---

## 7. Decision record

| Decision | Choice |
|----------|--------|
| Host | Tauri 2 |
| UI | React 19 + Vite + `@healthcare-os/ui` |
| Backend | Existing FastAPI only |
| Auth | Extend existing JWT/session; native JSON tokens |
| Offline v1 | Disabled |
| Electron | Fallback only |
| EXE claim in Phase 1.1 | **None** — blueprint only |
