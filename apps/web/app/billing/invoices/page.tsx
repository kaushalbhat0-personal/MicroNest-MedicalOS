"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  LoadingState,
  Status,
  Table,
  MoneyDisplay,
  Td,
  Th,
  PageHeader,
} from "@healthcare-os/ui";
import { useState } from "react";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { useTenantApi } from "@/lib/use-api";
import { Shell } from "../../shell";

export type InvoiceListItem = {
  id: string;
  status: string;
  currency: string;
  grand_total: string;
  outstanding_amount: string;
  financial_year: string | null;
  doc_number: number | null;
};

export default function InvoicesPage() {
  const router = useRouter();
  const { data, loading, error } = useTenantApi<{ items: InvoiceListItem[] }>(
    (t) => `/api/v1/tenants/${t}/invoices?limit=50`,
  );
  const [status, setStatus] = useState("");
  const [patientId, setPatientId] = useState("");
  const [description, setDescription] = useState("Consultation");
  const [rate, setRate] = useState("500.00");
  const [locationId, setLocationId] = useState("");
  const [locations, setLocations] = useState<{ id: string; name: string }[]>([]);

  async function ensureLocations() {
    const t = getSelectedTenant();
    if (!t || locations.length > 0) return;
    try {
      const locs = await api.get<{ id: string; name: string }[]>(
        `/api/v1/tenants/${t}/locations`,
        t,
      );
      setLocations(locs);
    } catch {
      /* locations load lazily on submit instead */
    }
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    const t = getSelectedTenant();
    if (!t || !patientId || !locationId) {
      if (!t) router.push("/");
      return;
    }
    try {
      const created = await api.post<{ id: string }>(
        `/api/v1/tenants/${t}/invoices`,
        {
          patient_id: patientId,
          location_id: locationId,
          items: [{ description, quantity: "1", unit_rate: rate }],
        },
        t,
      );
      router.push(`/billing/invoices/${created.id}`);
    } catch (err) {
      alert((err as Error).message);
    }
  }

  const items = (data?.items ?? []).filter((i) => !status || i.status === status);

  return (
    <Shell>
      <PageHeader
        title="Invoices"
        description="Draft -> issued -> paid. Balances are derived server-side."
        actions={<Link href="/billing/estimates">Estimates</Link>}
      />
      {error ? (
        <Alert tone="danger" title="Something went wrong">
          {error}
        </Alert>
      ) : null}
      <Card title="All invoices">
        {loading ? (
          <LoadingState label="Loading invoices" />
        ) : items.length === 0 ? (
          <EmptyState title="No invoices">
            {status ? "No invoices with this status." : "Create the first draft below."}
          </EmptyState>
        ) : (
          <Table
            caption="Invoices"
            density="compact"
            columns={
              <>
                <Th>Number</Th>
                <Th>Status</Th>
                <Th numeric>Total</Th>
                <Th numeric>Outstanding</Th>
              </>
            }
          >
            {items.map((i) => (
              <tr key={i.id}>
                <Td>
                  <Link href={`/billing/invoices/${i.id}`}>
                    {i.financial_year && i.doc_number
                      ? `${i.financial_year}#${i.doc_number}`
                      : `${i.id.slice(0, 8)}... (draft)`}
                  </Link>
                </Td>
                <Td>
                  <Status value={i.status} />
                </Td>
                <Td numeric>
                  <MoneyDisplay amount={i.grand_total} currency={i.currency} />
                </Td>
                <Td numeric>
                  <MoneyDisplay amount={i.outstanding_amount} currency={i.currency} />
                </Td>
              </tr>
            ))}
          </Table>
        )}
        <Field label="Filter by status" htmlFor="inv-status">
          {() => (
            <select
              id="inv-status"
              className="hos-input"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              onFocus={() => void ensureLocations()}
            >
              <option value="">All</option>
              <option value="draft">draft</option>
              <option value="issued">issued</option>
              <option value="partially_paid">partially paid</option>
              <option value="paid">paid</option>
              <option value="voided">voided</option>
            </select>
          )}
        </Field>
      </Card>
      <Card title="New draft invoice">
        <form onSubmit={create}>
          <Field label="Patient ID" htmlFor="ni-patient" required description="Paste a patient ID (UUID).">
            {({ describedBy }) => (
              <Input
                id="ni-patient"
                value={patientId}
                onChange={(e) => setPatientId(e.target.value)}
                required
                aria-describedby={describedBy}
              />
            )}
          </Field>
          <Field label="Location ID" htmlFor="ni-location" required>
            {() => (
              <Input
                id="ni-location"
                value={locationId}
                onChange={(e) => setLocationId(e.target.value)}
                required
                onFocus={() => void ensureLocations()}
                list="ni-locations"
              />
            )}
          </Field>
          <datalist id="ni-locations">
            {locations.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </datalist>
          <Field label="Line description" htmlFor="ni-desc" required>
            {() => (
              <Input id="ni-desc" value={description} onChange={(e) => setDescription(e.target.value)} required />
            )}
          </Field>
          <Field label="Unit rate (INR)" htmlFor="ni-rate" required>
            {() => (
              <Input
                id="ni-rate"
                type="number"
                step="0.01"
                min="0"
                value={rate}
                onChange={(e) => setRate(e.target.value)}
                required
              />
            )}
          </Field>
          <p>
            <Button type="submit">Create draft</Button>
          </p>
        </form>
      </Card>
    </Shell>
  );
}
