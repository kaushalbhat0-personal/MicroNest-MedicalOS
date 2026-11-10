"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  LoadingState,
  MoneyDisplay,
  PageHeader,
  Select,
  Status,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { useTenantApi } from "@/lib/use-api";
import { Shell } from "../../shell";

type Payment = {
  id: string;
  status: string;
  method: string;
  amount: string;
  allocated_amount: string;
  unallocated_amount: string;
  currency: string;
};

export default function PaymentsPage() {
  const router = useRouter();
  const { data, loading, error, reload } = useTenantApi<{ items: Payment[] }>(
    (t) => `/api/v1/tenants/${t}/payments?limit=50`,
  );
  const [patientId, setPatientId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [method, setMethod] = useState("cash");
  const [amount, setAmount] = useState("");

  async function record(e: React.FormEvent) {
    e.preventDefault();
    const t = getSelectedTenant();
    if (!t || !patientId || !locationId) {
      if (!t) router.push("/");
      return;
    }
    try {
      await api.post(`/api/v1/tenants/${t}/payments`, {
        patient_id: patientId,
        location_id: locationId,
        method,
        amount,
      }, t);
      setAmount("");
      reload();
    } catch (err) {
      alert((err as Error).message);
    }
  }

  return (
    <Shell>
      <PageHeader
        title="Payments"
        description="Money received. Allocation applies it to invoices; the remainder stays as patient credit."
        actions={<Link href="/billing/invoices">Invoices</Link>}
      />
      {error ? (
        <Alert tone="danger" title="Something went wrong">
          {error}
        </Alert>
      ) : null}
      <Card title="All payments">
        {loading ? (
          <LoadingState label="Loading payments" />
        ) : (data?.items ?? []).length === 0 ? (
          <EmptyState title="No payments recorded" />
        ) : (
          <Table
            caption="Payments"
            density="compact"
            columns={
              <>
                <Th>Method</Th>
                <Th>Status</Th>
                <Th numeric>Amount</Th>
                <Th numeric>Allocated</Th>
                <Th numeric>Unallocated</Th>
              </>
            }
          >
            {(data?.items ?? []).map((p) => (
              <tr key={p.id}>
                <Td>{p.method}</Td>
                <Td>
                  <Status value={p.status} />
                </Td>
                <Td numeric>
                  <MoneyDisplay amount={p.amount} currency={p.currency} />
                </Td>
                <Td numeric>
                  <MoneyDisplay amount={p.allocated_amount} currency={p.currency} />
                </Td>
                <Td numeric>
                  <MoneyDisplay amount={p.unallocated_amount} currency={p.currency} />
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <Card title="Record payment">
        <form onSubmit={record}>
          <Field label="Patient ID" htmlFor="p-patient" required>
            {() => (
              <Input id="p-patient" value={patientId} onChange={(e) => setPatientId(e.target.value)} required />
            )}
          </Field>
          <Field label="Location ID" htmlFor="p-location" required>
            {() => (
              <Input id="p-location" value={locationId} onChange={(e) => setLocationId(e.target.value)} required />
            )}
          </Field>
          <Field label="Method" htmlFor="p-method" required>
            {() => (
              <Select
                id="p-method"
                value={method}
                onChange={(e) => setMethod(e.target.value)}
                required
                options={["cash", "upi", "manual_card", "manual_other"].map((m) => ({
                  value: m,
                  label: m,
                }))}
              />
            )}
          </Field>
          <Field label="Amount (INR)" htmlFor="p-amount" required>
            {() => (
              <Input
                id="p-amount"
                type="number"
                step="0.01"
                min="0.01"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                required
              />
            )}
          </Field>
          <p>
            <Button type="submit">Record</Button>
          </p>
        </form>
        <p className="hos-helper">
          To allocate, refund, or receipt a payment, open its invoice or use the invoice workspace.
        </p>
      </Card>
    </Shell>
  );
}
