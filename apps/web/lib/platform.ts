// Platform console shared types + identity gate. Mirrors the O1.3R
// PlatformTenantItem/PlatformTenantList contracts exactly (server is
// authoritative; these types are display-only projections). No tenant
// selector here: platform calls carry no X-Tenant header.

"use client";

import { useEffect, useState } from "react";
import { api, type Me } from "@/lib/api";

export type PlanLimits = {
  max_locations: number;
  max_practitioners: number;
  max_staff_seats: number;
  enforced: boolean;
};

export type SubscriptionSummary = {
  status: string;
  trial_ends_at: string | null;
  plan_code: string;
  plan_name: string;
  trial_starts_at: string | null;
  is_in_trial: boolean;
  limits: PlanLimits | null;
};

export type SpecialtyDetail = {
  code: string;
  pack_version: string;
  label: string;
  maturity: string;
  ready_for_use: boolean;
};

export type PlatformTenantItem = {
  id: string;
  name: string;
  slug: string;
  status: string;
  created_at: string;
  updated_at: string;
  subscription: SubscriptionSummary | null;
  specialties_enabled: string[];
  specialties: SpecialtyDetail[];
};

export type PlatformTenantList = {
  items: PlatformTenantItem[];
  total: number;
  limit: number;
  offset: number;
};

/** Server-authoritative identity for the console gate. Client-side only as
 *  UX: every platform API re-checks `is_platform_admin` server-side. */
export function usePlatformMe() {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<number | null>(null);

  useEffect(() => {
    api
      .get<Me>("/api/v1/auth/me")
      .then((m) => {
        setMe(m);
        setStatus(null);
      })
      .catch((e: Error & { status?: number }) => {
        setMe(null);
        setStatus(typeof e.status === "number" ? e.status : null);
      })
      .finally(() => setLoading(false));
  }, []);

  return { me, loading, status, isPlatformAdmin: me?.is_platform_admin === true };
}
