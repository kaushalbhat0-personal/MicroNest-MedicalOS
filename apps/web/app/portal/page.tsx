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
  MoneyDisplay,
  PageHeader,
  Status,
} from "@healthcare-os/ui";
import { api, type Me } from "@/lib/api";
import { getSelectedTenant, setSelectedTenant } from "@/lib/tenant";
import { portalUnavailableCopy } from "@/lib/portal";
import { PortalShell } from "./shell";

type PortalPatient = { id: string; display_name: string; phone: string | null; is_active: boolean };
type PortalMe = {
  user_id: string;
  email: string;
  display_name: string;
  tenant_id: string;
  tenant_name: string;
  patient: PortalPatient;
};
type Appointment = { id: string; start_at: string; status: string };
type Invoice = { id: string; status: string; grand_total: string; outstanding_amount: string; currency: string };
type CreditBalance = { currency: string; credit: string };

export default function PortalHomePage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [portal, setPortal] = useState<PortalMe | null>(null);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [balance, setBalance] = useState<CreditBalance | null>(null);
  const [tenant, setTenant] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [errorStatus, setErrorStatus] = useState<number | null>(null);

  function noteError(e: Error & { status?: number }) {
    setError(e.message);
    setErrorStatus(typeof e.status === "number" ? e.status : null);
  }

  useEffect(() => {
    api
      .get<Me>("/api/v1/auth/me")
      .then((m) => {
        setMe(m);
        const sel = getSelectedTenant() ?? (m.tenants.length === 1 ? m.tenants[0].id : null);
        if (sel) setSelectedTenant(sel);
        setTenant(sel);
        setLoading(false);
      })
      .catch(() => router.push("/login"));
  }, [router]);

  useEffect(() => {
    if (errorStatus === 401) router.push("/login");
  }, [errorStatus, router]);

  useEffect(() => {
    if (!tenant) return;
    api
      .get<PortalMe>("/api/v1/portal/me", tenant)
      .then(setPortal)
      .catch(noteError);
    api
      .get<Appointment[]>("/api/v1/portal/appointments?status=scheduled", tenant)
      .then((a) => setAppointments(a.slice(0, 3)))
      .catch(noteError);
    api
      .get<Invoice[]>("/api/v1/portal/invoices", tenant)
      .then(setInvoices)
      .catch(() => {});
    api
      .get<CreditBalance>("/api/v1/portal/credit-balance", tenant)
      .then(setBalance)
      .catch(() => {});
  }, [tenant]);

  function pick(id: string) {
    setSelectedTenant(id);
    setTenant(id);
  }

  if (loading || !me) {
    return (
      <PortalShell>
        <LoadingState label="Loading your portal" />
      </PortalShell>
    );
  }

  if (!tenant) {
    return (
      <PortalShell>
        <PageHeader title="Patient portal" description="Your care, in one calm place." />
        <Card title="Choose your care organization">
          {me.tenants.length === 0 ? (
            <p className="hos-helper">
              The patient portal is not enabled for this account.
            </p>
          ) : (
            <ul>
              {me.tenants.map((t) => (
                <li key={t.id}>
                  <Button variant="secondary" onClick={() => pick(t.id)}>
                    {t.name}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </PortalShell>
    );
  }

  if (error && !portal) {
    return (
      <PortalShell>
        <Alert tone="danger" title="Portal unavailable">
          {[403, 404].includes(errorStatus ?? 0) ? portalUnavailableCopy(errorStatus) : error}
        </Alert>
      </PortalShell>
    );
  }

  if (!portal) {
    return (
      <PortalShell>
        <LoadingState label="Loading your portal" />
      </PortalShell>
    );
  }

  const due = invoices.filter((i) => i.outstanding_amount !== "0.00");

  return (
    <PortalShell>
      <PageHeader
        title={`Hello, ${portal.patient.display_name}`}
        description={`${portal.tenant_name} · ${portal.email}`}
        actions={
          <Button variant="secondary" onClick={() => router.push("/portal/appointments")}>
            My appointments
          </Button>
        }
      />
      {error ? (
        <Alert tone="danger" title="Something went wrong">
          {error}
        </Alert>
      ) : null}
      <Card title="What needs you">
        {appointments.length === 0 ? (
          <EmptyState title="Nothing scheduled">Your upcoming visits will appear here.</EmptyState>
        ) : (
          <ul>
            {appointments.map((a) => (
              <li key={a.id}>
                <Link href={`/portal/appointments/${a.id}`}>
                  {new Date(a.start_at).toLocaleString()}
                </Link>{" "}
                <Status value={a.status} />
              </li>
            ))}
          </ul>
        )}
        {balance && balance.credit !== "0.00" ? (
          <p>
            Credit balance: <MoneyDisplay amount={balance.credit} currency={balance.currency} />
          </p>
        ) : null}
        {due.length > 0 ? (
          <p>
            {due.length} invoice{due.length === 1 ? "" : "s"} with an amount due.{" "}
            <Link href="/portal/billing">Review billing</Link>
          </p>
        ) : null}
      </Card>
      <Card title="Your care">
        <ul>
          <li><Link href="/portal/visits">Visit summaries</Link></li>
          <li><Link href="/portal/prescriptions">Medicines</Link></li>
          <li><Link href="/portal/dental">Dental care</Link></li>
          <li><Link href="/portal/documents">Documents</Link></li>
        </ul>
      </Card>
    </PortalShell>
  );
}
