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
  Status,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { useTenantApi } from "@/lib/use-api";
import { Shell } from "../../shell";

type Estimate = {
  id: string;
  status: string;
  currency: string;
  grand_total: string;
  valid_until: string | null;
};

export default function EstimatesPage() {
  const router = useRouter();
  const { data, loading, error } = useTenantApi<{ items: Estimate[] }>(
    (t) => `/api/v1/tenants/${t}/estimates?limit=50`,
  );
  const [patientId, setPatientId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [description, setDescription] = useState("Consultation");
  const [rate, setRate] = useState("500.00");

  async function create(e: React.FormEvent) {
    e.preventDefault();
    const t = getSelectedTenant();
    if (!t || !patientId || !locationId) {
      if (!t) router.push("/");
      return;
    }
    try {
      const created = await api.post<{ id: string }>(
        `/api/v1/tenants/${t}/estimates`,
        {
          patient_id: patientId,
          location_id: locationId,
          items: [{ description, quantity: "1", unit_rate: rate }],
        },
        t,
      );
      router.push(`/billing/estimates/${created.id}`);
    } catch (err) {
      alert((err as Error).message);
    }
  }

  return (
    <Shell>
      <PageHeader
        title="Estimates"
        description="Draft -> issued -> converted. Non-binding proposals; conversion snapshots lines into an invoice."
        actions={<Link href="/billing/invoices">Invoices</Link>}
      />
      {error ? (
        <Alert tone="danger" title="Something went wrong">
          {error}
        </Alert>
      ) : null}
      <Card title="All estimates">
        {loading ? (
          <LoadingState label="Loading estimates" />
        ) : (data?.items ?? []).length === 0 ? (
          <EmptyState title="No estimates" />
        ) : (
          <Table
            caption="Estimates"
            density="compact"
            columns={
              <>
                <Th>Estimate</Th>
                <Th>Status</Th>
                <Th numeric>Total</Th>
                <Th>Valid until</Th>
              </>
            }
          >
            {(data?.items ?? []).map((e) => (
              <tr key={e.id}>
                <Td>
                  <Link href={`/billing/estimates/${e.id}`}>{e.id.slice(0, 8)}...</Link>
                </Td>
                <Td>
                  <Status value={e.status} />
                </Td>
                <Td numeric>
                  <MoneyDisplay amount={e.grand_total} currency={e.currency} />
                </Td>
                <Td>{e.valid_until ?? "-"}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <Card title="New draft estimate">
        <form onSubmit={create}>
          <Field label="Patient ID" htmlFor="ne-patient" required>
            {() => (
              <Input id="ne-patient" value={patientId} onChange={(e) => setPatientId(e.target.value)} required />
            )}
          </Field>
          <Field label="Location ID" htmlFor="ne-location" required>
            {() => (
              <Input id="ne-location" value={locationId} onChange={(e) => setLocationId(e.target.value)} required />
            )}
          </Field>
          <Field label="Line description" htmlFor="ne-desc" required>
            {() => (
              <Input id="ne-desc" value={description} onChange={(e) => setDescription(e.target.value)} required />
            )}
          </Field>
          <Field label="Unit rate (INR)" htmlFor="ne-rate" required>
            {() => (
              <Input
                id="ne-rate"
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
