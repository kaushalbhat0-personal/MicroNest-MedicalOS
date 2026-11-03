"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";

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

  async function transition(id: string, action: "status" | "cancel", status?: string) {
    if (!tenant) return;
    setError("");
    try {
      if (action === "cancel") {
        await api.post(`/api/v1/tenants/${tenant}/appointments/${id}/cancel`, {}, tenant);
      } else {
        await api.post(
          `/api/v1/tenants/${tenant}/appointments/${id}/status`,
          { status },
          tenant,
        );
      }
      load(tenant);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <>
      <nav>
        <Link href="/">Home</Link>
        <Link href="/team">Team</Link>
        <Link href="/sessions">Sessions</Link>
        <Link href="/schedule">Schedule</Link>
        <Link href="/encounters">Encounters</Link>
      </nav>
      <div className="card">
        <h1>Schedule</h1>
        {error && (
          <p id="schedule-error" role="alert" className="error">
            {error}
          </p>
        )}
        {message && <p>{message}</p>}
        {loading ? (
          <p className="muted">Loading schedule…</p>
        ) : items.length === 0 ? (
          <p className="muted">No appointments yet. Book the first one below.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((a) => (
                <tr key={a.id}>
                  <td>{new Date(a.start_at).toLocaleString()}</td>
                  <td>{a.status}</td>
                  <td>
                    {LIVE.has(a.status) && (
                      <>
                        {a.status === "scheduled" && (
                          <button onClick={() => void transition(a.id, "status", "confirmed")}>
                            Confirm
                          </button>
                        )}{" "}
                        <button
                          className="secondary"
                          onClick={() => void transition(a.id, "cancel")}
                        >
                          Cancel
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div className="card">
        <h2>Book appointment</h2>
        <form onSubmit={create}>
          <label htmlFor="patient">Patient</label>
          <select id="patient" value={patientId} onChange={(e) => setPatientId(e.target.value)} required>
            <option value="" disabled>
              Select patient
            </option>
            {patients.map((p) => (
              <option key={p.id} value={p.id}>
                {p.display_name}
              </option>
            ))}
          </select>
          <label htmlFor="practitioner">Practitioner</label>
          <select
            id="practitioner"
            value={practitionerId}
            onChange={(e) => setPractitionerId(e.target.value)}
            required
          >
            <option value="" disabled>
              Select practitioner
            </option>
            {practitioners.map((p) => (
              <option key={p.id} value={p.id}>
                {p.display_name}
              </option>
            ))}
          </select>
          <label htmlFor="location">Location</label>
          <select id="location" value={locationId} onChange={(e) => setLocationId(e.target.value)} required>
            <option value="" disabled>
              Select location
            </option>
            {locations.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
          <label htmlFor="start">Start (location time)</label>
          <input
            id="start"
            type="datetime-local"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            required
          />
          <label htmlFor="duration">Duration (minutes)</label>
          <input
            id="duration"
            type="number"
            min={5}
            max={480}
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
            required
          />
          <p>
            <button type="submit">Book</button>
          </p>
        </form>
      </div>
    </>
  );
}
