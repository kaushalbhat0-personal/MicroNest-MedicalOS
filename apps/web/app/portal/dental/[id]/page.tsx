"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Alert,
  Card,
  LoadingState,
  PageHeader,
  Status,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { portalUnavailableCopy } from "@/lib/portal";
import { PortalShell } from "../../shell";

type PlanItem = { id: string; procedure_code: string; procedure_display: string | null; tooth: number | null; status: string; notes: string | null };
type Plan = { id: string; status: string; version: number; notes: string | null; items: PlanItem[] };

export default function PortalPlanDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const t = getSelectedTenant();
    if (!t) {
      router.push("/portal");
      return;
    }
    api
      .get<Plan>(`/api/v1/portal/treatment-plans/${id}`, t)
      .then((p) => {
        setPlan(p);
        setError("");
      })
      .catch((e: Error & { status?: number }) => {
        if (e.status === 401) {
          router.push("/login");
          return;
        }
        setError(e.status === 403 || e.status === 404 ? portalUnavailableCopy(e.status) : e.message);
      })
      .finally(() => setLoading(false));
  }, [id, router]);

  return (
    <PortalShell>
      <p><Link href="/portal/dental">Back to dental care</Link></p>
      {loading ? (
        <LoadingState label="Loading treatment plan" />
      ) : error && !plan ? (
        <Alert tone="danger" title="Could not load treatment plan">
          {error}
        </Alert>
      ) : plan ? (
        <>
          <PageHeader title={`Treatment plan v${plan.version}`} description={plan.notes ?? undefined} />
          <p><Status value={plan.status} /></p>
          <Card title="Planned procedures">
            {plan.items.length === 0 ? (
              <p className="hos-helper">No procedures listed yet.</p>
            ) : (
              <Table
                caption="Planned procedures"
                columns={
                  <>
                    <Th>Procedure</Th>
                    <Th>Tooth</Th>
                    <Th>Status</Th>
                  </>
                }
              >
                {plan.items.map((i) => (
                  <tr key={i.id}>
                    <Td>{i.procedure_display ?? i.procedure_code}</Td>
                    <Td numeric>{i.tooth ?? "-"}</Td>
                    <Td><Status value={i.status} /></Td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
        </>
      ) : null}
    </PortalShell>
  );
}
