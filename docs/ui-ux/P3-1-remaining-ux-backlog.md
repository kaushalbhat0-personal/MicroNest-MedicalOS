# P3.1 — Remaining UX backlog

Prioritized for pilot comfort. Do not fake missing backend capabilities.

## P0 — Pilot blockers (product / backend + UI)

| ID | User problem | Evidence | Expected | Backend | Frontend | Security | Tests | Priority |
|----|--------------|----------|----------|---------|----------|----------|-------|----------|
| UX-01 | Owner cannot create workspace from UI | P3.0 audit; home empty copy | Guided create + confirm | Provisioning API exists; UX incomplete | Onboarding wizard | Ownership checks | E2E create → dashboard | P0 |
| UX-02 | Practitioner approval not visible | P3.0 | Clear pending/approved states + admin approve | Approve endpoints | Admin/practitioner screens | Role-gated | Approval transition | P0 |
| UX-03 | Portal enrollment not self-serve | P3.0 | Staff-assisted enroll UI | Portal link APIs | Enrollment flow | Patient isolation | Cross-patient denial | P0 |
| UX-04 | Invitation accept UX unclear | Invites API | Accept/decline with expiry messaging | Existing invites | Invite landing | Expiry enforcement | Expired invite | P0 |

## P1 — High-value P3.1-B/C polish

| ID | User problem | Evidence | Expected | Notes |
|----|--------------|----------|----------|-------|
| UX-10 | Follow-ups/ops still raw `<select>` | follow-ups/page.tsx, operations/page.tsx | Use `Select`/`Field` | No backend change |
| UX-11 | Patient WhatsApp form raw controls | patients/[id]/page.tsx | `Select`/`Checkbox` | Keep click-to-chat only |
| UX-12 | Error paths use Alert only | Multiple pages | `ErrorState` + retry where reload exists | |
| UX-13 | Operations metric cards dense | operations/page.tsx | Align with attention-card pattern; `MoneyDisplay` | Prefer existing API fields |
| UX-14 | Portal visual polish incomplete | portal/* | Larger type, clearer next steps, empty CTAs | No admin chrome |
| UX-15 | Calendar empty actions weak | schedule/page.tsx | Empty → Book / Walk-in buttons | |
| UX-16 | Mobile portal nav not browser-verified | AppShell portal | Manual QA at 375/768/1280 | Screenshots |

## P2 — Deferred / out of scope

| ID | Item | Reason |
|----|------|--------|
| UX-20 | Ophthalmology exam templates | Discovery only |
| UX-21 | X-ray acquisition / annotation | Explicitly out of scope |
| UX-22 | Razorpay / P2.6 SaaS payments | Frozen at P2.5 |
| UX-23 | Dark mode | DESIGN deferred |
| UX-24 | Notification center | No channel API |
| UX-25 | Icon-heavy nav | Optional; groups sufficient for pilot |

## Recommended next phase

**P3.1-C / P3.2 Onboarding & portal enrollment** — implement UX-01–UX-04 with real APIs, then browser-verify dentist/eye-specialist assisted pilot paths. Continue opportunistic control normalization (UX-10–UX-12) without expanding payment or specialty clinical scope.

## Acceptance to call pilot UX-ready

1. Assisted clinic owner can reach dashboard with correct workspace context visible.
2. Receptionist can register patient → book → reception check-in on mobile and desktop.
3. Practitioner can open patient chart with breadcrumbs and timeline without nav confusion.
4. Portal patient sees “My Care” chrome and cannot access another patient.
5. Missing onboarding steps show honest pending/unavailable states — never false success.
6. Typecheck, Vitest, UI tests, and production build remain green.
7. At least one synthetic browser pass documented for dashboard, patients, schedule, reception, portal.
