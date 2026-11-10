# 07 — Testing Strategy

Conventions to follow: backend `tests/api/` (authz matrix style of
`test_document_access_api.py`), `tests/isolation/` (tenant/location),
`packages/ui` zero-dep `node --test` for pure math, `apps/web` vitest +
jsdom + testing-library (D1c: 30 web tests). Do not claim frontend tests
prove backend authz — server tests are the evidence.

## 1. Coordinate correctness (pure unit, zero-dep, `node --test`)

New `annotation-geometry` module beside `imaging-transform.ts` (no React,
no DOM — same discipline). Matrix over:
- all 4 rotations × flipH on/off × flipV on/off (16 combos),
- zoom × pan arbitrary incl. extremes (0.25/5, ±pan),
- aspect ratios (square, panoramic 2:1, portrait, ultra-wide),
- responsive sizes (DESKTOP 1440 → 320px widths; `d` recomputed),
- pointer mapping round-trip: N → S → N within 1 per-mille,
- boundary: clamp markers, reject zero-area rects, min 8×8 rule,
- forward/inverse consistency proof per combination (property-style loop).

## 2. Persistence (API + DB)

- Save/list/finalize round-trips; revision chain inspectable; draft vs
  finalized visibility rules.
- Stale `expected_version` → 409; replay-onto-fresh succeeds.
- Idempotency-Key: duplicate finalize POST yields one revision.
- Single-transaction save: partial batch fails atomically (no orphan items).
- Original immutability: reference row + bytes untouched after all
  annotation operations (hash/content-type assertions).
- Soft-delete: draft item hidden, history retained; finalized delete
  attempt → 409/422, no path.

## 3. Authorization (API; replicate D1b probes)

- No-auth 401; `staff` (no DENTAL_READ) 403 on view; `nurse` reads but
  403 on write; cross-tenant 404 (both path-tenant mismatch and actor
  tenant); out-of-scope location 403; non-image document 422 on set
  creation; unknown document 404.
- Author-spoof attempt (client-sent `created_by`) ignored/stripped.
- Audit probe: opaque ids only; no URL/geometry/label in audit rows.

## 4. Clinical integrity (API)

- Finalized revision UPDATE impossible (service has no path; test the
  negative via direct service call).
- Amendments append revisions; chain order + authorship correct.
- Annotation bound to exact `document_id`; new reference starts empty.

## 5. Browser E2E (vitest/jsdom + targeted real-browser pass)

- jsdom: mode toggle visibility by permission, keyboard list operations,
  undo/redo, save/finalize/discard states, overlay toggle, no-PHI/no-URL
  assertions, no-download assertion, focus management, 44px targets
  (computed from tokens), overflow assertions (as in D1c tests).
- Real browser (at least one pass before release, 320/768/1440):
  pointer draw, DPR rendering, fullscreen interplay, reduced-motion.
  jsdom cannot prove layout — say so in the report.

## 6. Non-goals for test scope

No AI/diagnostic assertions anywhere; no performance benchmarks beyond
sane payload caps (validate item-count and label-length limits
server-side; exact caps are a D2 technical decision, T4).
