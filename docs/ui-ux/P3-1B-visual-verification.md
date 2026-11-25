# P3.1-B — Visual verification

## Status: **NOT PERFORMED (blocked)**

Authenticated browser testing was not completed in this phase.

### Blocker

1. No Playwright project/config in the repo (`playwright*.{ts,js}` absent).
2. Cursor browser MCP had **no open authenticated clinic session**.
3. Synthetic pilot credentials were not exercised against a running local stack in this turn.
4. Claiming screenshots without a logged-in synthetic clinic would misrepresent readiness.

### What was verified instead

| Check | Result |
|-------|--------|
| UI TypeScript | Pass |
| UI unit tests | 17 pass |
| Web TypeScript | Pass |
| Web Vitest | 44 pass |
| Next.js production build | Pass |

### Required before claiming visual pass

Capture desktop (~1280) and mobile (~375) for:

1. Dashboard — attention cards + today’s list  
2. Patient directory — search + long name  
3. Patient 360 — overview cards + timeline  
4. Appointments — day view + book form  
5. Reception — summary strip + waiting queue  

Use synthetic accounts/patients only. Document interactions (check-in, book, register), not just static renders.

### Before/after screenshots

**None attached.** Do not treat build success as UI visual proof.
