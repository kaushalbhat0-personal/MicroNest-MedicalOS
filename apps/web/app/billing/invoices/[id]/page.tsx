"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Alert,
  Badge,
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
  Td,
  Th,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { Shell } from "../../../shell";

type InvoiceLine = { id: string; description: string; line_total: string };
type Invoice = {
  id: string;
  patient_id: string;
  location_id: string;
  status: string;
  currency: string;
  subtotal: string;
  tax_total: string;
  grand_total: string;
  allocated_amount: string;
  outstanding_amount: string;
  financial_year: string | null;
  doc_number: number | null;
  lines: InvoiceLine[];
};
type Payment = {
  id: string;
  status: string;
  method: string;
  amount: string;
  allocated_amount: string;
  unallocated_amount: string;
  currency: string;
};
type Allocation = { id: string; payment_id: string; invoice_id: string; amount: string; reversed: boolean };
type Refund = { id: string; amount: string; reason: string; currency: string };
type CreditNote = {
  id: string;
  status: string;
  amount: string;
  reason: string;
  financial_year: string | null;
  doc_number: number | null;
};

export default function InvoiceDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const [inv, setInv] = useState<Invoice | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [allocs, setAllocs] = useState<Record<string, Allocation[]>>({});
  const [refunds, setRefunds] = useState<Record<string, Refund[]>>({});
  const [receipts, setReceipts] = useState<Record<string, string>>({});
  const [credits, setCredits] = useState<CreditNote[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [voiding, setVoiding] = useState(false);
  const [voidReason, setVoidReason] = useState("");
  const [payMethod, setPayMethod] = useState("cash");
  const [payAmount, setPayAmount] = useState("");
  const [allocAmount, setAllocAmount] = useState<Record<string, string>>({});
  const [refundAmount, setRefundAmount] = useState<Record<string, string>>({});
  const [creditAmount, setCreditAmount] = useState("");
  const [creditReason, setCreditReason] = useState("");

  function t() {
    return getSelectedTenant() ?? "";
  }

  function load() {
    const tenant = getSelectedTenant();
    if (!tenant) {
      router.push("/");
      return;
    }
    setLoading(true);
    const get = <T,>(path: string) => api.get<T>(`/api/v1/tenants/${tenant}${path}`, tenant);
    get<Invoice>(`/invoices/${id}`)
      .then((inv) => {
        setInv(inv);
        return get<{ items: Payment[] }>(`/payments?patient_id=${inv.patient_id}&limit=50`).then(
          (p) => ({ inv, pays: p.items }),
        );
      })
      .then(async ({ inv, pays }) => {
        setPayments(pays);
        const a: Record<string, Allocation[]> = {};
        const r: Record<string, Refund[]> = {};
        for (const p of pays) {
          try {
            const [al, rf] = await Promise.all([
              get<{ items: Allocation[] }>(`/payments/${p.id}/allocations`),
              get<{ items: Refund[] }>(`/payments/${p.id}/refunds`),
            ]);
            a[p.id] = al.items.filter((x) => x.invoice_id === inv.id);
            r[p.id] = rf.items;
          } catch {
            /* per-payment detail is best-effort */
          }
        }
        setAllocs(a);
        setRefunds(r);
        try {
          const cn = await get<{ items: CreditNote[] }>(`/invoices/${id}/credit-notes`);
          setCredits(cn.items);
        } catch {
          setCredits([]);
        }
        setError("");
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, [id, router]);

  async function issue() {
    setError("");
    try {
      await api.post(`/api/v1/tenants/${t()}/invoices/${id}/issue`, {}, t());
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function voidInvoice() {
    setError("");
    try {
      await api.post(
        `/api/v1/tenants/${t()}/invoices/${id}/void`,
        { reason: voidReason || null },
        t(),
      );
      setVoiding(false);
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function recordPayment(e: React.FormEvent) {
    e.preventDefault();
    if (!inv) return;
    setError("");
    try {
      await api.post(
        `/api/v1/tenants/${t()}/payments`,
        {
          patient_id: inv.patient_id,
          location_id: inv.location_id,
          method: payMethod,
          amount: payAmount,
        },
        t(),
      );
      setPayAmount("");
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function allocate(pid: string) {
    setError("");
    try {
      await api.post(
        `/api/v1/tenants/${t()}/payments/${pid}/allocations`,
        { allocations: [{ invoice_id: id, amount: allocAmount[pid] }] },
        t(),
      );
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function refund(pid: string) {
    setError("");
    try {
      await api.post(
        `/api/v1/tenants/${t()}/payments/${pid}/refunds`,
        { amount: refundAmount[pid], reason: "refund from invoice workspace" },
        t(),
      );
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function createReceipt(pid: string) {
    setError("");
    try {
      const r = await api.post<{ id: string }>(
        `/api/v1/tenants/${t()}/payments/${pid}/receipt`,
        {},
        t(),
      );
      setReceipts((m) => ({ ...m, [pid]: r.id }));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function createCredit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.post(`/api/v1/tenants/${t()}/invoices/${id}/credit-notes`, {
        amount: creditAmount,
        reason: creditReason,
      }, t());
      setCreditAmount("");
      setCreditReason("");
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function issueCredit(nid: string) {
    setError("");
    try {
      await api.post(`/api/v1/tenants/${t()}/credit-notes/${nid}/issue`, {}, t());
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Shell>
      {loading ? (
        <LoadingState label="Loading invoice" />
      ) : error && !inv ? (
        <Alert tone="danger" title="Could not load invoice">
          {error}
        </Alert>
      ) : inv ? (
        <>
          <p>
            <Link href="/billing/invoices">Back to invoices</Link>
          </p>
          {error ? (
            <Alert tone="danger" title="Something went wrong">
              {error}
            </Alert>
          ) : null}
          <Card
            title={`Invoice ${inv.financial_year && inv.doc_number ? `${inv.financial_year}#${inv.doc_number}` : "(draft)"}`}
          >
            <p>
              <Status value={inv.status} />
            </p>
            <FinancialSummary
              rows={[
                { label: "Subtotal", amount: inv.subtotal },
                { label: "Tax", amount: inv.tax_total },
                { label: "Allocated", amount: inv.allocated_amount },
              ]}
              total={{ label: "Outstanding", amount: inv.outstanding_amount }}
              currency={inv.currency}
            />
            <p>
              Grand total: <MoneyDisplay amount={inv.grand_total} currency={inv.currency} />
            </p>
            {inv.status === "draft" ? (
              <Button onClick={() => void issue()}>Issue invoice</Button>
            ) : null}
            {(inv.status === "draft" || inv.status === "issued") && (
              <>
                {" "}
                <Button variant="danger" onClick={() => setVoiding(true)}>
                  Void...
                </Button>
              </>
            )}
          </Card>
          <Card title="Lines">
            <Table
              caption="Invoice lines"
              columns={
                <>
                  <Th>Description</Th>
                  <Th numeric>Total</Th>
                </>
              }
            >
              {inv.lines.map((l) => (
                <tr key={l.id}>
                  <Td>{l.description}</Td>
                  <Td numeric>
                    <MoneyDisplay amount={l.line_total} currency={inv.currency} />
                  </Td>
                </tr>
              ))}
            </Table>
          </Card>
          <Card title="Record payment">
            <form onSubmit={recordPayment}>
              <Field label="Method" htmlFor="pay-method" required>
                {() => (
                  <Select
                    id="pay-method"
                    value={payMethod}
                    onChange={(e) => setPayMethod(e.target.value)}
                    required
                    options={["cash", "upi", "manual_card", "manual_other"].map((m) => ({
                      value: m,
                      label: m,
                    }))}
                  />
                )}
              </Field>
              <Field label={`Amount (${inv.currency})`} htmlFor="pay-amount" required>
                {() => (
                  <Input
                    id="pay-amount"
                    type="number"
                    step="0.01"
                    min="0.01"
                    value={payAmount}
                    onChange={(e) => setPayAmount(e.target.value)}
                    required
                  />
                )}
              </Field>
              <p>
                <Button type="submit">Record payment</Button>
              </p>
            </form>
            <p className="hos-helper">
              Location is taken from this invoice. Allocation to this invoice happens below, per payment.
            </p>
          </Card>
          <Card title="Payments & allocation">
            {payments.length === 0 ? (
              <EmptyState title="No payments from this patient yet" />
            ) : (
              payments.map((p) => (
                <div key={p.id} className="hos-card">
                  <p>
                    <Status value={p.status} /> {p.method} -{" "}
                    <MoneyDisplay amount={p.amount} currency={p.currency} /> - unallocated{" "}
                    <MoneyDisplay amount={p.unallocated_amount} currency={p.currency} />
                  </p>
                  {(allocs[p.id] ?? []).length > 0 ? (
                    <ul>
                      {(allocs[p.id] ?? []).map((a) => (
                        <li key={a.id}>
                          Allocated <MoneyDisplay amount={a.amount} currency={p.currency} />{" "}
                          {a.reversed ? <Badge tone="neutral">reversed</Badge> : null}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  <Field label={`Allocate to this invoice (${inv.currency})`} htmlFor={`alloc-${p.id}`}>
                    {() => (
                      <Input
                        id={`alloc-${p.id}`}
                        type="number"
                        step="0.01"
                        min="0.01"
                        value={allocAmount[p.id] ?? ""}
                        onChange={(e) =>
                          setAllocAmount((m) => ({ ...m, [p.id]: e.target.value }))
                        }
                      />
                    )}
                  </Field>
                  <p>
                    <Button size="sm" onClick={() => void allocate(p.id)}>
                      Allocate
                    </Button>{" "}
                    <Button size="sm" variant="secondary" onClick={() => void createReceipt(p.id)}>
                      Issue receipt
                    </Button>{" "}
                    {receipts[p.id] ? (
                      <Link href={`/billing/receipts/${receipts[p.id]}`}>View receipt</Link>
                    ) : null}
                  </p>
                  <Field label={`Refund amount (${p.currency})`} htmlFor={`ref-${p.id}`}>
                    {() => (
                      <Input
                        id={`ref-${p.id}`}
                        type="number"
                        step="0.01"
                        min="0.01"
                        value={refundAmount[p.id] ?? ""}
                        onChange={(e) =>
                          setRefundAmount((m) => ({ ...m, [p.id]: e.target.value }))
                        }
                      />
                    )}
                  </Field>
                  <p>
                    <Button size="sm" variant="danger" onClick={() => void refund(p.id)}>
                      Refund
                    </Button>
                  </p>
                  {(refunds[p.id] ?? []).length > 0 ? (
                    <ul>
                      {(refunds[p.id] ?? []).map((r) => (
                        <li key={r.id}>
                          Refunded <MoneyDisplay amount={r.amount} currency={r.currency} /> - {r.reason}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ))
            )}
          </Card>
          <Card title="Credit notes">
            {(credits ?? []).length === 0 ? (
              <EmptyState title="No credit notes" />
            ) : (
              <Table
                caption="Credit notes"
                columns={
                  <>
                    <Th>Amount</Th>
                    <Th>Status</Th>
                    <Th>Number</Th>
                    <Th>Actions</Th>
                  </>
                }
              >
                {credits.map((c) => (
                  <tr key={c.id}>
                    <Td numeric>
                      <MoneyDisplay amount={c.amount} currency={inv.currency} />
                    </Td>
                    <Td>
                      <Status value={c.status} />
                    </Td>
                    <Td>
                      {c.financial_year && c.doc_number
                        ? `${c.financial_year}#${c.doc_number}`
                        : "-"}
                    </Td>
                    <Td>
                      {c.status === "draft" ? (
                        <Button size="sm" onClick={() => void issueCredit(c.id)}>
                          Issue
                        </Button>
                      ) : null}
                    </Td>
                  </tr>
                ))}
              </Table>
            )}
            <h3>New credit note</h3>
            <form onSubmit={createCredit}>
              <Field label={`Amount (${inv.currency})`} htmlFor="cn-amount" required>
                {() => (
                  <Input
                    id="cn-amount"
                    type="number"
                    step="0.01"
                    min="0.01"
                    value={creditAmount}
                    onChange={(e) => setCreditAmount(e.target.value)}
                    required
                  />
                )}
              </Field>
              <Field label="Reason" htmlFor="cn-reason" required>
                {() => (
                  <Input
                    id="cn-reason"
                    value={creditReason}
                    onChange={(e) => setCreditReason(e.target.value)}
                    required
                    minLength={2}
                    maxLength={200}
                  />
                )}
              </Field>
              <p>
                <Button type="submit">Create draft note</Button>
              </p>
            </form>
          </Card>
          <ConfirmDialog
            open={voiding}
            onOpenChange={setVoiding}
            title="Void invoice?"
            confirmLabel="Void invoice"
            onConfirm={() => void voidInvoice()}
          >
            <p>Only unsettled invoices can be voided. Issued invoices need a reason.</p>
            <Field label="Reason" htmlFor="void-reason">
              {() => (
                <Input
                  id="void-reason"
                  value={voidReason}
                  onChange={(e) => setVoidReason(e.target.value)}
                  maxLength={200}
                />
              )}
            </Field>
          </ConfirmDialog>
        </>
      ) : null}
    </Shell>
  );
}
