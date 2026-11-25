import { describe, expect, it } from "vitest";
import { ENCOUNTER_TRANSITIONS } from "./clinicalApi";

describe("encounter lifecycle", () => {
  it("only allows open → closed", () => {
    expect(ENCOUNTER_TRANSITIONS.open).toEqual(["closed"]);
    expect(ENCOUNTER_TRANSITIONS.closed).toEqual([]);
  });

  it("does not invent in_progress", () => {
    expect(Object.keys(ENCOUNTER_TRANSITIONS)).toEqual(["open", "closed"]);
  });
});
