import { FormEvent, useEffect, useMemo, useState } from "react";
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
import { fetchOperationsDashboard, fetchTenantLocations } from "../../lib/api";
import {
  listEncounters,
  openEncounter,
  Encounter,
} from "../../lib/clinicalApi";
import { fmtTime, fmtWhen, statusLabel, toDateInput } from "../../lib/format";
import { hasPerm } from "../../lib/nav";
import { listPatients, Patient } from "../../lib/patientsApi";
import {
  Appointment,
  fetchReceptionQueue,
  flattenQueue,
  listAppointments,
  approvedPractitioners,
  listPractitioners,
  Practitioner,
} from "../../lib/schedulingApi";
import { useSession } from "../../lib/session";

export function DoctorConsultBoard({
  initialPatientId,
  initialAppointmentId,
  onOpenEncounter,
  onOpenPatient,
  onSessionExpired,
}: {
  initialPatientId?: string | null;
  initialAppointmentId?: string | null;
  onOpenEncounter: (encounterId: string) => void;
  onOpenPatient: (patientId: string) => void;
  onSessionExpired: () => void;
}) {
  const { tenant, workspace } = useSession();
  const canOpen = hasPerm(workspace?.permissions, "encounter.open");
  const canRead = hasPerm(workspace?.permissions, "encounter.read");

  const [locationId, setLocationId] = useState("");
  const [locations, setLocations] = useState<Array<{ id: string; name: string }>>([]);
  const [practitioners, setPractitioners] = useState<Practitioner[]>([]);
  const [practitionerId, setPractitionerId] = useState("");
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [waiting, setWaiting] = useState<Appointment[]>([]);
  const [openEncounters, setOpenEncounters] = useState<Encounter[]>([]);
  const [patientNames, setPatientNames] = useState<Record<string, string>>({});
  const [opsNext, setOpsNext] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [patientQ, setPatientQ] = useState("");
  const [patients, setPatients] = useState<Patient[]>([]);
  const [manualPatientId, setManualPatientId] = useState(initialPatientId ?? "");
  const [chief, setChief] = useState("");

  useEffect(() => {
    if (initialPatientId) setManualPatientId(initialPatientId);
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
        const approved = approvedPractitioners(pracs);
        setPractitioners(approved);
        const loc = workspace?.location_ids?.[0] ?? locs[0]?.id ?? "";
        setLocationId((prev) => prev || loc);
        const preferred =
          approved.find((p) => /linked/i.test(p.display_name)) ?? approved[0];
        if (preferred) setPractitionerId((prev) => prev || preferred.id);
      } catch (e) {
        if (String(e).includes("session_expired")) onSessionExpired();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenant?.id]);

  async function reload() {
    if (!tenant || !locationId) return;
    setLoading(true);
    setError(null);
    try {
      const day = toDateInput(new Date());
      const start = new Date();
      start.setHours(0, 0, 0, 0);
      const end = new Date();
      end.setHours(23, 59, 59, 999);

      const [appts, queue, encs, ops, pats] = await Promise.all([
        listAppointments(tenant.id, {
          locationId,
          practitionerId: practitionerId || undefined,
          startFrom: start.toISOString(),
          startTo: end.toISOString(),
          limit: 100,
        }),
        fetchReceptionQueue(tenant.id, locationId, { day }),
        canRead
          ? listEncounters(tenant.id, {
              locationId,
              practitionerId: practitionerId || undefined,
              status: "open",
              limit: 50,
            })
          : Promise.resolve([]),
        hasPerm(workspace?.permissions, "tenant.read")
          ? fetchOperationsDashboard(tenant.id, locationId).catch(() => null)
          : Promise.resolve(null),
        hasPerm(workspace?.permissions, "patient.read")
          ? listPatients(tenant.id, { limit: 200, activeOnly: true })
          : Promise.resolve([]),
      ]);

      setAppointments(
        appts.filter((a) => !["cancelled", "no_show", "completed"].includes(a.status)),
      );
      const flat = flattenQueue(queue).filter(
        (r) => r.bucket === "waiting" || r.bucket === "checked_in",
      );
      setWaiting(flat);
      setOpenEncounters(encs);
      setOpsNext(ops?.todays_appointments?.[0]?.id ?? null);

      const names: Record<string, string> = {};
      for (const p of pats) names[p.id] = p.display_name;
      setPatientNames(names);
    } catch (e) {
      if (String(e).includes("session_expired")) onSessionExpired();
      else if (String(e).includes("forbidden"))
        setError("Missing permission to load consultation board.");
      else setError("Failed to load consultation board.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void reload();
  }, [tenant?.id, locationId, practitionerId]);

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

  const nextAppt = useMemo(() => {
    if (opsNext) {
      const hit = appointments.find((a) => a.id === opsNext);
      if (hit) return hit;
    }
    return appointments[0] ?? waiting[0] ?? null;
  }, [appointments, waiting, opsNext]);

  async function startFromAppointment(appt: Appointment) {
    if (!tenant || !canOpen) return;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      // Wrong-patient prevention: use appointment's patient_id only.
      const patientId = appt.patient_id;
      const pracId = practitionerId || appt.practitioner_id;
      const locId = locationId || appt.location_id;
      if (!pracId || !locId) {
        setError("Practitioner and location are required to open an encounter.");
        return;
      }
      // Prefer existing open encounter for this patient+appointment
      const existing = openEncounters.find(
        (e) =>
          e.patient_id === patientId &&
          (e.appointment_id === appt.id || e.appointment_id == null),
      );
      if (existing) {
        setInfo("Opening existing open encounter for this patient.");
        onOpenEncounter(existing.id);
        return;
      }
      const enc = await openEncounter(tenant.id, {
        patient_id: patientId,
        practitioner_id: pracId,
        location_id: locId,
        appointment_id: appt.id,
        chief_complaint: chief.trim() || null,
      });
      setInfo("Encounter opened.");
      onOpenEncounter(enc.id);
    } catch (err) {
      const msg = String(err);
      if (msg.includes("session_expired")) onSessionExpired();
      else setError(msg.replace(/^Error:\s*/, "") || "Could not open encounter.");
    } finally {
      setBusy(false);
    }
  }

  async function startManual(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !canOpen) return;
    if (!manualPatientId || !practitionerId || !locationId) {
      setError("Patient, practitioner, and location are required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (initialAppointmentId) {
        const appt = appointments.find((a) => a.id === initialAppointmentId);
        if (appt && appt.patient_id !== manualPatientId) {
          setError("Selected patient does not match the appointment patient.");
          return;
        }
      }
      const enc = await openEncounter(tenant.id, {
        patient_id: manualPatientId,
        practitioner_id: practitionerId,
        location_id: locationId,
        appointment_id: initialAppointmentId || null,
        chief_complaint: chief.trim() || null,
      });
      onOpenEncounter(enc.id);
    } catch (err) {
      const msg = String(err);
      if (msg.includes("session_expired")) onSessionExpired();
      else setError(msg.replace(/^Error:\s*/, "") || "Open failed.");
    } finally {
      setBusy(false);
    }
  }

  const nameOf = (pid: string) => patientNames[pid] ?? pid.slice(0, 8);

  if (!canRead && !canOpen) {
    return (
      <Alert tone="danger" title="Consultations">
        Missing encounter.read / encounter.open.
      </Alert>
    );
  }

  return (
    <div className="hos-consult-board">
      <header className="hos-module-header">
        <h1>Consultations</h1>
        <p className="hos-muted">
          Today&apos;s appointments, waiting patients, and open encounters
        </p>
      </header>

      {error && (
        <Alert tone="danger" title="Consultations">
          {error}
        </Alert>
      )}
      {info && (
        <Alert tone="success" title="Updated">
          {info}
        </Alert>
      )}

      <div className="hos-toolbar-row">
        <Field label="Location" htmlFor="c-loc">
          {({ describedBy }) => (
            <Select
              id="c-loc"
              aria-describedby={describedBy}
              value={locationId}
              onChange={(ev) => setLocationId(ev.target.value)}
              options={locations.map((l) => ({ value: l.id, label: l.name }))}
            />
          )}
        </Field>
        <Field label="Practitioner" htmlFor="c-prac">
          {({ describedBy }) => (
            <Select
              id="c-prac"
              aria-describedby={describedBy}
              value={practitionerId}
              onChange={(ev) => setPractitionerId(ev.target.value)}
              options={practitioners.map((p) => ({
                value: p.id,
                label: p.display_name,
              }))}
            />
          )}
        </Field>
        <Button type="button" size="sm" variant="secondary" onClick={() => void reload()}>
          Refresh
        </Button>
      </div>

      {loading ? (
        <LoadingState label="Loading consultation board" />
      ) : (
        <div className="hos-consult-layout">
          <Card title="Today's appointments">
            {appointments.length === 0 ? (
              <EmptyState title="No active appointments today">
                Waiting queue and manual open remain available.
              </EmptyState>
            ) : (
              <Table
                caption="Today appointments"
                density="compact"
                columns={
                  <>
                    <Th>Time</Th>
                    <Th>Patient</Th>
                    <Th>Status</Th>
                    <Th>Action</Th>
                  </>
                }
              >
                {appointments.map((a) => (
                  <tr key={a.id}>
                    <Td>{fmtTime(a.start_at)}</Td>
                    <Td>
                      <button
                        type="button"
                        className="hos-link-btn"
                        onClick={() => onOpenPatient(a.patient_id)}
                      >
                        {nameOf(a.patient_id)}
                      </button>
                    </Td>
                    <Td>
                      <Status value={a.status} />
                    </Td>
                    <Td>
                      {canOpen && (
                        <Button
                          type="button"
                          size="sm"
                          disabled={busy}
                          onClick={() => void startFromAppointment(a)}
                        >
                          Open consultation
                        </Button>
                      )}
                    </Td>
                  </tr>
                ))}
              </Table>
            )}
            {nextAppt && (
              <p className="hos-caption">
                Next focus: {fmtTime(nextAppt.start_at)} · {nameOf(nextAppt.patient_id)} ·{" "}
                {statusLabel(nextAppt.status)}
              </p>
            )}
          </Card>

          <Card title="Waiting / checked in">
            {waiting.length === 0 ? (
              <EmptyState title="Queue empty">No waiting or checked-in patients.</EmptyState>
            ) : (
              <Table
                caption="Waiting"
                density="compact"
                columns={
                  <>
                    <Th>Token</Th>
                    <Th>Patient</Th>
                    <Th>Status</Th>
                    <Th>Action</Th>
                  </>
                }
              >
                {waiting.map((a) => (
                  <tr key={a.id}>
                    <Td>{a.queue_token ?? "—"}</Td>
                    <Td>
                      <button
                        type="button"
                        className="hos-link-btn"
                        onClick={() => onOpenPatient(a.patient_id)}
                      >
                        {nameOf(a.patient_id)}
                      </button>
                    </Td>
                    <Td>{statusLabel(a.status)}</Td>
                    <Td>
                      {canOpen && (
                        <Button
                          type="button"
                          size="sm"
                          disabled={busy}
                          onClick={() => void startFromAppointment(a)}
                        >
                          Start
                        </Button>
                      )}
                    </Td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>

          <Card title="Open encounters">
            {openEncounters.length === 0 ? (
              <EmptyState title="No open encounters">Start from an appointment above.</EmptyState>
            ) : (
              <Table
                caption="Open encounters"
                density="compact"
                columns={
                  <>
                    <Th>Opened</Th>
                    <Th>Patient</Th>
                    <Th>Action</Th>
                  </>
                }
              >
                {openEncounters.map((e) => (
                  <tr key={e.id}>
                    <Td>{fmtWhen(e.opened_at)}</Td>
                    <Td>
                      <button
                        type="button"
                        className="hos-link-btn"
                        onClick={() => onOpenPatient(e.patient_id)}
                      >
                        {nameOf(e.patient_id)}
                      </button>
                    </Td>
                    <Td>
                      <Button
                        type="button"
                        size="sm"
                        onClick={() => onOpenEncounter(e.id)}
                      >
                        Resume
                      </Button>
                    </Td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>

          {canOpen && (
            <Card title="Open without appointment">
              <form onSubmit={startManual}>
                <Field label="Find patient" htmlFor="c-pq">
                  {({ describedBy }) => (
                    <Input
                      id="c-pq"
                      aria-describedby={describedBy}
                      value={patientQ}
                      onChange={(ev) => setPatientQ(ev.target.value)}
                      placeholder="Name or phone"
                    />
                  )}
                </Field>
                <Field label="Patient" htmlFor="c-patient" required>
                  {({ describedBy }) => (
                    <Select
                      id="c-patient"
                      aria-describedby={describedBy}
                      value={manualPatientId}
                      onChange={(ev) => setManualPatientId(ev.target.value)}
                      required
                      options={[
                        { value: "", label: "Select…" },
                        ...(manualPatientId &&
                        !patients.some((p) => p.id === manualPatientId)
                          ? [
                              {
                                value: manualPatientId,
                                label: `Current (${manualPatientId.slice(0, 8)})`,
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
                <Field label="Chief complaint (optional)" htmlFor="c-chief">
                  {({ describedBy }) => (
                    <Input
                      id="c-chief"
                      aria-describedby={describedBy}
                      value={chief}
                      onChange={(ev) => setChief(ev.target.value)}
                      maxLength={500}
                    />
                  )}
                </Field>
                <Button type="submit" disabled={busy} loading={busy}>
                  Open encounter
                </Button>
                <p className="hos-caption">
                  Patient id is taken from selection only — not typed freely as an
                  encounter override after open.
                </p>
              </form>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
