# P3.7B Step 1 — Main Branch Release Audit

**Date:** 2026-11-24  
**Decision:** **B — BLOCKED**  
**Do not deploy `origin/main` as the Healthcare OS staging release candidate.**

## Git evidence

| Item | Value |
|------|-------|
| Current branch | `main` |
| Local `HEAD` | `2a0974e41af9e334e147794f45e258f34d6814d3` |
| `origin/main` | `2a0974e41af9e334e147794f45e258f34d6814d3` |
| Local vs origin divergence | `0 0` (same commit; dirty working tree) |
| Latest pushed commit subject | `chore(release): consolidate completed Healthcare OS phases through dental imaging` |
| Working tree | Extensive modified + untracked files (not on `origin/main`) |

`HEAD` and `origin/main` are identical **commits**. The release candidate content for P3.6 / post-0017 migrations lives only in the **local uncommitted working tree**.

## Decision

| Option | Result |
|--------|--------|
| A. READY FOR RENDER CONFIGURATION (deploy main) | **No** |
| **B. BLOCKED — fixes only local; need reviewed deployment branch** | **Yes** |
| C. BLOCKED — security/migration uncertain | Partial overlap (migration mismatch also blocks) |

## P3.6 security — origin/main vs local

| Control | `origin/main` @ `2a0974e` | Local working tree |
|---------|---------------------------|--------------------|
| Server-generated document storage keys (`allocate_document_storage_key`) | **Absent** | Present |
| Client `storage_key` ignored / optional | **Required client key persisted verbatim** | Ignored; server allocates |
| Tenant-bound key check on access (`_assert_document_storage_bound`) | **Absent** | Present |
| Dental procedure consent hard-gate (`_require_granted_procedure_consent`) | **Absent** (transitions without consent) | Required for `in_progress` / `completed` |
| Regression suite `tests/security/` | **Absent** | Untracked |
| Updated `test_document_access_api.py` / dental lifecycle tests | Baseline (expects client keys) | Modified for server keys + consent |

**Evidence (origin/main):** `create_document_ref(..., storage_key: str)` strips and stores the client key; no allocate/consent-gate symbols in that revision.

**Evidence (local):** symbols `_CONSENT_GATED_RECORD_STATUSES`, `_require_granted_procedure_consent`, `allocate_document_storage_key`, `_assert_document_storage_bound` in `backend/app/modules/dental/plans.py`.

## Alembic / Supabase staging mismatch

| Item | `origin/main` | Staging Supabase (`healthcare_os_preview`) |
|------|---------------|--------------------------------------------|
| Latest migration in tree | **`0017_o13r_visibility`** | **`0027_saas_payment_reliability`** |
| Migrations 0018–0027 | **Not on origin** (local untracked) | Applied |

Deploying `origin/main` against the already-migrated staging DB:

- Application code on main does not include modules/APIs introduced in 0018–0027.  
- Alembic history on main ends at 0017 while the database reports 0027 → release tooling mismatch.  
- Re-running migrate from main cannot “contain” 0027.

## Supabase compatibility on origin/main (partial)

Present on `origin/main` (usable once env is set):

| Capability | Status on `origin/main` |
|------------|-------------------------|
| `APP_DATABASE_URL` | Supported (`Settings` + readiness) |
| `OWNER_DATABASE_URL` | Alembic `env.py` / ops (migrations job) |
| `STORAGE_ADAPTER=s3` | Supported |
| `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` | Supported (`S3StorageAdapter` / boto3 in requirements) |
| Boot profile `ENV=preview` + db name containing `preview` | Supported (staging DB name `healthcare_os_preview` fits) |

Missing relative to P3.6/P3.7 release intent: server-side document key binding + consent hard-gate + migrations/code through 0027.

**Note:** Application env names are `S3_ACCESS_KEY` / `S3_SECRET_KEY` / `S3_ENDPOINT_URL` (not `S3_ACCESS_KEY_ID` / `S3_ENDPOINT`).

## Deploy surface (works for either main or a future branch)

| Item | Value |
|------|-------|
| Backend root | Repo root; app under `backend/` (`--app-dir backend`) |
| Python | **3.10** (`backend/Dockerfile`, `pyproject.toml` target) |
| Build | `pip install -r backend/requirements.txt` |
| Start | `python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT` |
| Health | `GET /api/healthz` |
| Readiness | `GET /api/readyz` |
| Migrations | `alembic -c backend/alembic.ini upgrade head` with `OWNER_DATABASE_URL` (not on web boot) |

## Exact local changes required for a reviewed deployment branch (minimum P3.6 + schema parity)

### Must include (P3.6)

- `backend/app/modules/dental/plans.py` (modified)
- `backend/app/modules/dental/schemas.py` (modified)
- `tests/api/test_document_access_api.py` (modified)
- `tests/api/test_dental_api.py` (modified)
- `tests/service/test_rx_dental.py` (modified)
- `tests/security/` (untracked — P3.6 suite)

### Must include (Alembic 0018→0027 + dependent modules)

Untracked migrations:

- `backend/alembic/versions/0018_patient_crm_availability.py` … `0027_saas_payment_reliability.py`

Plus the corresponding untracked/modified application modules that those revisions and later product phases expect (inventory, staff, subscriptions, saas_payments, communications, operations, etc.). Deploying only dental diffs without 0018–0027 code/migrations is insufficient for the current staging database.

### Docs (optional for runtime; recommended for release review)

- `docs/security/P3-6-*.md`, `docs/deployment/P3-7A-*.md`, `docs/deployment/P3-7B-*.md`

### Must never ship

- `.env` (contains secrets including `RENDER_API_KEY`, DB, S3)

## Render API key

`RENDER_API_KEY` is **PRESENT_FILLED** in local `.env` (value not recorded here).  
This audit still **does not deploy**. Key availability does not make `origin/main` safe to release.

## Recommended next action

1. **Do not deploy** the connected Render service from `main` @ `2a0974e`.  
2. Obtain approval to create a **reviewed deployment branch** (e.g. `release/p3.7b-staging`) that commits the local release candidate (P3.6 + 0018–0027 + required modules), **excluding `.env`**.  
3. Point the existing Render service `healthcare-os-api-staging` at that branch after review.  
4. Then proceed to Render env configuration + smoke tests (P3.7B later steps).

## Summary

| Question | Answer |
|----------|--------|
| Is `origin/main` the complete RC? | **No** |
| Can current main be deployed safely? | **No** |
| Why? | Missing P3.6 remediations; migrations/code stop at 0017 while staging DB is 0027 |
| Next | Reviewed deployment branch + explicit push approval |
