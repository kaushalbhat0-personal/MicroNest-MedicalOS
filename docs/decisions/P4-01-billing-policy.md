# P4-01 Billing Policy Lock (decision record)

Date: 2026-11-03 · Status: locked for P4.1 schema design. No code, no migration.

## 1. Context

P3 (clinical + dental) is committed and pushed (`f19b587`). P4 is billing
foundation. The locked architecture defines the chain
service catalog → estimate → invoice → payment → refund/credit note → receipt,
with dental explicitly owning no money tables (P3-02) and treatment plan ≠
estimate ≠ invoice. The P4 reconnaissance found the platform rules binding but
almost all billing-domain policy open. This record locks the policy so
migration 0009 can be designed without unresolved business questions.

## 2. Billing boundary

Billing owns monetary truth. In scope for P4: service catalog, estimates +
lines, invoices + lines, payments, allocations, refunds, credit notes,
receipts, patient credit balance (derived), numbering per series, idempotency,
audit, payment-provider seam (port only). Out of scope: dental money tables
(`dental_invoice`, `dental_payment`, `tooth_money` — forbidden), portal,
subscriptions, licensing, inventory coupling, PDF rendering (seam only),
production provider adapters (Razorpay deferred), generic tax engine, full
GST compliance, ledger accounting beyond the entities below.

## 3. Money model

- Storage: `NUMERIC(12,2)` for every money column. No `Float`, no float
  arithmetic anywhere. Python `Decimal` only.
- Single authority: `modules/billing/money.py` (`quantize_half_up`,
  `ROUND_HALF_UP`, line/invoice total helpers). No second helper.
- Deterministic order. Line: `quantity × unit_rate → discount → taxable
  amount → tax → line total`, each step quantized half-up to paise.
  Invoice: `sum(line totals) → final total`. No invoice-level
  discounts/adjustments in P4 (deferred; lines carry all discounts).
  Totals are stored on issue (snapshot) and recomputed by the single
  writer; readers never recompute with different order.

## 4. Currency

INR only for MVP. Explicit `currency CHAR(3) NOT NULL DEFAULT 'INR'` column
on every money table. No multi-currency calculation in P4; non-INR rejected
(`ValidationError`). Column exists so a future currency is a policy change,
not a schema migration.

## 5. Rounding

`ROUND_HALF_UP` to paise (2 dp) at two boundaries only: per-line total and
invoice total. Tax per line quantized at line computation. No intermediate
rounding inside `quantity × rate`. Deterministic: same inputs always yield
identical stored totals. No float drift by construction (Decimal +
quantize + stored snapshot).

## 6. Tax/GST boundary

P4 is NOT GST-compliant software and must never claim to be. P4 supports
financial tax *fields*; full Indian GST behavior is deferred.
- Lines snapshot at issue: `tax_rate`, `tax_amount`, `hsn_sac`,
  `tax_treatment` (`taxable | exempt | zero_rated` label only).
- P4 does NOT implement: CGST/SGST/IGST split, place-of-supply rules,
  tax-inclusive pricing, exemption logic, GSTIN validation, zero-rating
  rules, return filing, e-invoicing.
- `tax_treatment` is a stored label for display/reporting; it drives no
  engine. A future tax policy may add computation without rewriting P4
  snapshots.

## 7. Estimate model

- Owner: billing. Tenant + location + patient required; `encounter_id`,
  `treatment_plan_id` nullable references (IDs only, validated read-only).
- Lifecycle: `draft → issued → (converted | expired | cancelled)`.
  Draft editable (lines may change). `issued` freezes the proposal
  (frozen snapshot, no further line edits; corrections = new estimate
  version superseding, mirroring P3 supersede chains).
- `valid_until DATE NULLABLE`; expiry is an explicit `expired` transition
  (no cron in P4; readers may treat past-`valid_until` issued estimates as
  expired for business display, but status changes only via transition).
- Conversion: creates an invoice by immutable snapshot copy of selected
  estimate lines (prices/tax/HSN copied, never live-linked). One estimate
  may produce multiple invoices; partial conversion supported (each invoice
  records `source_estimate_id`). Later catalog/estimate changes never affect
  issued invoices. Treatment plans are referenced, never merged.

## 8. Invoice lifecycle

States: `DRAFT, ISSUED, PARTIALLY_PAID, PAID, VOIDED`.
- `DRAFT`: editable (lines/totals recomputed by writer). Number unassigned.
- `ISSUED`: number allocated (series, §10), snapshot frozen, immutable.
  Allowed next: `PARTIALLY_PAID` (first allocation), `PAID` (full
  allocation), `VOIDED` (only if zero allocations and zero credit notes).
- `PARTIALLY_PAID`: further allocations → `PAID`; credit notes reduce
  outstanding without state rewrite beyond balance.
- `PAID`: terminal for the invoice balance. Refunds track on the payment,
  not by reopening the invoice.
- `VOIDED`: terminal, only from `ISSUED` under the zero-settlement
  precondition above; otherwise use credit note + refund. Retry-safe:
  same-state transitions are no-op successes (`ConflictError` only on
  illegal edges, mirroring P2/P3). `paid`/`partially_paid` are maintained
  by the single allocation writer (derived from allocations, stored for
  query, never edited directly).

## 9. Invoice immutability

Draft editable; issued immutable. Issued financial facts (lines, rates,
tax, totals, number) are never destructively updated. Corrections use
financial adjustment documents (credit note, refund, replacement invoice),
never UPDATEs of issued rows. Only lifecycle-status columns move, via the
single transition writer.

## 10. Numbering

- Series key: `(tenant_id, location_id, financial_year, doc_type)` where
  `doc_type ∈ {invoice, receipt, credit_note}` (+ `estimate` internal
  sequence if useful; estimates are proposals, numbering optional).
- `financial_year` text `FY2026-27` (India Apr 1 → Mar 31, Asia/Kolkata).
  FY is numbering/business metadata, never a security boundary.
- Allocate at ISSUE (invoices/credit notes) / at creation (receipts on
  payment capture). Drafts carry no number.
- No visible prefix format is locked; canonical internal number is an
  integer per series with a presentation function deferred/configurable.
  Uniqueness: `UNIQUE(tenant_id, location_id, fy, doc_type, number)` +
  transactional series counter with advisory lock
  (`pg_advisory_xact_lock`, P2 precedent). Gaps possible on rollback and
  explicitly accepted: uniqueness guaranteed, gaplessness NOT promised.

## 11. Financial year

India FY Apr 1 → Mar 31, evaluated in `Asia/Kolkata` (locked platform
default, conventions:5-6). Representation `FY2026-27`. Single authority
(`billing/fiscal.py` or inside `numbering.py`). FY scopes numbering series
and business reporting only.

## 12. Payment/allocation

Payment = money received. Allocation = application of payment to
obligations. Separate concepts, separate rows.
- One payment → many invoices (via allocation rows). One invoice → many
  payments. Allocation rows reference `payment_id + invoice_id`
  (+ optional line), amount `NUMERIC(12,2)`, immutable once written;
  reversal = new reversing allocation, never edit/delete.
- Unallocated payments allowed (advance). Partial allocation allowed.
  Balances derived: `outstanding(invoice) = issued_total − allocated −
  credited`; `unallocated(payment) = amount − allocated − refunded`.
  No mutable `paid_amount` source of truth; cached invoice statuses are
  maintained by the allocation writer.

## 13. Credit balance

Patient-level within tenant: `(tenant_id, patient_id)` derived balance =
`sum(payments.unallocated) + sum(open credit-note remainder)`. No separate
ledger table in P4.1; no billing-account concept. Credit allocatable to
future invoices (via allocation rows), refundable in cash (via refund),
never expires in P4. Created only by overpayment remainder and credit
notes. Overpayments are never silently discarded nor rejected: the excess
stays as explicit unallocated/credit remainder visible to staff.

## 14. Refund

Separate immutable entity linked to `payment_id` (+ optional
`invoice_id`), with required reason (≤200 chars, mirroring P2/P3 reason
caps), amount `NUMERIC(12,2)`, idempotency key, actor + timestamp.
`amount ≤ (captured − already_refunded)` else `ValidationError`. Original
payment row immutable (only link/timestamp columns move). Refund reverses
affected allocations first (reversing rows), then records the refund.
Authorization per §17; provider-refund seam via gateway port (§21);
idempotent by key + same-state no-op.

## 15. Credit notes

Separate immutable numbered document linked to exactly one issued invoice
(`invoice_id NOT NULL`, CHECK-enforced single subject mirroring P3
consent pattern). Partial credit supported (`amount ≤ outstanding at
issue`, else rejected). Snapshot tax fields copied from the invoice lines
being credited. Effect: reduces invoice outstanding (via balance
derivation); any remainder beyond the invoice is rejected at issue time
(no excess credit notes — use a smaller amount). Credit notes are never
edited; void only before application, else supersede by a new note.
Numbered per §10 series. May create patient credit only through the
derived-balance mechanism (§13), never by direct ledger write.

## 16. Receipts

Receipt = evidence of payment; payment remains source of truth. One receipt
per payment capture (1:1 with payment in P4; split receipts deferred).
Immutable, numbered per §10 series at creation. Stores `payment_id` (+
derived invoice refs for display, copied not linked-live). Rendered
PDF/storage is deferred presentation: future renderer uses existing
`StoragePort` + document-reference pointer pattern (P3-02:60-66); no bytes
in the DB, no public URLs.

## 17. Permissions

Existing catalog extended (new permissions added in 0009 alongside seed
migration, mirroring 0007/0008 practice):
`billing.read`, `billing.create` (catalog/estimate/draft),
`invoice.issue` (issue/void), `payment.record` (record/allocate),
`billing.refund` (refund + credit note — one financial-adjustment
authority), `billing.config` (catalog/tax/numbering administration).
Bundles: `tenant_admin` full billing (all six); `accountant` all except
`billing.config`? — locked: accountant gets all six *including* config
(full financial operations per business default; tenant_admin retains
staff/role control separately); `doctor` gets `billing.read +
billing.create` (estimate request only — cannot issue/record/refund);
`receptionist` gets `billing.read + payment.record` (operational
collection under `invoice.issue`-holder approval for voids); `nurse`,
`staff`, `patient` none. No role-string checks; every route declares
`require()`. Custom roles subset-only (existing validator unchanged).

## 18. Location scope

Every billing row carries `tenant_id NOT NULL` + `location_id NOT NULL`
(catalog global exception if locked as global). Encounter-linked rows
derive `location_id = encounter.location_id` and enforce via
`_encounter_in_scope`; standalone rows (OTC, advance) take explicit
`location_id` validated by `clinics_service.get_location` + active +
scope check (recall precedent). Encounter-less estimates/invoices follow
the P4 dental fail-closed rule: scoped callers (`location_ids` non-empty)
are denied when no encounter anchors the row. Patient identity never
substitutes for billing location scope.

## 19. Idempotency

Per-resource `idempotency_key NULLABLE` + partial unique
`(tenant_id, key) WHERE key IS NOT NULL` on invoices, payments, refunds,
credit notes, receipts (P2 precedent, no new mechanism). Replay with
identical intent returns the row; divergent intent → 409; same-state
lifecycle retries → no-op success. `Idempotency-Key` header takes
precedence over body field. Provider webhooks deduped by provider
event-id unique constraint. No second idempotency infrastructure.

## 20. Audit

Every transition appends to the hash-chained stream (`invoice.issued`,
`payment.recorded/allocated/refunded`, `credit_note.issued`,
`refund.issued`, `receipt.issued`, estimate transitions) with opaque refs
only (`resource_type/resource_id`, invoice/payment ids). Never amounts,
tax fields, reasons with free text beyond the ≤200-char reason stored on
the row (not copied to audit beyond ref), PHI, provider secrets, or card
data. `assert_port_safe` extended by convention (amount keys stay out of
notify/outbox payloads; only `invoice_id/payment_id` refs cross).

## 21. Provider seam

New `PaymentGatewayPort` in `platform/ports/` with
`create_intent / verify_webhook / refund / reconcile`. Domain stores only
opaque `provider_data JSONB` (never queryable facts). Dev fake adapter in
`platform/adapters/` (fail-closed `health()=false` mirroring Notify).
No Razorpay or any production adapter in P4.0 — seam only. Webhook
handling idempotent; failures/retries via outbox, never inline branching
on deployment.

## 22. Deferred decisions

Full GST engine (split, place-of-supply, inclusive pricing, GSTIN
validation, filing, e-invoicing); invoice-level discounts; automatic
estimate expiry engine; dunning/late fees; split receipts; TDS/TCS;
multi-currency; deposits/advance product separate from unallocated;
subscription/recurring billing (P7+); portal patient payments (P5+).

## 23. Consequences

P4.1 schema can be written with zero unresolved business questions: all
tables/columns/enums/constraints derive from §§3–21. Deferred items need
no schema reservation beyond the snapshot columns already specified.
Implementation must preserve: billing→patients/encounters/dental ID-only
references (never reverse), no JOIN-writes, no issued-invoice mutation, no
floats, deterministic rounding, fail-closed location/tenant scope,
per-resource idempotency, refs-only audit/outbox, port/adapter split.
