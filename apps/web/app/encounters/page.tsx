"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  Field,
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
  const [closingId, setClosingId] = useState<string | null>(null);

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

  async function closeEncounter() {
    if (!tenant || !closingId) return;
    setError("");
    try {
      await api.post(
        `/api/v1/tenants/${tenant}/encounters/${closingId}/close`,
        { note_waiver: true, vitals_waiver: true, reason: "wrap-up" },
        tenant,
      );
      setClosingId(null);
      load(tenant);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Shell>
      <Card title="Encounters">
        {error ? (
          <Alert tone="danger" title="Something went wrong">
            {error}
          </Alert>
        ) : null}
        {message ? <Alert tone="success">{message}</Alert> : null}
        {loading ? (
          <LoadingState label="Loading encounters" />
        ) : items.length === 0 ? (
          <EmptyState title="No encounters yet">Open the first one below.</EmptyState>
        ) : (
          <Table
            caption="Encounters"
            density="compact"
            columns={
              <>
                <Th>Opened</Th>
                <Th>Status</Th>
                <Th>Actions</Th>
              </>
            }
          >
            {items.map((e) => (
              <tr key={e.id}>
                <Td>{new Date(e.opened_at).toLocaleString()}</Td>
                <Td>
                  <Status value={e.status} />
                </Td>
                <Td>
                  {e.status === "open" && (
                    <Button size="sm" variant="secondary" onClick={() => setClosingId(e.id)}>
                      Close
                    </Button>
                  )}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <Card title="Open encounter">
        <form onSubmit={openEncounter}>
          <Field label="Patient" htmlFor="patient" required>
            {() => (
              <Select
                id="patient"
                value={patientId}
                onChange={(e) => setPatientId(e.target.value)}
                required
                options={[
                  { value: "", label: "Select patient" },
                  ...patients.map((p) => ({ value: p.id, label: p.display_name ?? p.id })),
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
          <p>
            <Button type="submit">Open</Button>
          </p>
        </form>
      </Card>
      <ConfirmDialog
        open={closingId !== null}
        onOpenChange={(o) => {
          if (!o) setClosingId(null);
        }}
        title="Close encounter?"
        confirmLabel="Close encounter"
        onConfirm={() => void closeEncounter()}
      >
        Closing ends the encounter. This demo uses waivers; a real close requires
        a finalized note and vitals.
      </ConfirmDialog>
    </Shell>
  );
}
