"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  LoadingState,
  PageHeader,
  Table,
  Td,
  Th,
  presentStatus,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { useTenantApi } from "@/lib/use-api";
import { Shell } from "../shell";

type Location = { id: string; name: string; timezone: string; is_active: boolean };
type Role = { id: string; name: string; permissions: string[]; is_seed: boolean };
type AuditEvent = {
  id: string;
  occurred_at: string;
  action: string;
  resource_type: string;
  resource_id: string;
  actor_type: string;
  result: string;
};
type PlanLimits = {
  max_locations: number;
  max_practitioners: number;
  max_staff_seats: number;
  enforced: boolean;
};
type SubscriptionSummary = {
  status: string;
  trial_ends_at: string | null;
  plan_code: string;
  plan_name: string;
  trial_starts_at: string | null;
  is_in_trial: boolean;
  limits: PlanLimits | null;
};
type SpecialtyDetail = {
  code: string;
  pack_version: string;
  label: string;
  maturity: string;
  ready_for_use: boolean;
};
type TenantDetail = {
  id: string;
  name: string;
  slug: string;
  status: string;
  subscription: SubscriptionSummary | null;
  specialties_enabled: string[];
  specialties: SpecialtyDetail[];
};

export default function AdminPage() {
  const router = useRouter();
  const locations = useTenantApi<Location[]>((t) => `/api/v1/tenants/${t}/locations`);
  const roles = useTenantApi<Role[]>((t) => `/api/v1/tenants/${t}/roles`);
  const audit = useTenantApi<AuditEvent[]>((t) => `/api/v1/tenants/${t}/audit?limit=50`);
  const detail = useTenantApi<TenantDetail>((t) => `/api/v1/tenants/${t}`);
  const [locName, setLocName] = useState("");
  const [locTz, setLocTz] = useState("Asia/Kolkata");
  const [roleName, setRoleName] = useState("");
  const [rolePerms, setRolePerms] = useState("tenant.read, appointment.read");

  if (!locations.loading && !locations.tenant && typeof window !== "undefined") {
    router.push("/");
    return null;
  }

  async function createLocation(e: React.FormEvent) {
    e.preventDefault();
    const t = getSelectedTenant();
    if (!t) return;
    try {
      await api.post(`/api/v1/tenants/${t}/locations`, { name: locName, timezone: locTz }, t);
      setLocName("");
      locations.reload();
    } catch (err) {
      locations.setError((err as Error).message);
    }
  }

  async function createRole(e: React.FormEvent) {
    e.preventDefault();
    const t = getSelectedTenant();
    if (!t) return;
    try {
      await api.post(
        `/api/v1/tenants/${t}/roles`,
        { name: roleName, permissions: rolePerms.split(",").map((s) => s.trim()).filter(Boolean) },
        t,
      );
      setRoleName("");
      roles.reload();
    } catch (err) {
      roles.setError((err as Error).message);
    }
  }

  return (
    <Shell>
      <PageHeader
        title="Clinic administration"
        description="Locations, roles, and the audit trail."
        actions={<Link href="/team">Team</Link>}
      />
      {detail.loading ? (
        <LoadingState label="Loading subscription" />
      ) : detail.error ? (
        <Alert tone="danger" title="Subscription unavailable">
          {detail.error}
        </Alert>
      ) : detail.data?.subscription ? (
        <Card title="Subscription (read-only)">
          {(() => {
            const sub = detail.data.subscription;
            if (!sub) return null;
            const presented = presentStatus(sub.status);
            return (
              <>
                <p>
                  <strong>{sub.plan_name || sub.plan_code}</strong> ({sub.plan_code}){" "}
                  <Badge tone={presented.tone}>{presented.label}</Badge>{" "}
                  <Badge tone={sub.is_in_trial ? "success" : "neutral"}>
                    {sub.is_in_trial ? "In trial" : "Not in trial"}
                  </Badge>
                </p>
                <p className="hos-helper">
                  Trial period:{" "}
                  {sub.trial_starts_at
                    ? new Date(sub.trial_starts_at).toLocaleDateString()
                    : "—"}{" "}
                  →{" "}
                  {sub.trial_ends_at
                    ? new Date(sub.trial_ends_at).toLocaleDateString()
                    : "—"}
                </p>
                {sub.limits ? (
                  <p className="hos-helper">
                    Plan limits (informational only, not enforced):{" "}
                    {sub.limits.max_locations} locations ·{" "}
                    {sub.limits.max_practitioners} practitioners ·{" "}
                    {sub.limits.max_staff_seats} seats.
                  </p>
                ) : null}
                {(detail.data.specialties ?? []).length > 0 ? (
                  <Table
                    caption="Enabled specialties"
                    columns={
                      <>
                        <Th>Specialty</Th>
                        <Th>Pack version</Th>
                        <Th>Readiness</Th>
                      </>
                    }
                  >
                    {(detail.data.specialties ?? []).map((s) => (
                      <tr key={s.code}>
                        <Td>{s.code}</Td>
                        <Td>{s.pack_version}</Td>
                        <Td>
                          <Badge
                            tone={
                              s.ready_for_use
                                ? "success"
                                : s.maturity === "discovery"
                                  ? "warning"
                                  : "neutral"
                            }
                          >
                            {s.ready_for_use
                              ? "Ready"
                              : s.maturity === "discovery"
                                ? "Discovery only"
                                : "Unknown"}
                          </Badge>
                        </Td>
                      </tr>
                    ))}
                  </Table>
                ) : (
                  <EmptyState title="No specialties enabled" />
                )}
              </>
            );
          })()}
        </Card>
      ) : (
        <Card title="Subscription (read-only)">
          <EmptyState title="No subscription record" />
        </Card>
      )}
      {locations.error ? (
        <Alert tone="danger" title="Something went wrong">
          {locations.error}
        </Alert>
      ) : null}
      <Card title="Locations">
        {locations.loading ? (
          <LoadingState label="Loading locations" />
        ) : (locations.data ?? []).length === 0 ? (
          <EmptyState title="No locations" />
        ) : (
          <Table
            caption="Locations"
            columns={
              <>
                <Th>Name</Th>
                <Th>Timezone</Th>
                <Th>Active</Th>
              </>
            }
          >
            {(locations.data ?? []).map((l) => (
              <tr key={l.id}>
                <Td>{l.name}</Td>
                <Td>{l.timezone}</Td>
                <Td>
                  <Badge tone={l.is_active ? "success" : "neutral"}>
                    {l.is_active ? "yes" : "no"}
                  </Badge>
                </Td>
              </tr>
            ))}
          </Table>
        )}
        <h3>New location</h3>
        <form onSubmit={createLocation}>
          <Field label="Name" htmlFor="loc-name" required>
            {() => (
              <Input id="loc-name" value={locName} onChange={(e) => setLocName(e.target.value)} required minLength={2} maxLength={200} />
            )}
          </Field>
          <Field label="Timezone" htmlFor="loc-tz" required>
            {() => (
              <Input id="loc-tz" value={locTz} onChange={(e) => setLocTz(e.target.value)} required />
            )}
          </Field>
          <p>
            <Button type="submit">Create location</Button>
          </p>
        </form>
      </Card>
      <Card title="Roles">
        {roles.error ? <Alert tone="danger">{roles.error}</Alert> : null}
        {roles.loading ? (
          <LoadingState label="Loading roles" />
        ) : (
          <Table
            caption="Roles"
            columns={
              <>
                <Th>Name</Th>
                <Th>Permissions</Th>
                <Th>Seed</Th>
              </>
            }
          >
            {(roles.data ?? []).map((r) => (
              <tr key={r.id}>
                <Td>{r.name}</Td>
                <Td>{r.permissions.join(", ")}</Td>
                <Td>{r.is_seed ? "seed" : "custom"}</Td>
              </tr>
            ))}
          </Table>
        )}
        <h3>New custom role</h3>
        <form onSubmit={createRole}>
          <Field label="Name" htmlFor="role-name" required>
            {() => (
              <Input id="role-name" value={roleName} onChange={(e) => setRoleName(e.target.value)} required minLength={2} maxLength={80} />
            )}
          </Field>
          <Field
            label="Permissions (comma-separated)"
            htmlFor="role-perms"
            required
            description="Unknown or platform.* permissions are rejected server-side."
          >
            {({ describedBy }) => (
              <Input
                id="role-perms"
                value={rolePerms}
                onChange={(e) => setRolePerms(e.target.value)}
                required
                aria-describedby={describedBy}
              />
            )}
          </Field>
          <p>
            <Button type="submit">Create role</Button>
          </p>
        </form>
      </Card>
      <Card title="Audit trail">
        {audit.error ? <Alert tone="danger">{audit.error}</Alert> : null}
        {audit.loading ? (
          <LoadingState label="Loading audit events" />
        ) : (audit.data ?? []).length === 0 ? (
          <EmptyState title="No audit events" />
        ) : (
          <Table
            caption="Recent audit events"
            density="clinical-dense"
            columns={
              <>
                <Th>When</Th>
                <Th>Action</Th>
                <Th>Resource</Th>
                <Th>Result</Th>
              </>
            }
          >
            {(audit.data ?? []).slice(0, 30).map((a) => (
              <tr key={a.id}>
                <Td>{new Date(a.occurred_at).toLocaleString()}</Td>
                <Td>{a.action}</Td>
                <Td>
                  {a.resource_type}:{a.resource_id.slice(0, 8)}...
                </Td>
                <Td>
                  {a.result === "ok" ? (
                    <Badge tone="success">ok</Badge>
                  ) : (
                    <Badge tone="warning">{a.result}</Badge>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
        <p className="hos-helper">
          Reading this list is itself audited. Only refs are shown - never contents.
        </p>
      </Card>
    </Shell>
  );
}
