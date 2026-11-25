# Known Limitations — Phase 1.4+1.5

1. **Online-only** — no offline patient DB or sync.
2. **Patient list** — server `limit` ≤200; desktop uses ≤100 + client paging of that window (not full DB fetch / no cursor API on patients).
3. **Directory columns** — registration date / last visit not on list payload; last visit shown on overview after open.
4. **Clinical editors** — notes, prescriptions, plans, charting deferred (M7+); timeline still shows returned clinical events.
5. **Billing screens** — read-only lists in profile when authorized; no invoice/payment UI workflows.
6. **Queue refresh** — HTTP polling every 15s; not WebSocket/push.
7. **No `in_progress` status** — backend enum omits it; desktop does not invent it.
8. **Availability** — may return zero slots without working hours; booking still allowed with server validation (conflicts → error).
9. **Unverified practitioners** — list may include them; create/availability returns 403 until approved (backend authoritative).
10. **Reschedule history** — no dedicated history API; cancel/reschedule audit fields on appointment only.
11. **EXE interactive tour** — rebuild embeds M5/M6 UI; detailed click-path evidence is API JSON + unit/backend suites (Phase 1.3 covered native auth EXE).
12. **Not production signed / not deployed.**
