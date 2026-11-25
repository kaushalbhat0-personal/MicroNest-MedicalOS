import { describe, expect, it } from "vitest";
import { dashboardVariant, filterNavByPermissions, NAV } from "./nav";

describe("filterNavByPermissions", () => {
  it("keeps dashboard and sessions with empty perms", () => {
    const items = filterNavByPermissions(NAV, []);
    expect(items.map((i) => i.href)).toEqual(["/", "/sessions"]);
  });

  it("shows reception for appointment.read", () => {
    const items = filterNavByPermissions(NAV, ["appointment.read"]);
    expect(items.some((i) => i.href === "/reception")).toBe(true);
    expect(items.some((i) => i.href === "/staff")).toBe(false);
  });

  it("shows staff for staff.manage", () => {
    const items = filterNavByPermissions(NAV, ["staff.manage"]);
    expect(items.some((i) => i.href === "/staff")).toBe(true);
  });
});

describe("dashboardVariant", () => {
  it("maps doctor role", () => {
    expect(dashboardVariant("doctor", ["encounter.read"])).toBe("doctor");
  });
  it("maps receptionist role", () => {
    expect(dashboardVariant("receptionist", ["appointment.read"])).toBe(
      "receptionist",
    );
  });
  it("maps tenant_admin role", () => {
    expect(dashboardVariant("tenant_admin", ["staff.manage"])).toBe("admin");
  });
});
