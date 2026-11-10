"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Field,
  Input,
  LoadingState,
  MoneyDisplay,
  Status,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { Shell } from "../../../shell";

type Line = {
  id: string;
  description: string;
  line_total: string;
};
type Estimate = {
  id: string;
  status: string;
  currency: string;
  grand_total: string;
  lines: Line[];
};

export default function EstimateDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const [est, setEst] = useState<Estimate | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [converting, setConverting] = useState(false);

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
      .get<Estimate>(`/api/v1/tenants/${tenant}/estimates/${id}`, tenant)
      .then((e) => {
        setEst(e);
        setError("");
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, [id, router]);

  async function act(path: string, body: unknown = {}) {
    setError("");
    try {
      await api.post(`/api/v1/tenants/${t()}/estimates/${id}/${path}`, body, t());
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function convert() {
    setError("");
    setConverting(true);
    try {
      const inv = await api.post<{ id: string }>(
        `/api/v1/tenants/${t()}/estimates/${id}/convert`,
        {},
        t(),
      );
      router.push(`/billing/invoices/${inv.id}`);
    } catch (e) {
      setError((e as Error).message);
      setConverting(false);
    }
  }

  const [lineDesc, setLineDesc] = useState("");
  const [lineRate, setLineRate] = useState("100.00");

  async function addLine(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.post(
        `/api/v1/tenants/${t()}/estimates/${id}/lines`,
        { description: lineDesc, quantity: "1", unit_rate: lineRate },
        t(),
      );
      setLineDesc("");
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Shell>
      {loading ? (
        <LoadingState label="Loading estimate" />
      ) : error && !est ? (
        <Alert tone="danger" title="Could not load estimate">
          {error}
        </Alert>
      ) : est ? (
        <>
          <p>
            <Link href="/billing/estimates">Back to estimates</Link>
          </p>
          {error ? (
            <Alert tone="danger" title="Something went wrong">
              {error}
            </Alert>
          ) : null}
          <Card title={`Estimate ${est.id.slice(0, 8)}...`}>
            <p>
              <Status value={est.status} /> - Total{" "}
              <MoneyDisplay amount={est.grand_total} currency={est.currency} />
            </p>
            {est.status === "draft" ? (
              <>
                <Button onClick={() => void act("issue")}>Issue</Button>{" "}
                <Button variant="secondary" onClick={() => void act("cancel")}>
                  Cancel
                </Button>{" "}
                <Button variant="secondary" onClick={() => void act("expire")}>
                  Expire
                </Button>
              </>
            ) : null}
            {est.status === "issued" ? (
              <>
                {" "}
                <Button onClick={() => void convert()} loading={converting}>
                  Convert to invoice
                </Button>
              </>
            ) : null}
          </Card>
          <Card title="Lines">
            <Table
              caption="Estimate lines"
              columns={
                <>
                  <Th>Description</Th>
                  <Th numeric>Total</Th>
                </>
              }
            >
              {est.lines.map((l) => (
                <tr key={l.id}>
                  <Td>{l.description}</Td>
                  <Td numeric>
                    <MoneyDisplay amount={l.line_total} currency={est.currency} />
                  </Td>
                </tr>
              ))}
            </Table>
            {est.status === "draft" ? (
              <form onSubmit={addLine}>
                <Field label="Description" htmlFor="el-desc" required>
                  {() => (
                    <Input id="el-desc" value={lineDesc} onChange={(e) => setLineDesc(e.target.value)} required />
                  )}
                </Field>
                <Field label="Unit rate (INR)" htmlFor="el-rate" required>
                  {() => (
                    <Input
                      id="el-rate"
                      type="number"
                      step="0.01"
                      min="0"
                      value={lineRate}
                      onChange={(e) => setLineRate(e.target.value)}
                      required
                    />
                  )}
                </Field>
                <p>
                  <Button type="submit">Add line</Button>
                </p>
              </form>
            ) : (
              <p className="hos-helper">
                Issued estimates are immutable - corrections need a new estimate version.
              </p>
            )}
          </Card>
        </>
      ) : null}
    </Shell>
  );
}
