"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Alert, Card, LoadingState, MoneyDisplay, PageHeader } from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { Shell } from "../../../shell";

type Receipt = {
  id: string;
  payment_id: string;
  amount: string;
  currency: string;
  financial_year: string | null;
  doc_number: number | null;
  created_at: string;
};

export default function ReceiptPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const t = getSelectedTenant();
    if (!t) {
      router.push("/");
      return;
    }
    api
      .get<Receipt>(`/api/v1/tenants/${t}/receipts/${params.id}`, t)
      .then((r) => {
        setReceipt(r);
        setError("");
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [params.id, router]);

  return (
    <Shell>
      <PageHeader title="Receipt" description="Immutable evidence of a recorded payment." />
      {loading ? (
        <LoadingState label="Loading receipt" />
      ) : error ? (
        <Alert tone="danger" title="Could not load receipt">
          {error}
        </Alert>
      ) : receipt ? (
        <Card title={receipt.financial_year && receipt.doc_number ? `Receipt ${receipt.financial_year}#${receipt.doc_number}` : "Receipt"}>
          <p>
            Amount: <MoneyDisplay amount={receipt.amount} currency={receipt.currency} />
          </p>
          <p>Issued: {new Date(receipt.created_at).toLocaleString()}</p>
          <p>
            <Link href="/billing/invoices">Back to invoices</Link>
          </p>
        </Card>
      ) : null}
    </Shell>
  );
}
