# P3.1-C — Implementation report

**Verdict:** CONDITIONAL PASS  
**HEAD (unchanged):** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Migrations / payments:** none touched

## UX-01–04 completion matrix

| ID | Status | Evidence |
|----|--------|----------|
| UX-01 Workspace create | **Implemented (UI)** | `/onboarding` → `POST /workspaces` + `Idempotency-Key` via `api.postHeaders` |
| UX-02 Practitioner approval | **Implemented (UI)** | `/onboarding` step + `/admin` verification table Approve/Reject/Register |
| UX-03 Portal enroll | **Implemented (staff UI + activation page)** | Patient Details → enroll; `/password-reset` for first password |
| UX-04 Invite accept | **Implemented (UI)** | `/invite` (+ authenticated accept); staff/team show `/invite?token=` once |

Not claimed: full authenticated browser journey green (API/web not running in this environment).

## Workspace owner onboarding

Route: `/onboarding`  
Steps (server-backed): Create workspace → Review → Practitioner approval → Invite staff → Dashboard.  
Progress indicator; specialty limited to registry codes `dental` \| `ophthalmology`.  
Home empty state links to create workspace. Nav: Setup under Overview.

## Practitioner onboarding / approval

Pending explained as not-failure; booking blocked until approved (existing server rule).  
Admin + onboarding approve call `POST .../verification` with `staff.manage`.  
Register practitioner creates pending record.

## Staff invitation

Existing `/staff` and `/team` create invites.  
Accept link format `/invite?token=…` shown once after create (dev handoff; email via notification adapter).  
`/invite` handles new-user accept and signed-in accept; opaque invalid/expired errors.

## Patient portal enrollment

Staff enroll from patient chart Details tab (`POST .../portal-links`).  
Patients activate via `/password-reset` then `/portal`.  
No list portal-links API → cannot show historical links in UI (documented).

## Files added/changed

| Path | Role |
|------|------|
| `apps/web/app/onboarding/page.tsx` | Owner setup wizard |
| `apps/web/app/invite/page.tsx` | Invite acceptance |
| `apps/web/app/password-reset/page.tsx` | Password reset / portal activation |
| `apps/web/app/admin/page.tsx` | Verification queue |
| `apps/web/app/patients/[id]/page.tsx` | Portal enroll |
| `apps/web/app/page.tsx`, `shell.tsx`, `lib/nav.ts` | Setup entry points |
| `apps/web/app/staff/page.tsx`, `team/page.tsx` | Accept-link messaging |
| `apps/web/lib/api.ts` | `postHeaders` |
| `apps/web/playwright.config.ts`, `e2e/*` | Playwright harness |
| `packages/ui/components.css` | Onboarding step styles |

## Accessibility

- Semantic headings / labeled fields on new pages  
- Progress list with active/done markers  
- Keyboard-capable buttons and forms  
- Existing focus-visible tokens  
- Opaque patient-safe invite/reset errors  

## Backend dependencies still open

- No `GET` portal-links list  
- Email delivery depends on notification adapter (`DEV_NOTIFICATIONS_ALLOW`)  
- Playwright authenticated journeys need running API + synthetic owner env vars  
