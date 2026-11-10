"use client";

import * as React from "react";
import { Status } from "./feedback";

/**
 * Patient identity banner. Rendered at the top of every patient-bearing
 * workspace so identity is never ambiguous. Name + ID always visible;
 * never color-only (status badges carry text).
 */
export function PatientIdentityHeader({
  name,
  patientId,
  meta,
  status,
  alerts,
}: {
  name: string;
  patientId: string;
  meta?: string;
  status?: string;
  alerts?: string[];
}) {
  return (
    <section className="hos-patient-banner" aria-label={`Patient: ${name}`}>
      <div style={{ flex: 1 }}>
        <h1 className="hos-patient-name">{name}</h1>
        <p className="hos-patient-ids">ID {patientId}{meta ? ` - ${meta}` : null}</p>
      </div>
      {status ? <Status value={status} /> : null}
      {alerts?.map((a) => (
        <span key={a} role="note">
          {a}
        </span>
      ))}
    </section>
  );
}

/**
 * Money display. Shows backend-authoritative decimal strings only -
 * presentation components NEVER compute totals, taxes, or balances.
 */
export function MoneyDisplay({ amount, currency = "INR" }: { amount: string; currency?: string }) {
  return (
    <span className="hos-money">
      {currency} {amount}
    </span>
  );
}

export function FinancialSummary({
  rows,
  total,
  currency = "INR",
}: {
  rows: Array<{ label: string; amount: string }>;
  total?: { label: string; amount: string };
  currency?: string;
}) {
  return (
    <dl>
      {rows.map((r) => (
        <div key={r.label} style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
          <dt>{r.label}</dt>
          <dd className="hos-money">
            <MoneyDisplay amount={r.amount} currency={currency} />
          </dd>
        </div>
      ))}
      {total ? (
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: 12,
            borderTop: "1px solid var(--hos-border-strong)",
            marginTop: 8,
            paddingTop: 8,
            fontWeight: 700,
          }}
        >
          <dt>{total.label}</dt>
          <dd className="hos-money">
            <MoneyDisplay amount={total.amount} currency={currency} />
          </dd>
        </div>
      ) : null}
    </dl>
  );
}
