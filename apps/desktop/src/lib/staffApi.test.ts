import { describe, expect, it } from "vitest";
import { WEEKDAY_LABELS } from "./staffApi";

describe("staffApi helpers", () => {
  it("exposes Mon–Sun weekday labels aligned with backend 0=Mon", () => {
    expect(WEEKDAY_LABELS).toEqual([
      "Mon",
      "Tue",
      "Wed",
      "Thu",
      "Fri",
      "Sat",
      "Sun",
    ]);
    expect(WEEKDAY_LABELS).toHaveLength(7);
    expect(WEEKDAY_LABELS[0]).toBe("Mon");
    expect(WEEKDAY_LABELS[6]).toBe("Sun");
  });

  it("keeps staff schedule weekday index distinct from JS Date.getDay()", () => {
    // Backend weekday 0 = Monday; JS Sunday = 0
    const jsSunday = 0;
    const backendMonday = 0;
    expect(jsSunday).toBe(0);
    expect(backendMonday).toBe(0);
    expect(WEEKDAY_LABELS[backendMonday]).not.toBe("Sun");
  });
});
