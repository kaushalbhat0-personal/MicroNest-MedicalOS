# P3.2 — Owner / approval / invite / portal journeys

**Verdict (journeys):** PASS on local synthetic data with API + web running  
**HEAD:** `2a0974e41af9e334e147794f45e258f34d6814d3`

## Owner workspace journey

Evidence: Playwright `P3.2 owner workspace journey` on desktop-1440, desktop-1280, mobile-390.

| Step | Result |
|------|--------|
| Signup synthetic owner | Pass (`POST /api/v1/auth/signup` → 202) |
| UI login + session cookie | Pass (same hostname: `localhost` web + API) |
| Open `/onboarding` | Pass |
| Create workspace via UI | Pass (`POST /workspaces` + `Idempotency-Key`) |
| Tenant visible on `/auth/me` | Pass (slug match) |
| Pending practitioner shown | Pass |
| Approve practitioner | Pass (`Approve practitioner` → approved) |
| Reach dashboard + clinic screens | Pass (patients / schedule / reception) |

Idempotent duplicate create verified in invite journey via repeated `POST /workspaces` with the same `Idempotency-Key` → same `tenant.id`.

Screenshots: `docs/ui-ux/screenshots/p32-*-onboarding.png`, `*-workspace-created.png`, `*-practitioner-pending.png`, `*-practitioner-approved.png`, `*-dashboard.png`.

## Practitioner approval

| Check | Result |
|-------|--------|
| Pending visible after workspace create | Pass |
| Admin/owner approve updates UI from server | Pass |
| Receptionist cannot approve via API | Pass (`401`/`403` on verification POST) |
| Failed approval does not show success | Pass (unauthorized status asserted) |

Self-approve by a non-admin role is denied by server permissions (`staff.manage`).

## Staff invitation

Evidence: `staff invitation accept and rejection paths` (desktop-1280 only).

| Step | Result |
|------|--------|
| Owner creates invite (`role=receptionist`) | Pass |
| Invitee accepts via `/invite` (new account) | Pass → leaves `/invite` |
| Invalid token | Pass — opaque “invalid or expired” |
| Re-use accepted token | Pass — opaque invalid/expired |
| Wrong signed-in email | Pass — “invitation email does not match authenticated user” |

Raw tokens are not written to docs screenshots (capture after redirect only). Email delivery is **not** claimed; local handoff uses API token + `DEV_NOTIFICATIONS_ALLOW`.

## Patient portal enrollment

Evidence: `patient portal enrollment and isolation controls` (desktop-1280).

| Step | Result |
|------|--------|
| Staff registers synthetic patient | Pass |
| `POST .../portal-links` enroll | Pass |
| Password set via `scripts/p32_set_user_password.py` (dev helper; not production reset email) | Pass |
| Patient UI login → `/portal` | Pass |
| Unauthenticated `/portal` → `/login` | Pass |
| No clinical-note leakage on anon portal | Pass (body assertion) |

Public password-reset UI remains available; production email delivery remains a documented dependency.

## Commands

```powershell
npm run test:e2e -w @healthcare-os/web
# 14 passed · 4 skipped (invite/portal/isolation intentionally once on desktop-1280)
```
