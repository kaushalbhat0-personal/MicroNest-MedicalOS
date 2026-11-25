# Workforce Overview

## Screen

`StaffHub` → **Overview** tab

## Data sources (no fabricated metrics)

| Metric | Source API | Soft-fail |
|--------|------------|-----------|
| Active staff count | `GET /staff` (filtered active) | forbidden → hide |
| Pending invitations | `GET /invitations?status=pending` | invite-only may still load |
| Practitioner verification queue | `GET /verification` | staff.manage |
| Today's schedules | `GET /staff-schedules` + weekday match | staff.manage |
| Attendance (recent) | `GET /attendance` date window | tenant.read |
| Pending leave | `GET /leave-requests?status=pending` | manage/read |

Counts are derived only from successfully loaded slices. Missing permission yields a caption, not zeros inventing presence.

## Permissions note

Invite-only users (`staff.invite` without `staff.manage`) see Overview + Invitations with an Alert that directory/HR edits require `staff.manage`.

## Tenant / location scope

All calls use authenticated desktop client + `X-Tenant`. Location filters applied where APIs support them. No unbounded raw SQL from desktop.
