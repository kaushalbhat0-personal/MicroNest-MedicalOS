"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  LoadingState,
  PageHeader,
  Status,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { api, type Me } from "@/lib/api";
import { type PortalWorkspaces } from "@/lib/portal";
import { getSelectedTenant, setSelectedTenant } from "@/lib/tenant";
import { Shell } from "./shell";

type Appointment = { id: string; start_at: string; status: string; patient_id: string };
type TenantDetail = { name: string; slug: string; status: string };
type Location = { id: string; name: string };

function startOfToday(): string {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}

function startOfTomorrow(): string {
  const d = new Date();
  d.setHours(24, 0, 0, 0);
  return d.toISOString();
}

export default function HomePage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [tenant, setTenant] = useState<string | null>(null);
  const [today, setToday] = useState<Appointment[]>([]);
  const [todayLoading, setTodayLoading] = useState(false);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState<TenantDetail | null>(null);
  const [locations, setLocations] = useState<Location[]>([]);

  useEffect(() => {
    api
      .get<Me>("/api/v1/auth/me")
      .then(async (m) => {
        setMe(m);
        // Portal-only identities are routed to the portal; provider chrome
        // would only show them permission errors. Server is authoritative.
        const ws = await api
          .get<PortalWorkspaces>("/api/v1/portal/workspaces")
          .catch(() => null);
        if (ws && ws.portal && !ws.provider) {
          router.push("/portal");
          return;
        }
        const sel = getSelectedTenant();
        setTenant(sel ?? (m.tenants.length === 1 ? m.tenants[0].id : null));
      })
      .catch(() => router.push("/login"));
  }, [router]);

  useEffect(() => {
    if (!tenant) return;
    setTodayLoading(true);
    api
      .get<{ items: Appointment[] }>(
        `/api/v1/tenants/${tenant}/appointments?start_from=${encodeURIComponent(startOfToday())}&start_to=${encodeURIComponent(startOfTomorrow())}&limit=50`,
        tenant,
      )
      .then((r) => setToday(r.items))
      .catch((e: Error) => setError(e.message))
      .finally(() => setTodayLoading(false));
    api.get<TenantDetail>(`/api/v1/tenants/${tenant}`, tenant).then(setDetail).catch(() => {});
    api
      .get<Location[]>(`/api/v1/tenants/${tenant}/locations`, tenant)
      .then(setLocations)
      .catch(() => {});
  }, [tenant]);

  if (!me) return <LoadingState label="Loading" />;

  function pick(id: string) {
    setSelectedTenant(id);
    setTenant(id);
  }

  async function logout() {
    await api.post("/api/v1/auth/logout");
    setSelectedTenant(null);
    router.push("/login");
  }

  const counts = today.reduce<Record<string, number>>((acc, a) => {
    acc[a.status] = (acc[a.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <Shell>
      <PageHeader
        title={`Welcome, ${me.display_name}`}
        description={me.email}
        actions={
          <Button variant="secondary" onClick={() => void logout()}>
            Sign out
          </Button>
        }
      />
      {error ? (
        <Alert tone="danger" title="Something went wrong">
          {error}
        </Alert>
      ) : null}
      <Card title="Tenant">
        <label htmlFor="tenant" className="hos-label">
          Tenant
        </label>
        <select
          id="tenant"
          className="hos-input"
          value={tenant ?? ""}
          onChange={(e) => pick(e.target.value)}
        >
          <option value="" disabled>
            Select a tenant
          </option>
          {me.tenants.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name} ({t.slug})
            </option>
          ))}
        </select>
        {!tenant && <p>Select a tenant to continue.</p>}
        {detail ? (
          <p>
            {detail.name} - {detail.slug} - <Status value={detail.status} />
          </p>
        ) : null}
        {locations.length > 0 ? (
          <>
            <h3>Locations</h3>
            <ul>
              {locations.map((l) => (
                <li key={l.id}>{l.name}</li>
              ))}
            </ul>
          </>
        ) : null}
      </Card>
      {tenant ? (
        <Card
          title="Today"
          actions={<Link href="/schedule">Open schedule</Link>}
        >
          {todayLoading ? (
            <LoadingState label="Loading today's appointments" />
          ) : today.length === 0 ? (
            <EmptyState title="Nothing scheduled today">
              Book the first appointment from the schedule.
            </EmptyState>
          ) : (
            <>
              <p>
                {Object.entries(counts).map(([s, n]) => (
                  <span key={s} style={{ marginRight: 8 }}>
                    <Status value={s} /> x {n}
                  </span>
                ))}
              </p>
              <Table
                caption="Today's appointments"
                density="compact"
                columns={
                  <>
                    <Th>When</Th>
                    <Th>Status</Th>
                  </>
                }
              >
                {today.slice(0, 8).map((a) => (
                  <tr key={a.id}>
                    <Td>{new Date(a.start_at).toLocaleTimeString()}</Td>
                    <Td>
                      <Status value={a.status} />
                    </Td>
                  </tr>
                ))}
              </Table>
            </>
          )}
        </Card>
      ) : null}
    </Shell>
  );
}
