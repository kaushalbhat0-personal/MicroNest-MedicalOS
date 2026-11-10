# P7-01 — Deployment topology, profiles, and secrets

Status: accepted (P7 preview slice).

## Context

One modular monolith must serve cloud SaaS, dedicated private cloud, and
on-prem installations without business-logic branches on deployment type
(non-negotiable constraint).

## Decision

1. Same containers everywhere: `backend` image (API + `migrate` job +
   `worker` entrypoints), `web` image, Postgres 16, S3-compatible storage.
   Only the composition and the configuration differ per model:
   - cloud: hosted Postgres (PITR), S3, secret manager, reverse proxy + TLS.
   - private: dedicated instances of the same components, customer-held
     secrets, controlled upgrades.
   - on-prem: local Postgres + local S3-compatible storage (MinIO) +
     local worker; no inbound ports, no public DB exposure.
2. Deployment profiles (`ENV` × `DEPLOYMENT`) describe validated operational
   configuration only: development, test, preview, production-cloud,
   production-private, production-onprem. enforced by
   `config.validate_for_boot`, called by `create_app` and the worker.
3. Secrets come from the environment (preview: `.env.preview`; cloud/private:
   secret manager injected as env). `JWT_SECRET` length is validated;
   validation errors name variables, never values; logs are scrubbed.
4. `NEXT_PUBLIC_API_URL` is build-time public config (documented limitation:
   one web image per domain; runtime config is future work, not a blocker).

## Consequences

- Preview runs `COOKIE_SECURE=false` only for localhost-only origins
  (local stack is plain HTTP). Any non-localhost preview origin and all
  production profiles require `true` + HTTPS.
- Preview refuses to boot against a non-`preview` database name;
  production refuses `preview` names. This is a guardrail, not a substitute
  for access control.
