"use client";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  ConfirmDialog,
  Dialog,
  EmptyState,
  Field,
  Input,
  LoadingState,
  PageHeader,
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
  queue_token?: number | null;
};
type Option = { id: string; display_name?: string; name?: string; verification_status?: string };
type CalView = "day" | "week" | "month";

const LIVE = new Set(["scheduled", "confirmed", "checked_in"]);

function startOfDay(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

function addDays(d: Date, n: number): Date {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

function rangeForView(anchor: Date, view: CalView): { from: Date; to: Date; label: string } {
  const day = startOfDay(anchor);
  if (view === "day") {
    return { from: day, to: addDays(day, 1), label: day.toLocaleDateString() };
  }
  if (view === "week") {
    const weekday = (day.getDay() + 6) % 7; // Monday-first
    const from = addDays(day, -weekday);
    return {
      from,
      to: addDays(from, 7),
      label: `${from.toLocaleDateString()} – ${addDays(from, 6).toLocaleDateString()}`,
    };
  }
  const from = new Date(day.getFullYear(), day.getMonth(), 1);
  const to = new Date(day.getFullYear(), day.getMonth() + 1, 1);
  return {
    from,
    to,
    label: from.toLocaleDateString(undefined, { month: "long", year: "numeric" }),
  };
}

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
  const [filterPractitioner, setFilterPractitioner] = useState("");
  const [filterLocation, setFilterLocation] = useState("");
  const [start, setStart] = useState("");
  const [duration, setDuration] = useState("30");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [rescheduling, setRescheduling] = useState<Appointment | null>(null);
  const [selected, setSelected] = useState<Appointment | null>(null);
  const [newStart, setNewStart] = useState("");
  const [newDuration, setNewDuration] = useState("30");
  const [walkIn, setWalkIn] = useState(false);
  const [booking, setBooking] = useState(false);
  const [cancelId, setCancelId] = useState<string | null>(null);
  const [view, setView] = useState<CalView>("day");
  const [anchor, setAnchor] = useState(() => startOfDay(new Date()));

  function load(t: string, from: Date, to: Date, pract: string, loc: string) {
    setLoading(true);
    const q = new URLSearchParams({
      start_from: from.toISOString(),
      start_to: to.toISOString(),
      limit: "200",
    });
    if (pract) q.set("practitioner_id", pract);
    if (loc) q.set("location_id", loc);
    Promise.all([
      api.get<{ items: Appointment[] }>(`/api/v1/tenants/${t}/appointments?${q}`, t),
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
        if (typeof window !== "undefined") {
          const focus = new URLSearchParams(window.location.search).get("focus");
          if (focus) {
            const hit = appts.items.find((a) => a.id === focus) ?? null;
            setSelected(hit);
          }
        }
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
    if (typeof window !== "undefined") {
      const q = new URLSearchParams(window.location.search);
      if (q.get("walkin") === "1") setWalkIn(true);
      const patient = q.get("patient");
      if (patient) setPatientId(patient);
    }
  }, [router]);

  useEffect(() => {
    if (!tenant) return;
    const { from, to } = rangeForView(anchor, view);
    load(tenant, from, to, filterPractitioner, filterLocation);
  }, [tenant, anchor, view, filterPractitioner, filterLocation]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!tenant) return;
    setError("");
    setMessage("");
    setBooking(true);
    try {
      // datetime-local is wall-clock; the API interprets naive input in the
      // location's timezone and persists UTC. No auth data touches storage.
      await api.post<Appointment>(
        `/api/v1/tenants/${tenant}/appointments`,
        {
          patient_id: patientId,
          practitioner_id: practitionerId,
          location_id: locationId,
          start: walkIn ? new Date().toISOString() : start,
          duration_minutes: Number(duration),
          walk_in: walkIn,
        },
        tenant,
      );
      setMessage(walkIn ? "Walk-in checked in." : "Appointment booked.");
      setStart("");
      setWalkIn(false);
      const { from, to } = rangeForView(anchor, view);
      load(tenant, from, to, filterPractitioner, filterLocation);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBooking(false);
    }
  }

  function reload() {
    if (!tenant) return;
    const { from, to } = rangeForView(anchor, view);
    load(tenant, from, to, filterPractitioner, filterLocation);
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
      reload();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function cancel(id: string) {
    if (!tenant) return;
    setError("");
    try {
      await api.post(`/api/v1/tenants/${tenant}/appointments/${id}/cancel`, {}, tenant);
      reload();
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
      reload();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const range = useMemo(() => rangeForView(anchor, view), [anchor, view]);
  const visible = statusFilter ? items.filter((a) => a.status === statusFilter) : items;
  const patientNames = useMemo(() => {
    const map: Record<string, string> = {};
    for (const p of patients) map[p.id] = p.display_name ?? p.name ?? p.id.slice(0, 8);
    return map;
  }, [patients]);
  const practNames = useMemo(() => {
    const map: Record<string, string> = {};
    for (const p of practitioners) map[p.id] = p.display_name ?? p.name ?? p.id.slice(0, 8);
    return map;
  }, [practitioners]);

  return (
    <Shell>
      <PageHeader
        title="Appointments"
        description="Day, week, and month calendar with booking, walk-ins, reschedule, and cancellation."
        actions={
          <Button type="button" variant="secondary" size="sm" onClick={() => router.push("/reception")}>
            Reception queue
          </Button>
        }
      />
      <Card title="Calendar">
        {error ? (
          <Alert tone="danger" title="Something went wrong">
            {error}
          </Alert>
        ) : null}
        {message ? <Alert tone="success">{message}</Alert> : null}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "0.5rem",
            alignItems: "center",
            marginBottom: "0.75rem",
          }}
        >
          <Button
            size="sm"
            variant={view === "day" ? "primary" : "secondary"}
            onClick={() => setView("day")}
            aria-pressed={view === "day"}
          >
            Day
          </Button>
          <Button
            size="sm"
            variant={view === "week" ? "primary" : "secondary"}
            onClick={() => setView("week")}
            aria-pressed={view === "week"}
          >
            Week
          </Button>
          <Button
            size="sm"
            variant={view === "month" ? "primary" : "secondary"}
            onClick={() => setView("month")}
            aria-pressed={view === "month"}
          >
            Month
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() =>
              setAnchor((d) =>
                view === "month"
                  ? new Date(d.getFullYear(), d.getMonth() - 1, 1)
                  : addDays(d, view === "week" ? -7 : -1),
              )
            }
          >
            Previous
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setAnchor(startOfDay(new Date()))}>
            Today
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() =>
              setAnchor((d) =>
                view === "month"
                  ? new Date(d.getFullYear(), d.getMonth() + 1, 1)
                  : addDays(d, view === "week" ? 7 : 1),
              )
            }
          >
            Next
          </Button>
          <strong aria-live="polite">{range.label}</strong>
        </div>
        <div
          style={{
            display: "grid",
            gap: "0.75rem",
            gridTemplateColumns: "repeat(auto-fit, minmax(12rem, 1fr))",
            marginBottom: "0.75rem",
          }}
        >
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
          <Field label="Practitioner" htmlFor="cal-pract">
            {() => (
              <Select
                id="cal-pract"
                value={filterPractitioner}
                onChange={(e) => setFilterPractitioner(e.target.value)}
                options={[
                  { value: "", label: "All practitioners" },
                  ...practitioners.map((p) => ({
                    value: p.id,
                    label: p.display_name ?? p.id,
                  })),
                ]}
              />
            )}
          </Field>
          <Field label="Location" htmlFor="cal-loc">
            {() => (
              <Select
                id="cal-loc"
                value={filterLocation}
                onChange={(e) => setFilterLocation(e.target.value)}
                options={[
                  { value: "", label: "All locations" },
                  ...locations.map((l) => ({ value: l.id, label: l.name ?? l.id })),
                ]}
              />
            )}
          </Field>
        </div>
        {loading ? (
          <LoadingState label="Loading schedule" />
        ) : visible.length === 0 ? (
          <EmptyState
            title="No appointments in this view"
            action={
              <div className="hos-quick-actions">
                <Button
                  type="button"
                  size="sm"
                  onClick={() => document.getElementById("book-appointment")?.scrollIntoView({ behavior: "smooth" })}
                >
                  Book appointment
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setWalkIn(true);
                    document.getElementById("book-appointment")?.scrollIntoView({ behavior: "smooth" });
                  }}
                >
                  Walk-in
                </Button>
              </div>
            }
          >
            Change the day/week/month range, or book below.
          </EmptyState>
        ) : (
          <Table
            caption={`${view} appointments`}
            density="compact"
            columns={
              <>
                <Th>When</Th>
                <Th>Patient</Th>
                <Th>Practitioner</Th>
                <Th>Token</Th>
                <Th>Status</Th>
                <Th>Actions</Th>
              </>
            }
          >
            {visible.map((a) => (
              <tr key={a.id}>
                <Td>
                  <Button type="button" size="sm" variant="ghost" onClick={() => setSelected(a)}>
                    {new Date(a.start_at).toLocaleString()}
                  </Button>
                </Td>
                <Td>
                  <a href={`/patients/${a.patient_id}`} className="hos-truncate">
                    {patientNames[a.patient_id] ?? `${a.patient_id.slice(0, 8)}…`}
                  </a>
                </Td>
                <Td>{practNames[a.practitioner_id] ?? "—"}</Td>
                <Td>{a.queue_token ?? "—"}</Td>
                <Td>
                  <Status value={a.status} />
                </Td>
                <Td>
                  {LIVE.has(a.status) ? (
                    <div className="hos-row-actions">
                      {a.status === "scheduled" ? (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => void setStatus(a.id, "confirmed")}
                        >
                          Confirm
                        </Button>
                      ) : null}
                      {a.status === "scheduled" || a.status === "confirmed" ? (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => void setStatus(a.id, "checked_in")}
                        >
                          Check in
                        </Button>
                      ) : null}
                      {a.status === "checked_in" ? (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => void setStatus(a.id, "completed")}
                        >
                          Complete
                        </Button>
                      ) : null}
                      {a.status === "scheduled" || a.status === "confirmed" ? (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => void setStatus(a.id, "no_show")}
                        >
                          No-show
                        </Button>
                      ) : null}
                      {a.status === "scheduled" || a.status === "confirmed" ? (
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
                      ) : null}
                      <Button size="sm" variant="ghost" onClick={() => setCancelId(a.id)}>
                        Cancel
                      </Button>
                    </div>
                  ) : null}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <ConfirmDialog
        open={cancelId !== null}
        onOpenChange={(o) => {
          if (!o) setCancelId(null);
        }}
        title="Cancel appointment?"
        confirmLabel="Cancel appointment"
        onConfirm={() => {
          if (cancelId) void cancel(cancelId).then(() => setCancelId(null));
        }}
      >
        <p>This cancels the appointment on the server. The slot will free according to clinic rules.</p>
      </ConfirmDialog>
      <Dialog
        open={selected !== null}
        onOpenChange={(o) => {
          if (!o) setSelected(null);
        }}
        title="Appointment details"
        description="Operational details only — clinical notes live on the encounter."
        actions={
          <Button variant="secondary" onClick={() => setSelected(null)}>
            Close
          </Button>
        }
      >
        {selected ? (
          <dl style={{ display: "grid", gap: "0.35rem" }}>
            <div>
              <dt>When</dt>
              <dd>{new Date(selected.start_at).toLocaleString()} → {new Date(selected.end_at).toLocaleTimeString()}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>
                <Status value={selected.status} />
              </dd>
            </div>
            <div>
              <dt>Queue token</dt>
              <dd>{selected.queue_token ?? "Not checked in"}</dd>
            </div>
            <div>
              <dt>Patient</dt>
              <dd>
                <a href={`/patients/${selected.patient_id}`}>
                  {patientNames[selected.patient_id] ?? `${selected.patient_id.slice(0, 8)}…`}
                </a>
              </dd>
            </div>
            <div>
              <dt>Practitioner</dt>
              <dd>{practNames[selected.practitioner_id] ?? "—"}</dd>
            </div>
            <div>
              <dt>Notes</dt>
              <dd>{selected.notes ?? "—"}</dd>
            </div>
          </dl>
        ) : null}
      </Dialog>
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
      <div id="book-appointment">
      <Card title="Book appointment">
        <p className="hos-helper">
          1. Patient → 2. Practitioner &amp; location → 3. Time (or walk-in) → 4. Confirm. Success
          appears only after the server accepts the booking. Availability is enforced server-side.
        </p>
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
          <Checkbox
            id="walk-in"
            label="Walk-in — check in now (server assigns queue token)"
            checked={walkIn}
            onChange={(e) => setWalkIn(e.target.checked)}
          />
          {!walkIn ? (
            <Field label="Start (location wall-clock)" htmlFor="start" required>
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
          ) : null}
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
            <Button type="submit" loading={booking}>
              {walkIn ? "Check in walk-in" : "Confirm booking"}
            </Button>
          </p>
        </form>
      </Card>
      </div>
      <Card title="Location working hours">
        <WorkingHoursEditor tenant={tenant} locations={locations} onError={setError} onMessage={setMessage} />
      </Card>
    </Shell>
  );
}

function WorkingHoursEditor({
  tenant,
  locations,
  onError,
  onMessage,
}: {
  tenant: string | null;
  locations: Option[];
  onError: (m: string) => void;
  onMessage: (m: string) => void;
}) {
  const [locationId, setLocationId] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!locationId && locations[0]) setLocationId(locations[0].id);
  }, [locations, locationId]);

  async function saveDefaults(e: React.FormEvent) {
    e.preventDefault();
    if (!tenant || !locationId) return;
    setSaving(true);
    onError("");
    try {
      await api.put(
        `/api/v1/tenants/${tenant}/locations/${locationId}/working-hours`,
        {
          windows: [0, 1, 2, 3, 4, 5].map((weekday) => ({
            weekday,
            start_local: "09:00:00",
            end_local: "17:00:00",
            slot_minutes: 30,
          })),
        },
        tenant,
      );
      onMessage("Working hours set to Mon–Sat 09:00–17:00 (30 min slots).");
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={saveDefaults}>
      <p className="hos-helper">
        Portal self-booking needs published hours. Apply a simple Mon–Sat clinic day as a starting
        template.
      </p>
      <Field label="Location" htmlFor="hours-loc">
        {() => (
          <Select
            id="hours-loc"
            value={locationId}
            onChange={(e) => setLocationId(e.target.value)}
            options={[
              { value: "", label: "Select location" },
              ...locations.map((l) => ({ value: l.id, label: l.name ?? l.id })),
            ]}
          />
        )}
      </Field>
      <p>
        <Button type="submit" variant="secondary" loading={saving}>
          Apply Mon–Sat 09:00–17:00
        </Button>
      </p>
    </form>
  );
}
