"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  Alert,
  Card,
  EmptyState,
  LoadingState,
  PageHeader,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { useTenantApi } from "@/lib/use-api";
import { portalUnavailableCopy } from "@/lib/portal";
import { NoTenantHint } from "../no-tenant";
import { PortalShell } from "../shell";

type AccessEvent = { action: string; resource_type: string; resource_id: string; occurred_at: string };

export default function PortalAccessLogPage() {
  const router = useRouter();
  const list = useTenantApi<AccessEvent[]>((t) => `/api/v1/portal/access-log`);

  useEffect(() => {
    if (list.status === 401) router.push("/login");
  }, [list.status, router]);

  if (!list.tenant && !list.loading) {
    return (
      <PortalShell>
        <PageHeader title="Activity" description="Your recent portal activity." />
        <NoTenantHint />
      </PortalShell>
    );
  }

  return (
    <PortalShell>
      <PageHeader title="Activity" description="Your recent portal activity." />
      {list.error ? (
        <Alert tone="danger" title="Could not load activity">
          {[403, 404].includes(list.status ?? 0) ? portalUnavailableCopy(list.status) : list.error}
        </Alert>
      ) : null}
      <Card title="Recent activity">
        {list.loading ? (
          <LoadingState label="Loading activity" />
        ) : (list.data ?? []).length === 0 ? (
          <EmptyState title="No activity yet" />
        ) : (
          <Table
            caption="Portal activity"
            columns={
              <>
                <Th>When</Th>
                <Th>Action</Th>
                <Th>Record</Th>
              </>
            }
          >
            {(list.data ?? []).map((e, n) => (
              <tr key={n}>
                <Td>{new Date(e.occurred_at).toLocaleString()}</Td>
                <Td>{e.action}</Td>
                <Td>{e.resource_type} {e.resource_id.slice(0, 8)}…</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </PortalShell>
  );
}
