"use client";

import Link from "next/link";
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
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { useTenantApi } from "@/lib/use-api";
import { portalUnavailableCopy } from "@/lib/portal";
import { NoTenantHint } from "../no-tenant";
import { PortalShell } from "../shell";

type Estimate = { id: string; status: string; grand_total: string; currency: string };
type Invoice = { id: string; status: string; grand_total: string; outstanding_amount: string; currency: string };
type Payment = { id: string; status: string; method: string; amount: string; currency: string };
type CreditBalance = { currency: string; credit: string };

export default function PortalBillingPage() {
  const router = useRouter();
  const estimates = useTenantApi<Estimate[]>((t) => `/api/v1/portal/estimates`);
  const invoices = useTenantApi<Invoice[]>((t) => `/api/v1/portal/invoices`);
  const payments = useTenantApi<Payment[]>((t) => `/api/v1/portal/payments`);
  const balance = useTenantApi<CreditBalance>((t) => `/api/v1/portal/credit-balance`);
  const error = estimates.error || invoices.error || payments.error;
  const errorStatus = estimates.status ?? invoices.status ?? payments.status;

  useEffect(() => {
    if (estimates.status === 401) router.push("/login");
  }, [estimates.status, router]);

  if (!estimates.tenant && !estimates.loading) {
    return (
      <PortalShell>
        <PageHeader title="Billing" description="Estimates, invoices, and payments." />
        <NoTenantHint />
      </PortalShell>
    );
  }

  return (
    <PortalShell>
      <PageHeader title="Billing" description="Estimates, invoices, and payments." />
      {error ? (
        <Alert tone="danger" title="Could not load billing">
          {[403, 404].includes(errorStatus ?? 0) ? portalUnavailableCopy(errorStatus) : error}
        </Alert>
      ) : null}
      <Card title="Balance">
        {balance.loading ? (
          <LoadingState label="Loading balance" />
        ) : balance.data ? (
          <p>
            Credit balance: <MoneyDisplay amount={balance.data.credit} currency={balance.data.currency} />
          </p>
        ) : (
          <EmptyState title="No balance information" />
        )}
      </Card>
      <Card title="Invoices">
        {invoices.loading ? (
          <LoadingState label="Loading invoices" />
        ) : (invoices.data ?? []).length === 0 ? (
          <EmptyState title="No invoices" />
        ) : (
          <Table
            caption="Invoices"
            columns={
              <>
                <Th>Invoice</Th>
                <Th>Status</Th>
                <Th>Total</Th>
                <Th>Due</Th>
                <Th>Details</Th>
              </>
            }
          >
            {(invoices.data ?? []).map((i) => (
              <tr key={i.id}>
                <Td>{i.id.slice(0, 8)}…</Td>
                <Td><Status value={i.status} /></Td>
                <Td numeric><MoneyDisplay amount={i.grand_total} currency={i.currency} /></Td>
                <Td numeric><MoneyDisplay amount={i.outstanding_amount} currency={i.currency} /></Td>
                <Td><Link href={`/portal/billing/${i.id}`}>View</Link></Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <Card title="Estimates">
        {estimates.loading ? (
          <LoadingState label="Loading estimates" />
        ) : (estimates.data ?? []).length === 0 ? (
          <EmptyState title="No estimates" />
        ) : (
          <Table
            caption="Estimates"
            columns={
              <>
                <Th>Estimate</Th>
                <Th>Status</Th>
                <Th>Total</Th>
              </>
            }
          >
            {(estimates.data ?? []).map((e) => (
              <tr key={e.id}>
                <Td>{e.id.slice(0, 8)}…</Td>
                <Td><Status value={e.status} /></Td>
                <Td numeric><MoneyDisplay amount={e.grand_total} currency={e.currency} /></Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
      <Card title="Payments">
        {payments.loading ? (
          <LoadingState label="Loading payments" />
        ) : (payments.data ?? []).length === 0 ? (
          <EmptyState title="No payments recorded" />
        ) : (
          <Table
            caption="Payments"
            columns={
              <>
                <Th>Method</Th>
                <Th>Status</Th>
                <Th>Amount</Th>
              </>
            }
          >
            {(payments.data ?? []).map((p) => (
              <tr key={p.id}>
                <Td>{p.method}</Td>
                <Td><Status value={p.status} /></Td>
                <Td numeric><MoneyDisplay amount={p.amount} currency={p.currency} /></Td>
              </tr>
            ))}
          </Table>
        )}
        <p className="hos-helper">Online payment is not available yet. Please pay at the clinic.</p>
      </Card>
    </PortalShell>
  );
}
