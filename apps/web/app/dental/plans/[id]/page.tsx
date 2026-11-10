"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  LoadingState,
  Select,
  Status,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { Shell } from "../../../shell";

type PlanItem = {
  id: string;
  procedure_code: string;
  tooth: number | null;
  status: string;
  sequence: number;
};
type Plan = {
  id: string;
  status: string;
  version: number;
  notes: string | null;
  items: PlanItem[];
};
type Consent = { id: string; status: string; consenter_name: string };

const ITEM_NEXT: Record<string, string[]> = {
  proposed: ["planned", "cancelled"],
  planned: ["in_progress", "cancelled"],
  in_progress: ["completed", "cancelled"],
};

export default function PlanDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const [plan, setPlan] = useState<Plan | null>(null);
  const [consents, setConsents] = useState<Consent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [procCode, setProcCode] = useState("");
  const [tooth, setTooth] = useState("");
  const [consenter, setConsenter] = useState("");
  const [decision, setDecision] = useState("granted");

  function t() {
    return getSelectedTenant() ?? "";
  }

  function load() {
    const tenant = getSelectedTenant();
    if (!tenant) {
      router.push("/");
      return;
    }
    setLoading(true);
    api
      .get<Plan>(`/api/v1/tenants/${tenant}/treatment-plans/${id}`, tenant)
      .then((p) => {
        setPlan(p);
        setError("");
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, [id, router]);

  async function act(path: string, body: unknown = {}) {
    setError("");
    try {
      await api.post(`/api/v1/tenants/${t()}${path}`, body, t());
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function addItem(e: React.FormEvent) {
    e.preventDefault();
    await act(`/treatment-plans/${id}/items`, {
      procedure_code: procCode,
      tooth: tooth ? Number(tooth) : null,
    });
    setProcCode("");
    setTooth("");
  }

  async function createConsent(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const c = await api.post<Consent>(
        `/api/v1/tenants/${t()}/consents`,
        { plan_id: id, consenter_name: consenter },
        t(),
      );
      setConsents((list) => [...list, c]);
      setConsenter("");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function decide(cid: string) {
    setError("");
    try {
      const c = await api.post<Consent>(
        `/api/v1/tenants/${t()}/consents/${cid}/decide`,
        { decision },
        t(),
      );
      setConsents((list) => list.map((x) => (x.id === cid ? c : x)));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Shell>
      {loading ? (
        <LoadingState label="Loading plan" />
      ) : error && !plan ? (
        <Alert tone="danger" title="Could not load plan">
          {error}
        </Alert>
      ) : plan ? (
        <>
          <p>
            <Link href="/dental/plans">Back to treatment plans</Link>
          </p>
          {error ? (
            <Alert tone="danger" title="Something went wrong">
              {error}
            </Alert>
          ) : null}
          <Card title={`Plan v${plan.version}`}>
            <p>
              <Status value={plan.status} /> {plan.notes ?? ""}
            </p>
            {plan.status === "draft" ? (
              <>
                <Button onClick={() => void act(`/treatment-plans/${id}/activate`)}>Activate</Button>{" "}
                <Button variant="secondary" onClick={() => void act(`/treatment-plans/${id}/cancel`)}>
                  Cancel plan
                </Button>
              </>
            ) : plan.status === "active" ? (
              <>
                <Button onClick={() => void act(`/treatment-plans/${id}/complete`)}>Complete</Button>{" "}
                <Button variant="secondary" onClick={() => void act(`/treatment-plans/${id}/cancel`)}>
                  Cancel plan
                </Button>
              </>
            ) : null}
          </Card>
          <Card title="Items">
            {plan.items.length === 0 ? (
              <EmptyState title="No items yet" />
            ) : (
              <Table
                caption="Plan items"
                columns={
                  <>
                    <Th>Procedure</Th>
                    <Th numeric>Tooth</Th>
                    <Th>Status</Th>
                    <Th>Actions</Th>
                  </>
                }
              >
                {plan.items.map((i) => (
                  <tr key={i.id}>
                    <Td>{i.procedure_code}</Td>
                    <Td numeric>{i.tooth ?? "-"}</Td>
                    <Td>
                      <Status value={i.status} />
                    </Td>
                    <Td>
                      {(ITEM_NEXT[i.status] ?? []).map((s) => (
                        <span key={s}>
                          <Button size="sm" variant="secondary" onClick={() => void act(`/plan-items/${i.id}/status`, { status: s })}>
                            {s}
                          </Button>{" "}
                        </span>
                      ))}
                    </Td>
                  </tr>
                ))}
              </Table>
            )}
            {plan.status === "draft" ? (
              <form onSubmit={addItem}>
                <h3>Add item</h3>
                <Field label="Procedure code" htmlFor="pi-proc" required>
                  {() => (
                    <Input id="pi-proc" value={procCode} onChange={(e) => setProcCode(e.target.value)} required />
                  )}
                </Field>
                <Field label="Tooth (FDI, optional)" htmlFor="pi-tooth">
                  {() => (
                    <Input id="pi-tooth" type="number" min={11} max={48} value={tooth} onChange={(e) => setTooth(e.target.value)} />
                  )}
                </Field>
                <p>
                  <Button type="submit">Add item</Button>
                </p>
              </form>
            ) : null}
          </Card>
          <Card title="Consent">
            {consents.length === 0 ? (
              <EmptyState title="No consent recorded" />
            ) : (
              <ul>
                {consents.map((c) => (
                  <li key={c.id}>
                    {c.consenter_name} - <Status value={c.status} />
                  </li>
                ))}
              </ul>
            )}
            <form onSubmit={createConsent}>
              <Field label="Consenter name" htmlFor="c-name" required>
                {() => (
                  <Input id="c-name" value={consenter} onChange={(e) => setConsenter(e.target.value)} required minLength={2} />
                )}
              </Field>
              <Field label="Decision" htmlFor="c-decision">
                {() => (
                  <Select
                    id="c-decision"
                    value={decision}
                    onChange={(e) => setDecision(e.target.value)}
                    options={[
                      { value: "granted", label: "granted" },
                      { value: "declined", label: "declined" },
                    ]}
                  />
                )}
              </Field>
              <p>
                <Button type="submit">Record consent</Button>
              </p>
            </form>
            {consents
              .filter((c) => c.status === "pending")
              .map((c) => (
                <p key={`d-${c.id}`}>
                  <Button size="sm" onClick={() => void decide(c.id)}>
                    Apply decision ({decision})
                  </Button>
                </p>
              ))}
          </Card>
        </>
      ) : null}
    </Shell>
  );
}
