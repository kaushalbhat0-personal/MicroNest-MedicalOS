# M9 Workforce API Audit

**Branch:** `release/p3-7b-staging` @ `293dc66`  
**Date:** 2026-11-25

## Entity distinctions

| Concept | Model | Notes |
|---------|-------|-------|
| User | `users` | Global login identity |
| Membership | `memberships` | Tenant employment + role + location scope |
| Staff profile | `staff_profiles` | HR fields 1:1 with membership |
| Invitation | `invitations` | Pre-membership; token shown once |
| Practitioner | `practitioners` + verifications | Clinical identity; orthogonal to membership |

## Feature matrix

| Feature | API | Permission | Data model | State transitions | Existing tests | Desktop |
|---------|-----|------------|------------|-------------------|----------------|---------|
| Staff directory | GET `/staff?q&active_only&location_id` | `staff.manage` | StaffMemberResponse | — | `test_staff.py` | Implemented |
| Staff get/patch | GET/PATCH `/staff/{membership_id}` | `staff.manage` | profile + membership | employment_status; last-admin guard | same | Implemented |
| Invite create | POST `/invites` | `staff.invite` | invitations | → pending; token once | same | Implemented |
| Invite list/revoke | GET `/invitations`; POST revoke | `staff.invite` | — | pending→revoked | same | Implemented |
| Invite accept | POST `/invites/accept` (+ authenticated) | public / session | membership | pending→accepted | tenants API | Documented (portal/web flow) |
| Roles list/create | GET/POST `/roles` | `tenant.read` / `roles.manage` | roles | custom create only | tenants API | Implemented |
| Practitioners | GET `/practitioners` | `appointment.read` | verification_status | — | scheduling | Implemented |
| Verification | GET/POST `/verification` | `staff.manage` | pending/approved/rejected | set status | tenants API | Implemented |
| Staff schedules | POST/GET `/staff-schedules`; deactivate | `staff.manage` | staff_schedules | active→inactive | `test_staff.py` | Implemented |
| Attendance | check-in/out; GET list; correct | `tenant.read` / `staff.manage` | attendance_records | open→closed | same | Implemented |
| Leave types/list/request/decide | leave-types + leave-requests | `tenant.read` / `staff.manage` | leave_requests | pending→approved\|rejected | same | Implemented |
| Leave cancel | **NO HTTP** (404) | — | service only | — | — | **NOT IMPLEMENTED** |
| Leave balances | **MISSING** | — | — | — | — | **NOT IMPLEMENTED** |
| Self leave decide | decide endpoint | `staff.manage` + policy | — | own request → 403 observed | `test_staff.py` | UI uses decide; backend blocks self |
| Permissions catalog GET | **MISSING** | — | permissions.py | — | seed drift | Use roles[].permissions |
| Schedule PATCH | **MISSING** | — | create+deactivate only | — | — | Documented |

## Declared unused permissions

`schedule.manage`, `queue.manage`, `reports.view`, `reports.export`, `support.grant` — not attached to these HTTP adapters.

## Staff schedule vs appointment availability

- Staff schedules = HR windows on **membership**
- `/availability` = booking slots for **verified practitioner** + location working hours
