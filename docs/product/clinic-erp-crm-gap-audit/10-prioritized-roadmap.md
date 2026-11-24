# 10 — Prioritized roadmap

Mapped to pilot needs: replace Excel register, run appointments, connect portal, keep billing/clinical already shipped.

## P0 — Pilot clinic operations

1. Patient CRM: update, search, email, DOB, emergency contact, activate/deactivate, soft duplicates, CSV import
2. Working hours + free-slot availability (staff + portal-safe projection)
3. Patient portal self-booking (reuse appointments; concurrency locks)
4. Walk-in booking path for reception (`now` allowed → check-in)
5. Patient profile: appointments + prescriptions + WhatsApp click-to-chat
6. Seed `patient.update` (+ portal book permission)

## P1 — Complete clinic ERP

1. Calendar day/week/month UI
2. Queue tokens / waitlist product (`QUEUE_MANAGE`)
3. Patient communication log + notification consent store
4. Stricter portal treatment-plan release (hide drafts)
5. Specialty-filtered navigation
6. Team UI location assignment
7. Patient billing chronological ledger + estimates on profile
8. Document download signed URLs (still no storage keys to client)

## P2 — Valuable expansion

1. Patient merge / correction workflows
2. Financial reports / aging export
3. Recall→appointment linking; no-show follow-up workflow
4. Inventory module
5. Portal reschedule policy engine
6. Multi-tenant portal workspace selector UX polish

## P3 — Hospital / advanced

1. Multi-location accounting consolidation
2. Attendance / HR
3. Ophthalmology clinical pack (after sign-off)
4. Automated messaging providers (email/SMS/BSP) with consent
5. PWA / native shells (A3–A5 roadmap)
6. Online patient payments

## Explicitly paused / out of scope now

- D2 dental image annotation
- Automated WhatsApp Business API
- Parallel portal or scheduling systems
- Ophthalmology invented clinical rules
