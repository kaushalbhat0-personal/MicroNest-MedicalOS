"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  Alert,
  Card,
  EmptyState,
  LoadingState,
  PageHeader,
  Status,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { useTenantApi } from "@/lib/use-api";
import { portalUnavailableCopy } from "@/lib/portal";
import { NoTenantHint } from "../no-tenant";
import { PortalShell } from "../shell";

type PlanItem = { id: string; procedure_code: string; procedure_display: string | null; tooth: number | null; status: string };
type Plan = { id: string; status: string; version: number; notes: string | null; items: PlanItem[] };
type Recall = { id: string; due_date: string; reason: string; status: string };
type Consent = { id: string; status: string; consenter_name: string };

export default function PortalDentalPage() {
  const router = useRouter();
  const plans = useTenantApi<Plan[]>((t) => `/api/v1/portal/treatment-plans`);
  const recalls = useTenantApi<Recall[]>((t) => `/api/v1/portal/recalls`);
  const consents = useTenantApi<Consent[]>((t) => `/api/v1/portal/consents`);
  const error = plans.error || recalls.error || consents.error;
  const errorStatus = plans.status ?? recalls.status ?? consents.status;

  useEffect(() => {
    if (plans.status === 401) router.push("/login");
  }, [plans.status, router]);

  if (!plans.tenant && !plans.loading) {
    return (
      <PortalShell>
        <PageHeader title="Dental care" description="Treatment plans, recalls, and consents." />
        <NoTenantHint />
      </PortalShell>
    );
  }

  return (
    <PortalShell>
      <PageHeader title="Dental care" description="Treatment plans, recalls, and consents." />
      {error ? (
        <Alert tone="danger" title="Could not load dental information">
          {[403, 404].includes(errorStatus ?? 0) ? portalUnavailableCopy(errorStatus) : error}
        </Alert>
      ) : null}
      <Card title="Treatment plans">
        {plans.loading ? (
          <LoadingState label="Loading treatment plans" />
        ) : (plans.data ?? []).length === 0 ? (
          <EmptyState title="No treatment plans" />
        ) : (
          <Table
            caption="Treatment plans"
            columns={
              <>
                <Th>Plan</Th>
                <Th>Status</Th>
                <Th>Details</Th>
              </>
            }
          >
            {(plans.data ?? []).map((p) => (
              <tr key={p.id}>
                <Td>Plan v{p.version}</Td>
                <Td><Status value={p.status} /></Td>
                <Td><Link href={`/portal/dental/${p.id}`}>View</Link></Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <Card title="Recalls">
        {recalls.loading ? (
          <LoadingState label="Loading recalls" />
        ) : (recalls.data ?? []).length === 0 ? (
          <EmptyState title="No recalls" />
        ) : (
          <ul>
            {(recalls.data ?? []).map((r) => (
              <li key={r.id}>
                {r.due_date} — {r.reason} <Status value={r.status} />
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Consents">
        {consents.loading ? (
          <LoadingState label="Loading consents" />
        ) : (consents.data ?? []).length === 0 ? (
          <EmptyState title="No consents recorded" />
        ) : (
          <ul>
            {(consents.data ?? []).map((c) => (
              <li key={c.id}>
                {c.consenter_name} <Status value={c.status} />
              </li>
            ))}
          </ul>
        )}
        <p className="hos-helper">
          To grant or change a consent, please speak with the clinic.
        </p>
      </Card>
    </PortalShell>
  );
}
