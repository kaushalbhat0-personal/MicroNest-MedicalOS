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
  Status,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { fmtWhen, statusLabel } from "../../lib/format";
import {
  canCreateCreditNote,
  canIssueCreditNote,
  canVoidCreditNote,
  createCreditNote,
  getInvoiceBalance,
  getPatientCreditBalance,
  isPositiveMoneyAmount,
  isRefundReasonValid,
  issueCreditNote,
  listInvoiceCreditNotes,
  listInvoices,
  newIdempotencyKey,
  voidCreditNote,
  type CreditNote,
  type Invoice,
  type InvoiceBalance,
} from "../../lib/billingApi";

function shortId(id: string): string {
  return id.slice(0, 8);
}

function invoiceDocLabel(inv: Invoice): string {
  const num = inv.doc_number != null ? String(inv.doc_number) : "—";
  return inv.financial_year ? `${num} / FY ${inv.financial_year}` : num;
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

export function CreditNotesPanel({
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
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string | null>(null);
  const [creditNotes, setCreditNotes] = useState<CreditNote[]>([]);
  const [balance, setBalance] = useState<InvoiceBalance | null>(null);
  const [patientCredit, setPatientCredit] = useState<string | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const [cnAmount, setCnAmount] = useState("");
  const [cnReason, setCnReason] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [issueNoteId, setIssueNoteId] = useState<string | null>(null);
  const [voidNoteId, setVoidNoteId] = useState<string | null>(null);
  const [voidReason, setVoidReason] = useState("");
  const [busy, setBusy] = useState(false);
  const createKeyRef = useRef<string | null>(null);

  const selectedInvoice = useMemo(
    () => invoices.find((i) => i.id === selectedInvoiceId) ?? null,
    [invoices, selectedInvoiceId],
  );

  const outstandingHint = balance?.outstanding_amount ?? selectedInvoice?.outstanding_amount ?? "0.00";

  const canCreateForm =
    canRefund &&
    selectedInvoice &&
    canCreateCreditNote(selectedInvoice.status) &&
    isPositiveMoneyAmount(outstandingHint);

  const displayInvoices = useMemo(
    () => invoices.filter((inv) => inv.status !== "draft"),
    [invoices],
  );

  const reloadInvoices = useCallback(async () => {
    if (!canRead || !patientId) return;
    setLoadingList(true);
    setError(null);
    try {
      const data = await listInvoices(tenantId, { patientId, limit: 50 });
      setInvoices(data);
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Failed to load invoices.");
    } finally {
      setLoadingList(false);
    }
  }, [tenantId, patientId, canRead, onSessionExpired]);

  const reloadPatientCredit = useCallback(async () => {
    if (!patientId) {
      setPatientCredit(null);
      return;
    }
    try {
      const amt = await getPatientCreditBalance(tenantId, patientId);
      setPatientCredit(amt);
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Could not load patient credit.");
      setPatientCredit(null);
    }
  }, [tenantId, patientId, onSessionExpired]);

  const reloadCreditNotes = useCallback(async () => {
    if (!selectedInvoiceId) {
      setCreditNotes([]);
      setBalance(null);
      return;
    }
    setLoadingDetail(true);
    try {
      const [notes, bal] = await Promise.all([
        listInvoiceCreditNotes(tenantId, selectedInvoiceId),
        getInvoiceBalance(tenantId, selectedInvoiceId),
      ]);
      setCreditNotes(notes);
      setBalance(bal);
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Failed to load credit notes.");
      setCreditNotes([]);
      setBalance(null);
    } finally {
      setLoadingDetail(false);
    }
  }, [tenantId, selectedInvoiceId, onSessionExpired]);

  useEffect(() => {
    void reloadInvoices();
    void reloadPatientCredit();
  }, [reloadInvoices, reloadPatientCredit]);

  useEffect(() => {
    void reloadCreditNotes();
  }, [reloadCreditNotes]);

  useEffect(() => {
    setSelectedInvoiceId(null);
    setCnAmount("");
    setCnReason("");
  }, [patientId]);

  function openCreateConfirm(ev: FormEvent) {
    ev.preventDefault();
    if (!selectedInvoice) return;
    if (!isPositiveMoneyAmount(cnAmount.trim())) {
      setError("Enter a valid credit amount.");
      return;
    }
    if (!isRefundReasonValid(cnReason)) {
      setError("Reason must be 2–200 characters.");
      return;
    }
    createKeyRef.current = newIdempotencyKey("credit");
    setCreateOpen(true);
  }

  function onCreateOpenChange(open: boolean) {
    setCreateOpen(open);
    if (!open && !busy) createKeyRef.current = null;
  }

  async function submitCreate() {
    if (!selectedInvoice || !canRefund) return;
    const key = createKeyRef.current ?? newIdempotencyKey("credit");
    setBusy(true);
    setError(null);
    try {
      await createCreditNote(tenantId, selectedInvoice.id, {
        amount: cnAmount.trim(),
        reason: cnReason.trim(),
        idempotency_key: key,
      });
      createKeyRef.current = null;
      setCreateOpen(false);
      setCnAmount("");
      setCnReason("");
      setInfo("Credit note draft created.");
      await reloadCreditNotes();
      await reloadInvoices();
      await reloadPatientCredit();
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Create credit note failed.");
      createKeyRef.current = null;
    } finally {
      setBusy(false);
    }
  }

  async function submitIssue() {
    if (!issueNoteId) return;
    setBusy(true);
    setError(null);
    try {
      await issueCreditNote(tenantId, issueNoteId);
      setIssueNoteId(null);
      setInfo("Credit note issued.");
      await reloadCreditNotes();
      await reloadInvoices();
      await reloadPatientCredit();
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Issue credit note failed.");
    } finally {
      setBusy(false);
    }
  }

  async function submitVoid() {
    if (!voidNoteId) return;
    setBusy(true);
    setError(null);
    try {
      await voidCreditNote(tenantId, voidNoteId, voidReason.trim() || null);
      setVoidNoteId(null);
      setVoidReason("");
      setInfo("Credit note voided.");
      await reloadCreditNotes();
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Void credit note failed.");
    } finally {
      setBusy(false);
    }
  }

  if (!canRead) {
    return (
      <Alert tone="danger" title="Credit notes">
        You need billing.read permission to view credit notes.
      </Alert>
    );
  }

  if (!patientId) {
    return (
      <EmptyState title="Select a patient">
        Credit notes are tied to invoices. Choose a patient filter above to list invoices and
        credit note history.
      </EmptyState>
    );
  }

  return (
    <div className="hos-billing-credits">
      <p className="hos-caption">
        A credit note corrects invoice outstanding. It is not a cash refund.
      </p>

      {patientCredit != null && (
        <p className="hos-muted">
          Patient unallocated credit (backend):{" "}
          <MoneyDisplay amount={patientCredit} currency={selectedInvoice?.currency ?? "INR"} />
        </p>
      )}

      {error && (
        <Alert tone="danger" title="Credit note">
          {error}
        </Alert>
      )}
      {info && (
        <Alert tone="success" title="Updated">
          {info}
        </Alert>
      )}

      <div className="hos-billing-layout">
        <Card title="Invoices">
          {loadingList && displayInvoices.length === 0 ? (
            <LoadingState label="Loading invoices" />
          ) : displayInvoices.length === 0 ? (
            <EmptyState title="No invoices">No issued invoices for this patient.</EmptyState>
          ) : (
            <Table
              columns={
                <>
                  <Th>Doc / FY</Th>
                  <Th>Status</Th>
                  <Th>Outstanding</Th>
                  <Th>Open</Th>
                </>
              }
            >
              {displayInvoices.map((inv) => (
                <tr key={inv.id}>
                  <Td>{invoiceDocLabel(inv)}</Td>
                  <Td>{statusLabel(inv.status)}</Td>
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

        <Card
          title={
            selectedInvoice
              ? `Invoice ${invoiceDocLabel(selectedInvoice)}`
              : "Credit note detail"
          }
        >
          {!selectedInvoice ? (
            <EmptyState title="No invoice selected">
              Select an invoice to view credit notes or create a draft.
            </EmptyState>
          ) : loadingDetail ? (
            <LoadingState label="Loading credit notes" />
          ) : (
            <>
              <dl className="hos-dl">
                <div>
                  <dt>Patient</dt>
                  <dd>
                    <button
                      type="button"
                      className="hos-link-btn"
                      onClick={() => onOpenPatient(selectedInvoice.patient_id)}
                    >
                      {shortId(selectedInvoice.patient_id)}
                    </button>
                  </dd>
                </div>
                <div>
                  <dt>Outstanding (backend)</dt>
                  <dd>
                    <MoneyDisplay
                      amount={outstandingHint}
                      currency={selectedInvoice.currency}
                    />
                  </dd>
                </div>
              </dl>

              <h3 className="hos-caption">Credit notes</h3>
              {creditNotes.length === 0 ? (
                <p className="hos-muted">No credit notes for this invoice.</p>
              ) : (
                <Table
                  columns={
                    <>
                      <Th>Status</Th>
                      <Th>Amount</Th>
                      <Th>Doc / FY</Th>
                      <Th>Reason</Th>
                      <Th>Actions</Th>
                    </>
                  }
                >
                  {creditNotes.map((cn) => (
                    <tr key={cn.id}>
                      <Td>
                        <Status value={cn.status} />
                      </Td>
                      <Td>
                        <MoneyDisplay amount={cn.amount} currency={cn.currency} />
                      </Td>
                      <Td>
                        {cn.doc_number != null
                          ? invoiceDocLabel({
                              ...selectedInvoice,
                              doc_number: cn.doc_number,
                              financial_year: cn.financial_year,
                            })
                          : "—"}
                      </Td>
                      <Td>{cn.reason}</Td>
                      <Td>
                        <div className="hos-inline-actions">
                          {canRefund && canIssueCreditNote(cn.status) && (
                            <button
                              type="button"
                              className="hos-link-btn"
                              disabled={busy}
                              onClick={() => setIssueNoteId(cn.id)}
                            >
                              Issue
                            </button>
                          )}
                          {canRefund && canVoidCreditNote(cn.status) && (
                            <button
                              type="button"
                              className="hos-link-btn"
                              disabled={busy}
                              onClick={() => {
                                setVoidNoteId(cn.id);
                                setVoidReason("");
                              }}
                            >
                              Void
                            </button>
                          )}
                        </div>
                      </Td>
                    </tr>
                  ))}
                </Table>
              )}

              {canCreateForm && (
                <form className="hos-form-stack" onSubmit={openCreateConfirm}>
                  <p className="hos-caption">
                    Amount must not exceed outstanding ({outstandingHint}) — backend validates at
                    create and issue.
                  </p>
                  <Field label="Credit amount" htmlFor="cn-amt">
                    {({ describedBy }) => (
                      <Input
                        id="cn-amt"
                        aria-describedby={describedBy}
                        value={cnAmount}
                        onChange={(ev) => setCnAmount(ev.target.value)}
                        inputMode="decimal"
                        placeholder={outstandingHint}
                      />
                    )}
                  </Field>
                  <Field label="Reason (2–200 chars)" htmlFor="cn-reason">
                    {({ describedBy }) => (
                      <Input
                        id="cn-reason"
                        aria-describedby={describedBy}
                        value={cnReason}
                        onChange={(ev) => setCnReason(ev.target.value)}
                      />
                    )}
                  </Field>
                  <Button type="submit" size="sm" disabled={busy} loading={busy}>
                    Create draft…
                  </Button>
                </form>
              )}
            </>
          )}
        </Card>
      </div>

      <ConfirmDialog
        open={createOpen}
        onOpenChange={onCreateOpenChange}
        title="Create credit note draft?"
        confirmLabel="Create draft"
        pending={busy}
        onConfirm={() => void submitCreate()}
      >
        {selectedInvoice && (
          <p>
            Credit <strong>{cnAmount.trim()}</strong> {selectedInvoice.currency} on invoice{" "}
            {invoiceDocLabel(selectedInvoice)}
            {cnReason.trim() ? ` — ${cnReason.trim()}` : ""}.
          </p>
        )}
      </ConfirmDialog>

      <ConfirmDialog
        open={Boolean(issueNoteId)}
        onOpenChange={(open) => {
          if (!open) setIssueNoteId(null);
        }}
        title="Issue credit note?"
        confirmLabel="Issue"
        pending={busy}
        onConfirm={() => void submitIssue()}
      >
        Issuing allocates document numbering and reduces invoice outstanding. This cannot be undone.
      </ConfirmDialog>

      <ConfirmDialog
        open={Boolean(voidNoteId)}
        onOpenChange={(open) => {
          if (!open) {
            setVoidNoteId(null);
            setVoidReason("");
          }
        }}
        title="Void draft credit note?"
        confirmLabel="Void draft"
        pending={busy}
        onConfirm={() => void submitVoid()}
      >
        <Field label="Reason (optional)" htmlFor="void-cn-reason">
          {({ describedBy }) => (
            <Input
              id="void-cn-reason"
              aria-describedby={describedBy}
              value={voidReason}
              onChange={(ev) => setVoidReason(ev.target.value)}
            />
          )}
        </Field>
      </ConfirmDialog>
    </div>
  );
}