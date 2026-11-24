import type { NavItem } from "@healthcare-os/ui";

/**
 * Full clinic nav catalog with IA groups. Visibility is filtered by
 * ``filterNavByPermissions`` using server-derived membership permissions.
 * Unused catalog entries (queue.manage, reports.view) are intentionally
 * not used here.
 */
export const NAV: NavItem[] = [
  { href: "/", label: "Dashboard", group: "Overview" },
  { href: "/onboarding", label: "Setup", group: "Overview" },
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
  { href: "/team", label: "Team", group: "Workspace" },
  { href: "/admin", label: "Clinic settings", group: "Workspace" },
  { href: "/subscription", label: "Subscription", group: "Workspace" },
  { href: "/plans", label: "Plans", group: "Workspace" },
  { href: "/sessions", label: "Sessions", group: "Workspace" },
];

/** Any of these grants Operations nav visibility (matches API gate). */
export const OPERATIONS_PERMS = [
  "appointment.read",
  "followup.read",
  "billing.read",
  "staff.manage",
] as const;

type NavRule = { href: string; anyOf?: readonly string[]; allOf?: readonly string[] };

const NAV_RULES: NavRule[] = [
  { href: "/" },
  { href: "/onboarding" },
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
  { href: "/team", anyOf: ["staff.manage", "staff.invite"] },
  {
    href: "/admin",
    anyOf: ["settings.manage", "roles.manage", "locations.manage", "audit.read"],
  },
  { href: "/subscription", anyOf: ["subscription.read"] },
  { href: "/plans", anyOf: ["tenant.read", "subscription.read"] },
  { href: "/sessions" },
];

function hasAny(perms: ReadonlySet<string>, required: readonly string[]): boolean {
  return required.some((p) => perms.has(p));
}

/**
 * Filter nav items by server-derived permissions. Always keeps Dashboard and
 * Sessions. Unknown hrefs are hidden. Empty permission set → Dashboard + Sessions.
 * Group labels are preserved on surviving items.
 */
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

export function canAccessOperations(permissions: readonly string[] | null | undefined): boolean {
  return hasAny(new Set(permissions ?? []), OPERATIONS_PERMS);
}

export function hasPerm(
  permissions: readonly string[] | null | undefined,
  ...required: string[]
): boolean {
  return hasAny(new Set(permissions ?? []), required);
}
