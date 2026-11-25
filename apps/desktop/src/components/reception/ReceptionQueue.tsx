import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  LoadingState,
  Select,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { fetchTenantLocations } from "../../lib/api";
import { fmtTime, statusLabel, toDateInput } from "../../lib/format";
import { hasPerm } from "../../lib/nav";
import { createPatient, listPatients, Patient } from "../../lib/patientsApi";
import {
  allowedTransitions,
  Appointment,
  AppointmentStatus,
  createAppointment,
  fetchReceptionQueue,
  flattenQueue,
  listPractitioners,
  Practitioner,
  updateAppointmentStatus,
} from "../../lib/schedulingApi";
import { useSession } from "../../lib/session";

const POLL_MS = 15000;

export function ReceptionQueue({
  onOpenPatient,
  onRegisterHandoff,
  onConsult,
  onSessionExpired,
}: {
  onOpenPatient: (id: string) => void;
  onRegisterHandoff: () => void;
  onConsult?: (appointmentId: string, patientId: string) => void;
  onSessionExpired: () => void;
}) {
  const { tenant, workspace } = useSession();
  const canCreateAppt = hasPerm(workspace?.permissions, "appointment.create");
  const canUpdateAppt = hasPerm(workspace?.permissions, "appointment.update");
  const canCreatePatient = hasPerm(workspace?.permissions, "patient.create");

  const [locationId, setLocationId] = useState("");
  const [locations, setLocations] = useState<Array<{ id: string; name: string }>>([]);
  const [practitionerId, setPractitionerId] = useState("");
  const [practitioners, setPractitioners] = useState<Practitioner[]>([]);
  const [day, setDay] = useState(toDateInput(new Date()));
  const [rows, setRows] = useState<Array<Appointment & { bucket: string }>>([]);
  const [patientNames, setPatientNames] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<string | null>(null);

  const [patientQ, setPatientQ] = useState("");
  const [patients, setPatients] = useState<Patient[]>([]);
  const [walkInPatientId, setWalkInPatientId] = useState("");
  const [walkInPrac, setWalkInPrac] = useState("");
  const [walkInBusy, setWalkInBusy] = useState(false);
  const [quickName, setQuickName] = useState("");
  const [quickPhone, setQuickPhone] = useState("");

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
        const preferred = workspace?.location_ids?.[0] ?? locs[0]?.id ?? "";
        setLocationId((prev) => prev || preferred);
        if (pracs[0]) {
          setWalkInPrac(pracs[0].id);
        }
      } catch (e) {
        if (String(e).includes("session_expired")) onSessionExpired();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenant?.id]);

  async function reloadQueue() {
    if (!tenant || !locationId) return;
    setLoading(true);
    setError(null);
    try {
      const queue = await fetchReceptionQueue(tenant.id, locationId, {
        day,
        practitionerId: practitionerId || undefined,
      });
      const flat = flattenQueue(queue);
      setRows(flat);
      setLastRefresh(new Date().toLocaleTimeString());

      // Resolve display names via authorized patient list (no PHI logging).
      const ids = [...new Set(flat.map((r) => r.patient_id))];
      if (ids.length && hasPerm(workspace?.permissions, "patient.read")) {
        const listed = await listPatients(tenant.id, { limit: 200, activeOnly: false });
        const map: Record<string, string> = {};
        for (const p of listed) {
          if (ids.includes(p.id)) map[p.id] = p.display_name;
        }
        setPatientNames((prev) => ({ ...prev, ...map }));
      }
    } catch (e) {
      if (String(e).includes("session_expired")) onSessionExpired();
      else if (String(e).includes("forbidden"))
        setError("You do not have permission to view the reception queue.");
      else setError("Failed to load reception queue.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void reloadQueue();
  }, [tenant?.id, locationId, practitionerId, day]);

  useEffect(() => {
    if (!tenant || !locationId) return;
    const id = window.setInterval(() => {
      void reloadQueue();
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [tenant?.id, locationId, practitionerId, day]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!tenant || !patientQ.trim()) {
        setPatients([]);
        return;
      }
      try {
        const found = await listPatients(tenant.id, {
          q: patientQ.trim(),
          limit: 20,
          activeOnly: true,
        });
        if (!cancelled) setPatients(found);
      } catch {
        if (!cancelled) setPatients([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenant?.id, patientQ]);

  const waitingCount = useMemo(
    () => rows.filter((r) => r.bucket === "waiting").length,
    [rows],
  );
  const checkedInCount = useMemo(
    () => rows.filter((r) => r.bucket === "checked_in").length,
    [rows],
  );

  async function transition(appt: Appointment, status: AppointmentStatus) {
    if (!tenant || !canUpdateAppt) return;
    setError(null);
    setInfo(null);
    try {
      const updated = await updateAppointmentStatus(tenant.id, appt.id, status);
      if (status === "checked_in") {
        setInfo(
          `Checked in${updated.queue_token != null ? ` · queue token ${updated.queue_token}` : ""}.`,
        );
      } else {
        setInfo(`Status → ${statusLabel(status)}.`);
      }
      await reloadQueue();
    } catch (err) {
      const msg = String(err);
      if (msg.includes("session_expired")) onSessionExpired();
      else if (msg.includes("invalid_transition"))
        setError("Status transition not allowed (duplicate check-in or invalid state).");
      else setError("Action failed.");
    }
  }

  async function onWalkIn(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !canCreateAppt) return;
    let pid = walkInPatientId;
    setWalkInBusy(true);
    setError(null);
    setInfo(null);
    try {
      if (!pid && canCreatePatient && quickName.trim().length >= 2) {
        const created = await createPatient(tenant.id, {
          display_name: quickName.trim(),
          phone: quickPhone.trim() || null,
        });
        pid = created.id;
        setPatientNames((prev) => ({ ...prev, [pid]: created.display_name }));
        if (created.potential_duplicates?.length) {
          setInfo(
            `New patient registered with ${created.potential_duplicates.length} possible duplicate(s).`,
          );
        }
      }
      if (!pid || !walkInPrac || !locationId) {
        setError("Select or register a patient, practitioner, and location.");
        return;
      }
      const now = new Date();
      const start = `${toDateInput(now)}T${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:00`;
      const created = await createAppointment(tenant.id, {
        patient_id: pid,
        practitioner_id: walkInPrac,
        location_id: locationId,
        start,
        duration_minutes: 30,
        walk_in: true,
        notes: "walk-in",
      });
      setInfo(
        `Walk-in registered${created.queue_token != null ? ` · token ${created.queue_token}` : ""} (${statusLabel(created.status)}).`,
      );
      setWalkInPatientId("");
      setQuickName("");
      setQuickPhone("");
      setPatientQ("");
      await reloadQueue();
    } catch (err) {
      const msg = String(err);
      if (msg.includes("session_expired")) onSessionExpired();
      else if (msg.includes("conflict"))
        setError("Walk-in conflict — practitioner may already have an overlapping appointment.");
      else setError(msg.replace(/^Error:\s*/, "") || "Walk-in failed.");
    } finally {
      setWalkInBusy(false);
    }
  }

  return (
    <div className="hos-reception">
      <header className="hos-module-header">
        <h1>Reception</h1>
        <p className="hos-muted">
          Queue · check-in · walk-in · refreshes every {POLL_MS / 1000}s (polling, not push)
        </p>
      </header>

      {error && (
        <Alert tone="danger" title="Reception">
          {error}
        </Alert>
      )}
      {info && (
        <Alert tone="success" title="Updated">
          {info}
        </Alert>
      )}

      <div className="hos-toolbar-row">
        <Field label="Location" htmlFor="rq-loc">
          {({ describedBy }) => (
            <Select
              id="rq-loc"
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
        <Field label="Practitioner filter" htmlFor="rq-prac">
          {({ describedBy }) => (
            <Select
              id="rq-prac"
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
        <Field label="Day" htmlFor="rq-day">
          {({ describedBy }) => (
            <Input
              id="rq-day"
              type="date"
              aria-describedby={describedBy}
              value={day}
              onChange={(ev) => setDay(ev.target.value)}
            />
          )}
        </Field>
        <Button type="button" size="sm" variant="secondary" onClick={() => void reloadQueue()}>
          Refresh now
        </Button>
        <Badge tone="info">
          Waiting {waitingCount} · Checked in {checkedInCount}
        </Badge>
        {lastRefresh && (
          <span className="hos-caption">Last refresh {lastRefresh}</span>
        )}
      </div>

      <div className="hos-reception-layout">
        <Card title="Queue">
          {loading && rows.length === 0 ? (
            <LoadingState label="Loading queue" />
          ) : rows.length === 0 ? (
            <EmptyState title="Queue empty">
              No appointments for this location/day, or none visible with current filters.
            </EmptyState>
          ) : (
            <Table
              columns={
                <>
                  <Th>Token / pos</Th>
                  <Th>Patient</Th>
                  <Th>Time</Th>
                  <Th>Practitioner</Th>
                  <Th>Status</Th>
                  <Th>Actions</Th>
                </>
              }
            >
              {rows.map((r, idx) => {
                  const transitions = allowedTransitions(r.status);
                  return (
                    <tr key={r.id}>
                      <Td>
                        {r.queue_token ?? "—"}
                        <span className="hos-caption"> · #{idx + 1}</span>
                      </Td>
                      <Td>
                        <button
                          type="button"
                          className="hos-link-btn"
                          onClick={() => onOpenPatient(r.patient_id)}
                        >
                          {patientNames[r.patient_id] ?? r.patient_id.slice(0, 8)}
                        </button>
                      </Td>
                      <Td>{fmtTime(r.start_at)}</Td>
                      <Td>
                        {practitioners.find((p) => p.id === r.practitioner_id)
                          ?.display_name ?? r.practitioner_id.slice(0, 8)}
                      </Td>
                      <Td>{statusLabel(r.status)}</Td>
                      <Td>
                        <div className="hos-inline-actions">
                          {onConsult && (
                            <Button
                              type="button"
                              size="sm"
                              variant="secondary"
                              onClick={() => onConsult(r.id, r.patient_id)}
                            >
                              Consult
                            </Button>
                          )}
                          {canUpdateAppt &&
                            transitions.includes("checked_in") && (
                              <Button
                                type="button"
                                size="sm"
                                onClick={() => void transition(r, "checked_in")}
                              >
                                Check in
                              </Button>
                            )}
                          {canUpdateAppt &&
                            transitions
                              .filter((t) => t !== "checked_in" && t !== "cancelled")
                              .map((t) => (
                                <Button
                                  key={t}
                                  type="button"
                                  size="sm"
                                  variant="secondary"
                                  onClick={() => void transition(r, t)}
                                >
                                  {statusLabel(t)}
                                </Button>
                              ))}
                        </div>
                      </Td>
                    </tr>
                  );
                })}
            </Table>
          )}
        </Card>

        {canCreateAppt && (
          <Card title="Walk-in">
            <form onSubmit={onWalkIn} data-testid="walk-in-form">
              <Field label="Find existing patient" htmlFor="wi-q">
                {({ describedBy }) => (
                  <Input
                    id="wi-q"
                    aria-describedby={describedBy}
                    value={patientQ}
                    onChange={(ev) => setPatientQ(ev.target.value)}
                    placeholder="Name or phone"
                  />
                )}
              </Field>
              <Field label="Patient" htmlFor="wi-patient">
                {({ describedBy }) => (
                  <Select
                    id="wi-patient"
                    aria-describedby={describedBy}
                    value={walkInPatientId}
                    onChange={(ev) => setWalkInPatientId(ev.target.value)}
                    options={[
                      { value: "", label: "Select existing…" },
                      ...patients.map((p) => ({
                        value: p.id,
                        label: `${p.display_name}${p.phone ? ` · ${p.phone}` : ""}`,
                      })),
                    ]}
                  />
                )}
              </Field>
              {canCreatePatient && (
                <>
                  <p className="hos-muted">Or register quickly:</p>
                  <Field label="New patient name" htmlFor="wi-name">
                    {({ describedBy }) => (
                      <Input
                        id="wi-name"
                        aria-describedby={describedBy}
                        value={quickName}
                        onChange={(ev) => setQuickName(ev.target.value)}
                      />
                    )}
                  </Field>
                  <Field label="Phone" htmlFor="wi-phone">
                    {({ describedBy }) => (
                      <Input
                        id="wi-phone"
                        aria-describedby={describedBy}
                        value={quickPhone}
                        onChange={(ev) => setQuickPhone(ev.target.value)}
                      />
                    )}
                  </Field>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    onClick={onRegisterHandoff}
                  >
                    Full registration form…
                  </Button>
                </>
              )}
              <Field label="Practitioner" htmlFor="wi-prac" required>
                {({ describedBy }) => (
                  <Select
                    id="wi-prac"
                    aria-describedby={describedBy}
                    value={walkInPrac}
                    onChange={(ev) => setWalkInPrac(ev.target.value)}
                    required
                    options={practitioners.map((p) => ({
                      value: p.id,
                      label: p.display_name,
                    }))}
                  />
                )}
              </Field>
              <Button type="submit" disabled={walkInBusy} loading={walkInBusy}>
                Register walk-in
              </Button>
              <p className="hos-caption">
                Uses appointment.create with walk_in=true (server sets checked_in + queue token).
              </p>
            </form>
          </Card>
        )}
      </div>
    </div>
  );
}
