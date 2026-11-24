import { describe, expect, it } from "vitest";
import { isNavActive } from "@healthcare-os/ui";
import { NAV, canAccessOperations, filterNavByPermissions, hasPerm } from "./nav";

describe("filterNavByPermissions", () => {
  it("keeps Dashboard, Setup, and Sessions with empty permissions", () => {
    const filtered = filterNavByPermissions(NAV, []);
    expect(filtered.map((i) => i.href)).toEqual(["/", "/onboarding", "/sessions"]);
  });

  it("preserves IA groups on visible items", () => {
    const filtered = filterNavByPermissions(NAV, ["tenant.read", "appointment.read"]);
    const reception = filtered.find((i) => i.href === "/reception");
    expect(reception?.group).toBe("Patient Care");
    expect(filtered.find((i) => i.href === "/")?.group).toBe("Overview");
  });

  it("shows Operations for appointment.read", () => {
    const filtered = filterNavByPermissions(NAV, ["tenant.read", "appointment.read"]);
    const hrefs = filtered.map((i) => i.href);
    expect(hrefs).toContain("/operations");
    expect(hrefs).toContain("/reception");
    expect(hrefs).toContain("/schedule");
    expect(hrefs).not.toContain("/billing/invoices");
    expect(hrefs).not.toContain("/admin");
  });

  it("shows billing and hides clinical for accountant-like perms", () => {
    const filtered = filterNavByPermissions(NAV, [
      "tenant.read",
      "billing.read",
      "billing.create",
      "inventory.read",
    ]);
    const hrefs = filtered.map((i) => i.href);
    expect(hrefs).toContain("/operations");
    expect(hrefs).toContain("/billing/invoices");
    expect(hrefs).toContain("/inventory");
    expect(hrefs).not.toContain("/patients");
    expect(hrefs).not.toContain("/reception");
  });

  it("never uses unused queue.manage / reports.view for visibility", () => {
    const filtered = filterNavByPermissions(NAV, ["queue.manage", "reports.view"]);
    expect(filtered.map((i) => i.href)).toEqual(["/", "/onboarding", "/sessions"]);
  });
});

describe("canAccessOperations", () => {
  it("is true when any ops domain permission is present", () => {
    expect(canAccessOperations(["followup.read"])).toBe(true);
    expect(canAccessOperations(["tenant.read"])).toBe(false);
  });
});

describe("hasPerm", () => {
  it("matches any required permission", () => {
    expect(hasPerm(["patient.read"], "patient.read")).toBe(true);
    expect(hasPerm(["patient.read"], "billing.read")).toBe(false);
  });
});

describe("isNavActive", () => {
  it("matches nested patient charts without lighting Plans", () => {
    expect(isNavActive("/patients", "/patients/abc")).toBe(true);
    expect(isNavActive("/", "/patients")).toBe(false);
    expect(isNavActive("/portal", "/portal/appointments")).toBe(false);
    expect(isNavActive("/portal/appointments", "/portal/appointments/1")).toBe(true);
    expect(isNavActive("/plans", "/dental/plans")).toBe(false);
    expect(isNavActive("/dental/plans", "/dental/plans/xyz")).toBe(true);
  });
});
