"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Alert,
  Badge,
  Card,
  EmptyState,
  LoadingState,
  PageHeader,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { Shell } from "../shell";

type PlanLimits = {
  max_locations: number;
  max_practitioners: number;
  max_staff_seats: number;
  enforced: boolean;
};
type Plan = {
  code: string;
  family_code: string;
  version: number;
  name: string;
  description: string;
  currency: string;
  billing_interval: string | null;
  price_minor: number;
  features: Record<string, unknown>;
  limits: PlanLimits;
  trial_days: number;
  is_active: boolean;
};

function formatPrice(plan: Plan): string {
  if (plan.price_minor <= 0) return "No charge (catalog)";
  const major = (plan.price_minor / 100).toFixed(2);
  const interval = plan.billing_interval ? ` / ${plan.billing_interval}` : "";
  return `${plan.currency} ${major}${interval}`;
}

export default function PlansPage() {
  const router = useRouter();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!getSelectedTenant()) {
      router.push("/");
      return;
    }
    api
      .get<Plan[]>("/api/v1/plans")
      .then(setPlans)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [router]);

  return (
    <Shell>
      <PageHeader
        title="Plans"
        description="Healthcare OS plan catalog for clinics. Prices are catalog information only — no checkout or payment provider is connected."
      />
      {loading ? <LoadingState label="Loading plans" /> : null}
      {error ? (
        <Alert tone="danger" title="Could not load plans">
          {error}
        </Alert>
      ) : null}
      {!loading && plans.length === 0 ? <EmptyState title="No active plans" /> : null}
      <div
        style={{
          display: "grid",
          gap: "1rem",
          gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
        }}
      >
        {plans.map((p) => (
          <Card key={p.code} title={p.name}>
            <p style={{ color: "var(--hos-text-muted)", fontSize: "0.9rem" }}>{p.description}</p>
            <p style={{ fontSize: "1.25rem", fontWeight: 600, margin: "0.75rem 0" }}>
              {formatPrice(p)}
            </p>
            <p>
              <Badge tone="neutral">{p.family_code}</Badge> · v{p.version}
              {p.trial_days > 0 ? ` · ${p.trial_days}-day trial` : ""}
            </p>
            <ul style={{ marginTop: "0.75rem", paddingLeft: "1.1rem" }}>
              <li>
                Locations: {p.limits.max_locations}{" "}
                <span style={{ color: "var(--hos-text-muted)" }}>(informational)</span>
              </li>
              <li>
                Practitioners: {p.limits.max_practitioners}{" "}
                <span style={{ color: "var(--hos-text-muted)" }}>(informational)</span>
              </li>
              <li>
                Staff seats: {p.limits.max_staff_seats}{" "}
                <span style={{ color: "var(--hos-text-muted)" }}>(informational)</span>
              </li>
            </ul>
            {!p.limits.enforced ? (
              <p style={{ color: "var(--hos-text-muted)", fontSize: "0.8rem", marginTop: "0.75rem" }}>
                Staff seats, locations, and practitioners are enforced at
                capacity. Features remain informational.
              </p>
            ) : null}
          </Card>
        ))}
      </div>
    </Shell>
  );
}
