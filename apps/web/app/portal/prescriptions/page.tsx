"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  Alert,
  Card,
  EmptyState,
  LoadingState,
  PageHeader,
  Status,
} from "@healthcare-os/ui";
import { useTenantApi } from "@/lib/use-api";
import { portalUnavailableCopy } from "@/lib/portal";
import { NoTenantHint } from "../no-tenant";
import { PortalShell } from "../shell";

type RxItem = { medication_code: string; dose: string; route: string; frequency: string; instructions: string | null };
type Prescription = { id: string; status: string; items: RxItem[]; signed_at: string | null };

export default function PortalPrescriptionsPage() {
  const router = useRouter();
  const list = useTenantApi<Prescription[]>((t) => `/api/v1/portal/prescriptions`);

  useEffect(() => {
    if (list.status === 401) router.push("/login");
  }, [list.status, router]);

  if (!list.tenant && !list.loading) {
    return (
      <PortalShell>
        <PageHeader title="Medicines" description="Your signed prescriptions." />
        <NoTenantHint />
      </PortalShell>
    );
  }

  return (
    <PortalShell>
      <PageHeader title="Medicines" description="Your signed prescriptions." />
      {list.error ? (
        <Alert tone="danger" title="Could not load prescriptions">
          {[403, 404].includes(list.status ?? 0) ? portalUnavailableCopy(list.status) : list.error}
        </Alert>
      ) : null}
      {list.loading ? (
        <LoadingState label="Loading prescriptions" />
      ) : (list.data ?? []).length === 0 ? (
        <Card title="Prescriptions">
          <EmptyState title="No prescriptions">Signed prescriptions will appear here.</EmptyState>
        </Card>
      ) : (
        (list.data ?? []).map((p) => (
          <Card key={p.id} title={`Prescription · ${p.id.slice(0, 8)}`}>
            <p>
              <Status value={p.status} />
              {p.signed_at ? ` · signed ${new Date(p.signed_at).toLocaleDateString()}` : ""}
            </p>
            <ul>
              {p.items.map((i, n) => (
                <li key={n}>
                  <strong>{i.medication_code}</strong> — {i.dose}, {i.route}, {i.frequency}
                  {i.instructions ? <p className="hos-helper">{i.instructions}</p> : null}
                </li>
              ))}
            </ul>
          </Card>
        ))
      )}
    </PortalShell>
  );
}
