# Role-based workflow matrix (Phase 1.1)

Permissions are from `backend/app/platform/authz/permissions.py` `SEED_ROLES`.  
Nav visibility mirrors `apps/web/lib/nav.ts` rules (server-derived permission set).

**Do not invent roles.** Custom roles may exist per tenant but cannot include `PLATFORM_ONLY` codes.

---

## 1. Seed role → permission summary

| Role | Nav-relevant strengths | Notable exclusions |
|------|------------------------|--------------------|
| `doctor` | Clinical + appointments + billing create/read + inventory read/adjust + comms | Not full staff.manage / roles.manage / locations.manage (unless custom) |
| `receptionist` | Patients CRUD, appointments, encounter open/read, billing read + payment.record, comms, inventory read/adjust | No prescription.sign, limited clinical create vs doctor |
| `tenant_admin` | Broad clinic admin including staff, roles, locations, audit, billing, clinical, inventory | Not platform.* |
| `nurse` | Clinical read/create subset, follow-up/comms partial, inventory read/adjust | Narrower than doctor |
| `accountant` | Full billing + inventory + tenant.read | Not clinical write |
| `staff` | `tenant.read` only | Minimal — Dashboard + Sessions unless custom role |
| `patient` | Portal only | **Not** clinic desktop |
| `platform_admin` | Platform tenants | Out of clinic EXE MVP |

Exact code lists: see `SEED_ROLES` in `permissions.py` (authoritative).

---

## 2. Doctor — primary workflows

| Priority | Workflow | Screens | Permissions used (typical) | Gaps |
|----------|----------|---------|----------------------------|------|
| 1 | Today's appointments | Dashboard, Schedule | `appointment.read` | — |
| 2 | Waiting patients | Reception, Operations | `appointment.read` (+ update for status if allowed) | doctor seed includes appointment update? verify seed — doctor has appointment create/update in clinical-admin style bundles; confirm against `SEED_ROLES.doctor` at implement time |
| 3 | Open consultation | Encounters | `encounter.open/read`, `clinical.*` | — |
| 4 | Document visit | Encounter notes/vitals/dx | `clinical.create/read` | — |
| 5 | Prescribe | Encounter Rx | `prescription.*` | — |
| 6 | Treatment plans / charting | Dental plans, Odontogram | `dental.*`, `plan.manage` | Recalls not in sidebar today |
| 7 | Review history | Patient 360 | `patient.read` | — |
| 8 | Follow-up | Follow-ups | `followup.*` | — |

**Doctor default home:** Dashboard → deep link Reception “Waiting” + today's list.  
**Secondary:** Consultations, Patients, Treatment plans.

---

## 3. Receptionist — primary workflows

| Priority | Workflow | Screens | Permissions | Gaps |
|----------|----------|---------|-------------|------|
| 1 | Register patient | Patients | `patient.create/update/read` | — |
| 2 | Book appointment | Schedule | `appointment.create/read/update` | — |
| 3 | Calendar management | Schedule | appointment.* | — |
| 4 | Walk-ins / check-in | Reception | appointment.update/read | `queue.manage` unused — queue uses appointment.read |
| 5 | Waiting queue | Reception | appointment.read | — |
| 6 | Take payment | Billing payments / invoice | `billing.read`, `payment.record` | Payments not in sidebar |
| 7 | Follow-up coordination | Follow-ups | followup + communication | — |
| 8 | Open encounter (assist) | Encounters | `encounter.open/read` | No close/sign Rx typically |

**Receptionist default home:** Reception (or Operations).  
**Secondary:** Patients, Appointments, Billing, Follow-ups.

---

## 4. Clinic owner / tenant_admin — primary workflows

| Priority | Workflow | Screens | Permissions | Gaps |
|----------|----------|---------|-------------|------|
| 1 | Clinic performance | Dashboard, Operations | broad | Dedicated reports **future** (`reports.*` unused) |
| 2 | Staff management | Staff (directory, invites, roles) | `staff.*`, `roles.manage` | Team/Staff duplication |
| 3 | Financial overview | Billing hub, invoices, payments | `billing.*` | AR aging **future** |
| 4 | Inventory | Inventory | `inventory.*` | — |
| 5 | Clinic configuration | Admin (locations, audit, practitioners) | locations, audit, roles; nav also `settings.manage` | **`settings.manage` has no API `require()` yet** |
| 6 | Permissions | Roles in admin/staff | `roles.manage` | — |
| 7 | Subscription awareness | Subscription/Plans | `subscription.read` | Manage is platform-side |

**Owner default home:** Operations or Dashboard.  
**Secondary:** Staff, Billing, Admin, Inventory.

---

## 5. Other clinic staff

| Role | Suggested home | Visible areas (if seed unchanged) |
|------|----------------|-----------------------------------|
| `nurse` | Reception / Patients / Follow-ups | Clinical read/create subset per seed |
| `accountant` | Billing | Billing + Inventory; no clinical nav if perms lack encounter.read |
| `staff` | Dashboard | Minimal until granted custom role |

---

## 6. Permission / product gaps (explicit)

| Gap | Impact |
|-----|--------|
| `settings.manage` in nav for Admin but unused in API | Desktop must not assume a settings API behind that code alone |
| `queue.manage` / `schedule.manage` unused | Reception/schedule gated by appointment.* today |
| `documents.*` unused | Docs via dental/clinical routes |
| `reports.*` unused | No operational reports module yet |
| Team vs Staff overlap | Desktop IA should unify |
| Role seeds may be customized per tenant | Always use workspace-context permissions, never hardcode role name for authz |

---

## 7. Authz rule for desktop

1. Fetch permissions from server (`workspace-context`).  
2. Filter nav with the same rule table as web (port `NAV_RULES`).  
3. Hide actions client-side for UX; **server `require()` remains authoritative**.  
4. Never grant portal patient role a clinic shell.
