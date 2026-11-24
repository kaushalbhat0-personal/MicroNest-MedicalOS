import type { NavItem } from "@healthcare-os/ui";

/** Patient portal nav — calm labels, no clinic-admin groupings. */
export const PORTAL_NAV: NavItem[] = [
  { href: "/portal", label: "Home" },
  { href: "/portal/appointments", label: "Appointments" },
  { href: "/portal/visits", label: "Visits" },
  { href: "/portal/prescriptions", label: "Medicines" },
  { href: "/portal/dental", label: "Treatment plans" },
  { href: "/portal/billing", label: "Billing" },
  { href: "/portal/documents", label: "Documents" },
  { href: "/portal/profile", label: "Profile" },
  { href: "/portal/access-log", label: "Activity" },
];

export type PortalPatient = {
  id: string;
  display_name: string;
  phone: string | null;
  email?: string | null;
  is_active: boolean;
};

export type PortalMe = {
  user_id: string;
  email: string;
  display_name: string;
  tenant_id: string;
  tenant_name: string;
  patient: PortalPatient;
};

export type PortalWorkspaces = {
  provider: boolean;
  portal: boolean;
};

export function portalUnavailableCopy(status: number | null): string {
  if (status === 403 || status === 404)
    return "The patient portal is not enabled for this account, or this record is not shared with you.";
  return "Something went wrong loading the portal. Please try again.";
}
