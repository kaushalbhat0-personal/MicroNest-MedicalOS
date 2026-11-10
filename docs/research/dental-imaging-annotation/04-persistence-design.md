# 04 — Persistence Design

Inspected: `DocumentReference` (`backend/app/modules/dental/models.py:355`;
pointer-only: `storage_key`, `content_type`, `size_bytes`, `sha256`,
`notes`, `uploaded_by`, `encounter_id` RESTRICT, indexes on tenant +
encounter), `create/list_document_refs` + `grant_document_access`
(`plans.py:662-749`), audit `append` with hash-chained opaque IDs
(`audit/service.py:48-103`), additive-migration convention
(`alembic/versions/0017_*`: additive-only, idempotent seeds, RLS-safe,
downgrade documented), consent decide-once/withdraw + plan `version`
bump-on-transition precedents (`plans.py:201,226,251,514-541`).

Non-negotiable: **the original image (bytes + reference row) is immutable.**
Annotation data lives separately and references the document row; nothing
in this design updates `document_references` except a future nullable
counter/cache if ever needed (not proposed for first release).

## 1. Option A — JSON column on `document_references`

Payload (e.g. `annotations JSONB`, `annotated_by/at`) on the pointer row.

- Pros: one migration, one row per image, trivial save/load.
- Cons (fatal): pollutes the hot storage-pointer table with clinical
  content; whole-blob last-writer-wins concurrency (two clinicians =
  silent overwrite); no per-object identity (can't address, audit, or
  soft-delete one marker); versioning means copying blobs or losing
  history; tooth-link queries need JSON operators on a hot table;
  every annotation write contends with reference metadata.
- **Rejected.** This is DentalERP's shape (`Document.annotations Json`);
  the audit already flagged it as design-gated for exactly these reasons.

## 2. Option B — Dedicated tables (RECOMMENDED)

```sql
image_annotation_sets (
  id UUID PK, tenant_id FK CASCADE, encounter_id FK RESTRICT,
  document_id FK → document_references RESTRICT UNIQUE,  -- one set per image
  status TEXT CHECK (status IN ('draft','finalized')),
  version INT NOT NULL DEFAULT 1,                        -- optimistic lock
  created_by UUID, updated_by UUID, finalized_by UUID,
  created_at / updated_at / finalized_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX ON sets (document_id);               -- single active set
CREATE INDEX ON sets (tenant_id), (encounter_id);

image_annotation_items (
  id UUID PK (server uuid7, never client random),
  set_id FK → sets CASCADE,
  kind TEXT CHECK (kind IN ('marker','rect','label')),
  geom JSONB NOT NULL,        -- per-mille ints, server-validated schema
  tooth INT NULL, surface TEXT NULL,   -- existing validators apply
  label TEXT NULL (≤140), style JSONB NULL (fixed palette keys only),
  created_by UUID, updated_by UUID,
  created_at / updated_at TIMESTAMPTZ, deleted_at TIMESTAMPTZ NULL
);
CREATE INDEX ON items (set_id) WHERE deleted_at IS NULL;

image_annotation_revisions (           -- immutable snapshots
  id UUID PK, set_id FK CASCADE, version INT NOT NULL,
  payload JSONB NOT NULL,              -- full set snapshot at finalize
  finalized_by UUID NOT NULL, finalized_at TIMESTAMPTZ NOT NULL
);
UNIQUE (set_id, version);
```

Lifecycle: draft items mutate in place (soft-delete only); `finalize`
validates → inserts revision snapshot → sets `status='finalized'`,
`version+1`. Post-finalize edits: new draft cycle on the same set
(`status` back to `draft`, `version+1`) preserving all prior revisions;
corrections are new revisions, never UPDATEs of `revisions` rows
(table gets no UPDATE path in the service). Mirrors existing norms:
consent decide-once, plan version bumps, amend-new-version.

- Pros: per-object identity (select/nudge/delete one marker; keyboard/SR
  list maps 1:1 to rows); per-item attribution; tooth queries are indexed;
  optimistic concurrency at set granularity; history is first-class and
  inspectable; audit granularity per action; migration is additive and
  isolated from the hot pointer table.
- Cons: more tables + one migration; snapshot payload duplicates item
  rows (cheap: annotations are small; correctness > storage).
- **Recommended.** Only option meeting queryability + concurrency +
  auditability + lifecycle together.

## 3. Option C — Single JSON sidecar row per image

One `image_annotation_documents`-style row: `{document_id UNIQUE,
payload JSONB, version, status, …}`.

- Pros: smaller migration than B; whole-set versioning easy.
- Cons: same whole-blob concurrency loss as A (mitigated only by the
  version check, which then rejects frequently under multi-editor use);
  no per-object identity (deleting marker #3 = rewrite payload);
  tooth queries need JSON operators; per-item attribution bolted on.
- **Rejected for first release.** Acceptable only if the dentist drops
  tooth-linkage AND per-object history AND multi-editor drafts — an
  unlikely combination that would still need a later migration to B.
  Starting at B avoids a data migration under clinical history.

## 4. Comparison summary

| Criterion | A JSON column | B dedicated (rec.) | C JSON sidecar |
|---|---|---|---|
| Original immutability | ✓ (untouched) | ✓ (untouched) | ✓ (untouched) |
| Per-object identity/audit | ✗ | ✓ | ✗ |
| Concurrent editors | silent loss | 409 + retry | frequent 409s |
| Revision history | bolt-on | first-class | blob copies |
| Tooth-linked queries | JSON ops on hot table | indexed columns | JSON ops |
| Migration risk | couples hot table | isolated additive | isolated additive |
| Interop (FHIR/DICOM later) | poor | mappable per object | poor |

## 5. Concurrency model (first release)

- Single-set optimistic lock: writers send `expected_version` (the version
  they loaded); mismatch → `409` with the current server state; UI
  replays the user's pending command onto fresh state or asks (no silent
  merge). Matches existing 409-guard precedent (finding resolve).
- Duplicate-submit / retry-after-timeout: `Idempotency-Key` header
  (already in CORS allow-list, `main.py`) on save/finalize; server keeps
  a short keyed-result window per tenant.
- No collaborative real-time editing: no evidence of need; explicit
  non-goal. Sequential draft editing + 409 is the safe model.
- Partial-save failures: save is one transactional request (set + items
  in a single DB transaction); no multi-call choreography, no sagas.

## 6. Retention, deletion, replacement

- Draft items: soft-delete (`deleted_at`, attributed).
- Finalized revisions: no delete path; retention follows the clinical
  record-retention policy (Q5 — confirm years + legal-hold behavior).
- Reference rows are `RESTRICT`-bound and have no delete endpoint today;
  annotations inherit that protection automatically. If reference deletion
  is ever added, annotations must block it (RESTRICT) or archive with it —
  dentist/legal decision (Q5), not a default.
