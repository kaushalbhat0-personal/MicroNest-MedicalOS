# Authorization (P1, locked)

`Identity → Membership → Role(bundle) → Permissions → Location scope → Resource`.

- Catalog: `platform/authz/permissions.py`. P1 enforces tenant-admin bundle
  (`tenant.read/settings/staff.invite/staff.manage/roles.manage/locations.manage/audit.read`)
  + platform bundle; downstream permissions declared, unenforced.
- Seed roles inserted by migration 0002; tenant custom roles = subset only
  (platform permissions rejected server-side).
- Every protected route declares `require("<permission>")` (OpenAPI documents it).
- Location scope is relational (`membership_locations`); empty = all locations.
- Last-administrator guard: cannot deactivate/demote the final `staff.manage` holder.
- Practitioner verification states exist and are enforced at use sites (P3+);
  no verification theater (legacy no-ops deleted, none reproduced).
