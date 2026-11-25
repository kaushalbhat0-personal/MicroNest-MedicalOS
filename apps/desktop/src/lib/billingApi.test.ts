import { describe, expect, it } from "vitest";
import {
  canConvertEstimate,
  canCreateCreditNote,
  canIssueCreditNote,
  canIssueEstimate,
  canVoidCreditNote,
  invoiceHasOutstanding,
  isPositiveMoneyAmount,
  isRefundReasonValid,
  PAYMENT_METHODS,
  parseMoneyToCents,
  refundableFromPayment,
} from "./billingApi";

describe("billing helpers", () => {
  it("allows issue only from draft", () => {
    expect(canIssueEstimate("draft")).toBe(true);
    expect(canIssueEstimate("issued")).toBe(false);
  });

  it("allows convert from issued or partially converted", () => {
    expect(canConvertEstimate("issued")).toBe(true);
    expect(canConvertEstimate("converted")).toBe(true);
    expect(canConvertEstimate("draft")).toBe(false);
    expect(canConvertEstimate("cancelled")).toBe(false);
  });

  it("detects outstanding using backend strings", () => {
    expect(
      invoiceHasOutstanding({
        id: "1",
        tenant_id: "t",
        location_id: "l",
        patient_id: "p",
        encounter_id: null,
        source_estimate_id: null,
        status: "issued",
        currency: "INR",
        subtotal: "100.00",
        tax_total: "0.00",
        grand_total: "100.00",
        allocated_amount: "40.00",
        outstanding_amount: "60.00",
        financial_year: null,
        doc_number: null,
        due_date: null,
        notes: null,
        lines: [],
        created_at: "",
        updated_at: "",
      }),
    ).toBe(true);
    expect(
      invoiceHasOutstanding({
        id: "2",
        tenant_id: "t",
        location_id: "l",
        patient_id: "p",
        encounter_id: null,
        source_estimate_id: null,
        status: "paid",
        currency: "INR",
        subtotal: "100.00",
        tax_total: "0.00",
        grand_total: "100.00",
        allocated_amount: "100.00",
        outstanding_amount: "0.00",
        financial_year: null,
        doc_number: null,
        due_date: null,
        notes: null,
        lines: [],
        created_at: "",
        updated_at: "",
      }),
    ).toBe(false);
  });

  it("exposes only offline/manual payment methods", () => {
    expect(PAYMENT_METHODS.map((m) => m.value)).toEqual([
      "cash",
      "upi",
      "manual_card",
      "manual_other",
    ]);
  });

  it("refundableFromPayment sums allocated and unallocated in cents", () => {
    expect(
      refundableFromPayment({
        id: "p",
        tenant_id: "t",
        location_id: "l",
        patient_id: "pt",
        method: "cash",
        status: "recorded",
        amount: "100.00",
        allocated_amount: "60.00",
        unallocated_amount: "25.50",
        currency: "INR",
        received_at: "",
        provider_ref: null,
        created_at: "",
      }),
    ).toBe("85.50");
  });

  it("validates positive money and refund reason", () => {
    expect(isPositiveMoneyAmount("10.00")).toBe(true);
    expect(isPositiveMoneyAmount("0.00")).toBe(false);
    expect(isPositiveMoneyAmount("abc")).toBe(false);
    expect(isRefundReasonValid("ok")).toBe(true);
    expect(isRefundReasonValid("x")).toBe(false);
    expect(isRefundReasonValid("a".repeat(201))).toBe(false);
  });

  it("gates credit note lifecycle actions", () => {
    expect(canCreateCreditNote("issued")).toBe(true);
    expect(canCreateCreditNote("draft")).toBe(false);
    expect(canCreateCreditNote("voided")).toBe(false);
    expect(canIssueCreditNote("draft")).toBe(true);
    expect(canIssueCreditNote("issued")).toBe(false);
    expect(canVoidCreditNote("draft")).toBe(true);
    expect(canVoidCreditNote("issued")).toBe(false);
  });

  it("parseMoneyToCents rejects invalid amounts", () => {
    expect(parseMoneyToCents("12.34")).toBe(1234);
    expect(parseMoneyToCents("12.3")).toBe(1230);
    expect(parseMoneyToCents("12")).toBe(1200);
    expect(parseMoneyToCents("12.345")).toBeNull();
    expect(parseMoneyToCents("-1.00")).toBeNull();
    expect(parseMoneyToCents("")).toBeNull();
  });
});
