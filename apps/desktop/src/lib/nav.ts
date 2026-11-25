/**
 * Desktop nav catalog — mirrors apps/web/lib/nav.ts permission rules.
 * hrefs are desktop routes (hash/client), not Next paths.
 */

export type NavItem = { href: string; label: string; group: string };

export const NAV: NavItem[] = [
  { href: "/", label: "Dashboard", group: "Overview" },
  { href: "/operations", label: "Operations", group: "Overview" },
  { href: "/patients", label: "Patients", group: "Patient Care" },
  { href: "/schedule", label: "Appointments", group: "Patient Care" },
  { href: "/reception", label: "Reception", group: "Patient Care" },
  { href: "/follow-ups", label: "Follow-ups", group: "Patient Care" },
  { href: "/encounters", label: "Consultations", group: "Clinical" },
  { href: "/dental/plans", label: "Treatment plans", group: "Clinical" },
  { href: "/billing/invoices", label: "Billing", group: "Clinic Operations" },
  { href: "/inventory", label: "Inventory", group: "Clinic Operations" },
  { href: "/staff", label: "Staff", group: "Clinic Operations" },
  { href: "/admin", label: "Clinic settings", group: "Workspace" },
  { href: "/sessions", label: "Sessions", group: "Workspace" },
];

export const OPERATIONS_PERMS = [
  "appointment.read",
  "followup.read",
  "billing.read",
  "staff.manage",
] as const;

type NavRule = { href: string; anyOf?: readonly string[]; allOf?: readonly string[] };

const NAV_RULES: NavRule[] = [
  { href: "/" },
  { href: "/operations", anyOf: OPERATIONS_PERMS },
  { href: "/patients", anyOf: ["patient.read"] },
  { href: "/schedule", anyOf: ["appointment.read"] },
  { href: "/reception", anyOf: ["appointment.read"] },
  { href: "/follow-ups", anyOf: ["followup.read"] },
  { href: "/encounters", anyOf: ["encounter.read"] },
  { href: "/dental/plans", anyOf: ["dental.read", "plan.manage"] },
  { href: "/billing/invoices", anyOf: ["billing.read"] },
  { href: "/inventory", anyOf: ["inventory.read"] },
  { href: "/staff", anyOf: ["staff.manage", "staff.invite"] },
  {
    href: "/admin",
    anyOf: ["settings.manage", "roles.manage", "locations.manage", "audit.read"],
  },
  { href: "/sessions" },
];

function hasAny(perms: ReadonlySet<string>, required: readonly string[]): boolean {
  return required.some((p) => perms.has(p));
}

export function filterNavByPermissions(
  items: NavItem[],
  permissions: readonly string[] | null | undefined,
): NavItem[] {
  const set = new Set(permissions ?? []);
  const byHref = new Map(items.map((i) => [i.href, i]));
  const out: NavItem[] = [];
  for (const rule of NAV_RULES) {
    const item = byHref.get(rule.href);
    if (!item) continue;
    if (!rule.anyOf && !rule.allOf) {
      out.push(item);
      continue;
    }
    if (rule.allOf && !rule.allOf.every((p) => set.has(p))) continue;
    if (rule.anyOf && !hasAny(set, rule.anyOf)) continue;
    out.push(item);
  }
  return out;
}

export function hasPerm(
  permissions: readonly string[] | null | undefined,
  ...required: string[]
): boolean {
  return hasAny(new Set(permissions ?? []), required);
}

/** Map seed role name → dashboard variant (UX only; authz remains permission-based). */
export function dashboardVariant(
  role: string | null | undefined,
  permissions: readonly string[],
): "doctor" | "receptionist" | "admin" | "generic" {
  const r = (role ?? "").toLowerCase();
  if (r === "doctor" || r === "nurse") return "doctor";
  if (r === "receptionist") return "receptionist";
  if (r === "tenant_admin" || r === "accountant") return "admin";
  if (hasPerm(permissions, "staff.manage", "roles.manage")) return "admin";
  if (hasPerm(permissions, "encounter.read", "clinical.read")) return "doctor";
  if (hasPerm(permissions, "appointment.read", "patient.create")) return "receptionist";
  return "generic";
}
