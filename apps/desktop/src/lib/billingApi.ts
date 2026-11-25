import { apiFetch } from "./api";

export type MoneyLine = {
  id: string;
  description: string;
  quantity?: string;
  unit_rate?: string;
  taxable_amount?: string;
  tax_rate?: string;
  tax_amount?: string;
  tax_treatment?: string;
  line_total: string;
  sequence?: number;
  source_estimate_line_id?: string | null;
};

export type Estimate = {
  id: string;
  tenant_id: string;
  location_id: string;
  patient_id: string;
  encounter_id: string | null;
  treatment_plan_id: string | null;
  practitioner_id: string | null;
  status: string;
  currency: string;
  subtotal: string;
  tax_total: string;
  grand_total: string;
  valid_until: string | null;
  notes: string | null;
  lines: MoneyLine[];
  created_at: string;
  updated_at: string;
};

export type Invoice = {
  id: string;
  tenant_id: string;
  location_id: string;
  patient_id: string;
  encounter_id: string | null;
  source_estimate_id: string | null;
  status: string;
  currency: string;
  subtotal: string;
  tax_total: string;
  grand_total: string;
  allocated_amount: string;
  outstanding_amount: string;
  financial_year: string | null;
  doc_number: number | null;
  due_date: string | null;
  notes: string | null;
  lines: MoneyLine[];
  created_at: string;
  updated_at: string;
};

export type PaymentMethod = "cash" | "upi" | "manual_card" | "manual_other";

export type Payment = {
  id: string;
  tenant_id: string;
  location_id: string;
  patient_id: string;
  status: string;
  method: string;
  amount: string;
  allocated_amount: string;
  unallocated_amount: string;
  currency: string;
  received_at: string;
  provider_ref: string | null;
  created_at: string;
};

export type Allocation = {
  id: string;
  payment_id: string;
  invoice_id: string;
  amount: string;
  reversal_of_id: string | null;
  reversed: boolean;
};

export type InvoiceBalance = {
  invoice_id: string;
  status: string;
  grand_total: string;
  allocated_amount: string;
  outstanding_amount: string;
};

export type Refund = {
  id: string;
  payment_id: string;
  invoice_id: string | null;
  status: string;
  amount: string;
  currency: string;
  reason: string;
  created_at: string;
  updated_at: string;
};

export type CreditNote = {
  id: string;
  tenant_id: string;
  location_id: string;
  patient_id: string;
  invoice_id: string;
  status: string;
  amount: string;
  currency: string;
  tax_rate: string;
  tax_amount: string;
  hsn_sac: string | null;
  tax_treatment: string;
  financial_year: string | null;
  doc_number: number | null;
  reason: string;
  created_at: string;
  updated_at: string;
};

export const PAYMENT_METHODS: Array<{ value: PaymentMethod; label: string }> = [
  { value: "cash", label: "Cash" },
  { value: "upi", label: "UPI" },
  { value: "manual_card", label: "Card (manual)" },
  { value: "manual_other", label: "Other (manual)" },
];

function detailMessage(json: unknown, fallback: string): string {
  if (json && typeof json === "object" && "detail" in json) {
    const d = (json as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    return JSON.stringify(d);
  }
  return fallback;
}

async function billingFetch(
  path: string,
  tenantId: string,
  init: { method?: string; body?: unknown } = {},
): Promise<{ status: number; json: unknown }> {
  const res = await apiFetch(path, {
    method: init.method,
    tenantId,
    body: init.body,
  });
  if (res.status === 401) throw new Error("session_expired");
  if (res.status === 403) throw new Error("forbidden");
  return res;
}

function listItems<T>(json: unknown): T[] {
  if (Array.isArray(json)) return json as T[];
  if (json && typeof json === "object" && "items" in json) {
    return ((json as { items: T[] }).items ?? []) as T[];
  }
  return [];
}

export async function listEstimates(
  tenantId: string,
  opts: { patientId?: string; status?: string; limit?: number } = {},
): Promise<Estimate[]> {
  const params = new URLSearchParams();
  params.set("limit", String(opts.limit ?? 50));
  if (opts.patientId) params.set("patient_id", opts.patientId);
  if (opts.status) params.set("status", opts.status);
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/estimates?${params}`,
    tenantId,
  );
  if (res.status !== 200) return [];
  return listItems<Estimate>(res.json);
}

export async function getEstimate(
  tenantId: string,
  estimateId: string,
): Promise<Estimate> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/estimates/${estimateId}`,
    tenantId,
  );
  if (res.status === 404) throw new Error("not_found");
  if (res.status !== 200 || !res.json) throw new Error("load_failed");
  return res.json as Estimate;
}

export async function issueEstimate(
  tenantId: string,
  estimateId: string,
): Promise<Estimate> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/estimates/${estimateId}/issue`,
    tenantId,
    { method: "POST", body: {} },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "issue_failed"));
  return res.json as Estimate;
}

export async function cancelEstimate(
  tenantId: string,
  estimateId: string,
): Promise<Estimate> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/estimates/${estimateId}/cancel`,
    tenantId,
    { method: "POST", body: {} },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "cancel_failed"));
  return res.json as Estimate;
}

export async function expireEstimate(
  tenantId: string,
  estimateId: string,
): Promise<Estimate> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/estimates/${estimateId}/expire`,
    tenantId,
    { method: "POST", body: {} },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "expire_failed"));
  return res.json as Estimate;
}

export async function convertEstimate(
  tenantId: string,
  estimateId: string,
  body: {
    line_ids?: string[] | null;
    due_date?: string | null;
    notes?: string | null;
    idempotency_key?: string;
  } = {},
): Promise<Invoice> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/estimates/${estimateId}/convert`,
    tenantId,
    {
      method: "POST",
      body: {
        line_ids: body.line_ids ?? null,
        due_date: body.due_date ?? null,
        notes: body.notes ?? null,
        idempotency_key: body.idempotency_key ?? `cvt-${estimateId}-${Date.now()}`,
      },
    },
  );
  if (res.status === 409) throw new Error(detailMessage(res.json, "convert_conflict"));
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "convert_failed"));
  }
  return res.json as Invoice;
}

export async function listInvoices(
  tenantId: string,
  opts: { patientId?: string; status?: string; limit?: number } = {},
): Promise<Invoice[]> {
  const params = new URLSearchParams();
  params.set("limit", String(opts.limit ?? 50));
  if (opts.patientId) params.set("patient_id", opts.patientId);
  if (opts.status) params.set("status", opts.status);
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/invoices?${params}`,
    tenantId,
  );
  if (res.status !== 200) return [];
  return listItems<Invoice>(res.json);
}

export async function getInvoice(
  tenantId: string,
  invoiceId: string,
): Promise<Invoice> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/invoices/${invoiceId}`,
    tenantId,
  );
  if (res.status === 404) throw new Error("not_found");
  if (res.status !== 200 || !res.json) throw new Error("load_failed");
  return res.json as Invoice;
}

export async function getInvoiceBalance(
  tenantId: string,
  invoiceId: string,
): Promise<InvoiceBalance> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/invoices/${invoiceId}/balance`,
    tenantId,
  );
  if (res.status !== 200 || !res.json) throw new Error("balance_failed");
  return res.json as InvoiceBalance;
}

export async function issueInvoice(
  tenantId: string,
  invoiceId: string,
): Promise<Invoice> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/invoices/${invoiceId}/issue`,
    tenantId,
    { method: "POST", body: {} },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "issue_failed"));
  return res.json as Invoice;
}

export async function voidInvoice(
  tenantId: string,
  invoiceId: string,
  reason: string,
): Promise<Invoice> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/invoices/${invoiceId}/void`,
    tenantId,
    { method: "POST", body: { reason } },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "void_failed"));
  return res.json as Invoice;
}

export async function listPayments(
  tenantId: string,
  opts: { patientId?: string; status?: string; limit?: number } = {},
): Promise<Payment[]> {
  const params = new URLSearchParams();
  params.set("limit", String(opts.limit ?? 50));
  if (opts.patientId) params.set("patient_id", opts.patientId);
  if (opts.status) params.set("status", opts.status);
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/payments?${params}`,
    tenantId,
  );
  if (res.status !== 200) return [];
  return listItems<Payment>(res.json);
}

export async function getPayment(
  tenantId: string,
  paymentId: string,
): Promise<Payment> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/payments/${paymentId}`,
    tenantId,
  );
  if (res.status !== 200 || !res.json) throw new Error("load_failed");
  return res.json as Payment;
}

export async function recordPayment(
  tenantId: string,
  body: {
    patient_id: string;
    location_id: string;
    method: PaymentMethod;
    amount: string;
    currency?: string;
    provider_ref?: string | null;
    idempotency_key: string;
  },
): Promise<Payment> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/payments`,
    tenantId,
    {
      method: "POST",
      body: {
        patient_id: body.patient_id,
        location_id: body.location_id,
        method: body.method,
        amount: body.amount,
        currency: body.currency ?? "INR",
        provider_ref: body.provider_ref ?? null,
        idempotency_key: body.idempotency_key,
      },
    },
  );
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "payment_failed"));
  }
  return res.json as Payment;
}

export async function listAllocations(
  tenantId: string,
  paymentId: string,
): Promise<Allocation[]> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/payments/${paymentId}/allocations`,
    tenantId,
  );
  if (res.status !== 200) return [];
  return listItems<Allocation>(res.json);
}

export async function allocatePayment(
  tenantId: string,
  paymentId: string,
  allocations: Array<{ invoice_id: string; amount: string }>,
  idempotencyKey: string,
): Promise<Allocation[]> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/payments/${paymentId}/allocations`,
    tenantId,
    {
      method: "POST",
      body: {
        allocations,
        idempotency_key: idempotencyKey,
      },
    },
  );
  if (res.status === 409) throw new Error(detailMessage(res.json, "alloc_conflict"));
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "alloc_failed"));
  }
  return listItems<Allocation>(res.json);
}

export async function getPatientCreditBalance(
  tenantId: string,
  patientId: string,
): Promise<string> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/patients/${patientId}/credit-balance`,
    tenantId,
  );
  if (res.status !== 200 || !res.json) return "0.00";
  return String((res.json as { credit_amount?: string }).credit_amount ?? "0.00");
}

export async function listPaymentRefunds(
  tenantId: string,
  paymentId: string,
): Promise<Refund[]> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/payments/${paymentId}/refunds`,
    tenantId,
  );
  if (res.status !== 200) return [];
  return listItems<Refund>(res.json);
}

export async function getRefund(
  tenantId: string,
  refundId: string,
): Promise<Refund> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/refunds/${refundId}`,
    tenantId,
  );
  if (res.status === 404) throw new Error("not_found");
  if (res.status !== 200 || !res.json) throw new Error("load_failed");
  return res.json as Refund;
}

export async function createRefund(
  tenantId: string,
  paymentId: string,
  body: {
    amount: string;
    reason: string;
    invoice_id?: string | null;
    idempotency_key: string;
  },
): Promise<Refund> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/payments/${paymentId}/refunds`,
    tenantId,
    {
      method: "POST",
      body: {
        amount: body.amount,
        reason: body.reason,
        invoice_id: body.invoice_id ?? null,
        idempotency_key: body.idempotency_key,
      },
    },
  );
  if (res.status === 409) throw new Error(detailMessage(res.json, "refund_conflict"));
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "refund_failed"));
  }
  return res.json as Refund;
}

export async function listInvoiceCreditNotes(
  tenantId: string,
  invoiceId: string,
): Promise<CreditNote[]> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/invoices/${invoiceId}/credit-notes`,
    tenantId,
  );
  if (res.status !== 200) return [];
  return listItems<CreditNote>(res.json);
}

export async function getCreditNote(
  tenantId: string,
  noteId: string,
): Promise<CreditNote> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/credit-notes/${noteId}`,
    tenantId,
  );
  if (res.status === 404) throw new Error("not_found");
  if (res.status !== 200 || !res.json) throw new Error("load_failed");
  return res.json as CreditNote;
}

export async function createCreditNote(
  tenantId: string,
  invoiceId: string,
  body: {
    amount: string;
    reason: string;
    tax_rate?: string;
    tax_amount?: string;
    idempotency_key: string;
  },
): Promise<CreditNote> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/invoices/${invoiceId}/credit-notes`,
    tenantId,
    {
      method: "POST",
      body: {
        amount: body.amount,
        reason: body.reason,
        tax_rate: body.tax_rate ?? "0",
        tax_amount: body.tax_amount ?? "0",
        idempotency_key: body.idempotency_key,
      },
    },
  );
  if (res.status === 409) throw new Error(detailMessage(res.json, "credit_conflict"));
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "credit_failed"));
  }
  return res.json as CreditNote;
}

export async function issueCreditNote(
  tenantId: string,
  noteId: string,
): Promise<CreditNote> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/credit-notes/${noteId}/issue`,
    tenantId,
    { method: "POST", body: {} },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "issue_credit_failed"));
  return res.json as CreditNote;
}

export async function voidCreditNote(
  tenantId: string,
  noteId: string,
  reason?: string | null,
): Promise<CreditNote> {
  const res = await billingFetch(
    `/api/v1/tenants/${tenantId}/credit-notes/${noteId}/void`,
    tenantId,
    { method: "POST", body: { reason: reason ?? null } },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "void_credit_failed"));
  return res.json as CreditNote;
}

/** Convert produces draft invoice — eligible when estimate is issued (or partial converted). */
export function canConvertEstimate(status: string): boolean {
  return status === "issued" || status === "converted";
}

export function canIssueEstimate(status: string): boolean {
  return status === "draft";
}

export function invoiceHasOutstanding(inv: Invoice): boolean {
  const n = Number(inv.outstanding_amount);
  return Number.isFinite(n) && n > 0 && !["draft", "voided", "paid"].includes(inv.status);
}

export function canCreateCreditNote(status: string): boolean {
  return !["draft", "voided"].includes(status);
}

export function canIssueCreditNote(status: string): boolean {
  return status === "draft";
}

export function canVoidCreditNote(status: string): boolean {
  return status === "draft";
}

/**
 * Display hint for refundable balance from backend-derived payment fields.
 * Equals amount − refunded (= allocated + unallocated). Backend remains authoritative.
 */
export function refundableFromPayment(payment: Payment): string {
  return addMoneyStrings(payment.allocated_amount, payment.unallocated_amount);
}

export function parseMoneyToCents(value: string): number | null {
  const cleaned = value.trim();
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null;
  const [whole, frac = ""] = cleaned.split(".");
  const cents = Number(whole) * 100 + Number((frac + "00").slice(0, 2));
  return Number.isFinite(cents) ? cents : null;
}

export function formatCents(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  const whole = Math.floor(abs / 100);
  const frac = String(abs % 100).padStart(2, "0");
  return `${sign}${whole}.${frac}`;
}

export function addMoneyStrings(a: string, b: string): string {
  const ca = parseMoneyToCents(a);
  const cb = parseMoneyToCents(b);
  if (ca === null || cb === null) return "0.00";
  return formatCents(ca + cb);
}

/** Client-side form guard only — never overrides backend validation. */
export function isPositiveMoneyAmount(value: string): boolean {
  const cents = parseMoneyToCents(value);
  return cents !== null && cents > 0;
}

export function isRefundReasonValid(reason: string): boolean {
  const len = reason.trim().length;
  return len >= 2 && len <= 200;
}

export function newIdempotencyKey(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}
