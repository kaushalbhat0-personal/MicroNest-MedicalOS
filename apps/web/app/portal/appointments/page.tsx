"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
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
import { useTenantApi } from "@/lib/use-api";
import { portalUnavailableCopy } from "@/lib/portal";
import { NoTenantHint } from "../no-tenant";
import { PortalShell } from "../shell";

type Appointment = { id: string; start_at: string; end_at: string; status: string };
type Option = { id: string; name?: string; display_name?: string; timezone?: string };
type Slot = { start_at: string; end_at: string };

export default function PortalAppointmentsPage() {
  const router = useRouter();
  const [statusFilter, setStatusFilter] = useState("");
  const list = useTenantApi<Appointment[]>(
    (t) =>
      statusFilter
        ? `/api/v1/portal/appointments?status=${statusFilter}`
        : `/api/v1/portal/appointments`,
    [statusFilter],
  );

  const [locations, setLocations] = useState<Option[]>([]);
  const [practitioners, setPractitioners] = useState<Option[]>([]);
  const [locationId, setLocationId] = useState("");
  const [practitionerId, setPractitionerId] = useState("");
  const [day, setDay] = useState("");
  const [slots, setSlots] = useState<Slot[]>([]);
  const [slotMinutes, setSlotMinutes] = useState(30);
  const [bookError, setBookError] = useState("");
  const [booking, setBooking] = useState(false);
  const [loadingSlots, setLoadingSlots] = useState(false);

  useEffect(() => {
    if (list.status === 401) router.push("/login");
  }, [list.status, router]);

  useEffect(() => {
    const t = getSelectedTenant();
    if (!t) return;
    Promise.all([
      api.get<Option[]>("/api/v1/portal/locations", t),
      api.get<Option[]>("/api/v1/portal/practitioners", t),
    ])
      .then(([locs, practs]) => {
        setLocations(locs);
        setPractitioners(practs);
        if (locs[0]) setLocationId(locs[0].id);
        if (practs[0]) setPractitionerId(practs[0].id);
      })
      .catch(() => {
        /* booking panel stays empty if catalog unavailable */
      });
  }, [list.tenant]);

  async function loadSlots() {
    const t = getSelectedTenant();
    if (!t || !locationId || !practitionerId || !day) return;
    setLoadingSlots(true);
    setBookError("");
    try {
      const res = await api.get<{ slots: Slot[]; slot_minutes: number }>(
        `/api/v1/portal/availability?practitioner_id=${practitionerId}&location_id=${locationId}&day=${day}`,
        t,
      );
      setSlots(res.slots);
      setSlotMinutes(res.slot_minutes);
    } catch (e) {
      setBookError((e as Error).message);
      setSlots([]);
    } finally {
      setLoadingSlots(false);
    }
  }

  async function book(startAt: string) {
    const t = getSelectedTenant();
    if (!t) return;
    setBooking(true);
    setBookError("");
    try {
      await api.post(
        "/api/v1/portal/appointments",
        {
          practitioner_id: practitionerId,
          location_id: locationId,
          start: startAt,
          duration_minutes: slotMinutes,
        },
        t,
      );
      setSlots((prev) => prev.filter((s) => s.start_at !== startAt));
      list.reload();
    } catch (e) {
      setBookError((e as Error).message);
    } finally {
      setBooking(false);
    }
  }

  if (!list.tenant && !list.loading) {
    return (
      <PortalShell>
        <PageHeader title="Appointments" description="Your upcoming and past visits." />
        <NoTenantHint />
      </PortalShell>
    );
  }

  return (
    <PortalShell>
      <PageHeader title="Appointments" description="Your upcoming and past visits." />
      {list.error ? (
        <Alert tone="danger" title="Could not load appointments">
          {[403, 404].includes(list.status ?? 0) ? portalUnavailableCopy(list.status) : list.error}
        </Alert>
      ) : null}
      <Card title="Book a visit">
        <p className="hos-helper">
          Choose a clinic location, doctor, and day. Only free times are shown — other patients'
          details are never shared.
        </p>
        {bookError ? (
          <Alert tone="danger" title="Booking">
            {bookError}
          </Alert>
        ) : null}
        <Field label="Location" htmlFor="portal-loc">
          {() => (
            <Select
              id="portal-loc"
              value={locationId}
              onChange={(e) => setLocationId(e.target.value)}
              options={locations.map((l) => ({ value: l.id, label: l.name ?? l.id }))}
            />
          )}
        </Field>
        <Field label="Doctor" htmlFor="portal-pract">
          {() => (
            <Select
              id="portal-pract"
              value={practitionerId}
              onChange={(e) => setPractitionerId(e.target.value)}
              options={practitioners.map((p) => ({
                value: p.id,
                label: p.display_name ?? p.id,
              }))}
            />
          )}
        </Field>
        <Field label="Date" htmlFor="portal-day">
          {() => (
            <Input id="portal-day" type="date" value={day} onChange={(e) => setDay(e.target.value)} />
          )}
        </Field>
        <p>
          <Button type="button" variant="secondary" onClick={loadSlots} loading={loadingSlots}>
            Show available times
          </Button>
        </p>
        {slots.length === 0 ? (
          <EmptyState title="No open times">
            Pick another day, or ask the clinic to publish working hours.
          </EmptyState>
        ) : (
          <ul className="hos-stack">
            {slots.map((s) => (
              <li key={s.start_at}>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={booking}
                  onClick={() => book(s.start_at)}
                >
                  Book {new Date(s.start_at).toLocaleString()}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Filter">
        <Field label="Status" htmlFor="portal-appt-status">
          {() => (
            <Select
              id="portal-appt-status"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              options={[
                { value: "", label: "All" },
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
      </Card>
      <Card title="Your appointments">
        {list.loading ? (
          <LoadingState label="Loading appointments" />
        ) : (list.data ?? []).length === 0 ? (
          <EmptyState title="No appointments">Book a time above, or wait for the clinic desk.</EmptyState>
        ) : (
          <Table
            caption="Appointments"
            columns={
              <>
                <Th>When</Th>
                <Th>Status</Th>
                <Th>Details</Th>
              </>
            }
          >
            {(list.data ?? []).map((a) => (
              <tr key={a.id}>
                <Td>{new Date(a.start_at).toLocaleString()}</Td>
                <Td>
                  <Status value={a.status} />
                </Td>
                <Td>
                  <Link href={`/portal/appointments/${a.id}`}>View</Link>
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </PortalShell>
  );
}
