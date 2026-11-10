"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  EmptyState,
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

type Appointment = {
  id: string;
  patient_id: string;
  start_at: string;
  status: string;
};

const CHECKABLE = new Set(["scheduled", "confirmed"]);

function todayRange(): { from: string; to: string } {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  const from = d.toISOString();
  d.setHours(24, 0, 0, 0);
  return { from, to: d.toISOString() };
}

export default function ReceptionPage() {
  const router = useRouter();
  const [items, setItems] = useState<Appointment[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  function load() {
    const t = getSelectedTenant();
    if (!t) {
      router.push("/");
      return;
    }
    setLoading(true);
    const { from, to } = todayRange();
    Promise.all([
      api.get<{ items: Appointment[] }>(
        `/api/v1/tenants/${t}/appointments?start_from=${encodeURIComponent(from)}&start_to=${encodeURIComponent(to)}&limit=100`,
        t,
      ),
      api.get<{ id: string; display_name: string }[]>(`/api/v1/tenants/${t}/patients?limit=100`, t).catch(() => [] as { id: string; display_name: string }[]),
    ])
      .then(([appts, pats]) => {
        setItems(appts.items);
        const map: Record<string, string> = {};
        for (const p of pats) map[p.id] = p.display_name;
        setNames(map);
        setError("");
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, [router]);

  async function checkIn(id: string) {
    const t = getSelectedTenant();
    if (!t) return;
    setError("");
    try {
      await api.post(
        `/api/v1/tenants/${t}/appointments/${id}/status`,
        { status: "checked_in" },
        t,
      );
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Shell>
      <PageHeader
        title="Reception - today"
        description="Check in arrivals. Queue order follows appointment time."
        actions={<Link href="/schedule">Full schedule</Link>}
      />
      {error ? (
        <Alert tone="danger" title="Something went wrong">
          {error}
        </Alert>
      ) : null}
      <Card title="Today's arrivals">
        {loading ? (
          <LoadingState label="Loading today's appointments" />
        ) : items.length === 0 ? (
          <EmptyState title="No appointments today">
            <Link href="/schedule">Book one from the schedule</Link>
          </EmptyState>
        ) : (
          <Table
            caption="Today's appointments"
            density="compact"
            columns={
              <>
                <Th>Time</Th>
                <Th>Patient</Th>
                <Th>Status</Th>
                <Th>Actions</Th>
              </>
            }
          >
            {items.map((a) => (
              <tr key={a.id}>
                <Td>{new Date(a.start_at).toLocaleTimeString()}</Td>
                <Td>
                  <Link href={`/patients/${a.patient_id}`}>
                    {names[a.patient_id] ?? `${a.patient_id.slice(0, 8)}...`}
                  </Link>
                </Td>
                <Td>
                  <Status value={a.status} />
                </Td>
                <Td>
                  {CHECKABLE.has(a.status) ? (
                    <Button size="sm" onClick={() => void checkIn(a.id)}>
                      Check in
                    </Button>
                  ) : null}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </Shell>
  );
}
