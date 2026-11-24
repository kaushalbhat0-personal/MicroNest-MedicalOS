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
  LoadingState,
  PageHeader,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { Shell } from "../shell";

type Plan = {
  code: string;
  family_code: string;
  version: number;
  name: string;
  description: string;
  currency: string;
  billing_interval: string | null;
  price_minor: number;
  limits: {
    max_locations: number;
    max_practitioners: number;
    max_staff_seats: number;
    enforced: boolean;
  };
};
type Subscription = {
  id: string;
  status: string;
  plan: Plan;
  trial_starts_at: string | null;
  trial_ends_at: string | null;
  is_in_trial: boolean;
  period_start: string | null;
  period_end: string | null;
  grace_ends_at: string | null;
  cancelled_at: string | null;
  cancel_at_period_end?: boolean;
  limits_enforced: boolean;
  provider_ref: string | null;
};
type SubEvent = {
  id: string;
  event_type: string;
  from_status: string | null;
  to_status: string | null;
  note: string | null;
  created_at: string;
};
type EntitlementUsage = {
  available: boolean;
  value: number | null;
  definition: string;
  active_memberships?: number | null;
  pending_reservations?: number | null;
};
type ShadowEval = {
  key: string;
  result: string;
  usage: number | null;
  limit: number | null;
  would_deny_if_enforced: boolean;
  evaluation_mode?: string;
  probe?: string | null;
};
type Entitlements = {
  evaluation_mode: string;
  enforcement_active: boolean;
  enforced_keys?: string[];
  shadow_only_keys?: string[];
  features: Record<string, boolean>;
  limits: Record<string, number>;
  usage: Record<string, EntitlementUsage>;
  evaluations: ShadowEval[];
  authorization_note: string;
};
type SaasPayment = {
  id: string;
  status: string;
  amount_minor: number;
  currency: string;
  plan_code: string | null;
  provider: string;
  paid_at: string | null;
  created_at: string;
  failure_reason: string | null;
  purpose?: string;
  refunded_amount_minor?: number;
  period_end?: string | null;
  checkout?: { order_id: string; public_key: string | null; return_url_informational: boolean };
};

export default function SubscriptionPage() {
  const router = useRouter();
  const [sub, setSub] = useState<Subscription | null>(null);
  const [events, setEvents] = useState<SubEvent[]>([]);
  const [ents, setEnts] = useState<Entitlements | null>(null);
  const [payments, setPayments] = useState<SaasPayment[]>([]);
  const [checkoutMsg, setCheckoutMsg] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [forbidden, setForbidden] = useState(false);

  const load = useCallback(async (tid: string) => {
    setLoading(true);
    setError("");
    setForbidden(false);
    try {
      const [s, ev, e, pays] = await Promise.all([
        api.get<Subscription>(`/api/v1/tenants/${tid}/subscription`, tid),
        api.get<SubEvent[]>(`/api/v1/tenants/${tid}/subscription/events?limit=50`, tid),
        api.get<Entitlements>(`/api/v1/tenants/${tid}/entitlements`, tid),
        api.get<SaasPayment[]>(`/api/v1/tenants/${tid}/subscription/payments`, tid).catch(() => []),
      ]);
      setSub(s);
      setEvents(ev);
      setEnts(e);
      setPayments(pays);
    } catch (e) {
      const msg = (e as Error).message;
      if (/403|forbidden|permission/i.test(msg)) setForbidden(true);
      setError(msg);
      setSub(null);
      setEnts(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const startCheckout = async (planCode: string, purpose: "checkout" | "renewal" = "checkout") => {
    const tid = getSelectedTenant();
    if (!tid) return;
    setCheckoutMsg("");
    try {
      const key =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `idem-${Date.now()}`;
      const res = await api.post<SaasPayment>(
        `/api/v1/tenants/${tid}/subscription/checkout`,
        { plan_code: planCode, idempotency_key: key, purpose },
        tid,
      );
      setCheckoutMsg(
        `${purpose === "renewal" ? "Manual renewal" : "Checkout"} created (${res.status}). ` +
          `Order ${res.checkout?.order_id ?? "—"}. ` +
          "No automatic debit — activation waits for a verified provider webhook. " +
          "Browser return URL is not proof of payment.",
      );
      await load(tid);
    } catch (e) {
      setCheckoutMsg((e as Error).message);
    }
  };

  const cancelSubscription = async (atPeriodEnd: boolean) => {
    const tid = getSelectedTenant();
    if (!tid) return;
    const msg = atPeriodEnd
      ? "Schedule cancellation at period end? Access continues until the paid-through date."
      : "Cancel this clinic subscription immediately? This cannot be undone from self-serve.";
    if (typeof window !== "undefined" && !window.confirm(msg)) {
      return;
    }
    setCheckoutMsg("");
    try {
      await api.post(
        `/api/v1/tenants/${tid}/subscription/cancel`,
        { reason: "owner_requested_cancel", at_period_end: atPeriodEnd },
        tid,
      );
      setCheckoutMsg(
        atPeriodEnd
          ? "Cancellation scheduled at period end. Manual renewal is still available until then."
          : "Subscription cancelled immediately.",
      );
      await load(tid);
    } catch (e) {
      setCheckoutMsg((e as Error).message);
    }
  };

  useEffect(() => {
    const t = getSelectedTenant();
    if (!t) {
      router.push("/");
      return;
    }
    void load(t);
  }, [router, load]);

  return (
    <Shell>
      <PageHeader
        title="Subscription"
        description="Clinic SaaS subscription for this workspace. Patients are not billed as SaaS customers. Checkout amounts are server-controlled; webhooks activate paid plans."
        actions={
          <Link href="/plans" style={{ fontSize: "0.9rem" }}>
            View plan catalog
          </Link>
        }
      />
      {loading ? <LoadingState label="Loading subscription" /> : null}
      {forbidden ? (
        <Alert tone="danger" title="Permission denied">
          Subscription details require clinic administrator access.
        </Alert>
      ) : null}
      {error && !forbidden ? (
        <Alert tone="danger" title="Could not load subscription">
          {error}
        </Alert>
      ) : null}

      {!loading && sub ? (
        <>
          <Card title="Current plan">
            <p>
              <strong>{sub.plan.name}</strong>{" "}
              <Badge tone="info">{sub.status}</Badge>
              {sub.is_in_trial ? (
                <>
                  {" "}
                  <Badge tone="success">In trial</Badge>
                </>
              ) : null}
            </p>
            <p style={{ color: "var(--hos-text-muted)" }}>
              {sub.plan.code} · family {sub.plan.family_code} · v{sub.plan.version}
            </p>
            <p>{sub.plan.description}</p>
            <ul style={{ marginTop: "0.75rem", paddingLeft: "1.1rem" }}>
              <li>
                Trial:{" "}
                {sub.trial_starts_at
                  ? new Date(sub.trial_starts_at).toLocaleString()
                  : "—"}{" "}
                → {sub.trial_ends_at ? new Date(sub.trial_ends_at).toLocaleString() : "—"}
              </li>
              <li>
                Period:{" "}
                {sub.period_start ? new Date(sub.period_start).toLocaleString() : "—"} →{" "}
                {sub.period_end ? new Date(sub.period_end).toLocaleString() : "—"}
              </li>
              {sub.grace_ends_at ? (
                <li>Grace ends: {new Date(sub.grace_ends_at).toLocaleString()}</li>
              ) : null}
              {sub.cancel_at_period_end ? (
                <li>Cancellation scheduled at period end (no auto-renew implied).</li>
              ) : null}
            </ul>
            <Alert tone="info" title="Manual billing">
              Automatic provider debit is not enabled. Renew by starting a new server-priced
              checkout. Patient invoices are separate and never appear here.
            </Alert>
            <p style={{ marginTop: "0.75rem", color: "var(--hos-text-muted)", fontSize: "0.85rem" }}>
              Limits ({sub.limits_enforced ? "enforced" : "informational"}): locations{" "}
              {sub.plan.limits.max_locations}, practitioners{" "}
              {sub.plan.limits.max_practitioners}, staff seats{" "}
              {sub.plan.limits.max_staff_seats}.
            </p>
            <div style={{ marginTop: "1rem", display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
              <Button type="button" onClick={() => void startCheckout("starter-v1")}>
                Checkout Starter
              </Button>
              <Button type="button" onClick={() => void startCheckout("growth-v1")}>
                Checkout Growth
              </Button>
              {sub.status === "active" || sub.status === "past_due" || sub.status === "grace" ? (
                <Button
                  type="button"
                  onClick={() => void startCheckout(sub.plan.code, "renewal")}
                >
                  Manual renew ({sub.plan.code})
                </Button>
              ) : null}
              {sub.status !== "cancelled" && sub.status !== "expired" ? (
                <>
                  <Button type="button" onClick={() => void cancelSubscription(true)}>
                    Cancel at period end
                  </Button>
                  <Button type="button" onClick={() => void cancelSubscription(false)}>
                    Cancel now
                  </Button>
                </>
              ) : null}
            </div>
            {checkoutMsg ? (
              <Alert tone="info" title="Checkout">
                {checkoutMsg}
              </Alert>
            ) : null}
          </Card>

          <Card title="SaaS payment history">
            {payments.length === 0 ? (
              <EmptyState title="No SaaS payments yet" />
            ) : (
              <Table
                caption="Clinic subscription charges"
                columns={
                  <>
                    <Th>Status</Th>
                    <Th>Plan</Th>
                    <Th>Amount</Th>
                    <Th>Refunded</Th>
                    <Th>Purpose</Th>
                    <Th>Created</Th>
                  </>
                }
              >
                {payments.map((p) => (
                  <tr key={p.id}>
                    <Td>
                      <Badge
                        tone={
                          p.status === "paid"
                            ? "success"
                            : p.status === "failed" || p.status === "disputed"
                              ? "danger"
                              : "neutral"
                        }
                      >
                        {p.status}
                      </Badge>
                    </Td>
                    <Td>{p.plan_code ?? "—"}</Td>
                    <Td>
                      {(p.amount_minor / 100).toFixed(2)} {p.currency}
                    </Td>
                    <Td>
                      {((p.refunded_amount_minor ?? 0) / 100).toFixed(2)} {p.currency}
                    </Td>
                    <Td>{p.purpose ?? "checkout"}</Td>
                    <Td>{new Date(p.created_at).toLocaleString()}</Td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>

          {ents ? (
            <Card title="Entitlements (capacity enforced)">
              <Alert tone="info" title="Staff seats, locations, and practitioners are enforced">
                Creating or reactivating these resources is blocked when at plan capacity
                or when the subscription is inactive. Features remain informational.
                Permissions still control who may attempt each action. Appointments and
                storage quotas are not enforced.
              </Alert>
              <p style={{ color: "var(--hos-text-muted)", fontSize: "0.85rem" }}>
                Mode: {ents.evaluation_mode} · enforcement_active={" "}
                {String(ents.enforcement_active)}
              </p>
              <h3 style={{ fontSize: "1rem", marginTop: "1rem" }}>Usage vs limits</h3>
              <ul style={{ paddingLeft: "1.1rem" }}>
                {(["max_locations", "max_practitioners", "max_staff_seats"] as const).map(
                  (k) => {
                    const u = ents.usage[k];
                    const lim = ents.limits[k];
                    const remaining =
                      u?.available && lim != null && u.value != null
                        ? Math.max(lim - u.value, 0)
                        : null;
                    return (
                      <li key={k}>
                        {k}:{" "}
                        {u?.available ? (
                          <>
                            {u.value} / {lim ?? "—"}
                            {remaining != null ? ` · ${remaining} remaining` : ""}
                            {k === "max_staff_seats" &&
                            u.pending_reservations != null ? (
                              <span style={{ color: "var(--hos-text-muted)" }}>
                                {" "}
                                (active {u.active_memberships ?? "—"}, reserved{" "}
                                {u.pending_reservations})
                              </span>
                            ) : null}{" "}
                            <Badge tone="success">enforced</Badge>
                          </>
                        ) : (
                          <span style={{ color: "var(--hos-text-muted)" }}>unavailable</span>
                        )}
                      </li>
                    );
                  },
                )}
                <li>
                  max_storage_bytes:{" "}
                  <span style={{ color: "var(--hos-text-muted)" }}>
                    unavailable (incomplete storage ledger)
                  </span>
                </li>
              </ul>
              <h3 style={{ fontSize: "1rem", marginTop: "1rem" }}>Features</h3>
              <ul style={{ paddingLeft: "1.1rem" }}>
                {Object.entries(ents.features).map(([k, v]) => (
                  <li key={k}>
                    {k}: {v ? "included" : "not included"}
                  </li>
                ))}
              </ul>
              <Table
                caption="Entitlement evaluations"
                columns={
                  <>
                    <Th>Key</Th>
                    <Th>Result</Th>
                    <Th>Usage</Th>
                    <Th>Limit</Th>
                    <Th>Would deny if enforced</Th>
                  </>
                }
              >
                {ents.evaluations
                  .filter((e) => !e.probe)
                  .map((e) => (
                    <tr key={e.key}>
                      <Td>{e.key}</Td>
                      <Td>{e.result}</Td>
                      <Td>{e.usage ?? "—"}</Td>
                      <Td>{e.limit ?? "—"}</Td>
                      <Td>{e.would_deny_if_enforced ? "yes" : "no"}</Td>
                    </tr>
                  ))}
              </Table>
              <p style={{ color: "var(--hos-text-muted)", fontSize: "0.8rem", marginTop: "0.75rem" }}>
                {ents.authorization_note}
              </p>
            </Card>
          ) : null}

          <Card title="History">
            {events.length === 0 ? (
              <EmptyState title="No subscription events" />
            ) : (
              <Table
                caption="Subscription events"
                columns={
                  <>
                    <Th>When</Th>
                    <Th>Type</Th>
                    <Th>Status</Th>
                    <Th>Note</Th>
                  </>
                }
              >
                {events.map((e) => (
                  <tr key={e.id}>
                    <Td>{new Date(e.created_at).toLocaleString()}</Td>
                    <Td>{e.event_type}</Td>
                    <Td>
                      {e.from_status ?? "—"} → {e.to_status ?? "—"}
                    </Td>
                    <Td>{e.note ?? "—"}</Td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
        </>
      ) : null}

      {!loading && !sub && !error ? <EmptyState title="No subscription" /> : null}
    </Shell>
  );
}
