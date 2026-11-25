# Phase 1.1 acceptance matrix

Phase 1.1 is **documentation/architecture only**. This matrix records whether blueprint acceptance criteria are met, and maps future build gates.

---

## A. Phase 1.1 blueprint gates

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Existing application functionality mapped | **PASS** | `existing-application-audit.md` |
| Authentication dependencies identified | **PASS** | `authentication-integration-plan.md` — cookies-only login; refresh cookie-bound; Bearer accept exists |
| Tauri architecture evaluated vs constraints | **PASS** | `desktop-architecture.md` — recommended with online-first scope |
| Desktop navigation & role workflows specified | **PASS** | `desktop-information-architecture.md`, `role-workflow-matrix.md` |
| Desktop vs patient PWA boundary clear | **PASS** | `patient-pwa-boundary.md` |
| Milestones have measurable acceptance criteria | **PASS** | `implementation-roadmap.md` M1–M15 |
| Risks & missing infrastructure documented | **PASS** | Auth B0, Rust/Tauri scaffold, signing cert, settings.manage gap, unused perms |
| No false claim of EXE existence | **PASS** | Explicitly not built |
| No production code / commit / deploy this phase | **PASS** | Docs under `docs/architecture/desktop-client/` only |
| Uncommitted work preserved / branch unchanged | **PASS** | Remained on `release/p3-7b-staging` |

**Phase 1.1 complete:** **YES**

---

## B. Future implementation gates (not claimed now)

| Gate | Status now |
|------|------------|
| Native JSON login/refresh on FastAPI | **NOT IMPLEMENTED** |
| `apps/desktop` Tauri project | **NOT IMPLEMENTED** |
| DPAPI refresh store in Rust | **NOT IMPLEMENTED** (Python PoC only) |
| Signed installer | **NOT IMPLEMENTED** |
| Feature parity milestones M5–M11 | **NOT STARTED** |
| Offline encrypted DB | **OUT OF SCOPE v1** |

---

## C. Risk register (open)

| Risk | Severity | Resolution owner (next) |
|------|----------|-------------------------|
| Cannot login from desktop without backend token JSON | **High** | Backend M2 |
| No Rust toolchain on some workstations | Medium | Dev environment setup |
| WebView2 missing on old PCs | Medium | Installer prerequisite |
| Team/Staff IA confusion | Low | Desktop nav cleanup M4 |
| `settings.manage` dead permission | Low | Backend cleanup or wire routes |
| UI drift if pages copied without shared packages | Medium | api-client + ui discipline |
| Signing cert procurement delay | High for pilot | Ops before M14 |

---

## D. Unresolved product decisions

| Decision | Options | Notes |
|----------|---------|-------|
| Device registration required in online-first MVP? | Optional vs mandatory | Recommended optional for session hygiene |
| Per-user vs machine-wide install | Per-user default | GPO may need MSI later |
| Whether clinic web remains fully supported long-term | Yes (locked for now) | Desktop is priority workstation; web retained |
| When to start offline phase | After pilot | Separate major phase |

---

## E. Exact next phase entry criteria

Start **Phase 1.2** when approved:

1. Backend ADR accepted for native token response.  
2. Rust + Tauri toolchain available on implementer machine.  
3. Staging API URL known for synthetic users.  
4. Explicit approval to create `apps/desktop` (still no commit until asked).
