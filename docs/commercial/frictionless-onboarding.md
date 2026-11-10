# Frictionless Onboarding — Approved Identity & Commercial Decisions

Status: **APPROVED** (architecture alignment, 2026-11-08).
Companions: `specialty-pack-architecture.md`, `communications-architecture.md`,
`o1-revised-implementation-plan.md`.
Supersedes (in part): `o1-implementation-plan.md` §§6–9, `o1-security-and-data-model.md` §§3–4,
`o1-acceptance-criteria.md` O1.1/O1.2 gates, `onboarding-journey.md` §2 where they required
verification-gated provisioning.

Preservation: no code, migration, Docker/Compose/CI change in this slice. Docs only.
Multi-platform note (2026-11-08): this identity model governs all surfaces in
`docs/product/application-surfaces.md` — web, EXE (Tauri candidate), APK (Capacitor
candidate), PWA — over the single shared backend. No surface changes these rules.

## 0. Git baseline (recorded before work)

- Branch: `main`
- HEAD: `efefb0a3b31ff3c32a090506961d6f875a51b612`
- `git status`: pre-existing modified + untracked work preserved; this slice creates/updates
  only `docs/commercial/*`. No reset, clean, stash, discard, commit, push.

## 1. APPROVED decisions (binding)

1. **No mandatory email verification** for signup, clinic provisioning, trial activation,
   or initial workspace access. The user MUST reach the workspace without opening an inbox.
2. **Retain O1.1 verification as optional, additive security.** Do not delete
   `backend/app/modules/identity/verification.py`, `backend/app/api/v1/signup.py`,
   `backend/alembic/versions/0015_signup_verification.py`, `users.email_verified_at`,
   `is_verified()`, or `require_verified_email()`. They remain available for progressive
   assurance (sensitive actions, delivery consent, trust badges) but MUST NOT gate
   `POST /workspaces` (or its successor) or any provisioning write.
3. **Initial trial is 14 days, no card, no automatic charge, full capabilities.**
   Subscription enforcement is deferred to O1.3. Trial row creation is part of the
   provisioning transaction (atomic), not a follow-up job.
4. **Communication configuration is optional and skippable** during onboarding.
   A clinic may configure it later. Account verification is a platform-identity concern
   and MUST NOT depend on any clinic communication setting.
5. **No payment gateway, no provider implementation in this task.** Architecture only.
6. **Single generic Healthcare OS.** No per-specialty application fork.
   Specialty behavior arrives via registry + packs (see companion doc).
7. **Email identity changes remain protected.** An unverified address MUST NOT be able
   to take over an account. Any future email-change endpoint MUST verify the *new*
   address before swapping and MUST NOT transfer verification status across addresses.

## 2. Audit findings — existing O1.1 (verified against code)

All refs below were read from the working tree (post-`efefb0a` plus uncommitted work).

### 2.1 Which routes/helpers require verification?

- `require_verified_email()` is defined in
  `backend/app/modules/identity/verification.py:163-167`. Fail-closed `ForbiddenError`
  when `email_verified_at IS NULL`. Takes a server-resolved `User`, never a client id.
- **Zero production callers.** Grep over `backend/app` finds the definition plus one
  test caller (`tests/api/test_signup_api.py:375-383`). No route, dependency, or service
  invokes it. The "O1.2 provisioning gate" described in prior docs was **proposed but never
  wired**.
- `is_verified()` (`verification.py:159-160`) is used only in `signup.py:147` (resend
  suppression for already-verified users) and in `MeResponse.email_verified` projections
  (`auth.py:62,115`, `account.py:48`, `invites.py:56`). Display/routing hint only.
- Result: **no existing journey is blocked by verification today.**

### 2.2 Does verification block any existing user journey?

No. Login (`api/v1/auth.py:25-63`) authenticates by email+password with per-IP and
per-account throttles and issues a session pair regardless of `email_verified_at`.
`GET /auth/me` reports `email_verified: bool` for shell routing only. Password reset
request/confirm (`account.py:110-167`) likewise ignores verification status. Invite accept
(`invites.py:23-57`) does not check verification either. Provisioning today is operator/test
helpers only (`ops.py:cmd_bootstrap`, `tests/helpers.py:provision_tenant`); no public
workspace route exists to gate.

### 2.3 Is email normalization consistent?

Yes. Single authority `identity/service.py:27-28` (`strip().lower()`). Used by
`create_user`, `get_user_by_email`, `create_invitation`, `issue_challenge`,
`consume_challenge` (binding comparison). Signup test
(`test_signup_api.py:105-126`) proves `"  ALICE@Example.COM "` collapses to
`alice@example.com` and dedups. Invite + verification paths reuse the same helper.
No divergent normalizer found.

### 2.4 Is duplicate signup safe?

Yes. `signup.py:69-70`: if `get_user_by_email` hits, return identical `202 accepted`
with no write, no mail, no challenge. Race path (`ConflictError`/`IntegrityError`,
`signup.py:81-83`) maps to the same `202`. Tests (`duplicate_is_indistinguishable`,
`signup_throttle_stays_202`) assert zero new users/challenges and identical bodies.
No account oracle.

### 2.5 Does password recovery handle unverified accounts safely?

Yes, and it MUST stay that way for frictionless recovery. `reset_request` issues a
2h single-use token for any active account (verified or not) with a no-oracle `202`.
`consume_password_reset` (`identity/service.py:254-268`) checks only token validity and
`is_active`, revokes all sessions, and records `reset_completed`. There is no
verification precondition, so a user who mistyped-and-registered can still recover via
the address actually stored — and an attacker holding only an unverified address gains
nothing without inbox access. No change required except: do NOT add a verified-only
restriction in O1.2+.

### 2.6 Can an authenticated user safely correct a mistyped email?

**Not today — gap.** No email-change endpoint exists (grep for `email.*change|update_email`
returns nothing in `backend/app/api`). The binding check in `consume_challenge:148-150`
fail-closes if `user.email` moved after issue, which is correct but means a typo has no
self-serve fix. Recommended future endpoint (deferred implementation, specified here):
`POST /auth/email/change-request` + `POST /auth/email/change-confirm`, requiring:
(1) authenticated session, (2) password re-entry or fresh-session freshness,
(3) challenge issued against the *new* normalized address with its own TTL,
(4) swap only on consume, (5) `email_verified_at ← NULL` on swap (verification does not
transfer), (6) revoke-all-sessions or at minimum notify + audit, (7) per-account throttle.
Until built, support-assisted correction via operator tooling with the same guarantees.

### 2.7 Can verification remain optional without weakening identity security?

Yes, provided the five guards stay (all present in O1.1, all preserved):

1. Tokens are `secrets.token_urlsafe(48)`, stored as SHA-256, single-use, 24h TTL,
   superseding resend, row-locked consume (`FOR UPDATE`), identical `410` envelope.
2. Raw tokens never persist (DB, outbox refs-only, audit, API). Only the gated
   `DEV-ONLY` log line in dev/test (`signup.py:36-48`, config gate `config.py:102-110`).
3. Outbox payload allow-list (`ports.py:140-158`) forbids `token/email/phone` keys;
   `to_ref=user.id` resolved server-side at dispatch.
4. Resend throttles per-IP (10/min) + per-email (3/hour) prevent mailbox bombing;
   verified users create nothing (`signup.py:146-151`).
5. `require_verified_email` stays available for *progressive* gating of sensitive
   actions (e.g., enabling production comms provider, export, support-grant) — never
   for workspace creation.

Unverified-takeover analysis: duplicate-signup path creates nothing; resend for an
existing address delivers only to the stored inbox; cross-user presentation
(`cap-a/cap-b` test) verifies the *token owner*, not the presenter. No privilege
escalation found.

## 3. Recommended frictionless identity model (APPROVED)

```
signup (name/email/password) -> 202, session-capable immediately
  -> login allowed while unverified (existing behavior, keep)
  -> create workspace WITHOUT verified check (remove proposed gate)
  -> verify optionally, anytime (progressive assurance)
```

- Signup: unchanged (`202` always, no auto-login — keep current no-auto-login to avoid
  session-fixation ambiguity; user signs in normally). Keep `DEV-ONLY` link logging.
- Login: unchanged (no verification precondition).
- `MeResponse.email_verified`: keep as UI hint ("verify to unlock X") — never as an
  authorization claim for provisioning.
- Verify/resend: unchanged, optional. Copy MUST NOT imply the workspace is locked.
  Frontend `/signup` success state changes from "check inbox to continue" to
  "account created — continue to clinic setup; verification optional".
- `require_verified_email`: keep the function, remove it from the O1.2 contract.
  Future use only behind explicit product approval per sensitive action.
- Password reset: unchanged (works unverified).
- Email change: no endpoint until specified above; never allow unverified swap to
  claim another account's address (uniqueness check on normalized new address +
  verify-before-swap).

## 4. Non-goals (this doc)

No provider code, no gateway, no enforcement gates, no schema change. Enforcement of
trial expiry, suspension, metering, and specialty entitlements belongs to O1.3/O2.
