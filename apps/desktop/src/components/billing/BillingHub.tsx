import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  Field,
  FinancialSummary,
  Input,
  LoadingState,
  MoneyDisplay,
  Select,
  Status,
  Table,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Td,
  Th,
} from "@healthcare-os/ui";
import { fetchTenantLocations } from "../../lib/api";
import {
  allocatePayment,
  canConvertEstimate,
  canIssueEstimate,
  cancelEstimate,
  convertEstimate,
  expireEstimate,
  getEstimate,
  getInvoice,
  getInvoiceBalance,
  getPayment,
  invoiceHasOutstanding,
  issueEstimate,
  issueInvoice,
  listAllocations,
  listEstimates,
  listInvoices,
  listPayments,
  newIdempotencyKey,
  PAYMENT_METHODS,
  recordPayment,
  voidInvoice,
  type Allocation,
  type Estimate,
  type Invoice,
  type Payment,
  type PaymentMethod,
} from "../../lib/billingApi";
import { fmtWhen, statusLabel } from "../../lib/format";
import { hasPerm } from "../../lib/nav";
import { listPatients, type Patient } from "../../lib/patientsApi";
import { useSession } from "../../lib/session";
import { CreditNotesPanel } from "./CreditNotesPanel";
import { RefundsPanel } from "./RefundsPanel";

type HubTab = "estimates" | "invoices" | "payments" | "dues" | "refunds" | "credits";

const ESTIMATE_STATUSES = [
  { value: "", label: "All statuses" },
  { value: "draft", label: "Draft" },
  { value: "issued", label: "Issued" },
  { value: "converted", label: "Converted" },
  { value: "expired", label: "Expired" },
  { value: "cancelled", label: "Cancelled" },
];

const INVOICE_STATUSES = [
  { value: "", label: "All statuses" },
  { value: "draft", label: "Draft" },
  { value: "issued", label: "Issued" },
  { value: "partially_paid", label: "Partially paid" },
  { value: "paid", label: "Paid" },
  { value: "voided", label: "Voided" },
];

function shortId(id: string): string {
  return id.slice(0, 8);
}

function invoiceDocLabel(inv: Invoice): string {
  const num = inv.doc_number != null ? String(inv.doc_number) : "—";
  return inv.financial_year ? `${num} / FY ${inv.financial_year}` : num;
}

function isPastDueDate(dueDate: string | null): boolean {
  if (!dueDate) return false;
  const d = new Date(dueDate.length <= 10 ? `${dueDate}T00:00:00` : dueDate);
  if (Number.isNaN(d.getTime())) return false;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  d.setHours(0, 0, 0, 0);
  return d.getTime() < today.getTime();
}

function handleApiError(
  e: unknown,
  onSessionExpired: () => void,
  setError: (msg: string) => void,
  fallback: string,
) {
  const msg = String(e);
  if (msg.includes("session_expired")) onSessionExpired();
  else if (msg.includes("forbidden")) setError("You do not have permission for this action.");
  else setError(msg.includes("Error:") ? msg : fallback);
}

function EstimateDetailPanel({
  estimate,
  loading,
  canCreate,
  onOpenPatient,
  onIssue,
  onCancel,
  onExpire,
  onConvert,
  issueOpen,
  setIssueOpen,
  cancelOpen,
  setCancelOpen,
  expireOpen,
  setExpireOpen,
  convertOpen,
  setConvertOpen,
  busy,
}: {
  estimate: Estimate | null;
  loading: boolean;
  canCreate: boolean;
  onOpenPatient: (id: string) => void;
  onIssue: () => void;
  onCancel: () => void;
  onExpire: () => void;
  onConvert: () => void;
  issueOpen: boolean;
  setIssueOpen: (v: boolean) => void;
  cancelOpen: boolean;
  setCancelOpen: (v: boolean) => void;
  expireOpen: boolean;
  setExpireOpen: (v: boolean) => void;
  convertOpen: boolean;
  setConvertOpen: (v: boolean) => void;
  busy: boolean;
}) {
  if (loading) return <LoadingState label="Loading estimate" />;
  if (!estimate) {
    return (
      <EmptyState title="No estimate selected">
        Select an estimate from the list to view lines and actions.
      </EmptyState>
    );
  }

  const convertible = canConvertEstimate(estimate.status);
  const issuable = canIssueEstimate(estimate.status);

  return (
    <Card title={`Estimate ${shortId(estimate.id)}`}>
      <dl className="hos-dl">
        <div>
          <dt>Status</dt>
          <dd>
            <Status value={estimate.status} />
          </dd>
        </div>
        <div>
          <dt>Patient</dt>
          <dd>
            <button
              type="button"
              className="hos-link-btn"
              onClick={() => onOpenPatient(estimate.patient_id)}
            >
              {shortId(estimate.patient_id)}
            </button>
          </dd>
        </div>
        <div>
          <dt>Valid until</dt>
          <dd>{fmtWhen(estimate.valid_until)}</dd>
        </div>
      </dl>

      <FinancialSummary
        currency={estimate.currency}
        rows={[
          { label: "Subtotal", amount: estimate.subtotal },
          { label: "Tax", amount: estimate.tax_total },
        ]}
        total={{ label: "Grand total", amount: estimate.grand_total }}
      />

      <Table
        columns={
          <>
            <Th>Description</Th>
            <Th>Line total</Th>
          </>
        }
      >
        {estimate.lines.map((line) => (
          <tr key={line.id}>
            <Td>{line.description}</Td>
            <Td>
              <MoneyDisplay amount={line.line_total} currency={estimate.currency} />
            </Td>
          </tr>
        ))}
      </Table>

      {canCreate && (
        <div className="hos-toolbar-row">
          {issuable && (
            <Button type="button" size="sm" onClick={() => setIssueOpen(true)}>
              Issue
            </Button>
          )}
          {estimate.status === "draft" || estimate.status === "issued" ? (
            <>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => setCancelOpen(true)}
              >
                Cancel
              </Button>
              {estimate.status === "issued" && (
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => setExpireOpen(true)}
                >
                  Expire
                </Button>
              )}
            </>
          ) : null}
          {convertible && (
            <Button type="button" size="sm" onClick={() => setConvertOpen(true)}>
              Convert to invoice
            </Button>
          )}
        </div>
      )}

      {convertible && (
        <p className="hos-caption">
          Convert produces a <strong>draft</strong> invoice. Issue the invoice separately if you
          have invoice.issue permission.
        </p>
      )}

      <ConfirmDialog
        open={issueOpen}
        onOpenChange={setIssueOpen}
        title="Issue this estimate?"
        confirmLabel="Issue"
        pending={busy}
        onConfirm={onIssue}
      >
        <FinancialSummary
          currency={estimate.currency}
          rows={[
            { label: "Subtotal", amount: estimate.subtotal },
            { label: "Tax", amount: estimate.tax_total },
          ]}
          total={{ label: "Grand total", amount: estimate.grand_total }}
        />
      </ConfirmDialog>

      <ConfirmDialog
        open={cancelOpen}
        onOpenChange={setCancelOpen}
        title="Cancel estimate?"
        confirmLabel="Cancel estimate"
        pending={busy}
        onConfirm={onCancel}
      >
        This marks the estimate cancelled and cannot be undone.
      </ConfirmDialog>

      <ConfirmDialog
        open={expireOpen}
        onOpenChange={setExpireOpen}
        title="Expire estimate?"
        confirmLabel="Expire"
        pending={busy}
        onConfirm={onExpire}
      >
        Marks the estimate expired when it is no longer valid.
      </ConfirmDialog>

      <ConfirmDialog
        open={convertOpen}
        onOpenChange={setConvertOpen}
        title="Convert to invoice?"
        confirmLabel="Convert"
        pending={busy}
        onConfirm={onConvert}
      >
        Creates a draft invoice from this estimate. You must issue the invoice separately to
        finalize numbering.
      </ConfirmDialog>
    </Card>
  );
}

function InvoiceDetailPanel({
  invoice,
  balance,
  loading,
  canIssue,
  canPay,
  patientPayments,
  allocInputs,
  setAllocInputs,
  payMethod,
  setPayMethod,
  payAmount,
  setPayAmount,
  payRef,
  setPayRef,
  voidOpen,
  setVoidOpen,
  voidReason,
  setVoidReason,
  busyPay,
  busyAlloc,
  busyIssue,
  busyVoid,
  onOpenPatient,
  onIssue,
  onVoid,
  onRecordPayment,
  onAllocate,
  onRefreshBalance,
}: {
  invoice: Invoice | null;
  balance: import("../../lib/billingApi").InvoiceBalance | null;
  loading: boolean;
  canIssue: boolean;
  canPay: boolean;
  patientPayments: Payment[];
  allocInputs: Record<string, string>;
  setAllocInputs: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  payMethod: PaymentMethod;
  setPayMethod: (m: PaymentMethod) => void;
  payAmount: string;
  setPayAmount: (v: string) => void;
  payRef: string;
  setPayRef: (v: string) => void;
  voidOpen: boolean;
  setVoidOpen: (v: boolean) => void;
  voidReason: string;
  setVoidReason: (v: string) => void;
  busyPay: boolean;
  busyAlloc: boolean;
  busyIssue: boolean;
  busyVoid: boolean;
  onOpenPatient: (id: string) => void;
  onIssue: () => void;
  onVoid: () => void;
  onRecordPayment: (e: FormEvent) => void;
  onAllocate: (paymentId: string) => void;
  onRefreshBalance: () => void;
}) {
  if (loading) return <LoadingState label="Loading invoice" />;
  if (!invoice) {
    return (
      <EmptyState title="No invoice selected">
        Select an invoice to view balances, lines, and payment actions.
      </EmptyState>
    );
  }

  const outstanding =
    balance?.outstanding_amount ?? invoice.outstanding_amount;
  const allocated = balance?.allocated_amount ?? invoice.allocated_amount;
  const showPay =
    canPay &&
    Number(outstanding) > 0 &&
    invoice.status !== "voided" &&
    invoice.status !== "draft";

  return (
    <Card title={`Invoice ${invoiceDocLabel(invoice)}`}>
      <dl className="hos-dl">
        <div>
          <dt>Status</dt>
          <dd>
            <Status value={invoice.status} />
          </dd>
        </div>
        <div>
          <dt>Patient</dt>
          <dd>
            <button
              type="button"
              className="hos-link-btn"
              onClick={() => onOpenPatient(invoice.patient_id)}
            >
              {shortId(invoice.patient_id)}
            </button>
          </dd>
        </div>
        <div>
          <dt>Due date</dt>
          <dd>
            {fmtWhen(invoice.due_date)}
            {isPastDueDate(invoice.due_date) && (
              <span className="hos-caption"> · past due date</span>
            )}
          </dd>
        </div>
      </dl>

      <FinancialSummary
        currency={invoice.currency}
        rows={[
          { label: "Subtotal", amount: invoice.subtotal },
          { label: "Tax", amount: invoice.tax_total },
          { label: "Allocated", amount: allocated },
          { label: "Outstanding", amount: outstanding },
        ]}
        total={{ label: "Grand total", amount: invoice.grand_total }}
      />

      <Table
        columns={
          <>
            <Th>Description</Th>
            <Th>Line total</Th>
          </>
        }
      >
        {invoice.lines.map((line) => (
          <tr key={line.id}>
            <Td>{line.description}</Td>
            <Td>
              <MoneyDisplay amount={line.line_total} currency={invoice.currency} />
            </Td>
          </tr>
        ))}
      </Table>

      <div className="hos-toolbar-row">
        {canIssue && invoice.status === "draft" && (
          <Button type="button" size="sm" onClick={onIssue} disabled={busyIssue} loading={busyIssue}>
            Issue invoice
          </Button>
        )}
        {canIssue && invoice.status !== "voided" && invoice.status !== "draft" && (
          <Button type="button" size="sm" variant="secondary" onClick={() => setVoidOpen(true)}>
            Void
          </Button>
        )}
        <Button type="button" size="sm" variant="secondary" onClick={onRefreshBalance}>
          Refresh balance
        </Button>
      </div>

      {showPay && (
        <Card title="Record payment">
          <form onSubmit={onRecordPayment}>
            <Field label="Method" htmlFor="inv-pay-method">
              {({ describedBy }) => (
                <Select
                  id="inv-pay-method"
                  aria-describedby={describedBy}
                  value={payMethod}
                  onChange={(ev) => setPayMethod(ev.target.value as PaymentMethod)}
                  options={PAYMENT_METHODS}
                />
              )}
            </Field>
            <Field label="Amount" htmlFor="inv-pay-amt">
              {({ describedBy }) => (
                <Input
                  id="inv-pay-amt"
                  aria-describedby={describedBy}
                  value={payAmount}
                  onChange={(ev) => setPayAmount(ev.target.value)}
                  inputMode="decimal"
                  required
                />
              )}
            </Field>
            <Field label="Reference (optional)" htmlFor="inv-pay-ref">
              {({ describedBy }) => (
                <Input
                  id="inv-pay-ref"
                  aria-describedby={describedBy}
                  value={payRef}
                  onChange={(ev) => setPayRef(ev.target.value)}
                  autoComplete="off"
                />
              )}
            </Field>
            <Button type="submit" disabled={busyPay} loading={busyPay}>
              Record payment
            </Button>
          </form>
        </Card>
      )}

      {canPay && patientPayments.length > 0 && Number(outstanding) > 0 && (
        <Card title="Allocate unallocated payments">
          {patientPayments.map((p) => (
            <div key={p.id} className="hos-toolbar-row">
              <span className="hos-caption">
                {statusLabel(p.method)} · unallocated{" "}
                <MoneyDisplay amount={p.unallocated_amount} currency={p.currency} />
              </span>
              <Field label="Allocate" htmlFor={`alloc-${p.id}`}>
                {({ describedBy }) => (
                  <Input
                    id={`alloc-${p.id}`}
                    aria-describedby={describedBy}
                    value={allocInputs[p.id] ?? ""}
                    onChange={(ev) =>
                      setAllocInputs((prev) => ({ ...prev, [p.id]: ev.target.value }))
                    }
                    inputMode="decimal"
                  />
                )}
              </Field>
              <Button
                type="button"
                size="sm"
                disabled={busyAlloc}
                loading={busyAlloc}
                onClick={() => onAllocate(p.id)}
              >
                Allocate
              </Button>
            </div>
          ))}
        </Card>
      )}

      <ConfirmDialog
        open={voidOpen}
        onOpenChange={setVoidOpen}
        title="Void invoice?"
        confirmLabel="Void"
        pending={busyVoid}
        onConfirm={onVoid}
      >
        <Field label="Reason" htmlFor="void-reason">
          {({ describedBy }) => (
            <Input
              id="void-reason"
              aria-describedby={describedBy}
              value={voidReason}
              onChange={(ev) => setVoidReason(ev.target.value)}
              required
            />
          )}
        </Field>
      </ConfirmDialog>
    </Card>
  );
}

function PaymentDetailPanel({
  payment,
  allocations,
  loading,
  canPay,
  eligibleInvoices,
  allocToInvoice,
  setAllocToInvoice,
  busyAlloc,
  onAllocateToInvoice,
}: {
  payment: Payment | null;
  allocations: Allocation[];
  loading: boolean;
  canPay: boolean;
  eligibleInvoices: Invoice[];
  allocToInvoice: Record<string, string>;
  setAllocToInvoice: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  busyAlloc: boolean;
  onAllocateToInvoice: (invoiceId: string) => void;
}) {
  if (loading) return <LoadingState label="Loading payment" />;
  if (!payment) {
    return (
      <EmptyState title="No payment selected">
        Select a payment to view allocations or allocate to invoices.
      </EmptyState>
    );
  }

  return (
    <Card title={`Payment ${shortId(payment.id)}`}>
      <dl className="hos-dl">
        <div>
          <dt>Status</dt>
          <dd>
            <Status value={payment.status} />
          </dd>
        </div>
        <div>
          <dt>Method</dt>
          <dd>{statusLabel(payment.method)}</dd>
        </div>
        <div>
          <dt>Received</dt>
          <dd>{fmtWhen(payment.received_at)}</dd>
        </div>
        <div>
          <dt>Amount</dt>
          <dd>
            <MoneyDisplay amount={payment.amount} currency={payment.currency} />
          </dd>
        </div>
        <div>
          <dt>Unallocated</dt>
          <dd>
            <MoneyDisplay amount={payment.unallocated_amount} currency={payment.currency} />
          </dd>
        </div>
      </dl>

      <h3 className="hos-caption">Allocations</h3>
      {allocations.length === 0 ? (
        <p className="hos-muted">No allocations yet.</p>
      ) : (
        <Table
          columns={
            <>
              <Th>Invoice</Th>
              <Th>Amount</Th>
            </>
          }
        >
          {allocations.map((a) => (
            <tr key={a.id}>
              <Td>{shortId(a.invoice_id)}</Td>
              <Td>
                <MoneyDisplay amount={a.amount} currency={payment.currency} />
              </Td>
            </tr>
          ))}
        </Table>
      )}

      {canPay && Number(payment.unallocated_amount) > 0 && eligibleInvoices.length > 0 && (
        <Card title="Allocate to invoice">
          {eligibleInvoices.map((inv) => (
            <div key={inv.id} className="hos-toolbar-row">
              <span className="hos-caption">
                {invoiceDocLabel(inv)} · outstanding{" "}
                <MoneyDisplay amount={inv.outstanding_amount} currency={inv.currency} />
              </span>
              <Field label="Amount" htmlFor={`pay-alloc-${inv.id}`}>
                {({ describedBy }) => (
                  <Input
                    id={`pay-alloc-${inv.id}`}
                    aria-describedby={describedBy}
                    value={allocToInvoice[inv.id] ?? ""}
                    onChange={(ev) =>
                      setAllocToInvoice((prev) => ({ ...prev, [inv.id]: ev.target.value }))
                    }
                    inputMode="decimal"
                  />
                )}
              </Field>
              <Button
                type="button"
                size="sm"
                disabled={busyAlloc}
                loading={busyAlloc}
                onClick={() => onAllocateToInvoice(inv.id)}
              >
                Allocate
              </Button>
            </div>
          ))}
        </Card>
      )}
    </Card>
  );
}

export function BillingHub({
  initialTab,
  initialEstimateId,
  initialInvoiceId,
  initialPatientId,
  onOpenPatient,
  onSessionExpired,
}: {
  initialTab?: HubTab;
  initialEstimateId?: string | null;
  initialInvoiceId?: string | null;
  initialPatientId?: string | null;
  onOpenPatient: (id: string) => void;
  onSessionExpired: () => void;
}) {
  const { tenant, workspace } = useSession();
  const canRead = hasPerm(workspace?.permissions, "billing.read");
  const canCreate = hasPerm(workspace?.permissions, "billing.create");
  const canIssueInv = hasPerm(workspace?.permissions, "invoice.issue");
  const canRecordPay = hasPerm(workspace?.permissions, "payment.record");
  const canRefund = hasPerm(workspace?.permissions, "billing.refund");

  const [tab, setTab] = useState<HubTab>(initialTab ?? "estimates");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const [patientFilterId, setPatientFilterId] = useState(initialPatientId ?? "");
  const [patientQ, setPatientQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [patientOptions, setPatientOptions] = useState<Patient[]>([]);

  const [estimateStatus, setEstimateStatus] = useState("");
  const [invoiceStatus, setInvoiceStatus] = useState("");
  const [estimates, setEstimates] = useState<Estimate[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [duesRows, setDuesRows] = useState<Invoice[]>([]);

  const [selectedEstimateId, setSelectedEstimateId] = useState<string | null>(
    initialEstimateId ?? null,
  );
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string | null>(
    initialInvoiceId ?? null,
  );
  const [selectedPaymentId, setSelectedPaymentId] = useState<string | null>(null);

  const [estimateDetail, setEstimateDetail] = useState<Estimate | null>(null);
  const [invoiceDetail, setInvoiceDetail] = useState<Invoice | null>(null);
  const [invoiceBalance, setInvoiceBalance] =
    useState<import("../../lib/billingApi").InvoiceBalance | null>(null);
  const [paymentDetail, setPaymentDetail] = useState<Payment | null>(null);
  const [paymentAllocations, setPaymentAllocations] = useState<Allocation[]>([]);

  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const [locations, setLocations] = useState<Array<{ id: string; name: string }>>([]);

  const [estIssueOpen, setEstIssueOpen] = useState(false);
  const [estCancelOpen, setEstCancelOpen] = useState(false);
  const [estExpireOpen, setEstExpireOpen] = useState(false);
  const [estConvertOpen, setEstConvertOpen] = useState(false);
  const [estBusy, setEstBusy] = useState(false);

  const [invVoidOpen, setInvVoidOpen] = useState(false);
  const [voidReason, setVoidReason] = useState("");
  const [invBusyIssue, setInvBusyIssue] = useState(false);
  const [invBusyVoid, setInvBusyVoid] = useState(false);

  const [invPayMethod, setInvPayMethod] = useState<PaymentMethod>("cash");
  const [invPayAmount, setInvPayAmount] = useState("");
  const [invPayRef, setInvPayRef] = useState("");
  const [invPayBusy, setInvPayBusy] = useState(false);
  const payIdempotencyRef = useRef<string | null>(null);

  const [invAllocInputs, setInvAllocInputs] = useState<Record<string, string>>({});
  const [invAllocBusy, setInvAllocBusy] = useState(false);
  const invAllocKeyRef = useRef<string | null>(null);
  const [invoicePatientPayments, setInvoicePatientPayments] = useState<Payment[]>([]);

  const [payTabPatientId, setPayTabPatientId] = useState(initialPatientId ?? "");
  const [payTabPatientQ, setPayTabPatientQ] = useState("");
  const [payTabDebouncedQ, setPayTabDebouncedQ] = useState("");
  const [payTabPatients, setPayTabPatients] = useState<Patient[]>([]);
  const [payTabLocationId, setPayTabLocationId] = useState("");
  const [payTabMethod, setPayTabMethod] = useState<PaymentMethod>("cash");
  const [payTabAmount, setPayTabAmount] = useState("");
  const [payTabRef, setPayTabRef] = useState("");
  const [payRecordOpen, setPayRecordOpen] = useState(false);
  const [payRecordBusy, setPayRecordBusy] = useState(false);
  const payRecordKeyRef = useRef<string | null>(null);

  const [payAllocInputs, setPayAllocInputs] = useState<Record<string, string>>({});
  const [payDetailAllocBusy, setPayDetailAllocBusy] = useState(false);
  const payDetailAllocKeyRef = useRef<string | null>(null);
  const [payEligibleInvoices, setPayEligibleInvoices] = useState<Invoice[]>([]);

  const convertKeyRef = useRef<string | null>(null);

  useEffect(() => {
    const id = window.setTimeout(() => setDebouncedQ(patientQ.trim()), 250);
    return () => window.clearTimeout(id);
  }, [patientQ]);

  useEffect(() => {
    const id = window.setTimeout(() => setPayTabDebouncedQ(payTabPatientQ.trim()), 250);
    return () => window.clearTimeout(id);
  }, [payTabPatientQ]);

  useEffect(() => {
    setSelectedEstimateId(null);
    setSelectedInvoiceId(null);
    setSelectedPaymentId(null);
  }, [patientFilterId]);

  useEffect(() => {
    if (initialPatientId) setPatientFilterId(initialPatientId);
  }, [initialPatientId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!tenant || !hasPerm(workspace?.permissions, "patient.read")) return;
      try {
        const data = await listPatients(tenant.id, {
          q: debouncedQ || undefined,
          limit: 30,
          activeOnly: true,
        });
        if (!cancelled) setPatientOptions(data);
      } catch {
        if (!cancelled) setPatientOptions([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenant?.id, debouncedQ, workspace?.permissions]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!tenant || !hasPerm(workspace?.permissions, "patient.read")) return;
      try {
        const data = await listPatients(tenant.id, {
          q: payTabDebouncedQ || undefined,
          limit: 30,
          activeOnly: true,
        });
        if (!cancelled) setPayTabPatients(data);
      } catch {
        if (!cancelled) setPayTabPatients([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenant?.id, payTabDebouncedQ, workspace?.permissions]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!tenant) return;
      try {
        const locs = await fetchTenantLocations(tenant.id);
        if (cancelled) return;
        setLocations(locs);
        if (locs[0] && !payTabLocationId) setPayTabLocationId(locs[0].id);
      } catch (e) {
        handleApiError(e, onSessionExpired, setError, "Could not load locations.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenant?.id, onSessionExpired, payTabLocationId]);

  const reloadEstimates = useCallback(async () => {
    if (!tenant) return;
    setLoadingList(true);
    setError(null);
    try {
      const data = await listEstimates(tenant.id, {
        patientId: patientFilterId || undefined,
        status: estimateStatus || undefined,
        limit: 50,
      });
      setEstimates(data);
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Failed to load estimates.");
    } finally {
      setLoadingList(false);
    }
  }, [tenant, patientFilterId, estimateStatus, onSessionExpired]);

  const reloadInvoices = useCallback(async () => {
    if (!tenant) return;
    setLoadingList(true);
    setError(null);
    try {
      const data = await listInvoices(tenant.id, {
        patientId: patientFilterId || undefined,
        status: invoiceStatus || undefined,
        limit: 50,
      });
      setInvoices(data);
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Failed to load invoices.");
    } finally {
      setLoadingList(false);
    }
  }, [tenant, patientFilterId, invoiceStatus, onSessionExpired]);

  const reloadPayments = useCallback(async () => {
    if (!tenant) return;
    setLoadingList(true);
    setError(null);
    try {
      const data = await listPayments(tenant.id, {
        patientId: patientFilterId || undefined,
        limit: 50,
      });
      setPayments(data);
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Failed to load payments.");
    } finally {
      setLoadingList(false);
    }
  }, [tenant, patientFilterId, onSessionExpired]);

  const reloadDues = useCallback(async () => {
    if (!tenant) return;
    setLoadingList(true);
    setError(null);
    try {
      const data = await listInvoices(tenant.id, {
        patientId: patientFilterId || undefined,
        limit: 100,
      });
      setDuesRows(data.filter(invoiceHasOutstanding));
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Failed to load outstanding invoices.");
    } finally {
      setLoadingList(false);
    }
  }, [tenant, patientFilterId, onSessionExpired]);

  useEffect(() => {
    if (!tenant || !canRead) return;
    if (tab === "estimates") void reloadEstimates();
    else if (tab === "invoices") void reloadInvoices();
    else if (tab === "payments") void reloadPayments();
    else void reloadDues();
  }, [tab, tenant, canRead, reloadEstimates, reloadInvoices, reloadPayments, reloadDues]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!tenant || !selectedEstimateId) {
        setEstimateDetail(null);
        return;
      }
      setLoadingDetail(true);
      try {
        const est = await getEstimate(tenant.id, selectedEstimateId);
        if (!cancelled) setEstimateDetail(est);
      } catch (e) {
        handleApiError(e, onSessionExpired, setError, "Could not load estimate.");
        if (!cancelled) setEstimateDetail(null);
      } finally {
        if (!cancelled) setLoadingDetail(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenant, selectedEstimateId, onSessionExpired]);

  const refreshInvoiceDetail = useCallback(
    async (invoiceId: string) => {
      if (!tenant) return;
      setLoadingDetail(true);
      try {
        const [inv, bal] = await Promise.all([
          getInvoice(tenant.id, invoiceId),
          getInvoiceBalance(tenant.id, invoiceId),
        ]);
        setInvoiceDetail(inv);
        setInvoiceBalance(bal);
        if (canRecordPay) {
          const pays = await listPayments(tenant.id, {
            patientId: inv.patient_id,
            limit: 50,
          });
          setInvoicePatientPayments(
            pays.filter((p) => Number(p.unallocated_amount) > 0),
          );
        }
      } catch (e) {
        handleApiError(e, onSessionExpired, setError, "Could not load invoice.");
        setInvoiceDetail(null);
        setInvoiceBalance(null);
      } finally {
        setLoadingDetail(false);
      }
    },
    [tenant, canRecordPay, onSessionExpired],
  );

  useEffect(() => {
    if (!tenant || !selectedInvoiceId) {
      setInvoiceDetail(null);
      setInvoiceBalance(null);
      setInvoicePatientPayments([]);
      return;
    }
    void refreshInvoiceDetail(selectedInvoiceId);
  }, [tenant, selectedInvoiceId, refreshInvoiceDetail]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!tenant || !selectedPaymentId) {
        setPaymentDetail(null);
        setPaymentAllocations([]);
        setPayEligibleInvoices([]);
        return;
      }
      setLoadingDetail(true);
      try {
        const pay = await getPayment(tenant.id, selectedPaymentId);
        const allocs = await listAllocations(tenant.id, selectedPaymentId);
        let eligible: Invoice[] = [];
        if (canRecordPay && Number(pay.unallocated_amount) > 0) {
          const invs = await listInvoices(tenant.id, {
            patientId: pay.patient_id,
            limit: 50,
          });
          eligible = invs.filter(invoiceHasOutstanding);
        }
        if (!cancelled) {
          setPaymentDetail(pay);
          setPaymentAllocations(allocs);
          setPayEligibleInvoices(eligible);
        }
      } catch (e) {
        handleApiError(e, onSessionExpired, setError, "Could not load payment.");
        if (!cancelled) {
          setPaymentDetail(null);
          setPaymentAllocations([]);
        }
      } finally {
        if (!cancelled) setLoadingDetail(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenant, selectedPaymentId, canRecordPay, onSessionExpired]);

  const patientSelectOptions = useMemo(
    () => [
      { value: "", label: "All patients" },
      ...patientOptions.map((p) => ({
        value: p.id,
        label: `${p.display_name} (${shortId(p.id)})`,
      })),
      ...(patientFilterId &&
      !patientOptions.some((p) => p.id === patientFilterId)
        ? [{ value: patientFilterId, label: `Selected (${shortId(patientFilterId)})` }]
        : []),
    ],
    [patientOptions, patientFilterId],
  );

  const payPatientOptions = useMemo(
    () => [
      { value: "", label: "Select patient" },
      ...payTabPatients.map((p) => ({
        value: p.id,
        label: `${p.display_name} (${shortId(p.id)})`,
      })),
      ...(payTabPatientId &&
      !payTabPatients.some((p) => p.id === payTabPatientId)
        ? [{ value: payTabPatientId, label: `Selected (${shortId(payTabPatientId)})` }]
        : []),
    ],
    [payTabPatients, payTabPatientId],
  );

  if (!canRead) {
    return (
      <Alert tone="danger" title="Billing">
        You need billing.read permission to view this workspace.
      </Alert>
    );
  }

  async function runEstimateAction(
    action: "issue" | "cancel" | "expire" | "convert",
  ) {
    if (!tenant || !estimateDetail) return;
    setEstBusy(true);
    setError(null);
    try {
      if (action === "issue") {
        const updated = await issueEstimate(tenant.id, estimateDetail.id);
        setEstimateDetail(updated);
        setEstIssueOpen(false);
        setInfo("Estimate issued.");
      } else if (action === "cancel") {
        const updated = await cancelEstimate(tenant.id, estimateDetail.id);
        setEstimateDetail(updated);
        setEstCancelOpen(false);
        setInfo("Estimate cancelled.");
      } else if (action === "expire") {
        const updated = await expireEstimate(tenant.id, estimateDetail.id);
        setEstimateDetail(updated);
        setEstExpireOpen(false);
        setInfo("Estimate expired.");
      } else if (action === "convert") {
        if (!convertKeyRef.current) {
          convertKeyRef.current = newIdempotencyKey("cvt");
        }
        const inv = await convertEstimate(tenant.id, estimateDetail.id, {
          idempotency_key: convertKeyRef.current,
        });
        convertKeyRef.current = null;
        setEstConvertOpen(false);
        setInfo("Draft invoice created from estimate.");
        setTab("invoices");
        setSelectedInvoiceId(inv.id);
        setSelectedEstimateId(null);
        void reloadInvoices();
      }
      void reloadEstimates();
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Estimate action failed.");
      convertKeyRef.current = null;
    } finally {
      setEstBusy(false);
    }
  }

  async function onIssueInvoice() {
    if (!tenant || !invoiceDetail) return;
    setInvBusyIssue(true);
    setError(null);
    try {
      const updated = await issueInvoice(tenant.id, invoiceDetail.id);
      setInvoiceDetail(updated);
      setInfo("Invoice issued.");
      void reloadInvoices();
      const bal = await getInvoiceBalance(tenant.id, invoiceDetail.id);
      setInvoiceBalance(bal);
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Could not issue invoice.");
    } finally {
      setInvBusyIssue(false);
    }
  }

  async function onVoidInvoice() {
    if (!tenant || !invoiceDetail) return;
    setInvBusyVoid(true);
    setError(null);
    try {
      const updated = await voidInvoice(tenant.id, invoiceDetail.id, voidReason.trim());
      setInvoiceDetail(updated);
      setInvVoidOpen(false);
      setVoidReason("");
      setInfo("Invoice voided.");
      void reloadInvoices();
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Could not void invoice.");
    } finally {
      setInvBusyVoid(false);
    }
  }

  async function onInvoiceRecordPayment(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !invoiceDetail || !canRecordPay) return;
    if (!payIdempotencyRef.current) {
      payIdempotencyRef.current = newIdempotencyKey("pay");
    }
    setInvPayBusy(true);
    setError(null);
    try {
      await recordPayment(tenant.id, {
        patient_id: invoiceDetail.patient_id,
        location_id: invoiceDetail.location_id,
        method: invPayMethod,
        amount: invPayAmount.trim(),
        provider_ref: invPayRef.trim() || null,
        idempotency_key: payIdempotencyRef.current,
      });
      payIdempotencyRef.current = null;
      setInvPayAmount("");
      setInvPayRef("");
      setInfo("Payment recorded. Allocate to this invoice below if needed.");
      void reloadPayments();
      await refreshInvoiceDetail(invoiceDetail.id);
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Payment failed.");
      payIdempotencyRef.current = null;
    } finally {
      setInvPayBusy(false);
    }
  }

  async function onInvoiceAllocate(paymentId: string) {
    if (!tenant || !invoiceDetail) return;
    const amount = (invAllocInputs[paymentId] ?? "").trim();
    if (!amount) return;
    if (!invAllocKeyRef.current) {
      invAllocKeyRef.current = newIdempotencyKey("alloc");
    }
    setInvAllocBusy(true);
    setError(null);
    try {
      await allocatePayment(
        tenant.id,
        paymentId,
        [{ invoice_id: invoiceDetail.id, amount }],
        invAllocKeyRef.current,
      );
      invAllocKeyRef.current = null;
      setInvAllocInputs((prev) => ({ ...prev, [paymentId]: "" }));
      setInfo("Payment allocated.");
      await refreshInvoiceDetail(invoiceDetail.id);
      void reloadPayments();
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Allocation failed.");
      invAllocKeyRef.current = null;
    } finally {
      setInvAllocBusy(false);
    }
  }

  function openRecordPaymentConfirm() {
    if (!payTabPatientId || !payTabLocationId || !payTabAmount.trim()) {
      setError("Patient, location, and amount are required.");
      return;
    }
    payRecordKeyRef.current = newIdempotencyKey("pay");
    setPayRecordOpen(true);
  }

  async function submitRecordPayment() {
    if (!tenant || !canRecordPay) return;
    const key = payRecordKeyRef.current ?? newIdempotencyKey("pay");
    setPayRecordBusy(true);
    setError(null);
    try {
      const created = await recordPayment(tenant.id, {
        patient_id: payTabPatientId,
        location_id: payTabLocationId,
        method: payTabMethod,
        amount: payTabAmount.trim(),
        provider_ref: payTabRef.trim() || null,
        idempotency_key: key,
      });
      payRecordKeyRef.current = null;
      setPayRecordOpen(false);
      setPayTabAmount("");
      setPayTabRef("");
      setInfo("Payment recorded.");
      setSelectedPaymentId(created.id);
      void reloadPayments();
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Payment failed.");
      payRecordKeyRef.current = null;
    } finally {
      setPayRecordBusy(false);
    }
  }

  async function onPayDetailAllocate(invoiceId: string) {
    if (!tenant || !paymentDetail) return;
    const amount = (payAllocInputs[invoiceId] ?? "").trim();
    if (!amount) return;
    if (!payDetailAllocKeyRef.current) {
      payDetailAllocKeyRef.current = newIdempotencyKey("alloc");
    }
    setPayDetailAllocBusy(true);
    setError(null);
    try {
      await allocatePayment(
        tenant.id,
        paymentDetail.id,
        [{ invoice_id: invoiceId, amount }],
        payDetailAllocKeyRef.current,
      );
      payDetailAllocKeyRef.current = null;
      setPayAllocInputs((prev) => ({ ...prev, [invoiceId]: "" }));
      setInfo("Allocated to invoice.");
      const [pay, allocs] = await Promise.all([
        getPayment(tenant.id, paymentDetail.id),
        listAllocations(tenant.id, paymentDetail.id),
      ]);
      setPaymentDetail(pay);
      setPaymentAllocations(allocs);
      void reloadPayments();
      void reloadInvoices();
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Allocation failed.");
      payDetailAllocKeyRef.current = null;
    } finally {
      setPayDetailAllocBusy(false);
    }
  }

  function collectPaymentFromDues(inv: Invoice) {
    setTab("invoices");
    setSelectedInvoiceId(inv.id);
  }

  return (
    <div className="hos-billing">
      <header className="hos-module-header">
        <h1>Billing</h1>
        <p className="hos-muted">
          Estimates · invoices · payments · outstanding · refunds · credit notes
        </p>
      </header>

      {error && (
        <Alert tone="danger" title="Billing">
          {error}
        </Alert>
      )}
      {info && (
        <Alert tone="success" title="Updated">
          {info}
        </Alert>
      )}

      <Tabs value={tab} onValueChange={(v) => setTab(v as HubTab)}>
        <TabsList>
          <TabsTrigger value="estimates">Estimates</TabsTrigger>
          <TabsTrigger value="invoices">Invoices</TabsTrigger>
          <TabsTrigger value="payments">Payments</TabsTrigger>
          <TabsTrigger value="dues">Outstanding dues</TabsTrigger>
          <TabsTrigger value="refunds">Refunds</TabsTrigger>
          <TabsTrigger value="credits">Credit notes</TabsTrigger>
        </TabsList>

        <TabsContent value="estimates">
          <div className="hos-toolbar-row">
            <Field label="Status" htmlFor="est-status">
              {({ describedBy }) => (
                <Select
                  id="est-status"
                  aria-describedby={describedBy}
                  value={estimateStatus}
                  onChange={(ev) => setEstimateStatus(ev.target.value)}
                  options={ESTIMATE_STATUSES}
                />
              )}
            </Field>
            <Field label="Patient search" htmlFor="est-pq">
              {({ describedBy }) => (
                <Input
                  id="est-pq"
                  aria-describedby={describedBy}
                  value={patientQ}
                  onChange={(ev) => setPatientQ(ev.target.value)}
                  placeholder="Search patients"
                />
              )}
            </Field>
            <Field label="Patient filter" htmlFor="est-patient">
              {({ describedBy }) => (
                <Select
                  id="est-patient"
                  aria-describedby={describedBy}
                  value={patientFilterId}
                  onChange={(ev) => setPatientFilterId(ev.target.value)}
                  options={patientSelectOptions}
                />
              )}
            </Field>
          </div>
          <div className="hos-billing-layout">
            <Card title="Estimates">
              {loadingList && estimates.length === 0 ? (
                <LoadingState label="Loading estimates" />
              ) : estimates.length === 0 ? (
                <EmptyState title="No estimates">No estimates match filters.</EmptyState>
              ) : (
                <Table
                  columns={
                    <>
                      <Th>Status</Th>
                      <Th>Total</Th>
                      <Th>Patient</Th>
                      <Th>Valid until</Th>
                      <Th>Open</Th>
                    </>
                  }
                >
                  {estimates.map((est) => (
                    <tr key={est.id}>
                      <Td>{statusLabel(est.status)}</Td>
                      <Td>
                        <MoneyDisplay amount={est.grand_total} currency={est.currency} />
                      </Td>
                      <Td>{shortId(est.patient_id)}</Td>
                      <Td>{fmtWhen(est.valid_until)}</Td>
                      <Td>
                        <button
                          type="button"
                          className="hos-link-btn"
                          onClick={() => setSelectedEstimateId(est.id)}
                        >
                          Open
                        </button>
                      </Td>
                    </tr>
                  ))}
                </Table>
              )}
            </Card>
            <EstimateDetailPanel
              estimate={estimateDetail}
              loading={loadingDetail && Boolean(selectedEstimateId)}
              canCreate={canCreate}
              onOpenPatient={onOpenPatient}
              onIssue={() => void runEstimateAction("issue")}
              onCancel={() => void runEstimateAction("cancel")}
              onExpire={() => void runEstimateAction("expire")}
              onConvert={() => void runEstimateAction("convert")}
              issueOpen={estIssueOpen}
              setIssueOpen={setEstIssueOpen}
              cancelOpen={estCancelOpen}
              setCancelOpen={setEstCancelOpen}
              expireOpen={estExpireOpen}
              setExpireOpen={setEstExpireOpen}
              convertOpen={estConvertOpen}
              setConvertOpen={setEstConvertOpen}
              busy={estBusy}
            />
          </div>
        </TabsContent>

        <TabsContent value="invoices">
          <div className="hos-toolbar-row">
            <Field label="Status" htmlFor="inv-status">
              {({ describedBy }) => (
                <Select
                  id="inv-status"
                  aria-describedby={describedBy}
                  value={invoiceStatus}
                  onChange={(ev) => setInvoiceStatus(ev.target.value)}
                  options={INVOICE_STATUSES}
                />
              )}
            </Field>
            <Field label="Patient filter" htmlFor="inv-patient">
              {({ describedBy }) => (
                <Select
                  id="inv-patient"
                  aria-describedby={describedBy}
                  value={patientFilterId}
                  onChange={(ev) => setPatientFilterId(ev.target.value)}
                  options={patientSelectOptions}
                />
              )}
            </Field>
          </div>
          <div className="hos-billing-layout">
            <Card title="Invoices">
              {loadingList && invoices.length === 0 ? (
                <LoadingState label="Loading invoices" />
              ) : invoices.length === 0 ? (
                <EmptyState title="No invoices">No invoices match filters.</EmptyState>
              ) : (
                <Table
                  columns={
                    <>
                      <Th>Doc / FY</Th>
                      <Th>Status</Th>
                      <Th>Total</Th>
                      <Th>Allocated</Th>
                      <Th>Outstanding</Th>
                      <Th>Open</Th>
                    </>
                  }
                >
                  {invoices.map((inv) => (
                    <tr key={inv.id}>
                      <Td>{invoiceDocLabel(inv)}</Td>
                      <Td>{statusLabel(inv.status)}</Td>
                      <Td>
                        <MoneyDisplay amount={inv.grand_total} currency={inv.currency} />
                      </Td>
                      <Td>
                        <MoneyDisplay amount={inv.allocated_amount} currency={inv.currency} />
                      </Td>
                      <Td>
                        <MoneyDisplay amount={inv.outstanding_amount} currency={inv.currency} />
                      </Td>
                      <Td>
                        <button
                          type="button"
                          className="hos-link-btn"
                          onClick={() => setSelectedInvoiceId(inv.id)}
                        >
                          Open
                        </button>
                      </Td>
                    </tr>
                  ))}
                </Table>
              )}
            </Card>
            <InvoiceDetailPanel
              invoice={invoiceDetail}
              balance={invoiceBalance}
              loading={loadingDetail && Boolean(selectedInvoiceId)}
              canIssue={canIssueInv}
              canPay={canRecordPay}
              patientPayments={invoicePatientPayments}
              allocInputs={invAllocInputs}
              setAllocInputs={setInvAllocInputs}
              payMethod={invPayMethod}
              setPayMethod={setInvPayMethod}
              payAmount={invPayAmount}
              setPayAmount={setInvPayAmount}
              payRef={invPayRef}
              setPayRef={setInvPayRef}
              voidOpen={invVoidOpen}
              setVoidOpen={setInvVoidOpen}
              voidReason={voidReason}
              setVoidReason={setVoidReason}
              busyPay={invPayBusy}
              busyAlloc={invAllocBusy}
              busyIssue={invBusyIssue}
              busyVoid={invBusyVoid}
              onOpenPatient={onOpenPatient}
              onIssue={() => void onIssueInvoice()}
              onVoid={() => void onVoidInvoice()}
              onRecordPayment={(ev) => void onInvoiceRecordPayment(ev)}
              onAllocate={(pid) => void onInvoiceAllocate(pid)}
              onRefreshBalance={() => {
                if (selectedInvoiceId) void refreshInvoiceDetail(selectedInvoiceId);
              }}
            />
          </div>
        </TabsContent>

        <TabsContent value="payments">
          <Card title="Record payment">
            <div className="hos-toolbar-row">
              <Field label="Search patient" htmlFor="pay-pq">
                {({ describedBy }) => (
                  <Input
                    id="pay-pq"
                    aria-describedby={describedBy}
                    value={payTabPatientQ}
                    onChange={(ev) => setPayTabPatientQ(ev.target.value)}
                  />
                )}
              </Field>
              <Field label="Patient" htmlFor="pay-patient">
                {({ describedBy }) => (
                  <Select
                    id="pay-patient"
                    aria-describedby={describedBy}
                    value={payTabPatientId}
                    onChange={(ev) => setPayTabPatientId(ev.target.value)}
                    options={payPatientOptions}
                  />
                )}
              </Field>
              <Field label="Location" htmlFor="pay-loc">
                {({ describedBy }) => (
                  <Select
                    id="pay-loc"
                    aria-describedby={describedBy}
                    value={payTabLocationId}
                    onChange={(ev) => setPayTabLocationId(ev.target.value)}
                    options={locations.map((l) => ({ value: l.id, label: l.name }))}
                  />
                )}
              </Field>
              <Field label="Method" htmlFor="pay-method">
                {({ describedBy }) => (
                  <Select
                    id="pay-method"
                    aria-describedby={describedBy}
                    value={payTabMethod}
                    onChange={(ev) => setPayTabMethod(ev.target.value as PaymentMethod)}
                    options={PAYMENT_METHODS}
                  />
                )}
              </Field>
              <Field label="Amount" htmlFor="pay-amt">
                {({ describedBy }) => (
                  <Input
                    id="pay-amt"
                    aria-describedby={describedBy}
                    value={payTabAmount}
                    onChange={(ev) => setPayTabAmount(ev.target.value)}
                    inputMode="decimal"
                  />
                )}
              </Field>
              <Field label="Reference" htmlFor="pay-ref">
                {({ describedBy }) => (
                  <Input
                    id="pay-ref"
                    aria-describedby={describedBy}
                    value={payTabRef}
                    onChange={(ev) => setPayTabRef(ev.target.value)}
                    autoComplete="off"
                  />
                )}
              </Field>
              {canRecordPay && (
                <Button type="button" onClick={openRecordPaymentConfirm}>
                  Record payment…
                </Button>
              )}
            </div>
          </Card>

          <div className="hos-billing-layout">
            <Card title="Payments">
              {loadingList && payments.length === 0 ? (
                <LoadingState label="Loading payments" />
              ) : payments.length === 0 ? (
                <EmptyState title="No payments">No payments match filters.</EmptyState>
              ) : (
                <Table
                  columns={
                    <>
                      <Th>Received</Th>
                      <Th>Method</Th>
                      <Th>Amount</Th>
                      <Th>Unallocated</Th>
                      <Th>Open</Th>
                    </>
                  }
                >
                  {payments.map((p) => (
                    <tr key={p.id}>
                      <Td>{fmtWhen(p.received_at)}</Td>
                      <Td>{statusLabel(p.method)}</Td>
                      <Td>
                        <MoneyDisplay amount={p.amount} currency={p.currency} />
                      </Td>
                      <Td>
                        <MoneyDisplay amount={p.unallocated_amount} currency={p.currency} />
                      </Td>
                      <Td>
                        <button
                          type="button"
                          className="hos-link-btn"
                          onClick={() => setSelectedPaymentId(p.id)}
                        >
                          Open
                        </button>
                      </Td>
                    </tr>
                  ))}
                </Table>
              )}
            </Card>
            <PaymentDetailPanel
              payment={paymentDetail}
              allocations={paymentAllocations}
              loading={loadingDetail && Boolean(selectedPaymentId)}
              canPay={canRecordPay}
              eligibleInvoices={payEligibleInvoices}
              allocToInvoice={payAllocInputs}
              setAllocToInvoice={setPayAllocInputs}
              busyAlloc={payDetailAllocBusy}
              onAllocateToInvoice={(invId) => void onPayDetailAllocate(invId)}
            />
          </div>

          <ConfirmDialog
            open={payRecordOpen}
            onOpenChange={setPayRecordOpen}
            title="Record payment?"
            confirmLabel="Record"
            pending={payRecordBusy}
            onConfirm={() => void submitRecordPayment()}
          >
            <p>
              Method {statusLabel(payTabMethod)} · amount {payTabAmount.trim() || "—"}
            </p>
          </ConfirmDialog>
        </TabsContent>

        <TabsContent value="dues">
          <p className="hos-caption">
            Built from invoice list (limit 100) filtered by outstanding balance — no dedicated AR
            aging API.
          </p>
          <div className="hos-billing-layout">
            <Card title="Outstanding dues">
              {loadingList && duesRows.length === 0 ? (
                <LoadingState label="Loading outstanding" />
              ) : duesRows.length === 0 ? (
                <EmptyState title="No outstanding balances">
                  No invoices with collectible outstanding amounts.
                </EmptyState>
              ) : (
                <Table
                  columns={
                    <>
                      <Th>Patient</Th>
                      <Th>Status</Th>
                      <Th>Total</Th>
                      <Th>Allocated</Th>
                      <Th>Outstanding</Th>
                      <Th>Due</Th>
                      <Th>Actions</Th>
                    </>
                  }
                >
                  {duesRows.map((inv) => (
                    <tr key={inv.id}>
                      <Td>
                        <button
                          type="button"
                          className="hos-link-btn"
                          onClick={() => onOpenPatient(inv.patient_id)}
                        >
                          {shortId(inv.patient_id)}
                        </button>
                      </Td>
                      <Td>{statusLabel(inv.status)}</Td>
                      <Td>
                        <MoneyDisplay amount={inv.grand_total} currency={inv.currency} />
                      </Td>
                      <Td>
                        <MoneyDisplay amount={inv.allocated_amount} currency={inv.currency} />
                      </Td>
                      <Td>
                        <MoneyDisplay amount={inv.outstanding_amount} currency={inv.currency} />
                      </Td>
                      <Td>
                        {fmtWhen(inv.due_date)}
                        {isPastDueDate(inv.due_date) && (
                          <span className="hos-caption"> · past due date</span>
                        )}
                      </Td>
                      <Td>
                        <div className="hos-inline-actions">
                          <button
                            type="button"
                            className="hos-link-btn"
                            onClick={() => {
                              setTab("invoices");
                              setSelectedInvoiceId(inv.id);
                            }}
                          >
                            Open invoice
                          </button>
                          {canRecordPay && (
                            <button
                              type="button"
                              className="hos-link-btn"
                              onClick={() => collectPaymentFromDues(inv)}
                            >
                              Collect payment
                            </button>
                          )}
                        </div>
                      </Td>
                    </tr>
                  ))}
                </Table>
              )}
            </Card>
            <Card title="Actions">
              <p className="hos-muted">
                Open an invoice to issue, record payments, or allocate. Use patient links to jump
                to the patient profile.
              </p>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="refunds">
          <div className="hos-toolbar-row">
            <Field label="Patient search" htmlFor="ref-pq">
              {({ describedBy }) => (
                <Input
                  id="ref-pq"
                  aria-describedby={describedBy}
                  value={patientQ}
                  onChange={(ev) => setPatientQ(ev.target.value)}
                  placeholder="Search patients"
                />
              )}
            </Field>
            <Field label="Patient filter" htmlFor="ref-patient">
              {({ describedBy }) => (
                <Select
                  id="ref-patient"
                  aria-describedby={describedBy}
                  value={patientFilterId}
                  onChange={(ev) => setPatientFilterId(ev.target.value)}
                  options={patientSelectOptions}
                />
              )}
            </Field>
          </div>
          <RefundsPanel
            tenantId={tenant!.id}
            patientId={patientFilterId}
            canRead={canRead}
            canRefund={canRefund}
            onSessionExpired={onSessionExpired}
            onOpenPatient={onOpenPatient}
          />
        </TabsContent>

        <TabsContent value="credits">
          <div className="hos-toolbar-row">
            <Field label="Patient search" htmlFor="cr-pq">
              {({ describedBy }) => (
                <Input
                  id="cr-pq"
                  aria-describedby={describedBy}
                  value={patientQ}
                  onChange={(ev) => setPatientQ(ev.target.value)}
                  placeholder="Search patients"
                />
              )}
            </Field>
            <Field label="Patient filter" htmlFor="cr-patient">
              {({ describedBy }) => (
                <Select
                  id="cr-patient"
                  aria-describedby={describedBy}
                  value={patientFilterId}
                  onChange={(ev) => setPatientFilterId(ev.target.value)}
                  options={patientSelectOptions}
                />
              )}
            </Field>
          </div>
          <CreditNotesPanel
            tenantId={tenant!.id}
            patientId={patientFilterId}
            canRead={canRead}
            canRefund={canRefund}
            onSessionExpired={onSessionExpired}
            onOpenPatient={onOpenPatient}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}