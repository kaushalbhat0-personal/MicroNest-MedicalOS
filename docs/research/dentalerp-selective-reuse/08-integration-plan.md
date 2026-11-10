# 08 — Integration plan (dental-erp @ 389d9841)

Smallest sensible sequence. No implementation is performed by this audit; this
is the plan a future build slice would follow. Our architecture, data model,
authz, tenancy, and DESIGN.md stay authoritative throughout.

## Sequence

### Step 0 — Dentist walkthrough (gate for everything clinical)
- Run the `05-clinical-workflow-review.md` checklist (catalog coverage, surface
  rule, primary-dentition scope P-B, finding→plan→record linkage P-C, consent
  sufficiency P-D, recall practice, imaging modalities).
- No schema or UI work beyond mock-data demos until sign-off on scope items.

### Step 1 — Storage plumbing (prerequisite for imaging)
- **Modules:** StoragePort signed upload/download URLs surfaced to encounter
  docs flows (today: reference-only + "not available" helper).
- **API/schema:** additive endpoints only; no changes to existing
  `document_references` semantics; bytes never pass through clinical JSON.
- **Security gates:** tenant + location scope on every URL mint; content-type
  allowlist; size caps; audit opaque IDs; portal keeps `download_available=false`
  until release rules explicitly change.
- **Tests:** scope-denial (cross-tenant 404, out-of-scope 403), expiry, audit PHI probe.

### Step 2 — Imaging viewer (RC-1, Adapt)
- **UI:** new Dental-specialty viewer component under our tokens (viewer chrome,
  zoom/pan/rotate/flip/B-C, fullscreen, keyboard with disclosed shortcuts,
  labeled controls, loading/error/empty states, read-only prop from day one).
- **API/schema:** none (reads existing references + signed URLs).
- **Tests:** interaction (zoom/rotate/flip/keyboard), projection-only proof
  (adjustments never persist), a11y (labels, focus, 44px targets), responsive trio.
- **Dentist gate:** approve toolbar vocabulary on mock data.

### Step 3 — Annotation (RC-2, Adapt)
- **UI:** canvas annotator (6 tools, undo/redo, normalized coords, UUID ids,
  read-only, keyboard/SR annotation-list alternative).
- **API/schema:** additive annotations persistence on document rows (migration,
  design-gated) + tenant-scoped PUT; authorship + timestamps recorded.
- **Security gates:** author-vs-viewer authz, audit, no PHI in logs.
- **Tests:** round-trip coordinate invariance across resolutions, undo/redo,
  read-only enforcement, scope denial.
- **Dentist gate:** authorship + modality/pairing rules (§05).

### Step 4 — Compare (RC-3, Adapt)
- **UI:** slider (keyboard-accessible) + synced side-by-side, stacked <lg,
  mandatory dates.
- **API/schema:** none. **Tests:** sync proof, keyboard slider, responsive.

### Step 5 — Odontogram upgrade (RC-4, Recreate natively)
- **UI:** extend `packages/ui/dental.tsx` (surface select, legend fill+label+icon,
  resolved-history, summary counts, read-only, wrap/scroll).
- **API/schema:** none (existing findings endpoints suffice).
- **Tests:** keyboard grid, SR labels, history correctness (resolved rows appear),
  responsive, contrast.
- **Dentist gate:** chair-side tablet test.

### Step 6 — Workspace + plan presentation (RC-5/6)
- **UI:** documents/imaging section + lazy timeline in patient/encounter views;
  plan progress + consent badges + grouped picker (server values only).
- **API/schema:** none, except §22 list APIs if dentist wants recall/consent boards
  (separately scoped). **Tests:** state coverage (§11 nine states), no-PHI URLs.

### Step 7 — Shell micro-patterns (RC-7/8)
- **UI + API:** scoped minimal-PHI search + notification tray on our outbox APIs.
- **Security gates:** search audit, result minimization, authz on entity navigation.

## Affected modules (our OS)

- `packages/ui` (`dental.tsx` extend; new viewer/annotator/compare components).
- `apps/web/app/{patients,encounters,dental,portal,shell}` wiring only.
- `backend/app/modules/dental` (additive annotations design) + StoragePort adapters.
- Notifications/outbox wiring for recalls (with P8.1 provider, later).
- No changes to: tenancy, auth, billing, prescriptions, audit architecture.

## Explicit non-goals (reaffirmed)

No Prisma/MySQL, no second backend, no API-route imports, no auth/session import,
no billing/payment/AI/portal-server code, no duplicated entities, no browser-stored
clinical data, no weakened tenant isolation, no DESIGN.md changes in this package.
