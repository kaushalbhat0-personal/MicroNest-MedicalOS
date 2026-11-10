"use client";
import { useState } from "react";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  LoadingState,
  Status,
  Table,
  Td,
  Th,
  PageHeader,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { Shell } from "../../shell";

type Recall = { id: string; status: string; due_date: string; reason: string };

export default function RecallsPage() {
  const [patientId, setPatientId] = useState("");
  const [recalls, setRecalls] = useState<Recall[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [reason, setReason] = useState("");
  const [locId, setLocId] = useState("");

  async function load(e?: React.FormEvent) {
    e?.preventDefault();
    const t = getSelectedTenant();
    if (!t || !patientId) return;
    setLoading(true);
    try {
      const r = await api.get<Recall[]>(
        `/api/v1/tenants/${t}/recalls?patient_id=${patientId}`,
        t,
      );
      setRecalls(r);
      setError("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    const t = getSelectedTenant();
    if (!t) return;
    setError("");
    try {
      await api.post(
        `/api/v1/tenants/${t}/recalls`,
        { patient_id: patientId, location_id: locId, due_date: dueDate, reason },
        t,
      );
      setDueDate("");
      setReason("");
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function transition(rid: string, status: string) {
    const t = getSelectedTenant();
    if (!t) return;
    setError("");
    try {
      await api.post(`/api/v1/tenants/${t}/recalls/${rid}/status`, { status }, t);
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Shell>
      <PageHeader title="Recalls" description="Per-patient recall queue. Only scheduled recalls can move." />
      {error ? (
        <Alert tone="danger" title="Something went wrong">
          {error}
        </Alert>
      ) : null}
      <Card title="Find recalls">
        <form onSubmit={load}>
          <Field label="Patient ID" htmlFor="rc-patient" required>
            {() => (
              <Input id="rc-patient" value={patientId} onChange={(e) => setPatientId(e.target.value)} required />
            )}
          </Field>
          <p>
            <Button type="submit" loading={loading}>
              Load recalls
            </Button>
          </p>
        </form>
      </Card>
      <Card title="Recall queue">
        {recalls === null ? (
          <EmptyState title="No patient selected" />
        ) : recalls.length === 0 ? (
          <EmptyState title="No recalls" />
        ) : (
          <Table
            caption="Recalls"
            columns={
              <>
                <Th>Due</Th>
                <Th>Reason</Th>
                <Th>Status</Th>
                <Th>Actions</Th>
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
                <Td>
                  {r.status === "scheduled" ? (
                    <>
                      <Button size="sm" variant="secondary" onClick={() => void transition(r.id, "completed")}>
                        Complete
                      </Button>{" "}
                      <Button size="sm" variant="secondary" onClick={() => void transition(r.id, "missed")}>
                        Miss
                      </Button>{" "}
                      <Button size="sm" variant="secondary" onClick={() => void transition(r.id, "cancelled")}>
                        Cancel
                      </Button>
                    </>
                  ) : null}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <Card title="Schedule recall">
        <form onSubmit={create}>
          <Field label="Location ID" htmlFor="rc-loc" required description="Recall belongs to a location.">
            {({ describedBy }) => (
              <Input id="rc-loc" value={locId} onChange={(e) => setLocId(e.target.value)} required aria-describedby={describedBy} />
            )}
          </Field>
          <Field label="Due date" htmlFor="rc-due" required>
            {() => (
              <Input id="rc-due" type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} required />
            )}
          </Field>
          <Field label="Reason" htmlFor="rc-reason" required>
            {() => (
              <Input id="rc-reason" value={reason} onChange={(e) => setReason(e.target.value)} required minLength={2} maxLength={200} />
            )}
          </Field>
          <p>
            <Button type="submit">Schedule recall</Button>
          </p>
        </form>
      </Card>
    </Shell>
  );
}
