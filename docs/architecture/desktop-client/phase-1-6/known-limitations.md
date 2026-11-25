# Known Limitations — M7

1. **No PATCH draft note** — create new draft or amend after finalize.
2. **No PATCH encounter** — cannot relink appointment after open.
3. **Linked practitioner required** for notes/Rx (`no practitioner profile for this user` otherwise).
4. **Plan activate / procedure status / dental consent UI** not implemented — consent still enforced if those APIs are called elsewhere.
5. **Estimate issue/convert** not in desktop M7 (read-only list).
6. **Observation type codes** must match catalog; invalid codes rejected by API.
7. **Procedure codes** are catalog codes (`cleaning`, `filling`, …), not arbitrary CDT strings unless seeded.
8. **Timeline** omits note/vitals kinds (backend).
9. **Closed encounter backend write soft-lock incomplete** — desktop UI blocks writes.
10. **No AI diagnosis/Rx**, no dose calc, no auto WhatsApp.
11. **Interactive filmed click-tour** not separately recorded; API evidence + rebuild covers contracts.
12. **Online-only**; no offline clinical writes.
13. Not production signed / not deployed.
