# Patient PWA boundary (Phase 1.1)

**Decision:** Patient experience stays a **separate mobile-first Next.js application** under `/portal/*`.  
**Not in Phase 1.1:** PWA manifest work, service workers, or portal redesign implementation.

---

## 1. Separation rules

| Concern | Clinic Desktop EXE | Patient app |
|---------|--------------------|-------------|
| Host | Tauri Windows | Browser / future PWA on Next.js |
| Shell | `variant="clinic"` patterns | `PortalShell` / “My Care” |
| API | `/api/v1/tenants/...` staff routes | `/api/v1/portal/...` |
| Roles | doctor, receptionist, tenant_admin, … | `patient` (+ portal_links) |
| Auth | Future native Bearer | Existing cookie web auth |
| Offline | Deferred major phase | Not in scope here |

Do not embed portal routes inside the clinic EXE.

---

## 2. Existing patient features (evidence)

| Feature | Route | Status |
|---------|-------|--------|
| Portal home | `/portal` | **exists** |
| Appointments list/book/detail | `/portal/appointments*` | **exists** |
| Visits | `/portal/visits*` | **exists** |
| Prescriptions | `/portal/prescriptions` | **exists** |
| Dental plans / recalls / consents | `/portal/dental*` | **exists** |
| Billing / estimates | `/portal/billing*` | **exists** |
| Documents | `/portal/documents` | **exists** |
| Profile | `/portal/profile` | **exists** |
| Access log | `/portal/access-log` | **exists** |

APIs: `backend/app/api/v1/portal.py` with `portal.read` and appointment book/cancel permissions; commercial `assert_portal_access`.

Tests: Playwright portal enrollment/isolation; P3.3 `/portal` screenshot.

---

## 3. Mobile UX improvements needed (backlog — not Phase 1.1)

- Installable PWA (manifest, icons, `display: standalone`)  
- Stronger thumb-friendly booking and payment flows  
- Push notification strategy (privacy review)  
- Offline read of last appointment summary (optional later)  
- Performance on mid-tier Android browsers  

---

## 4. Authentication compatibility

- Portal users authenticate via same identity service; login routes portal-only users to `/portal` (`login/page.tsx`).  
- Clinic desktop must reject or refuse to load clinic shell for users lacking clinic membership permissions.  
- Cookie auth remains correct for PWA/browser; native patient apps (if ever) would need the same Bearer contract — **out of scope**.

---

## 5. Workflow touchpoints with clinic desktop

| Clinic action | Patient effect |
|---------------|----------------|
| Schedule appointment | Visible in portal appointments when released rules allow |
| Sign prescription | Portal medicines list |
| Issue invoice / estimate | Portal billing |
| Portal enrollment on patient chart | Enables portal_link |

Desktop should deep-link **to web portal enrollment UI** or call existing tenant portal-link APIs — not reimplement portal.

---

## 6. PWA installation requirements (future checklist)

- HTTPS hosting (Vercel)  
- Web app manifest + service worker policy (careful with PHI caches)  
- Icon set / splash  
- `start_url` → `/portal`  
- No caching of clinical documents without encryption policy  

**Phase 1.1 action:** document only; no implementation.
