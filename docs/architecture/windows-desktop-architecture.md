# Windows Desktop Client Architecture

**Phase:** A0 — architecture / feasibility (no EXE builds)  
**Date:** 2026-11-25

## 1. Goals

- Signed **EXE installer** (and ideally MSI/MSIX later) for clinic workstations.
- Same backend APIs, authz, tenancy, audit, and clinical rules as web/Android.
- Offline operation with encrypted local DB and OS-backed key protection.
- Secure auto-update and device revocation.

## 2. Technology options vs repository evidence

### Option A — Tauri 2 (Rust + webview) — **recommended**

| Criterion | Assessment |
| --- | --- |
| UI reuse | Host SPA built from React + `@healthcare-os/ui` (same strategy as Android shell) |
| Next.js direct | **Do not** embed full Next SSR; use static/SPA assets or localhost sidecar only for online-only mode |
| Binary size / attack surface | Smaller than Electron; Rust core for FS, crypto bridge, updater |
| SQLCipher | Via Rust crate or sidecar native lib behind `EncryptedDb` trait |
| Secrets | Call Windows **DPAPI** / Credential Manager from Rust; never JS-readable key material |
| Auto-update | Tauri updater with **signed** artifacts + HTTPS |
| Fit to monorepo | Add `apps/desktop` (Tauri) consuming shared packages |

### Option B — Electron

| Criterion | Assessment |
| --- | --- |
| UI reuse | Easiest Node/web tooling match |
| Security | Larger Chromium surface; requires hardened CSP, contextIsolation, no nodeIntegration in UI |
| Size / updates | Heavier; code-signing still mandatory |
| PHI offline | Possible but harder to keep keys out of renderer |

**Verdict:** Electron is a **fallback** if Tauri plugin gaps block SQLCipher/DPAPI timelines; default is **Tauri 2**.

### Option C — Pure .NET / WPF / WinUI

High control, near-zero reuse of `@healthcare-os/ui`. Only if clinic IT mandates native Microsoft stack.

## 3. Security building blocks (Windows)

| Concern | Mechanism | Notes |
| --- | --- | --- |
| Encryption keys | **DPAPI** (CurrentUser) or **Windows Credential Manager** | Not interchangeable with Android Keystore — separate `SecureKeyStore` impl |
| Local DB | SQLCipher (or sqlcipher-compatible) under `%LOCALAPPDATA%\HealthcareOS\` | ACLs: user-only; wipe on revoke |
| Tokens | Refresh in Credential Manager; access in process memory | Renderer never sees raw refresh |
| IPC | Tauri commands with allowlisted args; no open shell | Validate tenant_id server-side always |
| Background sync | Windows Task Scheduler / Tauri background task / Windows Service (elevated only if required) | Prefer per-user background task |
| Device revoke | Server flags device; client detects on sync → seal DB + clear credentials | |

**Do not assume** Android Keystore APIs or biometric TEE map 1:1 to Windows Hello; treat Windows Hello as optional unlock UX over DPAPI-unwrapped keys.

## 4. Auth flow (Windows)

Same Bearer + device registration model as Android:

1. Login against FastAPI.  
2. Persist refresh via DPAPI/Credential Manager.  
3. Calls use `Authorization: Bearer` + `X-Tenant`.  
4. Optional Windows Hello gate before unlocking local DB.

Cookie/`SameSite` web proxy (P3.7D) is **web-only**; desktop must not depend on Vercel rewrites.

## 5. Offline operation

- Same `AuthzLease` + local outbox contracts as Android (`cross-platform-sync-design.md`).  
- Clinic reception workflows (queue, demographics drafts) are first offline candidates.  
- Payments, WhatsApp sends, portal enrollment: **online-only** until explicit ADR.

## 6. Auto-update security

| Control | Requirement |
| --- | --- |
| Artifact signing | Authenticode on EXE/MSI; updater verifies publisher |
| Transport | HTTPS only; pin update manifest host |
| Privilege | Per-user install preferred; avoid SYSTEM service unless justified |
| Rollback | Keep N-1 package; fail closed if signature invalid |
| Channel | Staging vs production update feeds separated |

## 7. Feasibility verdict — Windows EXE

| Gate | Status |
| --- | --- |
| Tauri 2 + SPA + `@healthcare-os/ui` | **Feasible / recommended** |
| Electron alternative | Feasible, weaker default security posture |
| DPAPI + SQLCipher + signed updater | **Design-ready** |
| Ready to build EXE in A0 | **No** — needs SPA shell, Bearer device auth, sync MVP, signing cert ops |

**Readiness for Windows EXE development:** **CONDITIONAL / NOT YET** — architecture direction Tauri 2; blocked on same shared prerequisites as Android (token contract + sync scope + packaging keys).
