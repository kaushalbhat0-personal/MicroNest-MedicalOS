# 05 — Authorization and Audit

Verified against `backend/app/platform/authz/permissions.py`,
`api/v1/dental.py` endpoint conventions, `dental/service.py` scope
helpers, D1b tests (`tests/api/test_document_access_api.py`), and the
portal projection (`portal/schemas.py:141-147`).

## 1. Permission matrix (no new permissions)

| Operation | Permission | Scope checks |
|---|---|---|
| View image (existing D1b) | `DENTAL_READ` | tenant + location (`grant_document_access`, 404/403/422) |
| List annotations | `DENTAL_READ` | same encounter scope as the image |
| Create/edit draft, finalize | `DENTAL_RECORD` | tenant + location + verified-practitioner authorship |
| Read finalized revision | `DENTAL_READ` | same as list |
| Amend post-finalize (new draft cycle) | `DENTAL_RECORD` | same as create |
| Delete draft item | `DENTAL_RECORD` | same as create; finalized: no path |
| Portal/patient view | — (none; excluded) | no annotation field exposed |

`DENTAL_RECORD` is the existing write permission for dental clinical
writes (findings, consents, recalls: `dental.py:93,492,571,611`); annotation
authorship is exactly that class of operation. `DENTAL_READ` covers all
view paths. **No new permission is justified**: the operation set maps
cleanly onto the existing pair, and inventing `annotation.*` permissions
would fragment the dental authz model with zero additional precision
(location + tenant + authorship already discriminate).

Role consequences (seed roles, `permissions.py:94-154`): `doctor` and
`tenant_admin` author; `nurse` reads (has `ENCOUNTER_READ`/`CLINICAL_READ`
but no dental permissions — specialty boundary holds, correctly);
`receptionist`/`accountant`/`staff`/`patient` have no path. Custom roles
can only subset — a tenant cannot escalate itself into annotation rights.

## 2. Tenancy, location, encounter rules (unchanged)

- `match_tenant(ctx, tenant_id)` on every endpoint; cross-tenant probe →
  `404`, never an oracle (D1b test `test_cross_tenant_access_is_404` is
  the pattern to replicate).
- `_encounter_in_scope(..., location_ids=ctx.location_ids)` on every
  annotation endpoint, resolved via the parent `document_reference`
  (`ref.encounter_id`) — annotations never carry their own location; the
  image's encounter is the single scope source. Out-of-scope → `403`.
- Per-patient grants are **not** introduced (existing model: tenant +
  location scope; D1b test `test_same_scope_other_patient…` documents it).
- Frontend checks (Annotate-button visibility) are convenience only; the
  API re-verifies permission + scope + authorship on every call.

## 3. Authorship

- `created_by/updated_by/finalized_by` = authenticated user id
  (server-derived, never client-supplied); practitioner attribution follows
  the existing `practitioner_for_user` pattern where a practitioner link
  is required.
- Anonymous/author-spoofed writes are impossible by construction: no
  author fields in request schemas (same discipline as D1b's bodiless
  grant — client supplies only opaque ids + `expected_version`).
- Author-vs-editor: any in-scope `DENTAL_RECORD` holder may amend a draft
  (per-item attribution preserved); dentist may restrict to author-only
  (Q1) — a service-layer one-line rule change, no schema impact.

## 4. Minimum audit events (append-only, opaque ids)

- `annotation.draft_saved` (set id, version; no geometry/payload content)
- `annotation.item_deleted` (item id, set version)
- `annotation.finalized` (set id, revision version)
- `annotation.amendment_started` (new draft cycle on a finalized set)
- Reuse `document.access_granted` for views — **no** `annotation.viewed`
  event (audit noise; viewing is already evidenced).
- Audit rows carry ids only: never URLs, geometry, labels, or image bytes
  (D1b test asserts `reason is None` and URL-absence — replicate that probe).

## 5. Endpoint sketch (for D2; not implemented)

- `POST …/documents/{id}/annotation-sets` (create draft set; 409 if exists)
- `GET …/documents/{id}/annotation-sets` (latest draft + finalized heads)
- `PATCH …/annotation-sets/{set_id}` (draft save; `expected_version`; items
  upsert/delete batch, single transaction)
- `POST …/annotation-sets/{set_id}/finalize` (one-way; writes revision)
- `GET …/annotation-sets/{set_id}/revisions[/{version}]` (history)
- Flat item-action POSTs + `DENTAL_READ`/`DENTAL_RECORD` + `match_tenant` +
  `_encounter_in_scope` + `_audit(...)` — the exact D1b file conventions.
