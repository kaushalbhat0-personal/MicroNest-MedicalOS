"use client";
import { useState } from "react";
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
  Td,
  Th,
  PageHeader,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { useTenantApi } from "@/lib/use-api";
import { Shell } from "../../shell";

type CatalogItem = {
  id: string;
  code: string;
  display: string;
  description: string | null;
  default_rate: string;
  currency: string;
  is_active: boolean;
};

export default function CatalogPage() {
  const { data, loading, error, reload } = useTenantApi<{ items: CatalogItem[] }>(
    (t) => `/api/v1/tenants/${t}/service-catalog?limit=100`,
  );
  const [q, setQ] = useState("");
  const [code, setCode] = useState("");
  const [display, setDisplay] = useState("");
  const [rate, setRate] = useState("100.00");

  async function create(e: React.FormEvent) {
    e.preventDefault();
    const t = getSelectedTenant();
    if (!t) return;
    try {
      await api.post(
        `/api/v1/tenants/${t}/service-catalog`,
        { code, display, default_rate: rate },
        t,
      );
      setCode("");
      setDisplay("");
      reload();
    } catch (err) {
      alert((err as Error).message);
    }
  }

  async function toggle(item: CatalogItem) {
    const t = getSelectedTenant();
    if (!t) return;
    try {
      await api.post(
        `/api/v1/tenants/${t}/service-catalog/${item.id}/${item.is_active ? "deactivate" : "activate"}`,
        {},
        t,
      );
      reload();
    } catch (err) {
      alert((err as Error).message);
    }
  }

  return (
    <Shell>
      <PageHeader title="Service catalog" description="Global charge master. Rates snapshot into documents; edits never rewrite history." />
      {error ? (
        <Alert tone="danger" title="Something went wrong">
          {error}
        </Alert>
      ) : null}
      <Card title="Services">
        <Field label="Search" htmlFor="cat-q">
          {() => (
            <Input
              id="cat-q"
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Filter by code or name"
            />
          )}
        </Field>
        {loading ? (
          <LoadingState label="Loading catalog" />
        ) : (data?.items ?? []).length === 0 ? (
          <EmptyState title="No services" />
        ) : (
          <Table
            caption="Service catalog"
            density="clinical-dense"
            columns={
              <>
                <Th>Code</Th>
                <Th>Display</Th>
                <Th numeric>Rate</Th>
                <Th>Status</Th>
                <Th>Actions</Th>
              </>
            }
          >
            {(data?.items ?? [])
              .filter(
                (i) =>
                  !q ||
                  i.code.toLowerCase().includes(q.toLowerCase()) ||
                  i.display.toLowerCase().includes(q.toLowerCase()),
              )
              .map((i) => (
                <tr key={i.id}>
                  <Td>{i.code}</Td>
                  <Td>{i.display}</Td>
                  <Td numeric>
                    {i.currency} {i.default_rate}
                  </Td>
                  <Td>
                    <Status value={i.is_active ? "current" : "revoked"} />
                  </Td>
                  <Td>
                    <Button size="sm" variant="secondary" onClick={() => void toggle(i)}>
                      {i.is_active ? "Deactivate" : "Activate"}
                    </Button>
                  </Td>
                </tr>
              ))}
          </Table>
        )}
      </Card>
      <Card title="New service">
        <form onSubmit={create}>
          <Field label="Code" htmlFor="svc-code" required>
            {() => <Input id="svc-code" value={code} onChange={(e) => setCode(e.target.value)} required maxLength={40} />}
          </Field>
          <Field label="Display" htmlFor="svc-display" required>
            {() => (
              <Input id="svc-display" value={display} onChange={(e) => setDisplay(e.target.value)} required maxLength={200} />
            )}
          </Field>
          <Field label="Default rate (INR)" htmlFor="svc-rate" required>
            {() => (
              <Input
                id="svc-rate"
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
            <Button type="submit">Create service</Button>
          </p>
        </form>
      </Card>
    </Shell>
  );
}
