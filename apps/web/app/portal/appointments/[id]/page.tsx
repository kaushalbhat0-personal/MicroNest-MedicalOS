"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  ConfirmDialog,
  Field,
  Input,
  LoadingState,
  PageHeader,
  Status,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { portalUnavailableCopy } from "@/lib/portal";
import { PortalShell } from "../../shell";

type Appointment = {
  id: string;
  start_at: string;
  end_at: string;
  timezone: string;
  status: string;
  location_id: string;
  notes: string | null;
};

export default function PortalAppointmentDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const [appt, setAppt] = useState<Appointment | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  function noteError(e: Error & { status?: number }) {
    if (e.status === 401) {
      router.push("/login");
      return;
    }
    if (e.status === 403 || e.status === 404) {
      setError(portalUnavailableCopy(e.status));
    } else {
      setError(e.message);
    }
  }

  function load() {
    const t = getSelectedTenant();
    if (!t) {
      router.push("/portal");
      return;
    }
    setLoading(true);
    api
      .get<Appointment>(`/api/v1/portal/appointments/${id}`, t)
      .then((a) => {
        setAppt(a);
        setError("");
      })
      .catch(noteError)
      .finally(() => setLoading(false));
  }

  useEffect(load, [id, router]);

  async function cancel() {
    const t = getSelectedTenant();
    if (!t) return;
    setCancelling(true);
    try {
      const updated = await api.post<Appointment>(
        `/api/v1/portal/appointments/${id}/cancel`,
        { reason: reason || null },
        t,
      );
      setAppt(updated);
      setConfirming(false);
      setError("");
    } catch (e) {
      noteError(e as Error & { status?: number });
    } finally {
      setCancelling(false);
    }
  }

  const cancellable = appt && (appt.status === "scheduled" || appt.status === "confirmed");

  return (
    <PortalShell>
      <p><Link href="/portal/appointments">Back to appointments</Link></p>
      {loading ? (
        <LoadingState label="Loading appointment" />
      ) : error && !appt ? (
        <Alert tone="danger" title="Could not load appointment">
          {error}
        </Alert>
      ) : appt ? (
        <>
          <PageHeader
            title={`Visit on ${new Date(appt.start_at).toLocaleString()}`}
            description={`Ends ${new Date(appt.end_at).toLocaleString()} · ${appt.timezone}`}
          />
          {error ? (
            <Alert tone="danger" title="Something went wrong">{error}</Alert>
          ) : null}
          <Card title="Status">
            <p><Status value={appt.status} /></p>
            {appt.notes ? <p className="hos-helper">{appt.notes}</p> : null}
          </Card>
          {cancellable ? (
            <Card title="Cancel this visit">
              <p className="hos-helper">
                Only scheduled visits can be cancelled here. Please call the clinic for anything else.
              </p>
              <Field label="Reason (optional)" htmlFor="portal-cancel-reason">
                {() => (
                  <Input
                    id="portal-cancel-reason"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    maxLength={200}
                  />
                )}
              </Field>
              <p>
                <Button
                  id="portal-cancel-trigger"
                  variant="secondary"
                  onClick={() => setConfirming(true)}
                >
                  Cancel visit
                </Button>
              </p>
              <ConfirmDialog
                open={confirming}
                onOpenChange={(o) => {
                  if (!o) {
                    setConfirming(false);
                    // Deterministic focus return to the opening control.
                    // Deferred past Radix's unmount cleanup so the explicit
                    // target wins over any stale scope snapshot.
                    window.setTimeout(() => {
                      document.getElementById("portal-cancel-trigger")?.focus();
                    }, 0);
                  }
                }}
                title="Cancel this visit?"
                confirmLabel="Yes, cancel"
                onConfirm={() => void cancel()}
                pending={cancelling}
              >
                The clinic will be notified. This cannot be undone here.
              </ConfirmDialog>
            </Card>
          ) : null}
        </>
      ) : null}
    </PortalShell>
  );
}
