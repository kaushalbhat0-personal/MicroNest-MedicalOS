"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  LoadingState,
  PageHeader,
  Select,
  Table,
  Td,
  Textarea,
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
  email: string | null;
  is_active: boolean;
  potential_duplicates?: string[];
};

export default function PatientsPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [activeFilter, setActiveFilter] = useState<"all" | "active" | "inactive">("active");
  const { data, loading, error, setError, reload, tenant } = useTenantApi<Patient[]>(
    (t) =>
      debounced
        ? `/api/v1/tenants/${t}/patients?limit=100&q=${encodeURIComponent(debounced)}`
        : `/api/v1/tenants/${t}/patients?limit=100`,
    [debounced],
  );
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [creating, setCreating] = useState(false);
  const [csvText, setCsvText] = useState("");
  const [importMsg, setImportMsg] = useState("");
  const [showImport, setShowImport] = useState(false);

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(query.trim()), 250);
    return () => window.clearTimeout(id);
  }, [query]);

  useEffect(() => {
    if (!tenant && typeof window !== "undefined") {
      router.push("/");
    }
  }, [tenant, router]);

  const items = useMemo(() => {
    const rows = data ?? [];
    if (activeFilter === "active") return rows.filter((p) => p.is_active);
    if (activeFilter === "inactive") return rows.filter((p) => !p.is_active);
    return rows;
  }, [data, activeFilter]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    const t = getSelectedTenant();
    if (!t) return;
    setError("");
    setCreating(true);
    try {
      const p = await api.post<Patient>(
        `/api/v1/tenants/${t}/patients`,
        {
          display_name: name,
          phone: phone || null,
          email: email || null,
        },
        t,
      );
      setName("");
      setPhone("");
      setEmail("");
      if (p.potential_duplicates && p.potential_duplicates.length > 0) {
        setError(
          `Registered, but similar phone/email already exists (${p.potential_duplicates.length} match). Review before merging manually.`,
        );
      }
      router.push(`/patients/${p.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCreating(false);
    }
  }

  async function importCsv(e: React.FormEvent) {
    e.preventDefault();
    const t = getSelectedTenant();
    if (!t) return;
    setError("");
    setImportMsg("");
    const lines = csvText
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean);
    if (lines.length === 0) {
      setError("Paste CSV rows: display_name,phone,email");
      return;
    }
    const start = lines[0].toLowerCase().includes("display_name") ? 1 : 0;
    const rows = [];
    for (const line of lines.slice(start)) {
      const [display_name, phoneVal, emailVal] = line.split(",").map((c) => c.trim());
      if (!display_name) continue;
      rows.push({
        display_name,
        phone: phoneVal || null,
        email: emailVal || null,
      });
    }
    try {
      const res = await api.post<{ created: number; skipped: number; errors: number }>(
        `/api/v1/tenants/${t}/patients/import`,
        { rows },
        t,
      );
      setImportMsg(
        `Import finished: ${res.created} created, ${res.skipped} skipped duplicates, ${res.errors} errors.`,
      );
      setCsvText("");
      reload();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Shell>
      <PageHeader
        title="Patients"
        description="Find a patient quickly, open their chart, or register someone new."
        actions={
          <Button
            type="button"
            size="sm"
            onClick={() => document.getElementById("register-patient")?.scrollIntoView({ behavior: "smooth" })}
          >
            Register
          </Button>
        }
      />
      <Card title="Patient directory">
        {error ? (
          <Alert tone="danger" title="Something went wrong">
            {error}
          </Alert>
        ) : null}
        {importMsg ? <Alert tone="success" title="Import">{importMsg}</Alert> : null}
        <div className="hos-filter-row">
          <Field label="Search (name, phone, or email)" htmlFor="q">
            {() => (
              <Input
                id="q"
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Type to search"
                autoComplete="off"
              />
            )}
          </Field>
          <Field label="Status" htmlFor="active-filter">
            {() => (
              <Select
                id="active-filter"
                value={activeFilter}
                onChange={(e) => setActiveFilter(e.target.value as typeof activeFilter)}
                options={[
                  { value: "active", label: "Active" },
                  { value: "inactive", label: "Inactive" },
                  { value: "all", label: "All" },
                ]}
              />
            )}
          </Field>
        </div>
        <p className="hos-helper" role="status">
          {loading
            ? "Searching…"
            : `${items.length} patient${items.length === 1 ? "" : "s"} shown (max 100 from server)`}
        </p>
        {loading ? (
          <LoadingState label="Loading patients" />
        ) : items.length === 0 ? (
          <EmptyState
            title={debounced ? "No matching patients" : "No patients yet"}
            action={
              <Button
                type="button"
                size="sm"
                onClick={() =>
                  document.getElementById("register-patient")?.scrollIntoView({ behavior: "smooth" })
                }
              >
                Register patient
              </Button>
            }
          >
            {debounced ? "Try a different name, phone, or email." : "Register the first patient below."}
          </EmptyState>
        ) : (
          <Table
            caption="Patients"
            density="compact"
            columns={
              <>
                <Th>Name</Th>
                <Th>Phone</Th>
                <Th>Email</Th>
                <Th>Status</Th>
                <Th>Open</Th>
              </>
            }
          >
            {items.map((p) => (
              <tr key={p.id}>
                <Td>
                  <Link
                    href={`/patients/${p.id}`}
                    className="hos-truncate"
                    title={p.display_name}
                  >
                    {p.display_name}
                  </Link>
                </Td>
                <Td>{p.phone ?? "—"}</Td>
                <Td>
                  <span className="hos-truncate" title={p.email ?? undefined}>
                    {p.email ?? "—"}
                  </span>
                </Td>
                <Td>{p.is_active ? "Active" : "Inactive"}</Td>
                <Td>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    onClick={() => router.push(`/patients/${p.id}`)}
                  >
                    Chart
                  </Button>
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <div id="register-patient">
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
                autoComplete="name"
              />
            )}
          </Field>
          <Field label="Phone" htmlFor="phone">
            {() => (
              <Input
                id="phone"
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                autoComplete="tel"
              />
            )}
          </Field>
          <Field label="Email" htmlFor="email">
            {() => (
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
              />
            )}
          </Field>
          <p>
            <Button type="submit" loading={creating}>
              Register and open chart
            </Button>
          </p>
        </form>
      </Card>
      </div>
      <Card
        title="Import from CSV"
        actions={
          <Button type="button" size="sm" variant="secondary" onClick={() => setShowImport((v) => !v)}>
            {showImport ? "Hide" : "Show"}
          </Button>
        }
      >
        {showImport ? (
          <>
            <p className="hos-helper">
              Paste rows as display_name,phone,email. Header row optional. Duplicates by phone/email
              are skipped.
            </p>
            <form onSubmit={importCsv}>
              <Field label="CSV rows" htmlFor="csv">
                {() => (
                  <Textarea
                    id="csv"
                    rows={5}
                    value={csvText}
                    onChange={(e) => setCsvText(e.target.value)}
                    placeholder={"display_name,phone,email\nAda,+91...,ada@example.com"}
                  />
                )}
              </Field>
              <p>
                <Button type="submit" variant="secondary">
                  Import
                </Button>
              </p>
            </form>
          </>
        ) : (
          <p className="hos-helper">Optional bulk import for reception setup. Expand to paste rows.</p>
        )}
      </Card>
    </Shell>
  );
}
