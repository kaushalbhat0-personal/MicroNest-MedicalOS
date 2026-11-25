# Desktop information architecture (Phase 1.1)

Maps the clinic EXE navigation to **existing** web routes/APIs. Items marked **future** are not implemented today.

Desktop shell groups follow DESIGN.md / `apps/web/lib/nav.ts`, with recommended IA cleanups.

---

## 1. Global chrome

| Element | Behavior |
|---------|----------|
| Sidebar | Persistent ≥1024px; grouped; permission-filtered (same rules as `filterNavByPermissions`) |
| Top toolbar | Clinic/location context, global patient search, notifications (future), user menu |
| Workspace switcher | Tenant picker when multiple memberships; sets `X-Tenant` |
| User profile | Name, role, Sessions, Logout |
| Breadcrumbs | On detail surfaces (patient, encounter, invoice) |
| Status strip | Online indicator (required for online-first); API errors without PHI |

---

## 2. Overview

| Screen | Source today | Desktop role | Status |
|--------|--------------|--------------|--------|
| Clinic dashboard | `/` | Home — today's appointments, quick metrics | **exists** |
| Daily appointments (embedded) | Dashboard + `/schedule` | Jump to calendar | **exists** |
| Waiting patients | `/reception` + operations snapshot | Queue focus for doctor/reception | **exists** |
| Follow-ups | `/follow-ups` | Due outreach | **exists** |
| Outstanding payments | Patient/invoice billing tabs; `/billing/payments` | Surface in dashboard widgets | **partial** — dedicated AR view **future** |
| Operational alerts | `/operations` | Day board | **exists**; richer alerts **future** |
| Setup | `/onboarding` | First-run / incomplete clinic | **exists** |

---

## 3. Patient Care

| Screen | Route / API today | Status |
|--------|-------------------|--------|
| Patient directory | `/patients` | **exists** |
| Registration | `/patients` create | **exists** |
| Search | directory filters | **exists**; global command palette **future** |
| Patient 360 | `/patients/[id]` tabs Overview/Timeline/Clinical/Care/Billing/Details | **exists** |
| History | Timeline + encounters | **exists** |
| Communication | follow-ups + communication logs | **partial** — unified inbox **future** |

---

## 4. Scheduling

| Screen | Route | Status |
|--------|-------|--------|
| Calendar | `/schedule` day/week/month | **exists** |
| Appointment create / reschedule / cancel | schedule APIs | **exists** |
| Walk-ins | status + create | **exists** |
| Reception queue | `/reception` | **exists** |
| Check-in / completion | reception status | **exists** |
| Working hours | schedule + admin locations | **exists** |

---

## 5. Clinical

| Screen | Route | Status |
|--------|-------|--------|
| Consultation list | `/encounters` | **exists** |
| Consultation workspace | `/encounters/[id]` | **exists** |
| Notes / vitals / diagnoses | encounter APIs | **exists** |
| Prescriptions | encounter + prescriptions API | **exists** |
| Treatment plans | `/dental/plans*` | **exists** |
| Dental charting | Odontogram in encounter | **exists** |
| Recalls | `/dental/recalls` | **exists** — add to Clinical nav |
| Relevant history | patient 360 + encounter | **exists** |

---

## 6. Clinic Operations

| Screen | Route | Status |
|--------|-------|--------|
| Billing hub | `/billing/invoices` (nav) | **exists** |
| Estimates | `/billing/estimates*` | **exists** — promote in nav |
| Payments | `/billing/payments` | **exists** — promote in nav |
| Catalog | `/billing/catalog` | **exists** — promote under Billing |
| Receipts | `/billing/receipts/[id]` | **partial** |
| Inventory | `/inventory` | **exists** |
| Suppliers / POs | inventory tabs | **exists** |
| Financial reports | — | **future** (`reports.*` unused) |

---

## 7. Workforce

| Screen | Route | Status |
|--------|-------|--------|
| Staff directory | `/staff` Directory | **exists** |
| Invitations | `/staff` + `/team` | **exists** — **recommend single Staff hub** in desktop nav |
| Roles & permissions | admin + staff Roles | **exists** |
| Practitioner management | admin / onboarding | **exists** |
| Attendance / leave / schedules | `/staff` tabs | **exists** |

---

## 8. Workspace

| Screen | Route | Status |
|--------|-------|--------|
| Clinic settings | `/admin` | **exists** |
| Locations / hours | admin + tenants locations | **exists** |
| Practitioner availability | scheduling + staff | **exists** |
| User profile | me + sessions | **partial** — dedicated profile page **future** |
| Notifications | — | **future** |
| Security / sessions | `/sessions` | **exists** |
| Subscription | `/subscription`, `/plans` | **exists** (read; payment infra frozen) |

---

## 9. Recommended desktop nav (v1)

Consolidate vs web without inventing permissions:

**Overview:** Dashboard, Operations, Setup (if incomplete)  
**Patient Care:** Patients, Appointments, Reception, Follow-ups  
**Clinical:** Consultations, Treatment plans, Recalls  
**Clinic Operations:** Billing (invoices default; subnav Estimates / Payments / Catalog), Inventory, Staff  
**Workspace:** Clinic settings, Sessions, Subscription (if `subscription.read`)

Remove duplicate **Team** entry; fold invite into Staff → Invitations.

---

## 10. Out of desktop clinic EXE

- Patient portal `/portal/*`  
- Platform admin `/platform/*` (separate tool or web-only)  
- Marketing / signup public funnels (web)
