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
  LoadingState,
  PageHeader,
  Select,
  Status,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { useTenantApi } from "@/lib/use-api";
import { portalUnavailableCopy } from "@/lib/portal";
import { NoTenantHint } from "../no-tenant";
import { PortalShell } from "../shell";

type Appointment = { id: string; start_at: string; end_at: string; status: string };

export default function PortalAppointmentsPage() {
  const router = useRouter();
  const [statusFilter, setStatusFilter] = useState("");
  const list = useTenantApi<Appointment[]>((t) =>
    statusFilter ? `/api/v1/portal/appointments?status=${statusFilter}` : `/api/v1/portal/appointments`,
  [statusFilter]);

  useEffect(() => {
    if (list.status === 401) router.push("/login");
  }, [list.status, router]);

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
          <EmptyState title="No appointments">New bookings appear here after the desk schedules them.</EmptyState>
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
                <Td><Status value={a.status} /></Td>
                <Td><Link href={`/portal/appointments/${a.id}`}>View</Link></Td>
              </tr>
            ))}
          </Table>
        )}
        <p className="hos-helper">
          To book or move an appointment, please contact the clinic. Cancellation is available on
          scheduled visits.
        </p>
      </Card>
    </PortalShell>
  );
}
