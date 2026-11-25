# Packaging and security (Phase 1.1)

No production signing keys are created or exposed in this phase. No EXE is produced.

---

## 1. Installation format

| Choice | Recommendation |
|--------|----------------|
| v1 distribution | **Signed NSIS installer** (Tauri bundler) delivering per-user install under `%LOCALAPPDATA%\HealthcareOS\` |
| Alternative | MSI for GPO/clinic IT later |
| MSIX | Later channel |
| Portable unsigned EXE | Dev-only; never clinic pilot |

Layout:

```
%LOCALAPPDATA%\HealthcareOS\
  app\          # binaries / resources
  config\       # non-secret channel + API base (or machine policy)
  credentials\  # DPAPI-protected blobs only
  logs\         # no PHI, no tokens
```

---

## 2. Code signing

| Item | Requirement |
|------|-------------|
| Certificate | Organization Authenticode (EV preferred for SmartScreen) |
| Timestamp | RFC 3161 |
| Storage | HSM / locked CI — **never git** |
| Scope | Installer + app binaries + updater packages |

Phase 1.1: specify only; do not generate keys.

---

## 3. Secure updates

| Control | Spec |
|---------|------|
| Mechanism | Tauri updater with HTTPS manifest |
| Verification | Signature check before apply; fail closed |
| Channels | `staging` vs `production` feeds separated |
| Rollback | Retain N-1 package; document manual rollback |
| Min version | Optional server header / config for force-upgrade later |

---

## 4. API endpoint & environments

| Channel | API base | Notes |
|---------|----------|-------|
| Dev | Local FastAPI or staging URL | Config file / env at build |
| Staging | Render staging API | Synthetic data only |
| Production | Production API | Separate build channel |

Desktop **must not** depend on Vercel same-origin `/api` rewrite. Call FastAPI directly with Bearer.

Separate `API_BASE_URL` per channel; no secrets in client config beyond public URLs.

---

## 5. Secret & credential handling

| Secret | Handling |
|--------|----------|
| JWT access | Memory only; short TTL |
| Refresh | DPAPI CurrentUser or Windows Credential Manager via Rust (A2 PoC **PASS** for DPAPI wrap pattern) |
| JWT signing secret | Server only |
| Signing certs | CI only |

### DPAPI validation (existing experiment)

- Evidence: `experiments/native-client-poc/windows/evidence/a2_windows_runtime_evidence.json`  
- Proven: protect/unprotect DEK, sealed data, wipe on logout simulation  
- Limitations: bound to Windows user profile; profile change → re-login; not equivalent to Android Keystore  
- v1 use: **refresh token wrap only** (no local patient DB)

---

## 6. Crash logging

- Opt-in or clinic-controlled.  
- Scrub emails, names, MRNs, tokens.  
- Prefer stack + app version + request_id only.  
- No automatic PHI attachments.

---

## 7. Version management

| Field | Use |
|-------|-----|
| `version` / `tauri.conf` | Semver shown in About |
| Build metadata | git sha in About (non-secret) |
| Compatibility | Document minimum API version when breaking |

Upgrade: updater path. Rollback: reinstall N-1 signed installer.

---

## 8. Hardening checklist (implementation phases)

- [ ] CSP on webview  
- [ ] IPC allowlist  
- [ ] TLS only  
- [ ] No cleartext credentials on disk  
- [ ] Logout clears store  
- [ ] Disable dangerous webview APIs  
- [ ] Windows Defender / SmartScreen tested with signed build  

---

## 9. Deferred (explicit)

- Encrypted offline patient DB  
- Device attestation  
- MDM app wrapping policies (document when clinic IT requires)
