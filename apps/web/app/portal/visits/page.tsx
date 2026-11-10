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

type Encounter = { id: string; status: string; opened_at: string; closed_at: string | null };

export default function PortalVisitsPage() {
  const router = useRouter();
  const list = useTenantApi<Encounter[]>((t) => `/api/v1/portal/encounters`);

  useEffect(() => {
    if (list.status === 401) router.push("/login");
  }, [list.status, router]);

  if (!list.tenant && !list.loading) {
    return (
      <PortalShell>
        <PageHeader title="Visits" description="Summaries of your completed care." />
        <NoTenantHint />
      </PortalShell>
    );
  }

  return (
    <PortalShell>
      <PageHeader title="Visits" description="Summaries of your completed care." />
      {list.error ? (
        <Alert tone="danger" title="Could not load visits">
          {[403, 404].includes(list.status ?? 0) ? portalUnavailableCopy(list.status) : list.error}
        </Alert>
      ) : null}
      <Card title="Your visits">
        {list.loading ? (
          <LoadingState label="Loading visits" />
        ) : (list.data ?? []).length === 0 ? (
          <EmptyState title="No visits yet">Completed visits will appear here.</EmptyState>
        ) : (
          <Table
            caption="Visits"
            columns={
              <>
                <Th>Date</Th>
                <Th>Status</Th>
                <Th>Summary</Th>
              </>
            }
          >
            {(list.data ?? []).map((e) => (
              <tr key={e.id}>
                <Td>{new Date(e.opened_at).toLocaleDateString()}</Td>
                <Td><Status value={e.status} /></Td>
                <Td><Link href={`/portal/visits/${e.id}`}>View</Link></Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </PortalShell>
  );
}
