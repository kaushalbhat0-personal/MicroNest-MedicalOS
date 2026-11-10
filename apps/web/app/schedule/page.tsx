"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Dialog,
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
import { Shell } from "../shell";

type Appointment = {
  id: string;
  patient_id: string;
  practitioner_id: string;
  location_id: string;
  start_at: string;
  end_at: string;
  timezone: string;
  status: string;
  notes: string | null;
};
type Option = { id: string; display_name?: string; name?: string; verification_status?: string };

const LIVE = new Set(["scheduled", "confirmed", "checked_in"]);

export default function SchedulePage() {
  const router = useRouter();
  const [tenant, setTenant] = useState<string | null>(null);
  const [items, setItems] = useState<Appointment[]>([]);
  const [patients, setPatients] = useState<Option[]>([]);
  const [practitioners, setPractitioners] = useState<Option[]>([]);
  const [locations, setLocations] = useState<Option[]>([]);
  const [patientId, setPatientId] = useState("");
  const [practitionerId, setPractitionerId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [start, setStart] = useState("");
  const [duration, setDuration] = useState("30");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [rescheduling, setRescheduling] = useState<Appointment | null>(null);
  const [newStart, setNewStart] = useState("");
  const [newDuration, setNewDuration] = useState("30");

  function load(t: string) {
    setLoading(true);
    Promise.all([
      api.get<{ items: Appointment[] }>(`/api/v1/tenants/${t}/appointments`, t),
      api.get<Option[]>(`/api/v1/tenants/${t}/patients`, t),
      api.get<Option[]>(`/api/v1/tenants/${t}/practitioners`, t),
      api.get<Option[]>(`/api/v1/tenants/${t}/locations`, t),
    ])
      .then(([appts, pats, practs, locs]) => {
        setItems(appts.items);
        setPatients(pats);
        setPractitioners(practs.filter((p) => p.verification_status === "approved"));
        setLocations(locs);
        setError("");
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    const t = getSelectedTenant();
    if (!t) {
      router.push("/");
      return;
    }
    setTenant(t);
    load(t);
  }, [router]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!tenant) return;
    setError("");
    setMessage("");
    try {
      // datetime-local is wall-clock; the API interprets naive input in the
      // location's timezone and persists UTC. No auth data touches storage.
      await api.post<Appointment>(
        `/api/v1/tenants/${tenant}/appointments`,
        {
          patient_id: patientId,
          practitioner_id: practitionerId,
          location_id: locationId,
          start,
          duration_minutes: Number(duration),
        },
        tenant,
      );
      setMessage("Appointment booked.");
      setStart("");
      load(tenant);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function setStatus(id: string, status: string) {
    if (!tenant) return;
    setError("");
    try {
      await api.post(
        `/api/v1/tenants/${tenant}/appointments/${id}/status`,
        { status },
        tenant,
      );
      load(tenant);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function cancel(id: string) {
    if (!tenant) return;
    setError("");
    try {
      await api.post(`/api/v1/tenants/${tenant}/appointments/${id}/cancel`, {}, tenant);
      load(tenant);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function doReschedule(e: React.FormEvent) {
    e.preventDefault();
    if (!tenant || !rescheduling) return;
    setError("");
    try {
      await api.patch(
        `/api/v1/tenants/${tenant}/appointments/${rescheduling.id}`,
        { start: newStart, duration_minutes: Number(newDuration) },
        tenant,
      );
      setRescheduling(null);
      setMessage("Appointment rescheduled.");
      load(tenant);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const visible = statusFilter ? items.filter((a) => a.status === statusFilter) : items;

  return (
    <Shell>
      <Card title="Schedule">
        {error ? (
          <Alert tone="danger" title="Something went wrong">
            {error}
          </Alert>
        ) : null}
        {message ? <Alert tone="success">{message}</Alert> : null}
        <Field label="Filter by status" htmlFor="status-filter">
          {() => (
            <Select
              id="status-filter"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              options={[
                { value: "", label: "All statuses" },
                { value: "scheduled", label: "Scheduled" },
                { value: "confirmed", label: "Confirmed" },
                { value: "checked_in", label: "Checked in" },
                { value: "completed", label: "Completed" },
                { value: "cancelled", label: "Cancelled" },
                { value: "no_show", label: "No-show" },
              ]}
            />
          )}
        </Field>
        {loading ? (
          <LoadingState label="Loading schedule" />
        ) : visible.length === 0 ? (
          <EmptyState title="No appointments yet">Book the first one below.</EmptyState>
        ) : (
          <Table
            caption="Appointments"
            density="compact"
            columns={
              <>
                <Th>When</Th>
                <Th>Status</Th>
                <Th>Actions</Th>
              </>
            }
          >
            {visible.map((a) => (
              <tr key={a.id}>
                <Td>{new Date(a.start_at).toLocaleString()}</Td>
                <Td>
                  <Status value={a.status} />
                </Td>
                <Td>
                  {LIVE.has(a.status) && (
                    <>
                      {a.status === "scheduled" && (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => void setStatus(a.id, "confirmed")}
                        >
                          Confirm
                        </Button>
                      )}{" "}
                      {(a.status === "scheduled" || a.status === "confirmed") && (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => void setStatus(a.id, "checked_in")}
                        >
                          Check in
                        </Button>
                      )}{" "}
                      {a.status === "checked_in" && (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => void setStatus(a.id, "completed")}
                        >
                          Complete
                        </Button>
                      )}{" "}
                      {(a.status === "scheduled" || a.status === "confirmed") && (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => void setStatus(a.id, "no_show")}
                        >
                          No-show
                        </Button>
                      )}{" "}
                      {(a.status === "scheduled" || a.status === "confirmed") && (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => {
                            setRescheduling(a);
                            setNewStart("");
                            setNewDuration("30");
                          }}
                        >
                          Reschedule
                        </Button>
                      )}{" "}
                      <Button size="sm" variant="secondary" onClick={() => void cancel(a.id)}>
                        Cancel
                      </Button>
                    </>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <Dialog
        open={rescheduling !== null}
        onOpenChange={(o) => {
          if (!o) setRescheduling(null);
        }}
        title="Reschedule appointment"
        description="Pick a new start time. Practitioner overlap is checked server-side."
        actions={
          <>
            <Button variant="secondary" onClick={() => setRescheduling(null)}>
              Keep
            </Button>
            <Button type="submit" form="reschedule-form">
              Reschedule
            </Button>
          </>
        }
      >
        <form onSubmit={doReschedule} id="reschedule-form">
          <Field label="New start (location time)" htmlFor="new-start" required>
            {() => (
              <Input
                id="new-start"
                type="datetime-local"
                value={newStart}
                onChange={(e) => setNewStart(e.target.value)}
                required
              />
            )}
          </Field>
          <Field label="Duration (minutes)" htmlFor="new-duration" required>
            {() => (
              <Input
                id="new-duration"
                type="number"
                min={5}
                max={480}
                value={newDuration}
                onChange={(e) => setNewDuration(e.target.value)}
                required
              />
            )}
          </Field>
        </form>
      </Dialog>
      <Card title="Book appointment">
        <form onSubmit={create}>
          <Field label="Patient" htmlFor="patient" required>
            {() => (
              <Select
                id="patient"
                value={patientId}
                onChange={(e) => setPatientId(e.target.value)}
                required
                options={[
                  { value: "", label: "Select patient" },
                  ...patients.map((p) => ({
                    value: p.id,
                    label: p.display_name ?? p.id,
                  })),
                ]}
              />
            )}
          </Field>
          <Field label="Practitioner" htmlFor="practitioner" required>
            {() => (
              <Select
                id="practitioner"
                value={practitionerId}
                onChange={(e) => setPractitionerId(e.target.value)}
                required
                options={[
                  { value: "", label: "Select practitioner" },
                  ...practitioners.map((p) => ({
                    value: p.id,
                    label: p.display_name ?? p.id,
                  })),
                ]}
              />
            )}
          </Field>
          <Field label="Location" htmlFor="location" required>
            {() => (
              <Select
                id="location"
                value={locationId}
                onChange={(e) => setLocationId(e.target.value)}
                required
                options={[
                  { value: "", label: "Select location" },
                  ...locations.map((l) => ({ value: l.id, label: l.name ?? l.id })),
                ]}
              />
            )}
          </Field>
          <Field label="Start (location time)" htmlFor="start" required>
            {() => (
              <Input
                id="start"
                type="datetime-local"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                required
              />
            )}
          </Field>
          <Field label="Duration (minutes)" htmlFor="duration" required>
            {() => (
              <Input
                id="duration"
                type="number"
                min={5}
                max={480}
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
                required
              />
            )}
          </Field>
          <p>
            <Button type="submit">Book</Button>
          </p>
        </form>
      </Card>
    </Shell>
  );
}
