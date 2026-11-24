# P3.4 — Next phase plan

**After:** WhatsApp-assisted onboarding share (click-to-chat)  
**Still pending from P3.3:** live dentist + eye specialist sessions

## Recommended next work

| Priority | Item | Why |
|----------|------|-----|
| 1 | Complete P3.3b live professional sessions | Feedback still pending |
| 2 | P3.0 security: server-bound `storage_key` | Blocks real-patient-data |
| 3 | P3.0 security: dental consent hard-gate | Clinical safety |
| 4 | Billing patient picker (P3.3 FB-03) | High UX friction |
| 5 | Optional: portal activation token if product requires bound one-time links | Only if enrollment UX needs it — not invented client-side |
| 6 | Production notification provider | Email for invites/verify when leaving DEV_NOTIFICATIONS |

## Do not prioritize

- WhatsApp Business API / webhooks / bulk outreach  
- Automated reminders claiming delivery  
- Ophthalmology clinical module before discovery answers  
- SaaS payment expansion (P2.5 freeze)

## Pilot policy (unchanged)

| Mode | Status |
|------|--------|
| Synthetic data | Approved |
| Real patient data | **Blocked** until storage_key + consent gate addressed |
