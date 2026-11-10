"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  LoadingState,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { Shell } from "../shell";
import { useTenantApi } from "@/lib/use-api";

type Patient = {
  id: string;
  tenant_id: string;
  display_name: string;
  phone: string | null;
  is_active: boolean;
};

export default function PatientsPage() {
  const router = useRouter();
  const { data, loading, error, setError, reload, tenant } = useTenantApi<Patient[]>(
    (t) => `/api/v1/tenants/${t}/patients?limit=100`,
  );
  const [query, setQuery] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (!tenant && typeof window !== "undefined") {
      router.push("/");
    }
  }, [tenant, router]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    const t = getSelectedTenant();
    if (!t) return;
    setError("");
    setCreating(true);
    try {
      await api.post<Patient>(
        `/api/v1/tenants/${t}/patients`,
        { display_name: name, phone: phone || null },
        t,
      );
      setName("");
      setPhone("");
      reload();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCreating(false);
    }
  }

  const items = (data ?? []).filter((p) => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return (
      p.display_name.toLowerCase().includes(q) || (p.phone ?? "").toLowerCase().includes(q)
    );
  });

  return (
    <Shell>
      <Card title="Patients">
        {error ? (
          <Alert tone="danger" title="Something went wrong">
            {error}
          </Alert>
        ) : null}
        <Field label="Search (name or phone, this list)" htmlFor="q">
          {() => (
            <Input
              id="q"
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Type to filter the loaded list"
            />
          )}
        </Field>
        {loading ? (
          <LoadingState label="Loading patients" />
        ) : items.length === 0 ? (
          <EmptyState title="No patients found">
            {query ? "Try a different search." : "Register the first patient below."}
          </EmptyState>
        ) : (
          <Table
            caption="Patients"
            columns={
              <>
                <Th>Name</Th>
                <Th>Phone</Th>
                <Th>Active</Th>
              </>
            }
          >
            {items.map((p) => (
              <tr key={p.id}>
                <Td>
                  <Link href={`/patients/${p.id}`}>{p.display_name}</Link>
                </Td>
                <Td>{p.phone ?? "-"}</Td>
                <Td>{p.is_active ? "yes" : "no"}</Td>
              </tr>
            ))}
          </Table>
        )}
        <p className="hos-helper">
          Server-side search is not available yet - filtering applies to the loaded list.
          Patient editing is not supported by the API yet.
        </p>
      </Card>
      <Card title="Register patient">
        <form onSubmit={create}>
          <Field label="Display name" htmlFor="name" required>
            {() => (
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                minLength={2}
                maxLength={200}
              />
            )}
          </Field>
          <Field label="Phone" htmlFor="phone" description="Optional contact number.">
            {({ describedBy }) => (
              <Input
                id="phone"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                aria-describedby={describedBy}
              />
            )}
          </Field>
          <p>
            <Button type="submit" loading={creating}>
              Register
            </Button>
          </p>
        </form>
      </Card>
    </Shell>
  );
}
