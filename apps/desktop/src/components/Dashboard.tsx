import { useEffect, useState } from "react";
import { Alert, Card, EmptyState, LoadingState } from "@healthcare-os/ui";
import {
  fetchOperationsDashboard,
  fetchTenantLocations,
  OpsDashboard,
} from "../lib/api";
import { dashboardVariant, hasPerm } from "../lib/nav";
import { useSession } from "../lib/session";

export function Dashboard({
  onSessionExpired,
}: {
  onSessionExpired: () => void;
}) {
  const { tenant, workspace } = useSession();
  const [dash, setDash] = useState<OpsDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [omitted, setOmitted] = useState<string[]>([]);

  const variant = dashboardVariant(workspace?.role, workspace?.permissions ?? []);
  const perms = workspace?.permissions ?? [];

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!tenant) {
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      setDash(null);
      try {
        const locs = await fetchTenantLocations(tenant.id);
        if (cancelled) return;
        const locId =
          workspace?.location_ids?.[0] ??
          locs[0]?.id ??
          null;
        if (!locId) {
          setError("No clinic location available for this workspace.");
          return;
        }
        if (!hasPerm(perms, "tenant.read")) {
          setError("Missing tenant.read for dashboard.");
          return;
        }
        const data = await fetchOperationsDashboard(tenant.id, locId);
        if (cancelled) return;
        if (!data) {
          setError(
            "Operations dashboard unavailable (permission or feature entitlement).",
          );
          return;
        }
        setDash(data);
        setOmitted(data.sections_omitted ?? []);
      } catch (e) {
        if (cancelled) return;
        if (String(e).includes("session_expired")) onSessionExpired();
        else setError("Failed to load dashboard.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenant?.id, workspace?.membership_id, workspace?.location_ids?.join(",")]);

  if (loading) return <LoadingState label="Loading dashboard" />;
  if (error) return <Alert tone="danger" title="Dashboard">{error}</Alert>;
  if (!dash) {
    return (
      <EmptyState title="No dashboard data">
        Authorized metrics will appear when APIs and permissions allow.
      </EmptyState>
    );
  }

  const appt = dash.appointments ?? dash.reception;
  const next = dash.todays_appointments?.[0];

  return (
    <div className="hos-dash">
      <header className="hos-dash-header">
        <h1>
          {variant === "doctor"
            ? "Doctor dashboard"
            : variant === "receptionist"
              ? "Reception dashboard"
              : variant === "admin"
                ? "Clinic operations"
                : "Dashboard"}
        </h1>
        <p className="hos-muted">
          {dash.location_name} · {dash.service_date} · role {workspace?.role ?? "—"}
        </p>
      </header>

      <div className="hos-dash-grid">
        {appt && (
          <Card title="Today">
            <ul className="hos-metric-list">
              <li>Scheduled: {appt.scheduled_today}</li>
              <li>Waiting: {appt.waiting}</li>
              <li>Checked in: {appt.checked_in}</li>
              {"completed" in appt ? <li>Completed: {appt.completed}</li> : null}
            </ul>
          </Card>
        )}
        {dash.follow_ups && hasPerm(perms, "followup.read") && (
          <Card title="Follow-ups">
            <ul className="hos-metric-list">
              <li>Due today: {dash.follow_ups.due_today}</li>
              <li>Overdue: {dash.follow_ups.overdue}</li>
              <li>Upcoming: {dash.follow_ups.upcoming}</li>
            </ul>
          </Card>
        )}
        {dash.billing && hasPerm(perms, "billing.read") && (
          <Card title="Billing attention">
            <ul className="hos-metric-list">
              <li>
                Outstanding invoices: {dash.billing.outstanding_invoice_count}
              </li>
              <li>
                Outstanding: {dash.billing.outstanding_amount}{" "}
                {dash.billing.currency}
              </li>
              <li>Payments today: {dash.billing.payments_today_count}</li>
            </ul>
          </Card>
        )}
      </div>

      {(variant === "doctor" || variant === "receptionist" || variant === "generic") && (
        <Card title="Next / today’s appointments">
          {!dash.todays_appointments?.length ? (
            <EmptyState title="No appointments on this service day" />
          ) : (
            <table className="hos-table">
              <caption className="hos-sr-only">Today’s appointments</caption>
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Patient</th>
                  <th scope="col">Practitioner</th>
                  <th scope="col">Status</th>
                  {variant === "receptionist" ? <th scope="col">Token</th> : null}
                </tr>
              </thead>
              <tbody>
                {dash.todays_appointments.slice(0, 12).map((row) => (
                  <tr key={row.id}>
                    <td>{new Date(row.start_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</td>
                    <td>{row.patient_display_name}</td>
                    <td>{row.practitioner_display_name}</td>
                    <td>{row.status}</td>
                    {variant === "receptionist" ? (
                      <td>{row.queue_token ?? "—"}</td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {next && variant === "doctor" ? (
            <p className="hos-muted">
              Next: {next.patient_display_name} at{" "}
              {new Date(next.start_at).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </p>
          ) : null}
        </Card>
      )}

      {variant === "receptionist" && (
        <Card title="Quick actions">
          <p className="hos-muted">
            Full patient registration, booking, and check-in modules arrive in
            later milestones. Use web clinic app for complete workflows until then.
          </p>
        </Card>
      )}

      {variant === "admin" && (
        <Card title="Admin shortcuts">
          <ul className="hos-metric-list">
            <li>
              Staff nav:{" "}
              {hasPerm(perms, "staff.manage", "staff.invite") ? "available" : "hidden"}
            </li>
            <li>
              Inventory nav:{" "}
              {hasPerm(perms, "inventory.read") ? "available" : "hidden"}
            </li>
            <li>
              Settings nav:{" "}
              {hasPerm(perms, "settings.manage", "roles.manage", "locations.manage", "audit.read")
                ? "available"
                : "hidden"}
            </li>
          </ul>
        </Card>
      )}

      {omitted.length > 0 && (
        <p className="hos-caption">Sections omitted by permission: {omitted.join(", ")}</p>
      )}
    </div>
  );
}
