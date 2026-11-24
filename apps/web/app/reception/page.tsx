"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
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
  status: string;
  queue_token: number | null;
  notes: string | null;
};
type Option = { id: string; display_name?: string; name?: string; verification_status?: string };
type QueueBoard = {
  location_id: string;
  queue_date: string;
  timezone: string;
  waiting: Appointment[];
  checked_in: Appointment[];
  completed: Appointment[];
  no_show: Appointment[];
  cancelled: Appointment[];
};

const CHECKABLE = new Set(["scheduled", "confirmed"]);
const NO_SHOWABLE = new Set(["scheduled", "confirmed"]);
const COMPLETABLE = new Set(["checked_in"]);

function Section({
  title,
  rows,
  names,
  practNames,
  emptyHint,
  emptyAction,
  onCheckIn,
  onNoShow,
  onComplete,
  onStartConsult,
}: {
  title: string;
  rows: Appointment[];
  names: Record<string, string>;
  practNames: Record<string, string>;
  emptyHint?: string;
  emptyAction?: React.ReactNode;
  onCheckIn: (id: string) => void;
  onNoShow: (id: string) => void;
  onComplete: (id: string) => void;
  onStartConsult: (a: Appointment) => void;
}) {
  return (
    <Card title={`${title} (${rows.length})`}>
      {rows.length === 0 ? (
        <EmptyState title={`No ${title.toLowerCase()} patients`} action={emptyAction}>
          {emptyHint}
        </EmptyState>
      ) : (
        <Table
          caption={title}
          density="compact"
          columns={
            <>
              <Th>Token</Th>
              <Th>Time</Th>
              <Th>Patient</Th>
              <Th>Practitioner</Th>
              <Th>Status</Th>
              <Th>Actions</Th>
            </>
          }
        >
          {rows.map((a) => (
            <tr key={a.id}>
              <Td>
                <strong>{a.queue_token ?? "—"}</strong>
              </Td>
              <Td>
                <time dateTime={a.start_at}>{new Date(a.start_at).toLocaleTimeString()}</time>
              </Td>
              <Td>
                <Link href={`/patients/${a.patient_id}`} className="hos-truncate">
                  {names[a.patient_id] ?? `${a.patient_id.slice(0, 8)}…`}
                </Link>
              </Td>
              <Td>{practNames[a.practitioner_id] ?? "—"}</Td>
              <Td>
                <Status value={a.status} />
              </Td>
              <Td>
                <div className="hos-row-actions">
                  {CHECKABLE.has(a.status) ? (
                    <Button size="sm" onClick={() => onCheckIn(a.id)}>
                      Check in
                    </Button>
                  ) : null}
                  {NO_SHOWABLE.has(a.status) ? (
                    <Button size="sm" variant="secondary" onClick={() => onNoShow(a.id)}>
                      No-show
                    </Button>
                  ) : null}
                  {a.status === "checked_in" ? (
                    <Button size="sm" onClick={() => onStartConsult(a)}>
                      Start consult
                    </Button>
                  ) : null}
                  {COMPLETABLE.has(a.status) ? (
                    <Button size="sm" variant="secondary" onClick={() => onComplete(a.id)}>
                      Complete
                    </Button>
                  ) : null}
                  <Link href={`/patients/${a.patient_id}`}>Chart</Link>
                </div>
              </Td>
            </tr>
          ))}
        </Table>
      )}
    </Card>
  );
}

export default function ReceptionPage() {
  const router = useRouter();
  const [tenant, setTenant] = useState<string | null>(null);
  const [board, setBoard] = useState<QueueBoard | null>(null);
  const [locations, setLocations] = useState<Option[]>([]);
  const [practitioners, setPractitioners] = useState<Option[]>([]);
  const [locationId, setLocationId] = useState("");
  const [practitionerId, setPractitionerId] = useState("");
  const [names, setNames] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [showDone, setShowDone] = useState(false);

  const practNames = useMemo(() => {
    const map: Record<string, string> = {};
    for (const p of practitioners) map[p.id] = p.display_name ?? p.name ?? p.id.slice(0, 8);
    return map;
  }, [practitioners]);

  function loadBoard(t: string, loc: string, pract: string) {
    if (!loc) {
      setBoard(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    const q = new URLSearchParams();
    if (pract) q.set("practitioner_id", pract);
    const qs = q.toString() ? `?${q}` : "";
    Promise.all([
      api.get<QueueBoard>(`/api/v1/tenants/${t}/locations/${loc}/reception-queue${qs}`, t),
      api
        .get<{ id: string; display_name: string }[]>(`/api/v1/tenants/${t}/patients?limit=200`, t)
        .catch(() => [] as { id: string; display_name: string }[]),
    ])
      .then(([queue, pats]) => {
        setBoard(queue);
        const map: Record<string, string> = {};
        for (const p of pats) map[p.id] = p.display_name;
        setNames(map);
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
    Promise.all([
      api.get<Option[]>(`/api/v1/tenants/${t}/locations`, t),
      api.get<Option[]>(`/api/v1/tenants/${t}/practitioners`, t),
    ])
      .then(([locs, practs]) => {
        setLocations(locs);
        setPractitioners(practs.filter((p) => p.verification_status === "approved"));
        const first = locs[0]?.id ?? "";
        setLocationId(first);
        if (first) loadBoard(t, first, "");
        else setLoading(false);
      })
      .catch((e: Error) => {
        setError(e.message);
        setLoading(false);
      });
  }, [router]);

  useEffect(() => {
    if (!tenant || !locationId) return;
    loadBoard(tenant, locationId, practitionerId);
  }, [tenant, locationId, practitionerId]);

  async function setStatus(id: string, status: string, okMsg: string) {
    if (!tenant) return;
    setError("");
    setMessage("");
    try {
      await api.post(`/api/v1/tenants/${tenant}/appointments/${id}/status`, { status }, tenant);
      setMessage(okMsg);
      loadBoard(tenant, locationId, practitionerId);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function startConsult(a: Appointment) {
    if (!tenant) return;
    setError("");
    setMessage("");
    try {
      const enc = await api.post<{ id: string }>(
        `/api/v1/tenants/${tenant}/encounters`,
        {
          patient_id: a.patient_id,
          practitioner_id: a.practitioner_id,
          location_id: a.location_id,
          appointment_id: a.id,
        },
        tenant,
      );
      setMessage("Consultation started.");
      router.push(`/encounters/${enc.id}`);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const waiting = board?.waiting ?? [];
  const checkedIn = board?.checked_in ?? [];
  const nextToken =
    waiting.find((a) => a.queue_token != null)?.queue_token ??
    checkedIn.find((a) => a.queue_token != null)?.queue_token ??
    null;

  return (
    <Shell>
      <PageHeader
        title="Reception"
        description="Who has arrived, who is waiting, and who needs attention — tokens from the server only."
        actions={
          <>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => tenant && locationId && loadBoard(tenant, locationId, practitionerId)}
            >
              Refresh
            </Button>
            <Button type="button" size="sm" variant="secondary" onClick={() => router.push("/schedule")}>
              Calendar
            </Button>
            <Button type="button" size="sm" onClick={() => router.push("/schedule?walkin=1")}>
              Walk-in
            </Button>
          </>
        }
      />
      {error ? (
        <ErrorState
          title="Reception board failed"
          onRetry={() => tenant && locationId && loadBoard(tenant, locationId, practitionerId)}
        >
          {error}
        </ErrorState>
      ) : null}
      {message ? <Alert tone="info" title="Updated">{message}</Alert> : null}

      <Card title="Board filters">
        <div className="hos-filter-row">
          <Field label="Location" htmlFor="recv-location" required>
            {({ describedBy }) => (
              <Select
                id="recv-location"
                aria-describedby={describedBy}
                value={locationId}
                onChange={(e) => setLocationId(e.target.value)}
                options={[
                  { value: "", label: "Select location" },
                  ...locations.map((l) => ({
                    value: l.id,
                    label: l.name ?? l.display_name ?? l.id.slice(0, 8),
                  })),
                ]}
              />
            )}
          </Field>
          <Field label="Practitioner" htmlFor="recv-pract">
            {({ describedBy }) => (
              <Select
                id="recv-pract"
                aria-describedby={describedBy}
                value={practitionerId}
                onChange={(e) => setPractitionerId(e.target.value)}
                options={[
                  { value: "", label: "All practitioners" },
                  ...practitioners.map((p) => ({
                    value: p.id,
                    label: p.display_name ?? p.name ?? p.id.slice(0, 8),
                  })),
                ]}
              />
            )}
          </Field>
        </div>
        {board ? (
          <p className="hos-helper" role="status">
            Service day <strong>{board.queue_date}</strong> · {board.timezone}
          </p>
        ) : null}
      </Card>

      {board && !loading ? (
        <div className="hos-summary-strip" aria-label="Queue summary">
          <div>
            <p className="hos-attention-label">Waiting</p>
            <p className="hos-attention-value">{waiting.length}</p>
          </div>
          <div>
            <p className="hos-attention-label">Checked in</p>
            <p className="hos-attention-value">{checkedIn.length}</p>
          </div>
          <div>
            <p className="hos-attention-label">Next token</p>
            <p className="hos-attention-value">{nextToken ?? "—"}</p>
          </div>
          <div>
            <p className="hos-attention-label">Completed today</p>
            <p className="hos-attention-value">{board.completed.length}</p>
          </div>
        </div>
      ) : null}

      {loading ? (
        <LoadingState label="Loading reception queue" />
      ) : !locationId ? (
        <EmptyState title="Choose a location" />
      ) : board ? (
        <div style={{ display: "grid", gap: "1rem" }}>
          <Section
            title="Waiting"
            rows={waiting}
            names={names}
            practNames={practNames}
            emptyHint="Nobody is waiting. Check in an arrival or register a walk-in."
            emptyAction={
              <Button type="button" size="sm" onClick={() => router.push("/schedule?walkin=1")}>
                Walk-in
              </Button>
            }
            onCheckIn={(id) => void setStatus(id, "checked_in", "Checked in.")}
            onNoShow={(id) => void setStatus(id, "no_show", "Marked no-show.")}
            onComplete={(id) => void setStatus(id, "completed", "Visit completed.")}
            onStartConsult={(a) => void startConsult(a)}
          />
          <Section
            title="Checked in"
            rows={checkedIn}
            names={names}
            practNames={practNames}
            emptyHint="No patients checked in yet."
            onCheckIn={(id) => void setStatus(id, "checked_in", "Checked in.")}
            onNoShow={(id) => void setStatus(id, "no_show", "Marked no-show.")}
            onComplete={(id) => void setStatus(id, "completed", "Visit completed.")}
            onStartConsult={(a) => void startConsult(a)}
          />
          <p>
            <Button type="button" size="sm" variant="ghost" onClick={() => setShowDone((v) => !v)}>
              {showDone ? "Hide" : "Show"} completed &amp; no-shows
            </Button>
          </p>
          {showDone ? (
            <>
              <Section
                title="Completed"
                rows={board.completed}
                names={names}
                practNames={practNames}
                onCheckIn={() => undefined}
                onNoShow={() => undefined}
                onComplete={() => undefined}
                onStartConsult={() => undefined}
              />
              <Section
                title="No-shows"
                rows={board.no_show}
                names={names}
                practNames={practNames}
                onCheckIn={() => undefined}
                onNoShow={() => undefined}
                onComplete={() => undefined}
                onStartConsult={() => undefined}
              />
            </>
          ) : null}
        </div>
      ) : null}
    </Shell>
  );
}
