# P3.1-C — Onboarding UX audit

**Date:** 2026-11-24  
**HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3`  
**Sources:** P3.0 onboarding plan, P3.1 / P3.1-B backlogs, live API/routes.

## UX-01–04 definitions (from backlog)

| ID | User problem | Expected |
|----|--------------|----------|
| UX-01 | Owner cannot create workspace from UI | Guided create + confirm via `POST /workspaces` |
| UX-02 | Practitioner approval not visible | Pending/approved UI + admin approve |
| UX-03 | Portal enrollment not self-serve | Staff-assisted enroll UI + patient activation |
| UX-04 | Invitation accept UX unclear | Accept page; expired/invalid handling |

## Backend mapping (pre-implementation)

| ID | API exists? | Frontend before P3.1-C |
|----|-------------|------------------------|
| UX-01 | Yes — `POST /api/v1/workspaces` + `Idempotency-Key` | Missing wizard; home said unavailable |
| UX-02 | Yes — `GET/POST .../verification`, `POST .../practitioners` | Schedule filters approved only; no approve UI |
| UX-03 | Yes — `POST .../portal-links`; password-reset APIs | No enroll UI; no password-reset page |
| UX-04 | Yes — invites create/list/revoke; `POST /invites/accept` (+ authenticated) | Send UI on `/team` `/staff`; **no** `/invite` page |

## Assisted pilot reality (P3.0)

Pilots were API-bootstrapped. Self-serve UI was the gap — not missing provisioning APIs.

## Security constraints retained

- Owner from session only on workspace create (no owner id in body).
- Verification requires `staff.manage` server-side.
- Portal enroll requires `staff.manage`; patient id server-validated.
- Invite accept uses opaque Gone errors (no token oracle).
- Password-reset request does not reveal account existence in UI copy.
- No payment / Razorpay changes.
