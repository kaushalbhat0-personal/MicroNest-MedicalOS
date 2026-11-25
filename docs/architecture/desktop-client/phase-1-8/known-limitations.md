# Known Limitations — M9

| Item | Status | Notes |
|------|--------|-------|
| Leave cancel HTTP | **NOT IMPLEMENTED** | Service may exist; no public cancel route |
| Leave balances / accrual | **NOT IMPLEMENTED** | No balance API |
| Staff schedule PATCH | **NOT IMPLEMENTED** | Create + deactivate only |
| Permissions catalog GET | **MISSING** | Use `roles[].permissions` |
| Email delivery of invites | May be absent | UI distinguishes create vs delivery |
| Automated WhatsApp | Out of scope | Manual copy only |
| Payroll / salary | Out of scope | — |
| Biometric / GPS attendance | Out of scope | — |
| Offline workforce ops | Out of scope | Online-only v1 |
| Invitation accept in desktop EXE | Uses existing web/portal accept | Desktop creates/lists/revokes |
| Filmed EXE click-through | **PARTIAL** | Debug EXE exists; full filmed pass not claimed |
| Unused catalog perms | Declared | `schedule.manage`, `queue.manage`, reports.*, `support.grant` |
