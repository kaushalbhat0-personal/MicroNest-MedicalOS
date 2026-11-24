"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  MoneyDisplay,
  PageHeader,
  Select,
  Status,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { api, type Me } from "@/lib/api";
import { canAccessOperations, hasPerm } from "@/lib/nav";
import { type PortalWorkspaces } from "@/lib/portal";
import { getSelectedTenant, setSelectedTenant } from "@/lib/tenant";
import { fetchWorkspaceContext } from "@/lib/workspace";
import { Shell } from "./shell";

type TenantDetail = { name: string; slug: string; status: string };
type Location = { id: string; name: string };
type AppointmentMetrics = {
  scheduled_today: number;
  waiting: number;
  checked_in: number;
  completed: number;
  no_show: number;
};
type FollowUpMetrics = { due_today: number; overdue: number; upcoming: number };
type BillingMetrics = {
  outstanding_invoice_count: number;
  outstanding_amount: string;
  currency: string;
};
type AppointmentRow = {
  id: string;
  start_at: string;
  status: string;
  patient_id: string;
  patient_display_name: string;
  practitioner_display_name: string;
  queue_token: number | null;
};
type Dashboard = {
  location_id: string;
  location_name: string;
  service_date: string;
  timezone: string;
  appointments: AppointmentMetrics | null;
  reception: AppointmentMetrics | null;
  follow_ups: FollowUpMetrics | null;
  billing: BillingMetrics | null;
  todays_appointments: AppointmentRow[];
  sections_omitted: string[];
};

export default function HomePage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [tenant, setTenant] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState<TenantDetail | null>(null);
  const [locations, setLocations] = useState<Location[]>([]);
  const [locationId, setLocationId] = useState("");
  const [permissions, setPermissions] = useState<string[]>([]);
  const [opsReady, setOpsReady] = useState(false);
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [dashLoading, setDashLoading] = useState(false);
  const [dashError, setDashError] = useState("");

  useEffect(() => {
    api
      .get<Me>("/api/v1/auth/me")
      .then(async (m) => {
        setMe(m);
        const ws = await api
          .get<PortalWorkspaces>("/api/v1/portal/workspaces")
          .catch(() => null);
        if (ws && ws.portal && !ws.provider) {
          router.push("/portal");
          return;
        }
        const sel = getSelectedTenant();
        const next = sel ?? (m.tenants.length === 1 ? m.tenants[0].id : null);
        if (next && !sel) setSelectedTenant(next);
        setTenant(next);
      })
      .catch(() => router.push("/login"));
  }, [router]);

  useEffect(() => {
    if (!tenant) {
      setPermissions([]);
      setOpsReady(false);
      setDash(null);
      return;
    }
    api.get<TenantDetail>(`/api/v1/tenants/${tenant}`, tenant).then(setDetail).catch(() => {});
    api
      .get<Location[]>(`/api/v1/tenants/${tenant}/locations`, tenant)
      .then((locs) => {
        setLocations(locs);
        setLocationId((prev) => prev || locs[0]?.id || "");
      })
      .catch(() => {});
    fetchWorkspaceContext(tenant)
      .then((ctx) => {
        setPermissions(ctx.permissions);
        setOpsReady(true);
      })
      .catch((e: Error) => {
        setError(e.message);
        setOpsReady(true);
      });
  }, [tenant]);

  const loadDash = useCallback(() => {
    if (!tenant || !locationId || !canAccessOperations(permissions)) {
      setDash(null);
      return;
    }
    setDashLoading(true);
    setDashError("");
    api
      .get<Dashboard>(
        `/api/v1/tenants/${tenant}/locations/${locationId}/operations-dashboard`,
        tenant,
      )
      .then(setDash)
      .catch((e: Error) => {
        setDash(null);
        setDashError(e.message);
      })
      .finally(() => setDashLoading(false));
  }, [tenant, locationId, permissions]);

  useEffect(() => {
    loadDash();
  }, [loadDash]);

  if (!me) return <LoadingState label="Loading" />;

  function pick(id: string) {
    setSelectedTenant(id);
    setTenant(id);
  }

  const showOps = canAccessOperations(permissions);
  const canPatients = hasPerm(permissions, "patient.read");
  const canAppts = hasPerm(permissions, "appointment.read");
  const canFollowUps = hasPerm(permissions, "followup.read");
  const canBilling = hasPerm(permissions, "billing.read");
  const a = dash?.appointments ?? dash?.reception ?? null;
  const f = dash?.follow_ups ?? null;
  const b = dash?.billing ?? null;
  const todays = dash?.todays_appointments ?? [];
  const needsAttention =
    (a?.waiting ?? 0) + (a?.checked_in ?? 0) + (f?.overdue ?? 0) + (f?.due_today ?? 0);

  return (
    <Shell>
      <PageHeader
        title="Clinic dashboard"
        description={
          detail
            ? `${detail.name} — what needs attention today`
            : "Select a workspace to continue clinic work"
        }
        actions={
          tenant && showOps ? (
            <Button type="button" size="sm" variant="secondary" onClick={loadDash}>
              Refresh
            </Button>
          ) : null
        }
      />
      {error ? (
        <Alert tone="danger" title="Workspace context failed">
          {error}
        </Alert>
      ) : null}

      {tenant ? (
        <div className="hos-quick-actions" aria-label="Quick actions">
          {canPatients ? (
            <Button type="button" onClick={() => router.push("/patients")}>
              Register patient
            </Button>
          ) : null}
          {canAppts ? (
            <Button type="button" variant="secondary" onClick={() => router.push("/schedule")}>
              Book appointment
            </Button>
          ) : null}
          {canAppts ? (
            <Button type="button" variant="secondary" onClick={() => router.push("/reception")}>
              Open reception
            </Button>
          ) : null}
          {canAppts ? (
            <Button
              type="button"
              variant="secondary"
              onClick={() => router.push("/schedule?walkin=1")}
            >
              Walk-in
            </Button>
          ) : null}
          {canFollowUps ? (
            <Button type="button" variant="secondary" onClick={() => router.push("/follow-ups")}>
              Follow-ups
            </Button>
          ) : null}
        </div>
      ) : null}

      {tenant && opsReady && showOps ? (
        <Card
          title="Today’s attention"
          actions={
            <Button type="button" variant="secondary" size="sm" onClick={() => router.push("/operations")}>
              Full operations
            </Button>
          }
        >
          {locations.length > 0 ? (
            <Field label="Focus location (service day)" htmlFor="home-location">
              {({ describedBy }) => (
                <Select
                  id="home-location"
                  aria-describedby={describedBy}
                  value={locationId}
                  onChange={(e) => setLocationId(e.target.value)}
                  options={locations.map((l) => ({ value: l.id, label: l.name }))}
                />
              )}
            </Field>
          ) : (
            <EmptyState title="No locations yet">
              Configure locations under Clinic settings when you have access.
            </EmptyState>
          )}

          {dashLoading ? <LoadingState label="Loading today’s clinic activity" /> : null}
          {dashError ? (
            <ErrorState title="Could not load today’s metrics" onRetry={loadDash}>
              {dashError}
            </ErrorState>
          ) : null}

          {!dashLoading && !dashError && locationId && dash ? (
            <>
              <p className="hos-helper" role="status">
                {dash.location_name} · service day <strong>{dash.service_date}</strong> (
                {dash.timezone})
                {needsAttention > 0
                  ? ` · ${needsAttention} item${needsAttention === 1 ? "" : "s"} may need action`
                  : " · no waiting or overdue follow-ups"}
              </p>
              <div className="hos-attention-grid">
                {a ? (
                  <>
                    <Link className="hos-attention-card" href="/schedule">
                      <p className="hos-attention-label">Scheduled today</p>
                      <p className="hos-attention-value">{a.scheduled_today}</p>
                    </Link>
                    <Link className="hos-attention-card" href="/reception">
                      <p className="hos-attention-label">Waiting now</p>
                      <p className="hos-attention-value">{a.waiting}</p>
                    </Link>
                    <Link className="hos-attention-card" href="/reception">
                      <p className="hos-attention-label">Checked in</p>
                      <p className="hos-attention-value">{a.checked_in}</p>
                    </Link>
                  </>
                ) : null}
                {f ? (
                  <Link className="hos-attention-card" href="/follow-ups">
                    <p className="hos-attention-label">Follow-ups due today</p>
                    <p className="hos-attention-value">{f.due_today}</p>
                  </Link>
                ) : null}
                {f ? (
                  <Link className="hos-attention-card" href="/follow-ups">
                    <p className="hos-attention-label">Overdue follow-ups</p>
                    <p className="hos-attention-value">{f.overdue}</p>
                  </Link>
                ) : null}
                {b && canBilling ? (
                  <Link className="hos-attention-card" href="/billing/invoices">
                    <p className="hos-attention-label">Outstanding invoices</p>
                    <p className="hos-attention-value">{b.outstanding_invoice_count}</p>
                    <p className="hos-helper">
                      <MoneyDisplay amount={b.outstanding_amount} currency={b.currency} />
                    </p>
                  </Link>
                ) : null}
              </div>

              {!a && !f && !(b && canBilling) ? (
                <EmptyState title="No operational metrics for your role">
                  Your permissions do not include appointment, follow-up, or billing summaries for
                  this location.
                </EmptyState>
              ) : null}

              {canAppts ? (
                <div style={{ marginTop: "var(--hos-space-4)" }}>
                  <h3 className="hos-page-title" style={{ fontSize: "var(--hos-text-h3)" }}>
                    Today’s appointments
                  </h3>
                  {todays.length === 0 ? (
                    <EmptyState
                      title="No appointments on this service day"
                      action={
                        <Button type="button" size="sm" onClick={() => router.push("/schedule")}>
                          Book appointment
                        </Button>
                      }
                    />
                  ) : (
                    <Table
                      caption="Today’s appointments"
                      density="compact"
                      columns={
                        <>
                          <Th>Time</Th>
                          <Th>Patient</Th>
                          <Th>Practitioner</Th>
                          <Th>Token</Th>
                          <Th>Status</Th>
                        </>
                      }
                    >
                      {todays.map((row) => (
                        <tr key={row.id}>
                          <Td>
                            <time dateTime={row.start_at}>
                              {new Date(row.start_at).toLocaleTimeString([], {
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </time>
                          </Td>
                          <Td>
                            <Link href={`/patients/${row.patient_id}`} className="hos-truncate">
                              {row.patient_display_name}
                            </Link>
                          </Td>
                          <Td>{row.practitioner_display_name}</Td>
                          <Td>{row.queue_token ?? "—"}</Td>
                          <Td>
                            <Status value={row.status} />
                          </Td>
                        </tr>
                      ))}
                    </Table>
                  )}
                </div>
              ) : null}

              {dash.sections_omitted?.length ? (
                <p className="hos-helper">
                  Some sections were omitted by the server based on your permissions.
                </p>
              ) : null}
            </>
          ) : null}
        </Card>
      ) : null}

      {tenant && opsReady && !showOps ? (
        <Card title="Today’s attention">
          <EmptyState title="No operations access">
            Your role does not include clinic operations metrics. Use Sessions or ask an
            administrator for access.
          </EmptyState>
        </Card>
      ) : null}

      <Card title="Workspace">
        <Field label="Current clinic workspace" htmlFor="tenant">
          {({ describedBy }) => (
            <Select
              id="tenant"
              aria-describedby={describedBy}
              value={tenant ?? ""}
              onChange={(e) => pick(e.target.value)}
              options={[
                { value: "", label: "Select a workspace" },
                ...me.tenants.map((t) => ({
                  value: t.id,
                  label: `${t.name} (${t.slug})`,
                })),
              ]}
            />
          )}
        </Field>
        {!tenant ? (
          <EmptyState
            title="No workspace selected"
            action={
              <Button type="button" onClick={() => router.push("/onboarding")}>
                Create clinic workspace
              </Button>
            }
          >
            Choose a clinic workspace above, or create a new one. Setup is saved on the server.
          </EmptyState>
        ) : detail ? (
          <p className="hos-helper">
            {detail.name} · {detail.slug} · <Status value={detail.status} /> ·{" "}
            <Link href="/onboarding">Continue setup</Link>
          </p>
        ) : null}
        {me.tenants.length === 0 ? (
          <p>
            <Button type="button" onClick={() => router.push("/onboarding")}>
              Start clinic onboarding
            </Button>
          </p>
        ) : null}
      </Card>
    </Shell>
  );
}
