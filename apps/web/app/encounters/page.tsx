"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";

type Encounter = {
  id: string;
  patient_id: string;
  practitioner_id: string;
  location_id: string;
  status: string;
  opened_at: string;
  version: number;
};
type Option = { id: string; display_name?: string; name?: string; verification_status?: string };

export default function EncountersPage() {
  const router = useRouter();
  const [tenant, setTenant] = useState<string | null>(null);
  const [items, setItems] = useState<Encounter[]>([]);
  const [patients, setPatients] = useState<Option[]>([]);
  const [practitioners, setPractitioners] = useState<Option[]>([]);
  const [locations, setLocations] = useState<Option[]>([]);
  const [patientId, setPatientId] = useState("");
  const [practitionerId, setPractitionerId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);

  function load(t: string) {
    setLoading(true);
    Promise.all([
      api.get<{ items: Encounter[] }>(`/api/v1/tenants/${t}/encounters`, t),
      api.get<Option[]>(`/api/v1/tenants/${t}/patients`, t),
      api.get<Option[]>(`/api/v1/tenants/${t}/practitioners`, t),
      api.get<Option[]>(`/api/v1/tenants/${t}/locations`, t),
    ])
      .then(([encs, pats, practs, locs]) => {
        setItems(encs.items);
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

  async function openEncounter(e: React.FormEvent) {
    e.preventDefault();
    if (!tenant) return;
    setError("");
    setMessage("");
    try {
      await api.post<Encounter>(
        `/api/v1/tenants/${tenant}/encounters`,
        { patient_id: patientId, practitioner_id: practitionerId, location_id: locationId },
        tenant,
      );
      setMessage("Encounter opened.");
      load(tenant);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function closeEncounter(id: string) {
    if (!tenant) return;
    setError("");
    try {
      await api.post(
        `/api/v1/tenants/${tenant}/encounters/${id}/close`,
        { note_waiver: true, vitals_waiver: true, reason: "wrap-up" },
        tenant,
      );
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
        <h1>Encounters</h1>
        {error && <p className="error">{error}</p>}
        {message && <p>{message}</p>}
        {loading ? (
          <p className="muted">Loading encounters…</p>
        ) : items.length === 0 ? (
          <p className="muted">No encounters yet. Open the first one below.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Opened</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr key={e.id}>
                  <td>{new Date(e.opened_at).toLocaleString()}</td>
                  <td>{e.status}</td>
                  <td>
                    {e.status === "open" && (
                      <button onClick={() => void closeEncounter(e.id)}>Close</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div className="card">
        <h2>Open encounter</h2>
        <form onSubmit={openEncounter}>
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
          <p>
            <button type="submit">Open</button>
          </p>
        </form>
      </div>
    </>
  );
}
