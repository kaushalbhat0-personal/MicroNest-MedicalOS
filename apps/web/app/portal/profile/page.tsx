"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  Alert,
  Card,
  EmptyState,
  LoadingState,
  MoneyDisplay,
  PageHeader,
  Status,
} from "@healthcare-os/ui";
import { useTenantApi } from "@/lib/use-api";
import { portalUnavailableCopy } from "@/lib/portal";
import { NoTenantHint } from "../no-tenant";
import { PortalShell } from "../shell";

type PortalOverview = {
  display_name: string;
  phone: string | null;
  email: string | null;
  date_of_birth: string | null;
  is_active: boolean;
  last_visit_at: string | null;
  next_appointment_at: string | null;
  outstanding_balance: string;
  currency: string;
  follow_up_due: string | null;
};

type TimelinePage = {
  items: {
    event_id: string;
    kind: string;
    category: string;
    occurred_at: string;
    title: string;
    summary: string | null;
    status: string | null;
  }[];
  next_cursor: string | null;
};

export default function PortalProfilePage() {
  const router = useRouter();
  const overview = useTenantApi<PortalOverview>((_t) => `/api/v1/portal/overview`);
  const timeline = useTenantApi<TimelinePage>((_t) => `/api/v1/portal/timeline?limit=20`);
  const error = overview.error || timeline.error;
  const errorStatus = overview.status ?? timeline.status;

  useEffect(() => {
    if (overview.status === 401) router.push("/login");
  }, [overview.status, router]);

  if (!overview.tenant && !overview.loading) {
    return (
      <PortalShell>
        <PageHeader title="Your profile" description="Contact details and visit history." />
        <NoTenantHint />
      </PortalShell>
    );
  }

  return (
    <PortalShell>
      <PageHeader
        title="Your profile"
        description="Read-only summary of your clinic records. Contact the clinic to update demographics."
      />
      {error ? (
        <Alert tone="danger" title="Could not load profile">
          {[403, 404].includes(errorStatus ?? 0) ? portalUnavailableCopy(errorStatus) : error}
        </Alert>
      ) : null}
      <Card title="Overview">
        {overview.loading || !overview.data ? (
          <LoadingState label="Loading profile" />
        ) : (
          <>
            <p>
              <strong>{overview.data.display_name}</strong>{" "}
              <Status value={overview.data.is_active ? "current" : "revoked"} />
            </p>
            <p>Phone: {overview.data.phone ?? "Not on file"}</p>
            <p>Email: {overview.data.email ?? "Not on file"}</p>
            <p>
              Date of birth:{" "}
              {overview.data.date_of_birth
                ? new Date(overview.data.date_of_birth).toLocaleDateString()
                : "Not on file"}
            </p>
            <p>
              Last visit:{" "}
              {overview.data.last_visit_at
                ? new Date(overview.data.last_visit_at).toLocaleString()
                : "None recorded"}
            </p>
            <p>
              Next appointment:{" "}
              {overview.data.next_appointment_at
                ? new Date(overview.data.next_appointment_at).toLocaleString()
                : "None scheduled"}
            </p>
            <p>
              Balance due:{" "}
              <MoneyDisplay
                amount={overview.data.outstanding_balance}
                currency={overview.data.currency}
              />
            </p>
            <p>
              Follow-up:{" "}
              {overview.data.follow_up_due
                ? new Date(overview.data.follow_up_due).toLocaleDateString()
                : "None"}
            </p>
          </>
        )}
      </Card>
      <Card title="Visit history">
        {timeline.loading ? (
          <LoadingState label="Loading history" />
        ) : (timeline.data?.items ?? []).length === 0 ? (
          <EmptyState title="No visit history yet">
            Published records from your clinic will appear here.
          </EmptyState>
        ) : (
          <ul>
            {(timeline.data?.items ?? []).map((ev) => (
              <li key={ev.event_id}>
                <time dateTime={ev.occurred_at}>
                  {new Date(ev.occurred_at).toLocaleString()}
                </time>
                {" — "}
                {ev.title}
                {ev.status ? ` (${ev.status})` : ""}
                {ev.summary ? ` · ${ev.summary}` : ""}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </PortalShell>
  );
}
