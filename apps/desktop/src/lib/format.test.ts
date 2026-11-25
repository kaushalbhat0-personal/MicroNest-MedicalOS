import { describe, expect, it } from "vitest";
import { addDays, startOfDay, statusLabel, toDateInput, weekRange } from "./format";

describe("format helpers", () => {
  it("formats status labels", () => {
    expect(statusLabel("checked_in")).toBe("checked in");
  });

  it("builds monday-based week range", () => {
    // Wednesday 2026-11-25
    const wed = new Date(2026, 10, 25, 15, 0, 0);
    const { start, end } = weekRange(wed);
    expect(toDateInput(start)).toBe("2026-11-23");
    expect(toDateInput(end)).toBe("2026-11-30");
  });

  it("adds days from start of day", () => {
    const d = startOfDay(new Date(2026, 10, 25));
    expect(toDateInput(addDays(d, 1))).toBe("2026-11-26");
  });
});
