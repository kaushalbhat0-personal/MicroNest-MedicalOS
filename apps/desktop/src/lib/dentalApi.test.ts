import { describe, expect, it } from "vitest";
import {
  deriveOdontogramStates,
  isDentalSurface,
  isFdiPermanent,
  PLAN_ITEM_NEXT,
  PROCEDURE_RECORD_NEXT,
  procedureTransitionNeedsConsent,
} from "./dentalApi";

describe("dental helpers", () => {
  it("isFdiPermanent accepts permanent only", () => {
    expect(isFdiPermanent(16)).toBe(true);
    expect(isFdiPermanent(99)).toBe(false);
    expect(isFdiPermanent(51)).toBe(false);
  });

  it("isDentalSurface validates surface codes", () => {
    expect(isDentalSurface("mesial")).toBe(true);
    expect(isDentalSurface("MESIAL")).toBe(true);
    expect(isDentalSurface("facial")).toBe(false);
  });

  it("deriveOdontogramStates prefers finding over planned", () => {
    const states = deriveOdontogramStates(
      [{ tooth: 16, status: "active" }],
      [{ tooth: 16, status: "planned" }],
    );
    expect(states[16]).toBe("finding");
  });

  it("deriveOdontogramStates uses completed when no active finding", () => {
    const states = deriveOdontogramStates(
      [{ tooth: 16, status: "resolved" }],
      [{ tooth: 16, status: "completed" }],
    );
    expect(states[16]).toBe("completed");
  });

  it("procedureTransitionNeedsConsent for in_progress and completed", () => {
    expect(procedureTransitionNeedsConsent("in_progress")).toBe(true);
    expect(procedureTransitionNeedsConsent("completed")).toBe(true);
    expect(procedureTransitionNeedsConsent("planned")).toBe(false);
    expect(procedureTransitionNeedsConsent("cancelled")).toBe(false);
  });

  it("PLAN_ITEM_NEXT transition keys", () => {
    expect(PLAN_ITEM_NEXT.proposed).toEqual(["planned", "cancelled"]);
    expect(PLAN_ITEM_NEXT.planned).toEqual(["in_progress", "cancelled"]);
    expect(PLAN_ITEM_NEXT.in_progress).toEqual(["completed", "cancelled"]);
  });

  it("PROCEDURE_RECORD_NEXT transition keys", () => {
    expect(PROCEDURE_RECORD_NEXT.planned).toEqual(["in_progress", "cancelled"]);
    expect(PROCEDURE_RECORD_NEXT.in_progress).toEqual(["completed", "cancelled"]);
  });
});