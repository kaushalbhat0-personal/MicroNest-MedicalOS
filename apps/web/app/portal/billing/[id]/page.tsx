"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Alert,
  Card,
  FinancialSummary,
  LoadingState,
  MoneyDisplay,
  PageHeader,
  Status,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { portalUnavailableCopy } from "@/lib/portal";
import { PortalShell } from "../../shell";

type Line = { description: string; quantity: string; unit_rate: string; line_total: string };
type Invoice = {
  id: string;
  status: string;
  currency: string;
  subtotal: string;
  tax_total: string;
  grand_total: string;
  allocated_amount: string;
  outstanding_amount: string;
  due_date: string | null;
  lines: Line[];
};

export default function PortalInvoiceDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const [inv, setInv] = useState<Invoice | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const t = getSelectedTenant();
    if (!t) {
      router.push("/portal");
      return;
    }
    api
      .get<Invoice>(`/api/v1/portal/invoices/${id}`, t)
      .then((i) => {
        setInv(i);
        setError("");
      })
      .catch((e: Error & { status?: number }) => {
        if (e.status === 401) {
          router.push("/login");
          return;
        }
        setError(e.status === 403 || e.status === 404 ? portalUnavailableCopy(e.status) : e.message);
      })
      .finally(() => setLoading(false));
  }, [id, router]);

  return (
    <PortalShell>
      <p><Link href="/portal/billing">Back to billing</Link></p>
      {loading ? (
        <LoadingState label="Loading invoice" />
      ) : error && !inv ? (
        <Alert tone="danger" title="Could not load invoice">
          {error}
        </Alert>
      ) : inv ? (
        <>
          <PageHeader title={`Invoice ${inv.id.slice(0, 8)}…`} description={inv.due_date ? `Due ${inv.due_date}` : undefined} />
          <p><Status value={inv.status} /></p>
          <Card title="Summary">
            <FinancialSummary
              currency={inv.currency}
              rows={[
                { label: "Subtotal", amount: inv.subtotal },
                { label: "Tax", amount: inv.tax_total },
                { label: "Allocated", amount: inv.allocated_amount },
              ]}
              total={{ label: "Outstanding", amount: inv.outstanding_amount }}
            />
            <p>
              Grand total: <MoneyDisplay amount={inv.grand_total} currency={inv.currency} />
            </p>
          </Card>
          <Card title="Lines">
            <Table
              caption="Invoice lines"
              columns={
                <>
                  <Th>Description</Th>
                  <Th>Qty</Th>
                  <Th>Total</Th>
                </>
              }
            >
              {inv.lines.map((l, n) => (
                <tr key={n}>
                  <Td>{l.description}</Td>
                  <Td numeric>{l.quantity}</Td>
                  <Td numeric><MoneyDisplay amount={l.line_total} currency={inv.currency} /></Td>
                </tr>
              ))}
            </Table>
          </Card>
        </>
      ) : null}
    </PortalShell>
  );
}
