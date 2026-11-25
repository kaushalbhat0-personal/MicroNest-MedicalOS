import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  LoadingState,
  Select,
} from "@healthcare-os/ui";
import { fetchTenantLocations } from "../../lib/api";
import {
  addDays,
  fmtTime,
  fmtWhen,
  startOfDay,
  statusLabel,
  toDateInput,
  toIsoLocal,
  weekRange,
} from "../../lib/format";
import { hasPerm } from "../../lib/nav";
import { listPatients, Patient } from "../../lib/patientsApi";
import {
  allowedTransitions,
  Appointment,
  AppointmentStatus,
  cancelAppointment,
  createAppointment,
  fetchAvailability,
  listAppointments,
  listPractitioners,
  Practitioner,
  rescheduleAppointment,
  Slot,
  updateAppointmentStatus,
} from "../../lib/schedulingApi";
import { useSession } from "../../lib/session";

type ViewMode = "day" | "week";

export function ScheduleCalendar({
  initialPatientId,
  onOpenPatient,
  onConsult,
  onSessionExpired,
}: {
  initialPatientId?: string | null;
  onOpenPatient: (id: string) => void;
  onConsult?: (appointmentId: string, patientId: string) => void;
  onSessionExpired: () => void;
}) {
  const { tenant, workspace } = useSession();
  const canCreate = hasPerm(workspace?.permissions, "appointment.create");
  const canUpdate = hasPerm(workspace?.permissions, "appointment.update");

  const [view, setView] = useState<ViewMode>("day");
  const [anchor, setAnchor] = useState(() => startOfDay(new Date()));
  const [locationId, setLocationId] = useState("");
  const [locations, setLocations] = useState<Array<{ id: string; name: string }>>([]);
  const [practitionerId, setPractitionerId] = useState("");
  const [practitioners, setPractitioners] = useState<Practitioner[]>([]);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const [patientId, setPatientId] = useState(initialPatientId ?? "");
  const [patientQ, setPatientQ] = useState("");
  const [bookDay, setBookDay] = useState(toDateInput(new Date()));
  const [duration, setDuration] = useState(30);
  const [notes, setNotes] = useState("");
  const [slots, setSlots] = useState<Slot[]>([]);
  const [selectedSlot, setSelectedSlot] = useState("");
  const [booking, setBooking] = useState(false);

  const [selected, setSelected] = useState<Appointment | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [rescheduleStart, setRescheduleStart] = useState("");
  const [busyAction, setBusyAction] = useState(false);

  useEffect(() => {
    if (initialPatientId) setPatientId(initialPatientId);
  }, [initialPatientId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!tenant) return;
      try {
        const [locs, pracs] = await Promise.all([
          fetchTenantLocations(tenant.id),
          listPractitioners(tenant.id),
        ]);
        if (cancelled) return;
        setLocations(locs);
        setPractitioners(pracs);
        const preferred =
          workspace?.location_ids?.[0] ?? locs[0]?.id ?? "";
        setLocationId((prev) => prev || preferred);
        if (pracs[0] && !practitionerId) setPractitionerId(pracs[0].id);
      } catch (e) {
        if (String(e).includes("session_expired")) onSessionExpired();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenant?.id]);

  const range = useMemo(() => {
    if (view === "day") {
      const start = startOfDay(anchor);
      return { start, end: addDays(start, 1) };
    }
    return weekRange(anchor);
  }, [anchor, view]);

  async function reloadAppointments() {
    if (!tenant) return;
    setLoading(true);
    setError(null);
    try {
      const items = await listAppointments(tenant.id, {
        locationId: locationId || undefined,
        practitionerId: practitionerId || undefined,
        startFrom: range.start.toISOString(),
        startTo: range.end.toISOString(),
        limit: 200,
      });
      setAppointments(items);
    } catch (e) {
      if (String(e).includes("session_expired")) onSessionExpired();
      else if (String(e).includes("forbidden"))
        setError("You do not have permission to view the schedule.");
      else setError("Failed to load appointments.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void reloadAppointments();
  }, [tenant?.id, locationId, practitionerId, range.start.getTime(), range.end.getTime()]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!tenant || !patientQ.trim()) {
        setPatients([]);
        return;
      }
      try {
        const rows = await listPatients(tenant.id, {
          q: patientQ.trim(),
          limit: 20,
          activeOnly: true,
        });
        if (!cancelled) setPatients(rows);
      } catch {
        if (!cancelled) setPatients([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenant?.id, patientQ]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!tenant || !practitionerId || !locationId || !bookDay) {
        setSlots([]);
        return;
      }
      try {
        const avail = await fetchAvailability(tenant.id, {
          practitionerId,
          locationId,
          day: bookDay,
        });
        if (!cancelled) {
          setSlots(avail?.slots ?? []);
          setSelectedSlot("");
        }
      } catch {
        if (!cancelled) setSlots([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenant?.id, practitionerId, locationId, bookDay]);

  async function onBook(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !canCreate) return;
    if (!patientId || !practitionerId || !locationId || !selectedSlot) {
      setError("Patient, practitioner, location, and an available slot are required.");
      return;
    }
    setBooking(true);
    setError(null);
    setInfo(null);
    try {
      const created = await createAppointment(tenant.id, {
        patient_id: patientId,
        practitioner_id: practitionerId,
        location_id: locationId,
        start: selectedSlot,
        duration_minutes: duration,
        notes: notes.trim() || null,
        walk_in: false,
      });
      setInfo(`Appointment booked (${statusLabel(created.status)}).`);
      setNotes("");
      await reloadAppointments();
    } catch (err) {
      const msg = String(err);
      if (msg.includes("session_expired")) onSessionExpired();
      else if (msg.includes("conflict"))
        setError("Time conflict — slot no longer available. Pick another slot.");
      else setError(msg.replace(/^Error:\s*/, "") || "Booking failed.");
    } finally {
      setBooking(false);
    }
  }

  async function applyStatus(appt: Appointment, status: AppointmentStatus) {
    if (!tenant || !canUpdate) return;
    setBusyAction(true);
    setError(null);
    try {
      await updateAppointmentStatus(tenant.id, appt.id, status);
      setInfo(`Status updated to ${statusLabel(status)}.`);
      setSelected(null);
      await reloadAppointments();
    } catch (err) {
      if (String(err).includes("session_expired")) onSessionExpired();
      else if (String(err).includes("invalid_transition"))
        setError("That status transition is not allowed.");
      else setError("Status update failed.");
    } finally {
      setBusyAction(false);
    }
  }

  async function onCancel() {
    if (!tenant || !selected || !canUpdate) return;
    setBusyAction(true);
    try {
      await cancelAppointment(tenant.id, selected.id);
      setCancelOpen(false);
      setSelected(null);
      setInfo("Appointment cancelled.");
      await reloadAppointments();
    } catch (err) {
      if (String(err).includes("session_expired")) onSessionExpired();
      else setError("Cancellation failed.");
    } finally {
      setBusyAction(false);
    }
  }

  async function onReschedule() {
    if (!tenant || !selected || !canUpdate || !rescheduleStart) return;
    setBusyAction(true);
    try {
      const durationMinutes = Math.max(
        5,
        Math.round(
          (new Date(selected.end_at).getTime() -
            new Date(selected.start_at).getTime()) /
            60000,
        ),
      );
      await rescheduleAppointment(tenant.id, selected.id, {
        start: rescheduleStart.includes("T")
          ? rescheduleStart.length === 16
            ? `${rescheduleStart}:00`
            : rescheduleStart
          : toIsoLocal(new Date(rescheduleStart)),
        duration_minutes: durationMinutes,
      });
      setInfo("Appointment rescheduled.");
      setSelected(null);
      await reloadAppointments();
    } catch (err) {
      const msg = String(err);
      if (msg.includes("session_expired")) onSessionExpired();
      else if (msg.includes("conflict")) setError("Reschedule conflict.");
      else if (msg.includes("cannot_reschedule"))
        setError("Only scheduled/confirmed appointments can be rescheduled.");
      else setError("Reschedule failed.");
    } finally {
      setBusyAction(false);
    }
  }

  const patientName = (id: string) =>
    patients.find((p) => p.id === id)?.display_name ??
    (id === patientId ? "Selected patient" : id.slice(0, 8));

  const pracName = (id: string) =>
    practitioners.find((p) => p.id === id)?.display_name ?? id.slice(0, 8);

  const dayColumns = useMemo(() => {
    if (view === "day") return [startOfDay(anchor)];
    const { start } = weekRange(anchor);
    return Array.from({ length: 7 }, (_, i) => addDays(start, i));
  }, [view, anchor]);

  return (
    <div className="hos-schedule">
      <header className="hos-module-header">
        <h1>Appointments</h1>
        <p className="hos-muted">Day/week calendar with server-side availability</p>
      </header>

      {error && (
        <Alert tone="danger" title="Schedule">
          {error}
        </Alert>
      )}
      {info && (
        <Alert tone="success" title="Updated">
          {info}
        </Alert>
      )}

      <div className="hos-toolbar-row">
        <Button
          type="button"
          size="sm"
          variant={view === "day" ? "primary" : "secondary"}
          onClick={() => setView("day")}
        >
          Day
        </Button>
        <Button
          type="button"
          size="sm"
          variant={view === "week" ? "primary" : "secondary"}
          onClick={() => setView("week")}
        >
          Week
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={() => setAnchor(addDays(anchor, view === "day" ? -1 : -7))}
        >
          Previous
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={() => setAnchor(startOfDay(new Date()))}
        >
          Today
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={() => setAnchor(addDays(anchor, view === "day" ? 1 : 7))}
        >
          Next
        </Button>
        <Field label="Location" htmlFor="sched-loc">
          {({ describedBy }) => (
            <Select
              id="sched-loc"
              aria-describedby={describedBy}
              value={locationId}
              onChange={(ev) => setLocationId(ev.target.value)}
              options={locations.map((l) => ({
                value: l.id,
                label: l.name,
              }))}
            />
          )}
        </Field>
        <Field label="Practitioner" htmlFor="sched-prac">
          {({ describedBy }) => (
            <Select
              id="sched-prac"
              aria-describedby={describedBy}
              value={practitionerId}
              onChange={(ev) => setPractitionerId(ev.target.value)}
              options={[
                { value: "", label: "All" },
                ...practitioners.map((p) => ({
                  value: p.id,
                  label: p.display_name,
                })),
              ]}
            />
          )}
        </Field>
      </div>

      <div className="hos-schedule-layout">
        <Card title={view === "day" ? toDateInput(anchor) : "Week view"}>
          {loading ? (
            <LoadingState label="Loading calendar" />
          ) : appointments.length === 0 ? (
            <EmptyState title="No appointments in range">
              Book below using an available slot.
            </EmptyState>
          ) : (
            <div className={`hos-cal-grid hos-cal-${view}`}>
              {dayColumns.map((day) => {
                const key = toDateInput(day);
                const dayAppts = appointments.filter(
                  (a) => toDateInput(new Date(a.start_at)) === key,
                );
                return (
                  <div key={key} className="hos-cal-day">
                    <h3>{key}</h3>
                    {dayAppts.length === 0 ? (
                      <p className="hos-muted">—</p>
                    ) : (
                      dayAppts.map((a) => (
                        <button
                          key={a.id}
                          type="button"
                          className={`hos-cal-appt hos-cal-${a.status}`}
                          onClick={() => {
                            setSelected(a);
                            setRescheduleStart(
                              toIsoLocal(new Date(a.start_at)).slice(0, 16),
                            );
                          }}
                        >
                          <strong>{fmtTime(a.start_at)}</strong>
                          <span>{statusLabel(a.status)}</span>
                          <span className="hos-caption">
                            Pt {a.patient_id.slice(0, 8)} · {pracName(a.practitioner_id)}
                          </span>
                        </button>
                      ))
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        {canCreate && (
          <Card title="Book appointment">
            <form onSubmit={onBook}>
              <Field label="Find patient" htmlFor="book-pq">
                {({ describedBy }) => (
                  <Input
                    id="book-pq"
                    aria-describedby={describedBy}
                    value={patientQ}
                    onChange={(ev) => setPatientQ(ev.target.value)}
                    placeholder="Search name/phone"
                  />
                )}
              </Field>
              <Field label="Patient" htmlFor="book-patient" required>
                {({ describedBy }) => (
                  <Select
                    id="book-patient"
                    aria-describedby={describedBy}
                    value={patientId}
                    onChange={(ev) => setPatientId(ev.target.value)}
                    required
                    options={[
                      { value: "", label: "Select…" },
                      ...(patientId &&
                      !patients.some((p) => p.id === patientId)
                        ? [
                            {
                              value: patientId,
                              label: `Current (${patientId.slice(0, 8)})`,
                            },
                          ]
                        : []),
                      ...patients.map((p) => ({
                        value: p.id,
                        label: `${p.display_name}${p.phone ? ` · ${p.phone}` : ""}`,
                      })),
                    ]}
                  />
                )}
              </Field>
              <Field label="Day" htmlFor="book-day" required>
                {({ describedBy }) => (
                  <Input
                    id="book-day"
                    type="date"
                    aria-describedby={describedBy}
                    value={bookDay}
                    onChange={(ev) => setBookDay(ev.target.value)}
                    required
                  />
                )}
              </Field>
              <Field label="Available slot" htmlFor="book-slot" required>
                {({ describedBy }) => (
                  <Select
                    id="book-slot"
                    aria-describedby={describedBy}
                    value={selectedSlot}
                    onChange={(ev) => setSelectedSlot(ev.target.value)}
                    required
                    options={[
                      {
                        value: "",
                        label: slots.length
                          ? "Select slot…"
                          : "No slots (check practitioner/day)",
                      },
                      ...slots.map((s) => ({
                        value: s.start_at,
                        label: `${fmtTime(s.start_at)} – ${fmtTime(s.end_at)}`,
                      })),
                    ]}
                  />
                )}
              </Field>
              <Field label="Duration (minutes)" htmlFor="book-dur">
                {({ describedBy }) => (
                  <Input
                    id="book-dur"
                    type="number"
                    min={5}
                    max={480}
                    aria-describedby={describedBy}
                    value={duration}
                    onChange={(ev) => setDuration(Number(ev.target.value) || 30)}
                  />
                )}
              </Field>
              <Field label="Notes" htmlFor="book-notes">
                {({ describedBy }) => (
                  <Input
                    id="book-notes"
                    aria-describedby={describedBy}
                    value={notes}
                    onChange={(ev) => setNotes(ev.target.value)}
                  />
                )}
              </Field>
              <Button type="submit" disabled={booking} loading={booking}>
                Book
              </Button>
              <p className="hos-caption">
                Availability is checked server-side; conflicts return an error.
              </p>
            </form>
          </Card>
        )}
      </div>

      {selected && (
        <Card title="Appointment details">
          <dl className="hos-dl">
            <div>
              <dt>When</dt>
              <dd>
                {fmtWhen(selected.start_at)} – {fmtTime(selected.end_at)}
              </dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{statusLabel(selected.status)}</dd>
            </div>
            <div>
              <dt>Patient</dt>
              <dd>
                <button
                  type="button"
                  className="hos-link-btn"
                  onClick={() => onOpenPatient(selected.patient_id)}
                >
                  {patientName(selected.patient_id)}
                </button>
              </dd>
            </div>
            <div>
              <dt>Practitioner</dt>
              <dd>{pracName(selected.practitioner_id)}</dd>
            </div>
            <div>
              <dt>Queue token</dt>
              <dd>{selected.queue_token ?? "—"}</dd>
            </div>
            <div>
              <dt>Notes</dt>
              <dd>{selected.notes ?? "—"}</dd>
            </div>
          </dl>
          {onConsult &&
            !["cancelled", "no_show"].includes(selected.status) && (
              <div className="hos-toolbar-row">
                <Button
                  type="button"
                  size="sm"
                  onClick={() => onConsult(selected.id, selected.patient_id)}
                >
                  Open consultation
                </Button>
              </div>
            )}
          {canUpdate && (
            <div className="hos-toolbar-row">
              {allowedTransitions(selected.status).map((st) =>
                st === "cancelled" ? (
                  <Button
                    key={st}
                    type="button"
                    size="sm"
                    variant="secondary"
                    disabled={busyAction}
                    onClick={() => setCancelOpen(true)}
                  >
                    Cancel…
                  </Button>
                ) : (
                  <Button
                    key={st}
                    type="button"
                    size="sm"
                    variant="secondary"
                    disabled={busyAction}
                    onClick={() => void applyStatus(selected, st)}
                  >
                    Mark {statusLabel(st)}
                  </Button>
                ),
              )}
            </div>
          )}
          {canUpdate &&
            (selected.status === "scheduled" || selected.status === "confirmed") && (
              <div className="hos-toolbar-row">
                <Field label="Reschedule to" htmlFor="resched">
                  {({ describedBy }) => (
                    <Input
                      id="resched"
                      type="datetime-local"
                      aria-describedby={describedBy}
                      value={rescheduleStart}
                      onChange={(ev) => setRescheduleStart(ev.target.value)}
                    />
                  )}
                </Field>
                <Button
                  type="button"
                  size="sm"
                  disabled={busyAction}
                  onClick={() => void onReschedule()}
                >
                  Reschedule
                </Button>
              </div>
            )}
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => setSelected(null)}
          >
            Close
          </Button>
        </Card>
      )}

      <ConfirmDialog
        open={cancelOpen}
        onOpenChange={setCancelOpen}
        title="Cancel appointment?"
        confirmLabel="Cancel appointment"
        pending={busyAction}
        onConfirm={() => void onCancel()}
      >
        This uses the backend cancel API and preserves audit fields. This cannot be undone
        from the desktop UI.
      </ConfirmDialog>
    </div>
  );
}
