# AMENDMENT (2026-11-08, frictionless onboarding — GOVERNING)

> The §2 flow step "verify-email (token…) → authenticated" as a provisioning
> precondition is SUPERSEDED by `docs/commercial/o1-revised-implementation-plan.md` §5:
> signup → clinic → specialty → doctor → trial → workspace with verification optional
> and comms skippable. Preserved for history.

# Onboarding Journey

Status: discovery ONLY. Target journey; step maturity is marked honestly.
Companion: `docs/commercial/customer-onboarding-architecture.md`.

## 1. Target journey with current maturity

| # | Step | Today | Gap to close |
|---|---|---|---|
| 1 | Doctor visits public site | missing — no public site | O1: marketing/product/specialty pages |
| 2 | Reviews product + specialty capabilities | partial — discovery docs only, no pages | O1: dental + ophthalmology pages from approved discovery |
| 3 | Creates an account | missing — no signup | O1: signup + email verification (new; P8.1B eligibility + post-P8.1C delivery carry the verify mail) |
| 4 | Verifies account | partial — reset flow exists, no verify flow | O1: token-based verify reusing invite-token patterns |
| 5 | Creates clinic workspace | missing self-service — platform-admin/CLI only | O1: atomic provision transaction |
| 6 | Selects specialty | missing — no specialty field | O2/O3: specialty set on tenant, gates modules |
| 7 | Enters clinic information | partial — tenant name/slug only | O3: clinic profile |
| 8 | Configures location + timezone | partial — location exists, timezone unvalidated | O1: add IANA validation at write |
| 9 | Completes doctor/practitioner profile | exists — practitioner + verification | reuse; add specialty linkage |
| 10 | Selects subscription plan | missing | O2: plan catalog + selection |
| 11 | Completes payment | missing | O2 test-mode, O4 production |
| 12 | Activates clinic workspace | partial — status flag exists, no activation flow | O1: activation on provision/subscribe |
| 13 | Configures services + appointment settings | exists — catalog + scheduling | reuse; add working hours (missing) |
| 14 | Invites staff | exists — invite flow | reuse + subscription-state gate |
| 15 | Adds/imports patients | partial — single registration, no import | O3: import tooling + dedup rules (open decision) |
| 16 | Enables portal enrollment | exists — staff-gated enrollment | reuse + subscription-state gate |
| 17 | Starts operating | exists — full clinic loop verified in pilots | reuse |

## 2. Onboarding UX flow (proposed, no screens built)

Public (unauthenticated): landing → specialty pages → pricing → signup (email + password, locale-aware) → verify-email (token, expiry, resend throttled like reset flow) → authenticated.
Workspace creation (authenticated, no tenant yet — new `X-Tenant`-less context): clinic name/slug (availability checked server-side, no oracle) → specialty → location + timezone (validated IANA picker, default Asia/Kolkata) → practitioner profile → plan selection (trial default) → payment or trial start → atomic provision → progress checklist (services, hours, staff invites, first patient, portal test) → completion.
All forms follow DESIGN.md §12 (labels, error summary with focus, `role=alert`, 44px targets, keyboard-complete); mobile-first; WCAG 2.2 AA; existing tokens/components only (`packages/ui`), no second system. New statuses (trial, past_due, grace, suspended) extend `status.ts` mapping — never client-invented strings.

## 3. Two-pilot onboarding scenario (synthetic)

Pilot A (Nevase's Multispeciality Dental Clinic, Vadgaon Budruk Pune): signup as owner → workspace `nevase-dental` → specialty dental → location "Main Clinic", timezone Asia/Kolkata → practitioner profile + self-verification approval (second owner/admin if available, else platform-admin countersign — D8) → trial plan → service catalog seed (dental procedures) → working hours → invite receptionist + doctor → register synthetic patients → portal enrollment for one synthetic patient → operate: appointment → encounter → finding → plan → consent → estimate → invoice → payment → recall.
Pilot B (independent ophthalmology clinic, Pune): same spine with specialty ophthalmology (discovery-only module — expectations set: shared core only), location "Eye Clinic", identical isolation assertions.
Independence assertions per pilot: separate tenants/slugs, locations, memberships, patients, appointments, clinical rows, invoices, portal links, audit streams; cross-pilot reads 404; dual-membership user requires explicit `X-Tenant`; subscription state of A never affects B. Success criteria: the existing `test_p8_two_tenant_pilots.py` pattern extended to provision-via-future-API, all green on synthetic data.
