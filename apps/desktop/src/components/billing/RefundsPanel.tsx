import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  LoadingState,
  MoneyDisplay,
  Select,
  Status,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { fmtWhen, statusLabel } from "../../lib/format";
import {
  createRefund,
  isPositiveMoneyAmount,
  isRefundReasonValid,
  listAllocations,
  listPaymentRefunds,
  listPayments,
  newIdempotencyKey,
  refundableFromPayment,
  type Allocation,
  type Payment,
  type Refund,
} from "../../lib/billingApi";

function shortId(id: string): string {
  return id.slice(0, 8);
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

export function RefundsPanel({
  tenantId,
  patientId,
  canRead,
  canRefund,
  onSessionExpired,
  onOpenPatient,
}: {
  tenantId: string;
  patientId: string;
  canRead: boolean;
  canRefund: boolean;
  onSessionExpired: () => void;
  onOpenPatient: (id: string) => void;
}) {
  const [payments, setPayments] = useState<Payment[]>([]);
  const [selectedPaymentId, setSelectedPaymentId] = useState<string | null>(null);
  const [refunds, setRefunds] = useState<Refund[]>([]);
  const [allocations, setAllocations] = useState<Allocation[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const [refundAmount, setRefundAmount] = useState("");
  const [refundReason, setRefundReason] = useState("");
  const [refundInvoiceId, setRefundInvoiceId] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [refundBusy, setRefundBusy] = useState(false);
  const refundKeyRef = useRef<string | null>(null);

  const selectedPayment = useMemo(
    () => payments.find((p) => p.id === selectedPaymentId) ?? null,
    [payments, selectedPaymentId],
  );

  const refundableHint = selectedPayment ? refundableFromPayment(selectedPayment) : "0.00";
  const canShowRefundForm =
    canRefund &&
    selectedPayment &&
    isPositiveMoneyAmount(refundableHint);

  const invoiceOptions = useMemo(() => {
    const active = allocations.filter((a) => !a.reversed);
    return [
      { value: "", label: "No invoice scope (optional)" },
      ...active.map((a) => ({
        value: a.invoice_id,
        label: `Invoice ${shortId(a.invoice_id)} · ${a.amount}`,
      })),
    ];
  }, [allocations]);

  const reloadPayments = useCallback(async () => {
    if (!canRead || !patientId) return;
    setLoadingList(true);
    setError(null);
    try {
      const data = await listPayments(tenantId, { patientId, limit: 50 });
      setPayments(data);
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Failed to load payments.");
    } finally {
      setLoadingList(false);
    }
  }, [tenantId, patientId, canRead, onSessionExpired]);

  const reloadRefunds = useCallback(async () => {
    if (!selectedPaymentId) {
      setRefunds([]);
      setAllocations([]);
      return;
    }
    setLoadingDetail(true);
    try {
      const [refundList, allocs] = await Promise.all([
        listPaymentRefunds(tenantId, selectedPaymentId),
        listAllocations(tenantId, selectedPaymentId),
      ]);
      setRefunds(refundList);
      setAllocations(allocs);
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Failed to load refunds.");
      setRefunds([]);
      setAllocations([]);
    } finally {
      setLoadingDetail(false);
    }
  }, [tenantId, selectedPaymentId, onSessionExpired]);

  useEffect(() => {
    void reloadPayments();
  }, [reloadPayments]);

  useEffect(() => {
    void reloadRefunds();
  }, [reloadRefunds]);

  useEffect(() => {
    setSelectedPaymentId(null);
    setRefundAmount("");
    setRefundReason("");
    setRefundInvoiceId("");
  }, [patientId]);

  function openRefundConfirm(ev: FormEvent) {
    ev.preventDefault();
    if (!selectedPayment) return;
    if (!isPositiveMoneyAmount(refundAmount.trim())) {
      setError("Enter a valid refund amount.");
      return;
    }
    if (!isRefundReasonValid(refundReason)) {
      setError("Reason must be 2–200 characters.");
      return;
    }
    refundKeyRef.current = newIdempotencyKey("refund");
    setConfirmOpen(true);
  }

  function onConfirmOpenChange(open: boolean) {
    setConfirmOpen(open);
    if (!open && !refundBusy) refundKeyRef.current = null;
  }

  async function submitRefund() {
    if (!selectedPayment || !canRefund) return;
    const key = refundKeyRef.current ?? newIdempotencyKey("refund");
    setRefundBusy(true);
    setError(null);
    try {
      await createRefund(tenantId, selectedPayment.id, {
        amount: refundAmount.trim(),
        reason: refundReason.trim(),
        invoice_id: refundInvoiceId || null,
        idempotency_key: key,
      });
      refundKeyRef.current = null;
      setConfirmOpen(false);
      setRefundAmount("");
      setRefundReason("");
      setRefundInvoiceId("");
      setInfo("Refund recorded.");
      await reloadPayments();
      await reloadRefunds();
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Refund failed.");
      refundKeyRef.current = null;
    } finally {
      setRefundBusy(false);
    }
  }

  if (!canRead) {
    return (
      <Alert tone="danger" title="Refunds">
        You need billing.read permission to view refunds.
      </Alert>
    );
  }

  if (!patientId) {
    return (
      <EmptyState title="Select a patient">
        Refunds are listed per payment. Choose a patient filter above to load payments and refund
        history.
      </EmptyState>
    );
  }

  return (
    <div className="hos-billing-refunds">
      <p className="hos-caption">
        Records a clinic refund against the payment. This is not a bank/gateway settlement.
      </p>

      {error && (
        <Alert tone="danger" title="Refund">
          {error}
        </Alert>
      )}
      {info && (
        <Alert tone="success" title="Updated">
          {info}
        </Alert>
      )}

      <div className="hos-billing-layout">
        <Card title="Payments">
          {loadingList && payments.length === 0 ? (
            <LoadingState label="Loading payments" />
          ) : payments.length === 0 ? (
            <EmptyState title="No payments">No payments for this patient.</EmptyState>
          ) : (
            <Table
              columns={
                <>
                  <Th>Received</Th>
                  <Th>Method</Th>
                  <Th>Amount</Th>
                  <Th>Refundable hint</Th>
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
                    <MoneyDisplay
                      amount={refundableFromPayment(p)}
                      currency={p.currency}
                    />
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

        <Card title={selectedPayment ? `Payment ${shortId(selectedPayment.id)}` : "Refund detail"}>
          {!selectedPayment ? (
            <EmptyState title="No payment selected">
              Select a payment to view refund history or record a refund.
            </EmptyState>
          ) : loadingDetail ? (
            <LoadingState label="Loading refunds" />
          ) : (
            <>
              <dl className="hos-dl">
                <div>
                  <dt>Patient</dt>
                  <dd>
                    <button
                      type="button"
                      className="hos-link-btn"
                      onClick={() => onOpenPatient(selectedPayment.patient_id)}
                    >
                      {shortId(selectedPayment.patient_id)}
                    </button>
                  </dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>
                    <Status value={selectedPayment.status} />
                  </dd>
                </div>
                <div>
                  <dt>Refundable (backend-derived: allocated + unallocated)</dt>
                  <dd>
                    <MoneyDisplay
                      amount={refundableHint}
                      currency={selectedPayment.currency}
                    />
                  </dd>
                </div>
              </dl>

              <h3 className="hos-caption">Refund history</h3>
              {refunds.length === 0 ? (
                <p className="hos-muted">No refunds for this payment.</p>
              ) : (
                <Table
                  columns={
                    <>
                      <Th>Status</Th>
                      <Th>Amount</Th>
                      <Th>Currency</Th>
                      <Th>Reason</Th>
                      <Th>Invoice</Th>
                      <Th>Created</Th>
                    </>
                  }
                >
                  {refunds.map((r) => (
                    <tr key={r.id}>
                      <Td>
                        <Status value={r.status} />
                      </Td>
                      <Td>
                        <MoneyDisplay amount={r.amount} currency={r.currency} />
                      </Td>
                      <Td>{r.currency}</Td>
                      <Td>{r.reason}</Td>
                      <Td>{r.invoice_id ? shortId(r.invoice_id) : "—"}</Td>
                      <Td>{fmtWhen(r.created_at)}</Td>
                    </tr>
                  ))}
                </Table>
              )}

              {canShowRefundForm && (
                <form className="hos-form-stack" onSubmit={openRefundConfirm}>
                  <Field label="Refund amount" htmlFor="refund-amt">
                    {({ describedBy }) => (
                      <Input
                        id="refund-amt"
                        aria-describedby={describedBy}
                        value={refundAmount}
                        onChange={(ev) => setRefundAmount(ev.target.value)}
                        inputMode="decimal"
                        placeholder={refundableHint}
                      />
                    )}
                  </Field>
                  <Field label="Reason (2–200 chars)" htmlFor="refund-reason">
                    {({ describedBy }) => (
                      <Input
                        id="refund-reason"
                        aria-describedby={describedBy}
                        value={refundReason}
                        onChange={(ev) => setRefundReason(ev.target.value)}
                      />
                    )}
                  </Field>
                  {invoiceOptions.length > 1 && (
                    <Field label="Invoice scope (optional)" htmlFor="refund-inv">
                      {({ describedBy }) => (
                        <Select
                          id="refund-inv"
                          aria-describedby={describedBy}
                          value={refundInvoiceId}
                          onChange={(ev) => setRefundInvoiceId(ev.target.value)}
                          options={invoiceOptions}
                        />
                      )}
                    </Field>
                  )}
                  <Button
                    type="submit"
                    size="sm"
                    disabled={refundBusy}
                    loading={refundBusy}
                  >
                    Record refund…
                  </Button>
                </form>
              )}
            </>
          )}
        </Card>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={onConfirmOpenChange}
        title="Record refund?"
        confirmLabel="Record refund"
        pending={refundBusy}
        onConfirm={() => void submitRefund()}
      >
        {selectedPayment && (
          <p>
            Refund <strong>{refundAmount.trim()}</strong> {selectedPayment.currency} against payment{" "}
            {shortId(selectedPayment.id)}
            {refundReason.trim() ? ` — ${refundReason.trim()}` : ""}.
          </p>
        )}
      </ConfirmDialog>
    </div>
  );
}