# P3.1-C — Remaining backlog

## Still blocked / incomplete

| ID | Item | Priority |
|----|------|----------|
| VIS-AUTH | Authenticated Playwright journeys (owner setup, approve, enroll, invite accept API) | P0 |
| VIS-ISO | Browser isolation journeys E (cross-patient / unauthorized clinic routes) | P0 |
| API-PORTAL-LIST | `GET` portal-links for patient chart status display | P1 |
| UX-10 | Follow-ups/ops raw selects | P1 |
| UX-14 | Deeper portal polish | P1 |
| MAIL | Production email for invites/reset (dev console only today) | P1 |
| HOURS | Working-hours step inside onboarding wizard | P2 (API exists elsewhere on schedule) |

## Explicitly deferred

- Ophthalmology clinical modules  
- X-ray acquisition  
- SaaS payments beyond P2.5  
- Weakening auth for Playwright  

## Recommended next step

1. Run API + web locally with synthetic owner env vars.  
2. Extend e2e to create workspace → approve practitioner → invite → accept → portal enroll.  
3. Capture 1440/1280/390 screenshots for authenticated screens.
