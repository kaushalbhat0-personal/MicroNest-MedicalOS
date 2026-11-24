"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  LoadingState,
  PageHeader,
  Status,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { Shell } from "../shell";

type Location = { id: string; name: string; timezone?: string };
type AppointmentMetrics = {
  scheduled_today: number;
  waiting: number;
  checked_in: number;
  in_consultation: number;
  completed: number;
  cancelled: number;
  no_show: number;
};
type FollowUpMetrics = { due_today: number; overdue: number; upcoming: number };
type BillingMetrics = {
  outstanding_invoice_count: number;
  outstanding_amount: string;
  currency: string;
  payments_today_count: number;
  payments_today_amount: string;
};
type AppointmentRow = {
  id: string;
  start_at: string;
  status: string;
  patient_id: string;
  patient_display_name: string;
  practitioner_display_name: string;
  queue_token: number | null;
  notes: string | null;
};
type PractitionerWindow = {
  practitioner_id: string;
  display_name: string;
  verification_status: string;
  staff_windows: string[];
};
type AppointmentListMeta = {
  total: number;
  returned: number;
  truncated: boolean;
  limit: number;
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
  availability: {
    clinic_hours: { start_local: string; end_local: string }[];
    practitioners: PractitionerWindow[];
  } | null;
  todays_appointments: AppointmentRow[];
  appointments_list: AppointmentListMeta | null;
  sections_omitted: string[];
  follow_up_day_basis: string | null;
};

function MetricCard({ label, value, href }: { label: string; value: string | number; href?: string }) {
  const inner = (
    <div style={{ padding: "0.75rem 0" }}>
      <div style={{ color: "var(--hos-text-muted)", fontSize: "0.85rem" }}>{label}</div>
      <div style={{ fontSize: "1.5rem", fontWeight: 600 }}>{value}</div>
    </div>
  );
  return href ? <Link href={href}>{inner}</Link> : inner;
}

export default function OperationsPage() {
  const router = useRouter();
  const [tenant, setTenant] = useState<string | null>(null);
  const [locations, setLocations] = useState<Location[]>([]);
  const [locationId, setLocationId] = useState("");
  const [day, setDay] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [forbidden, setForbidden] = useState(false);

  const load = useCallback(
    async (tid: string, lid: string) => {
      setError("");
      setForbidden(false);
      setLoading(true);
      try {
        const qs = new URLSearchParams();
        if (day) qs.set("day", day);
        if (statusFilter) qs.set("status", statusFilter);
        const data = await api.get<Dashboard>(
          `/api/v1/tenants/${tid}/locations/${lid}/operations-dashboard?${qs}`,
          tid,
        );
        setDash(data);
      } catch (e) {
        const msg = (e as Error).message;
        if (/403|forbidden|permission/i.test(msg)) setForbidden(true);
        setError(msg);
        setDash(null);
      } finally {
        setLoading(false);
      }
    },
    [day, statusFilter],
  );

  useEffect(() => {
    const t = getSelectedTenant();
    if (!t) {
      router.push("/");
      return;
    }
    setTenant(t);
    api
      .get<Location[]>(`/api/v1/tenants/${t}/locations`, t)
      .then((locs) => {
        setLocations(locs);
        const first = locs[0]?.id || "";
        setLocationId((prev) => prev || first);
        if (locs[0]) return load(t, locs[0].id);
        setLoading(false);
      })
      .catch((e: Error) => {
        setError(e.message);
        setLoading(false);
      });
  }, [router, load]);

  useEffect(() => {
    if (tenant && locationId) void load(tenant, locationId);
  }, [tenant, locationId, load]);

  const a = dash?.appointments;

  return (
    <Shell>
      <PageHeader
        title="Operations"
        description="Today's clinic work — appointments, reception, follow-ups, billing"
        actions={
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <Button type="button" variant="secondary" onClick={() => router.push("/reception")}>
              Reception
            </Button>
            <Button type="button" variant="secondary" onClick={() => router.push("/schedule")}>
              Schedule
            </Button>
          </div>
        }
      />

      <div
        style={{
          display: "grid",
          gap: "0.75rem",
          gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
          marginBottom: "1rem",
        }}
      >
        <Field label="Location" htmlFor="ops-loc">
          {() => (
            <select
              id="ops-loc"
              className="hos-input"
              value={locationId}
              onChange={(e) => setLocationId(e.target.value)}
            >
              {locations.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="Service day" htmlFor="ops-day">
          {() => (
            <input
              id="ops-day"
              className="hos-input"
              type="date"
              value={day}
              onChange={(e) => setDay(e.target.value)}
            />
          )}
        </Field>
        <Field label="Status filter" htmlFor="ops-status">
          {() => (
            <select
              id="ops-status"
              className="hos-input"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">All</option>
              <option value="scheduled">Scheduled</option>
              <option value="confirmed">Confirmed</option>
              <option value="checked_in">Checked in</option>
              <option value="completed">Completed</option>
              <option value="cancelled">Cancelled</option>
              <option value="no_show">No-show</option>
            </select>
          )}
        </Field>
      </div>

      {loading ? <LoadingState label="Loading operations" /> : null}
      {forbidden ? (
        <Alert tone="danger" title="Permission denied">
          You do not have access to clinic operations for this workspace.
        </Alert>
      ) : null}
      {error && !forbidden ? (
        <Alert tone="danger" title="Could not load dashboard">
          {error}
        </Alert>
      ) : null}

      {!loading && dash ? (
        <>
          <p style={{ color: "var(--hos-text-muted)", marginBottom: "1rem" }}>
            {dash.location_name} · {dash.service_date} · {dash.timezone}
          </p>

          {a ? (
            <Card title="Today's overview">
              <div
                style={{
                  display: "grid",
                  gap: "0.5rem",
                  gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
                }}
              >
                <MetricCard label="Scheduled" value={a.scheduled_today} />
                <MetricCard label="Waiting" value={a.waiting} href="/reception" />
                <MetricCard label="Checked in" value={a.checked_in} href="/reception" />
                <MetricCard label="In consultation" value={a.in_consultation} href="/encounters" />
                <MetricCard label="Completed" value={a.completed} />
                <MetricCard label="Cancelled" value={a.cancelled} />
                <MetricCard label="No-shows" value={a.no_show} />
              </div>
            </Card>
          ) : null}

          <Card title="Today's appointments">
            {dash.appointments_list?.truncated ? (
              <Alert tone="warning" title="Partial list">
                Showing {dash.appointments_list.returned} of {dash.appointments_list.total}{" "}
                appointments for this service day (limit {dash.appointments_list.limit}). Totals
                above are complete. Open Reception or Schedule for the full board.
              </Alert>
            ) : null}
            {dash.todays_appointments.length === 0 ? (
              <EmptyState title="No appointments for this day" />
            ) : (
              <Table
                caption="Appointments"
                columns={
                  <>
                    <Th>Time</Th>
                    <Th>Patient</Th>
                    <Th>Practitioner</Th>
                    <Th>Status</Th>
                    <Th>Token</Th>
                    <Th>Actions</Th>
                  </>
                }
              >
                {dash.todays_appointments.map((row) => (
                  <tr key={row.id}>
                    <Td>{new Date(row.start_at).toLocaleTimeString()}</Td>
                    <Td>
                      <Link href={`/patients/${row.patient_id}`}>{row.patient_display_name}</Link>
                    </Td>
                    <Td>{row.practitioner_display_name}</Td>
                    <Td>
                      <Status value={row.status} />
                    </Td>
                    <Td>{row.queue_token ?? "—"}</Td>
                    <Td>
                      <Link href="/reception">Reception</Link>
                      {" · "}
                      <Link href="/schedule">Schedule</Link>
                    </Td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>

          {dash.reception ? (
            <Card title="Reception snapshot">
              <p>
                Waiting {dash.reception.waiting} · Checked in {dash.reception.checked_in} ·
                Completed {dash.reception.completed} · No-show {dash.reception.no_show}
              </p>
              <Button type="button" onClick={() => router.push("/reception")}>
                Open reception board
              </Button>
            </Card>
          ) : null}

          {dash.follow_ups ? (
            <Card title="Follow-ups (location service day)">
              <p style={{ color: "var(--hos-text-muted)", fontSize: "0.85rem", marginBottom: "0.5rem" }}>
                These KPIs use this location&apos;s timezone midnight–midnight
                {dash.timezone ? ` (${dash.timezone})` : ""}
                {dash.follow_up_day_basis === "location_service_day"
                  ? " — location service day"
                  : ""}
                . The Follow-ups workspace lists use UTC calendar-day buckets and may disagree near
                midnight.
              </p>
              <div
                style={{
                  display: "grid",
                  gap: "0.5rem",
                  gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
                }}
              >
                <MetricCard
                  label="Due on service day"
                  value={dash.follow_ups.due_today}
                  href="/follow-ups"
                />
                <MetricCard label="Overdue" value={dash.follow_ups.overdue} href="/follow-ups" />
                <MetricCard label="Upcoming" value={dash.follow_ups.upcoming} href="/follow-ups" />
              </div>
            </Card>
          ) : null}

          {dash.billing ? (
            <Card title="Billing snapshot">
              <p>
                Outstanding invoices: {dash.billing.outstanding_invoice_count} (
                {dash.billing.currency} {dash.billing.outstanding_amount})
              </p>
              <p>
                Payments today: {dash.billing.payments_today_count} (
                {dash.billing.currency} {dash.billing.payments_today_amount})
              </p>
              <Button type="button" variant="secondary" onClick={() => router.push("/billing/invoices")}>
                Open billing
              </Button>
            </Card>
          ) : null}

          {dash.availability ? (
            <Card title="Availability">
              <p style={{ color: "var(--hos-text-muted)" }}>
                Clinic hours are location open windows. Staff windows are employment schedules.
                Practitioner booking uses verified practitioners + free slots separately.
              </p>
              {dash.availability.clinic_hours.length === 0 ? (
                <p>No clinic hours configured for this weekday.</p>
              ) : (
                <ul>
                  {dash.availability.clinic_hours.map((h, i) => (
                    <li key={i}>
                      {String(h.start_local).slice(0, 5)} – {String(h.end_local).slice(0, 5)}
                    </li>
                  ))}
                </ul>
              )}
              {dash.availability.practitioners.length === 0 ? (
                <EmptyState title="No approved practitioners" />
              ) : (
                <ul>
                  {dash.availability.practitioners.map((p) => (
                    <li key={p.practitioner_id}>
                      {p.display_name}{" "}
                      <Badge tone="success">{p.verification_status}</Badge>
                      {p.staff_windows.length
                        ? ` · staff ${p.staff_windows.join(", ")}`
                        : ""}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          ) : null}

          {dash.sections_omitted.length > 0 ? (
            <p style={{ color: "var(--hos-text-muted)", fontSize: "0.85rem" }}>
              Hidden for your role: {dash.sections_omitted.join(", ")}
            </p>
          ) : null}
        </>
      ) : null}

      {!loading && !dash && !error && locations.length === 0 ? (
        <EmptyState title="No locations available" />
      ) : null}
    </Shell>
  );
}
