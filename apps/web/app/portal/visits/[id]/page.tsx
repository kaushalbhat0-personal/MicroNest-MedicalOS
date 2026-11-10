"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
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
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { portalUnavailableCopy } from "@/lib/portal";
import { PortalShell } from "../../shell";

type Note = { id: string; note_type: string; status: string; subjective: string | null; objective: string | null; assessment: string | null; plan: string | null };
type Observation = { id: string; type_code: string; value: string; unit: string | null };
type Diagnosis = { id: string; status: string; code: string | null; display: string | null; free_text: string | null };
type EncounterDetail = {
  id: string;
  status: string;
  opened_at: string;
  closed_at: string | null;
  notes: Note[];
  observations: Observation[];
  diagnoses: Diagnosis[];
};

export default function PortalVisitDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const [enc, setEnc] = useState<EncounterDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const t = getSelectedTenant();
    if (!t) {
      router.push("/portal");
      return;
    }
    api
      .get<EncounterDetail>(`/api/v1/portal/encounters/${id}`, t)
      .then((e) => {
        setEnc(e);
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
      <p><Link href="/portal/visits">Back to visits</Link></p>
      {loading ? (
        <LoadingState label="Loading visit" />
      ) : error && !enc ? (
        <Alert tone="danger" title="Could not load visit">
          {error}
        </Alert>
      ) : enc ? (
        <>
          <PageHeader
            title={`Visit on ${new Date(enc.opened_at).toLocaleDateString()}`}
            description={enc.closed_at ? `Completed ${new Date(enc.closed_at).toLocaleDateString()}` : "In progress"}
          />
          <p><Status value={enc.status} /></p>
          {enc.status !== "closed" ? (
            <Card title="Summary not ready yet">
              <p className="hos-helper">
                Details of this visit will appear here after it is completed and reviewed.
              </p>
            </Card>
          ) : (
            <>
              <Card title="Clinician notes">
                {enc.notes.length === 0 ? (
                  <EmptyState title="No shared notes" />
                ) : (
                  enc.notes.map((n) => (
                    <section key={n.id}>
                      <h3>{n.note_type} <Status value={n.status} /></h3>
                      {n.subjective ? <p>{n.subjective}</p> : null}
                      {n.objective ? <p>{n.objective}</p> : null}
                      {n.assessment ? <p>{n.assessment}</p> : null}
                      {n.plan ? <p>{n.plan}</p> : null}
                    </section>
                  ))
                )}
              </Card>
              <Card title="Observations">
                {enc.observations.length === 0 ? (
                  <EmptyState title="No observations shared" />
                ) : (
                  <Table
                    caption="Observations"
                    columns={
                      <>
                        <Th>Measure</Th>
                        <Th>Value</Th>
                      </>
                    }
                  >
                    {enc.observations.map((o) => (
                      <tr key={o.id}>
                        <Td>{o.type_code}</Td>
                        <Td numeric>{o.value}{o.unit ? ` ${o.unit}` : ""}</Td>
                      </tr>
                    ))}
                  </Table>
                )}
              </Card>
              <Card title="Diagnoses">
                {enc.diagnoses.length === 0 ? (
                  <EmptyState title="No diagnoses shared" />
                ) : (
                  <ul>
                    {enc.diagnoses.map((d) => (
                      <li key={d.id}>
                        {d.display ?? d.code ?? d.free_text ?? "Diagnosis"} <Status value={d.status} />
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </>
          )}
        </>
      ) : null}
    </PortalShell>
  );
}
