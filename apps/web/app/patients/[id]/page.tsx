"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Alert,
  Card,
  EmptyState,
  LoadingState,
  MoneyDisplay,
  PatientIdentityHeader,
  Status,
  Table,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Td,
  Th,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { Shell } from "../../shell";

type Patient = { id: string; display_name: string; phone: string | null; is_active: boolean };
type Encounter = { id: string; status: string; opened_at: string };
type Plan = { id: string; status: string; version: number };
type Recall = { id: string; status: string; due_date: string; reason: string };
type Invoice = {
  id: string;
  status: string;
  grand_total: string;
  outstanding_amount: string;
  currency: string;
};
type Payment = { id: string; status: string; method: string; amount: string; currency: string };

export default function PatientWorkspacePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const [patient, setPatient] = useState<Patient | null>(null);
  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [recalls, setRecalls] = useState<Recall[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [credit, setCredit] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const t = getSelectedTenant();
    if (!t) {
      router.push("/");
      return;
    }
    setLoading(true);
    const get = <T,>(path: string) => api.get<T>(`/api/v1/tenants/${t}${path}`, t);
    Promise.all([
      get<Patient>(`/patients/${id}`),
      get<{ items: Encounter[] }>(`/encounters?patient_id=${id}&limit=50`),
      get<Plan[]>(`/treatment-plans?patient_id=${id}`),
      get<Recall[]>(`/recalls?patient_id=${id}`),
      get<{ items: Invoice[] }>(`/invoices?patient_id=${id}&limit=50`),
      get<{ items: Payment[] }>(`/payments?patient_id=${id}&limit=50`),
      get<{ credit_amount: string }>(`/patients/${id}/credit-balance`),
    ])
      .then(([p, enc, pl, rec, inv, pay, cred]) => {
        setPatient(p);
        setEncounters(enc.items);
        setPlans(pl);
        setRecalls(rec);
        setInvoices(inv.items);
        setPayments(pay.items);
        setCredit(cred.credit_amount);
        setError("");
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id, router]);

  return (
    <Shell>
      {loading ? (
        <LoadingState label="Loading patient" />
      ) : error ? (
        <Alert tone="danger" title="Could not load patient">
          {error}
        </Alert>
      ) : patient ? (
        <>
          <PatientIdentityHeader
            name={patient.display_name}
            patientId={patient.id}
            meta={patient.phone ?? undefined}
            status={patient.is_active ? "current" : "revoked"}
          />
          <Tabs defaultValue="overview">
            <TabsList>
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="encounters">Encounters</TabsTrigger>
              <TabsTrigger value="dental">Dental</TabsTrigger>
              <TabsTrigger value="billing">Billing</TabsTrigger>
            </TabsList>
            <TabsContent value="overview">
              <Card title="Overview">
                <p>
                  Contact: {patient.phone ?? "-"} - Status:{" "}
                  {patient.is_active ? "active" : "inactive"}
                </p>
                <p>
                  {encounters.length} encounters - {plans.length} treatment plans -{" "}
                  {invoices.length} invoices - patient credit{" "}
                  {credit ? <MoneyDisplay amount={credit} /> : "-"}
                </p>
              </Card>
            </TabsContent>
            <TabsContent value="encounters">
              <Card title="Encounters">
                {encounters.length === 0 ? (
                  <EmptyState title="No encounters" />
                ) : (
                  <Table
                    caption="Patient encounters"
                    columns={
                      <>
                        <Th>Opened</Th>
                        <Th>Status</Th>
                      </>
                    }
                  >
                    {encounters.map((e) => (
                      <tr key={e.id}>
                        <Td>
                          <Link href={`/encounters/${e.id}`}>
                            {new Date(e.opened_at).toLocaleString()}
                          </Link>
                        </Td>
                        <Td>
                          <Status value={e.status} />
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
              </Card>
            </TabsContent>
            <TabsContent value="dental">
              <Card title="Treatment plans">
                {plans.length === 0 ? (
                  <EmptyState title="No treatment plans" />
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
              <Card title="Recalls">
                {recalls.length === 0 ? (
                  <EmptyState title="No recalls" />
                ) : (
                  <Table
                    caption="Recalls"
                    columns={
                      <>
                        <Th>Due</Th>
                        <Th>Reason</Th>
                        <Th>Status</Th>
                      </>
                    }
                  >
                    {recalls.map((r) => (
                      <tr key={r.id}>
                        <Td>{r.due_date}</Td>
                        <Td>{r.reason}</Td>
                        <Td>
                          <Status value={r.status} />
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
              </Card>
            </TabsContent>
            <TabsContent value="billing">
              <Card title="Invoices">
                {invoices.length === 0 ? (
                  <EmptyState title="No invoices" />
                ) : (
                  <Table
                    caption="Invoices"
                    columns={
                      <>
                        <Th>Invoice</Th>
                        <Th>Status</Th>
                        <Th numeric>Total</Th>
                        <Th numeric>Outstanding</Th>
                      </>
                    }
                  >
                    {invoices.map((i) => (
                      <tr key={i.id}>
                        <Td>
                          <Link href={`/billing/invoices/${i.id}`}>{i.id.slice(0, 8)}...</Link>
                        </Td>
                        <Td>
                          <Status value={i.status} />
                        </Td>
                        <Td numeric>
                          <MoneyDisplay amount={i.grand_total} currency={i.currency} />
                        </Td>
                        <Td numeric>
                          <MoneyDisplay amount={i.outstanding_amount} currency={i.currency} />
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
              </Card>
              <Card title="Payments">
                {payments.length === 0 ? (
                  <EmptyState title="No payments" />
                ) : (
                  <Table
                    caption="Payments"
                    columns={
                      <>
                        <Th>Method</Th>
                        <Th>Status</Th>
                        <Th numeric>Amount</Th>
                      </>
                    }
                  >
                    {payments.map((p) => (
                      <tr key={p.id}>
                        <Td>{p.method}</Td>
                        <Td>
                          <Status value={p.status} />
                        </Td>
                        <Td numeric>
                          <MoneyDisplay amount={p.amount} currency={p.currency} />
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
              </Card>
            </TabsContent>
          </Tabs>
        </>
      ) : null}
    </Shell>
  );
}
