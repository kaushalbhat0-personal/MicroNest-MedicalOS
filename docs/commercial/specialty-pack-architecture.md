# Specialty Pack Architecture

Status: **APPROVED in direction, PROPOSED in details** (architecture alignment, 2026-11-08).
Companion: `frictionless-onboarding.md`, `o1-revised-implementation-plan.md`.
Sources inspected: `backend/app/modules/dental/{models,service,plans}.py`,
`backend/app/modules/clinical/{models,service}.py`, `backend/app/modules/tenancy/*`,
`backend/app/modules/clinics/*`, `apps/web/lib/nav.ts`, `apps/web/app/dental/**`,
`apps/web/app/encounters/**`, `packages/ui/dental.tsx`, `docs/specialties/*`,
`docs/decisions/P3-02-dental-model.md`, `docs/pilots/*`.

No code, migration, or dynamic-loading framework in this slice. Docs only.
Multi-platform note (2026-11-08): packs configure workflows uniformly across clinic
web/EXE and patient web/PWA/APK (`docs/product/application-surfaces.md`); packs never
alter identity, authorization, or tenant isolation on any surface.

## 1. APPROVED principles

1. **One generic core, N specialty packs.** The platform ships one Healthcare OS.
   Specialty behavior is configuration + scoped modules, never an app fork.
2. **Explicit, typed, registry-based configuration.** No generic plugin marketplace,
   no dynamic code loading, no runtime module download. Packs are first-party code
   reviewed, versioned, and shipped with the platform (cloud / private / on-prem identical).
3. **Packs configure; core enforces.** Shared core owns identity, tenancy, memberships +
   permissions, patients, scheduling, encounters, clinical records, documents, billing,
   inventory, reports. Packs may NOT fork or bypass those systems.
4. **Do not duplicate existing dental capabilities.** Dental (`P3`) is the reference
   pack. Ophthalmology discovery stays research-driven; no clinically authoritative
   eye workflows are invented here.
5. **Initial specialties: dental + ophthalmology.** Future specialties add a new pack
   without touching the core or other packs.

## 2. What exists today (verified)

- **Shared core (specialty-neutral):** `patients`, `scheduling` (future-start, double-book
  guard, idempotency, verified-practitioner gate), `encounters` (lifecycle + SOAP
  `clinical_notes`, `observations` with typed ranges, `encounter_diagnoses` coded-XOR-free-text),
  `prescriptions` (signed-only portal rule), `documents` (`document_references` + StoragePort),
  `billing` (Decimal-only `Money`, INR-only, FY doc numbers, idempotency, estimate→invoice→
  payment/allocation→receipt/refund/credit-note, tenant+location scope), `inventory`,
  `portal` (staff-gated links, closed-encounter finalized-only release), `audit` (refs only).
- **Dental pack (shipped):** `dental/models.py` — `dental_conditions` (global read-only
  catalog), `tooth_findings` + `tooth_finding_surfaces` (FDI permanent 11–48 only,
  `dental/service.py:27-52` single validator; primary 51–85 rejected), `dental_procedures`
  (catalog) + `dental_procedure_records`, `treatment_plans` + items (draft→active→
  completed/cancelled), `consents` (pending/granted/declined/withdrawn), `recalls`.
  Odontogram is a frontend projection (`packages/ui/dental.tsx`) over finding rows —
  no stored pixels. Billing linkage is manual (procedure → billing line); dental owns
  no money tables (P4-01). Portal mirrors plans/records/consents/recalls (issued-financials).
- **Ophthalmology (discovery only):** `docs/specialties/ophthalmology-discovery.md`
  (17 sections). No tables, no endpoints, no logic. Open design questions: laterality
  primitive (OD/OS/OU), acuity/refraction notations, IOP method handling, slit-lamp/fundus
  structure lists, diagnosis laterality, drops laterality on Rx items, optical orders,
  imaging comparison, referral tracking. All require ophthalmologist sign-off.
- **Tenancy/clinics:** `tenants{id,name,slug,status}`, `locations{tenant_id,name,timezone}`
  (timezone **unvalidated string**, default `Asia/Kolkata` — must add IANA validation in
  provisioning path), `memberships` + `membership_locations` (relational scope, empty = all),
  seed + custom roles, practitioner `Verification` per `(tenant,practitioner)`.
  **No specialty column exists** on tenant or location (grep confirms).
- **Frontend nav:** single static `NAV` (`apps/web/lib/nav.ts`) with `/dental/plans`
  always visible; encounters page hardcodes a Dental tab. No specialty-aware filtering.
- **Subscription discovery** anticipated `specialties_enabled` as a relational set, never a
  JSON blob on the tenant (`subscription-domain-discovery.md:33`). Adopted below.

## 3. Smallest safe model for specialty selection (PROPOSED, recommended)

### 3.1 Where does specialty live? Tenant, location, or both?

**Both, with distinct meanings (PROPOSED):**

- `tenant_specialties(tenant_id, specialty_code, enabled_by, enabled_at)` — commercial /
  capability scope. "This clinic is entitled to use dental and/or ophthalmology."
  Relational set (one row per enabled pack). Seeded by provisioning choice; later gated
  by subscription entitlement (O2). Never a JSON column.
- `location_specialties(location_id, specialty_code)` — operational scope. "This chair/room
  serves dental." A single-location clinic inherits its tenant's set; a multi-location
  group may scope locations differently (e.g., Location A = dental, Location B = eye).
  Empty set = inherits all tenant specialties (mirrors `membership_locations` empty=all
  convention). Validation: every location specialty MUST be a subset of the tenant set.

Rationale: multi-specialty clinics and multi-location groups are first-class (approved
direction). Tenant-only would force a whole clinic into one specialty; location-only would
lose the commercial entitlement anchor. The pair covers: solo dentist (1 tenant / 1 location /
`{dental}`), multi-doctor dental (same, more memberships), multi-location group
(tenant `{dental,ophthalmology}`, locations split), white-label org (same, plus branding
resolver later).

### 3.2 Multi-specialty rules

- A clinic MAY enable multiple packs simultaneously. Data isolation is by `tenant_id`
  (+ `location_id` where relevant), never by specialty — specialty NEVER weakens RLS.
- Cross-specialty reads within the same tenant follow normal membership + permission +
  location-scope checks. Hiding an unsupported specialty's UI NEVER changes authorization
  (see §5).
- Practitioners are specialty-agnostic rows; *verification* and *scheduling eligibility*
  are per-tenant as today. A future `practitioner_specialties` link is DEFERRED until
  a specialty requires practitioner-level gating (ophthalmology may; dental does not).
- Billing, inventory, documents, reports stay shared. Specialty catalogs (dental procedures,
  future eye procedures/catalogs) are separate tables; billing lines reference them by id
  without specialty FKs leaking into money tables.

### 3.3 How specialty configuration is resolved (PROPOSED)

```
request -> get_ctx (tenant + permissions + location scope, unchanged)
  -> resolve_specialties(tenant_id, location_id?)
       tenant set  = SELECT code FROM tenant_specialties WHERE tenant_id
       location set = SELECT code FROM location_specialties WHERE location_id
                      (empty => tenant set)
       effective   = tenant set INTERSECT location set  (+ single-location default)
  -> registry lookup -> pack descriptor (typed, versioned)
  -> UI + API shape filtering (hide-only, never authorize)
```

- Resolution is server-side, per request, from relational rows. No client-supplied
  specialty claim is trusted. No per-request DB hotspot concern: tiny sets, cachable
  per (tenant, location) with invalidation on enable/disable.
- Default for pre-pack tenants (all existing test/bootstrap tenants): `{dental}`
  backfill note (migration-time data note, not code in this slice) OR treat empty as
  `{dental}` for backward compatibility — **UNRESOLVED**, needs product sign-off
  (see §7). Recommended: explicit backfill row at migration time so resolution never
  branches on "empty means legacy".

### 3.4 Registry shape (PROPOSED, explicit + typed)

```python
# app/modules/specialties/registry.py (FUTURE, not built here)
@dataclass(frozen=True)
class SpecialtyPack:
    code: str                    # "dental" | "ophthalmology" | ...
    version: str                 # semver of the pack contract, e.g. "1.0.0"
    label: str                   # display name (i18n key, not free text)
    terminology: dict[str, str]  # e.g. {"practitioner": "Dentist", "visit": "Sitting"}
    dashboard_widgets: tuple[str, ...]   # widget keys the shell may render
    nav: tuple[NavEntry, ...]             # href/label/icon, filtered by enablement
    clinical_forms: tuple[str, ...]       # form keys (finding form, eye-exam form, ...)
    workflow_steps: tuple[str, ...]       # consultation pipeline steps
    catalogs: tuple[str, ...]             # catalog table keys this pack reads
    message_templates: tuple[str, ...]    # notify template keys
    shortcuts: tuple[str, ...]            # keyboard/shortcut sets
```

- Registry is a **compile-time dict** (`SPECIALTIES: dict[str, SpecialtyPack]`) in
  first-party code. Adding a specialty = new module + registry entry + migration for
  its tables + tests. No marketplace UI, no `pip install pack`, no `importlib` tricks.
- Pack version is stored alongside enablement (`tenant_specialties.pack_version`) so
  upgrades are explicit per tenant (migrate-then-bump), and the UI can show "pack v1.1
  available". Core schema version and pack versions evolve independently.
- Dental pack v1 = codification of what exists (FDI rules, surfaces, plan/consent/recall
  state machines, odontogram projection, catalog keys). No refactor of dental tables.

### 3.5 What packs MAY configure vs MUST NOT fork

| Pack MAY configure | Pack MUST NOT fork/replace |
|---|---|
| Terminology (labels, visit nouns) | Identity, sessions, authN/Z primitives |
| Dashboard widgets (keys only; data via core queries) | Tenancy, memberships, roles, location scope |
| Clinical forms + validation (FDI, laterality, notations) | Patients, encounters lifecycle, notes finality |
| Workflow steps (consultation pipelines as UI + service orchestration over core) | Billing/inventory money tables or state machines |
| Relevant catalogues (own tables; shared catalogs by data rows only) | Audit, RLS policies, outbox, ports |
| Message templates (keys; delivery via comms architecture) | Notification eligibility or port boundaries |
| Navigation + shortcuts (hide/show; never permission) | Permission strings or `require()` gates |

Hiding rule: `if pack not enabled: hide nav/form/widget`. Authorization stays
`require(permission)` + `match_tenant` + location scope. A hidden route that is
directly requested MUST still 404/403 by tenant isolation, not by specialty check —
specialty checks produce UX filtering only, plus a `422/404 specialty-not-enabled`
*advisory* error that never leaks cross-tenant existence.

## 4. Dental pack (reference, no duplication)

Codify as-is: `PERMANENT_TEETH`, `SURFACES`, finding lifecycle (active→resolved),
plan/item/record/consent/recall state machines, catalog-read-only discipline,
manual procedure→billing linkage, portal release rules, `packages/ui/dental.tsx`
projection. Any change (e.g., primary dentition 51–85) is a pack-version bump with
migration + tests, not a core change.

## 5. Ophthalmology pack (research-driven, NOT invented)

Approved shape, deferred content: new `ophthalmology` module beside `dental`
(tables only after discovery sign-off), laterality enum (values TBD by doctor),
acuity/refraction/IOP/slit-lamp/fundus fields (notations TBD), eye-scoped
procedure/consent/recall mirrors (no dental-table reuse), shared billing/portal/
audit reuse. **Explicit non-goals carried forward:** no diagnostic thresholds or
treatment rules in code, no device integration, no optical inventory, no tables
before domain approval (`ophthalmology-discovery.md` §16).

## 6. Versioning (PROPOSED)

- Packs versioned by semver string in the registry + `pack_version` column on
  `tenant_specialties`. Patch = copy/terminology/template tweaks. Minor = new
  optional forms/widgets. Major = breaking form/catalog contract (requires migration
  + per-tenant opt-in).
- Core exposes `specialty_capabilities(tenant_id)` read (for shell + tests), never
  a write path for bumping versions from the browser. Bumps are migration/operator
  actions with audit refs.

## 7. Unresolved (needs owner sign-off)

1. Legacy default: explicit `{dental}` backfill vs empty-means-dental.
2. Location-level scoping in v1 vs tenant-only v1 + location split in v2.
3. `practitioner_specialties` needed in v1 (ophthalmology may demand it).
4. Specialty-gated subscription entitlements shape (O2).
5. White-label pack overrides (branding resolver is a separate future doc).
