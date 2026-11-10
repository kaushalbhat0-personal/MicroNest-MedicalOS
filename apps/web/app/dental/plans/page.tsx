"use client";
import Link from "next/link";
import { useState } from "react";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  Select,
  Status,
  Table,
  Td,
  Th,
  PageHeader,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { useTenantApi } from "@/lib/use-api";
import { Shell } from "../../shell";

type Plan = { id: string; status: string; version: number };

export default function TreatmentPlansPage() {
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [patientId, setPatientId] = useState("");
  const [loadingPlans, setLoadingPlans] = useState(false);
  const [error, setError] = useState("");
  const [practitioners, setPractitioners] = useState<{ id: string; display_name: string }[]>([]);
  const [practitionerId, setPractitionerId] = useState("");
  const [procCode, setProcCode] = useState("cleaning");
  const [tooth, setTooth] = useState("");

  async function loadPractitioners() {
    const t = getSelectedTenant();
    if (!t || practitioners.length > 0) return;
    try {
      const p = await api.get<{ id: string; display_name: string }[]>(
        `/api/v1/tenants/${t}/practitioners`,
        t,
      );
      setPractitioners(p);
    } catch {
      /* creation will surface the error */
    }
  }

  async function createPlan(e: React.FormEvent) {
    e.preventDefault();
    const t = getSelectedTenant();
    if (!t) return;
    setError("");
    try {
      const p = await api.post<{ id: string }>(
        `/api/v1/tenants/${t}/treatment-plans`,
        {
          patient_id: patientId,
          practitioner_id: practitionerId,
          items: tooth
            ? [{ procedure_code: procCode, tooth: Number(tooth) }]
            : [{ procedure_code: procCode }],
        },
        t,
      );
      window.location.href = `/dental/plans/${p.id}`;
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function load(e?: React.FormEvent) {
    e?.preventDefault();
    const t = getSelectedTenant();
    if (!t || !patientId) return;
    setLoadingPlans(true);
    try {
      const r = await api.get<Plan[]>(
        `/api/v1/tenants/${t}/treatment-plans?patient_id=${patientId}`,
        t,
      );
      setPlans(r);
      setError("");
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setLoadingPlans(false);
    }
  }

  return (
    <Shell>
      <PageHeader
        title="Treatment plans"
        description="Dental plans are per-patient. Pick a patient to list theirs."
        actions={<Link href="/dental/recalls">Recalls</Link>}
      />
      {error ? (
        <Alert tone="danger" title="Something went wrong">
          {error}
        </Alert>
      ) : null}
      <Card title="Find plans">
        <form onSubmit={load}>
          <Field label="Patient ID" htmlFor="tp-patient" required>
            {() => (
              <Input id="tp-patient" value={patientId} onChange={(e) => setPatientId(e.target.value)} required />
            )}
          </Field>
          <p>
            <Button type="submit" loading={loadingPlans}>
              Load plans
            </Button>
          </p>
        </form>
      </Card>
      <Card title="New plan">
        <form onSubmit={createPlan}>
          <Field label="Patient ID" htmlFor="np-patient" required description="Same patient as above, or another.">
            {({ describedBy }) => (
              <Input
                id="np-patient"
                value={patientId}
                onChange={(e) => setPatientId(e.target.value)}
                required
                aria-describedby={describedBy}
              />
            )}
          </Field>
          <Field label="Practitioner" htmlFor="np-pract" required>
            {() => (
              <Select
                id="np-pract"
                value={practitionerId}
                onChange={(e) => setPractitionerId(e.target.value)}
                required
                onFocus={() => void loadPractitioners()}
                options={[
                  { value: "", label: "Select practitioner" },
                  ...practitioners.map((p) => ({ value: p.id, label: p.display_name })),
                ]}
              />
            )}
          </Field>
          <Field label="First procedure code" htmlFor="np-proc" required>
            {() => (
              <Input id="np-proc" value={procCode} onChange={(e) => setProcCode(e.target.value)} required />
            )}
          </Field>
          <Field label="Tooth (FDI, optional)" htmlFor="np-tooth">
            {() => (
              <Input id="np-tooth" type="number" min={11} max={48} value={tooth} onChange={(e) => setTooth(e.target.value)} />
            )}
          </Field>
          <p>
            <Button type="submit">Create draft plan</Button>
          </p>
        </form>
      </Card>
      <Card title="Plans">
        {plans === null ? (
          <EmptyState title="No patient selected" />
        ) : plans.length === 0 ? (
          <EmptyState title="No treatment plans for this patient" />
        ) : (
          <Table
            caption="Treatment plans"
            columns={
              <>
                <Th>Plan</Th>
                <Th>Status</Th>
              </>
            }
          >
            {plans.map((p) => (
              <tr key={p.id}>
                <Td>
                  <Link href={`/dental/plans/${p.id}`}>Plan v{p.version}</Link>
                </Td>
                <Td>
                  <Status value={p.status} />
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </Shell>
  );
}
