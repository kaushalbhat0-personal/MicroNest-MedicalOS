"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  LoadingState,
  PageHeader,
  Status,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { Shell } from "../shell";

type FollowUp = {
  id: string;
  patient_id: string;
  location_id: string;
  due_at: string;
  category: string;
  reason: string;
  source_type: string;
  source_id: string | null;
  priority: string;
  status: string;
  next_action: string | null;
};

type Location = { id: string; name: string };

const BUCKETS = [
  { value: "due_today", label: "Due today" },
  { value: "overdue", label: "Overdue" },
  { value: "upcoming", label: "Upcoming" },
  { value: "in_progress", label: "In progress" },
  { value: "assigned_to_me", label: "Assigned to me" },
  { value: "completed", label: "Completed" },
  { value: "all", label: "All" },
] as const;

function sourceHref(fu: FollowUp): string | null {
  if (!fu.source_id) return null;
  if (fu.source_type === "encounter") return `/encounters/${fu.source_id}`;
  if (fu.source_type === "treatment_plan") return `/dental/plans/${fu.source_id}`;
  if (fu.source_type === "appointment") return `/schedule?focus=${fu.source_id}`;
  return null;
}

export default function FollowUpsPage() {
  const router = useRouter();
  const [items, setItems] = useState<FollowUp[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [bucket, setBucket] = useState<string>("due_today");
  const [locationId, setLocationId] = useState("");
  const [category, setCategory] = useState("");
  const [priority, setPriority] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(() => {
    const t = getSelectedTenant();
    if (!t) {
      router.push("/");
      return;
    }
    setLoading(true);
    const params = new URLSearchParams({ limit: "100", bucket });
    if (locationId) params.set("location_id", locationId);
    if (category) params.set("category", category);
    if (priority) params.set("priority", priority);
    Promise.all([
      api.get<FollowUp[]>(`/api/v1/tenants/${t}/follow-ups?${params}`, t),
      api.get<Location[]>(`/api/v1/tenants/${t}/locations`, t).catch(() => []),
    ])
      .then(([rows, locs]) => {
        setItems(rows);
        setLocations(locs);
        setError("");
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [bucket, category, locationId, priority, router]);

  useEffect(() => {
    load();
  }, [load]);

  async function transition(id: string, status: string, extra: Record<string, unknown> = {}) {
    const t = getSelectedTenant();
    if (!t) return;
    setBusyId(id);
    try {
      await api.post(`/api/v1/tenants/${t}/follow-ups/${id}/transition`, { status, ...extra }, t);
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Shell>
      <PageHeader
        title="Follow-ups"
        description="Care follow-ups and outreach tasks. List buckets use UTC calendar days (date-only due dates compared in UTC). Operations dashboard KPIs use each location’s service-day midnight instead — totals near midnight can differ. WhatsApp stays click-to-chat — outcomes are logged only after staff confirm."
      />
      {error ? (
        <Alert tone="danger" title="Could not load follow-ups">
          {error}
        </Alert>
      ) : null}
      <Card title="Filters">
        <p className="hos-helper" role="group" aria-label="Follow-up buckets">
          {BUCKETS.map((b) => (
            <Button
              key={b.value}
              type="button"
              size="sm"
              variant={bucket === b.value ? "primary" : "secondary"}
              onClick={() => setBucket(b.value)}
            >
              {b.label}
            </Button>
          ))}
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "1rem" }}>
          <Field label="Location" htmlFor="fu-loc">
            {() => (
              <select
                id="fu-loc"
                className="hos-input"
                value={locationId}
                onChange={(e) => setLocationId(e.target.value)}
              >
                <option value="">All locations</option>
                {locations.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Category" htmlFor="fu-cat">
            {() => (
              <select
                id="fu-cat"
                className="hos-input"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              >
                <option value="">All</option>
                <option value="encounter">Encounter</option>
                <option value="treatment_plan">Treatment plan</option>
                <option value="prescription">Prescription</option>
                <option value="appointment">Appointment</option>
                <option value="manual">Manual</option>
              </select>
            )}
          </Field>
          <Field label="Priority" htmlFor="fu-pri">
            {() => (
              <select
                id="fu-pri"
                className="hos-input"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
              >
                <option value="">All</option>
                <option value="urgent">Urgent</option>
                <option value="high">High</option>
                <option value="normal">Normal</option>
                <option value="low">Low</option>
              </select>
            )}
          </Field>
        </div>
      </Card>
      <Card title="Workspace">
        {loading ? (
          <LoadingState label="Loading follow-ups" />
        ) : items.length === 0 ? (
          <EmptyState title="No follow-ups in this view" />
        ) : (
          <Table
            caption="Follow-up tasks"
            columns={
              <>
                <Th>Due</Th>
                <Th>Reason</Th>
                <Th>Priority</Th>
                <Th>Status</Th>
                <Th>Actions</Th>
              </>
            }
          >
            {items.map((fu) => {
              const src = sourceHref(fu);
              return (
                <tr key={fu.id}>
                  <Td>{new Date(fu.due_at).toLocaleString()}</Td>
                  <Td>
                    {fu.reason}
                    <br />
                    <span className="hos-helper">
                      {fu.category}
                      {" · "}
                      <Link href={`/patients/${fu.patient_id}`}>Patient</Link>
                      {src ? (
                        <>
                          {" · "}
                          <Link href={src}>Source</Link>
                        </>
                      ) : null}
                    </span>
                  </Td>
                  <Td>
                    <Status value={fu.priority} />
                  </Td>
                  <Td>
                    <Status value={fu.status} />
                  </Td>
                  <Td>
                    {fu.status === "open" || fu.status === "snoozed" ? (
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        loading={busyId === fu.id}
                        onClick={() => transition(fu.id, "in_progress")}
                      >
                        Start
                      </Button>
                    ) : null}{" "}
                    {fu.status !== "completed" && fu.status !== "cancelled" ? (
                      <>
                        <Button
                          type="button"
                          size="sm"
                          loading={busyId === fu.id}
                          onClick={() => transition(fu.id, "completed", { outcome: "completed" })}
                        >
                          Complete
                        </Button>{" "}
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          loading={busyId === fu.id}
                          onClick={() =>
                            transition(fu.id, "snoozed", {
                              snooze_until: new Date(Date.now() + 86400000).toISOString(),
                            })
                          }
                        >
                          Snooze 1d
                        </Button>
                      </>
                    ) : null}
                  </Td>
                </tr>
              );
            })}
          </Table>
        )}
      </Card>
      <Card title="Create manual follow-up">
        <CreateFollowUpForm locations={locations} onCreated={load} onError={setError} />
      </Card>
    </Shell>
  );
}

function CreateFollowUpForm({
  locations,
  onCreated,
  onError,
}: {
  locations: Location[];
  onCreated: () => void;
  onError: (msg: string) => void;
}) {
  const [patientId, setPatientId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [reason, setReason] = useState("");
  const [due, setDue] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const t = getSelectedTenant();
    if (!t) return;
    setSaving(true);
    try {
      await api.post(
        `/api/v1/tenants/${t}/follow-ups`,
        {
          patient_id: patientId,
          location_id: locationId || locations[0]?.id,
          due_at: new Date(due).toISOString(),
          category: "manual",
          reason,
          source_type: "manual",
          priority: "normal",
        },
        t,
      );
      setReason("");
      onCreated();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <Field label="Patient ID" htmlFor="fu-pid" required>
        {() => (
          <Input id="fu-pid" value={patientId} onChange={(e) => setPatientId(e.target.value)} required />
        )}
      </Field>
      <Field label="Location" htmlFor="fu-cloc" required>
        {() => (
          <select
            id="fu-cloc"
            className="hos-input"
            value={locationId}
            onChange={(e) => setLocationId(e.target.value)}
            required
          >
            <option value="">Select</option>
            {locations.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
        )}
      </Field>
      <Field label="Due" htmlFor="fu-due" required>
        {() => (
          <Input
            id="fu-due"
            type="datetime-local"
            value={due}
            onChange={(e) => setDue(e.target.value)}
            required
          />
        )}
      </Field>
      <Field label="Reason" htmlFor="fu-reason" required>
        {() => (
          <Input
            id="fu-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            required
            minLength={2}
          />
        )}
      </Field>
      <Button type="submit" loading={saving}>
        Create follow-up
      </Button>
    </form>
  );
}
