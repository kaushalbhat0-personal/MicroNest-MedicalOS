import { describe, expect, it } from "vitest";
import { allowedTransitions, STATUS_TRANSITIONS } from "./schedulingApi";

describe("appointment status transitions", () => {
  it("matches backend matrix for scheduled", () => {
    expect(allowedTransitions("scheduled")).toEqual([
      "confirmed",
      "checked_in",
      "cancelled",
      "no_show",
    ]);
  });

  it("blocks transitions from terminal states", () => {
    expect(allowedTransitions("completed")).toEqual([]);
    expect(allowedTransitions("cancelled")).toEqual([]);
    expect(allowedTransitions("no_show")).toEqual([]);
  });

  it("does not expose in_progress", () => {
    expect(Object.keys(STATUS_TRANSITIONS)).not.toContain("in_progress");
  });

  it("allows check-in from confirmed only once path", () => {
    expect(allowedTransitions("confirmed")).toContain("checked_in");
    expect(allowedTransitions("checked_in")).not.toContain("checked_in");
  });
});
