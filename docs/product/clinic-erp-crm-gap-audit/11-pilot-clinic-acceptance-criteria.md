# 11 — Pilot clinic acceptance criteria

Synthetic data only. No real PHI.

## A. Replace Excel patient register

- [ ] Staff can register patient with name, phone, email, DOB, emergency contact
- [ ] Staff can search by name/phone/email server-side
- [ ] Staff can update demographics and deactivate
- [ ] Soft warning when phone/email already exists in tenant
- [ ] Staff can CSV-import a synthetic register (≥10 rows) with duplicate report
- [ ] Tenant isolation: other tenant’s patients never appear

## B. Appointment operations

- [ ] Book / reschedule / cancel / check-in / no-show / complete still work
- [ ] Concurrent double-book returns 409
- [ ] Reception can create walk-in for “now” and check in
- [ ] Working hours configured for a location; free slots listed for a doctor/day

## C. Patient portal connection

- [ ] Linked patient sees only own appointments
- [ ] Patient can view free slots (no other patient identifiers)
- [ ] Patient can book; confirmation appears in upcoming list
- [ ] Concurrent portal books cannot double-book same practitioner slot
- [ ] Patient can cancel eligible appointments
- [ ] Closed visit / signed Rx / issued billing remain visible under existing release rules

## D. Patient profile

- [ ] Profile shows appointments, encounters, plans, billing, prescriptions
- [ ] WhatsApp click-to-chat opens only when phone present (user-initiated)

## E. Regression gates

- [ ] Existing scheduling / portal security / billing / clinical isolation tests green
- [ ] New patient + portal booking tests green
- [ ] No D2 annotation artifacts introduced
