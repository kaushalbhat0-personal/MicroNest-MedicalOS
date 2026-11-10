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

type Document = { id: string; doc_type: string; content_type: string | null; size_bytes: number | null; created_at: string };

export default function PortalDocumentsPage() {
  const router = useRouter();
  const list = useTenantApi<Document[]>((t) => `/api/v1/portal/documents`);

  useEffect(() => {
    if (list.status === 401) router.push("/login");
  }, [list.status, router]);

  if (!list.tenant && !list.loading) {
    return (
      <PortalShell>
        <PageHeader title="Documents" description="Reports and images shared with you." />
        <NoTenantHint />
      </PortalShell>
    );
  }

  return (
    <PortalShell>
      <PageHeader title="Documents" description="Reports and images shared with you." />
      {list.error ? (
        <Alert tone="danger" title="Could not load documents">
          {[403, 404].includes(list.status ?? 0) ? portalUnavailableCopy(list.status) : list.error}
        </Alert>
      ) : null}
      <Card title="Shared documents">
        {list.loading ? (
          <LoadingState label="Loading documents" />
        ) : (list.data ?? []).length === 0 ? (
          <EmptyState title="No documents shared">Shared reports will appear here.</EmptyState>
        ) : (
          <Table
            caption="Documents"
            columns={
              <>
                <Th>Type</Th>
                <Th>Shared on</Th>
                <Th>Access</Th>
              </>
            }
          >
            {(list.data ?? []).map((d) => (
              <tr key={d.id}>
                <Td>{d.doc_type}</Td>
                <Td>{new Date(d.created_at).toLocaleDateString()}</Td>
                <Td>Ask the clinic for a copy</Td>
              </tr>
            ))}
          </Table>
        )}
        <p className="hos-helper">
          File download is not available in the portal yet. Please ask the clinic for copies.
        </p>
      </Card>
    </PortalShell>
  );
}
