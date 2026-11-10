"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AppShell } from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { PORTAL_NAV, type PortalMe } from "@/lib/portal";
import { getSelectedTenant, setSelectedTenant } from "@/lib/tenant";
import { useTenantApi } from "@/lib/use-api";

export function PortalShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const me = useTenantApi<PortalMe>((t) => `/api/v1/portal/me`);
  // Client-only tenant presence: reading localStorage during render would
  // differ from the server snapshot and cause a hydration mismatch.
  const [hasTenant, setHasTenant] = useState(false);

  useEffect(() => {
    setHasTenant(getSelectedTenant() !== null);
  }, [pathname]);

  useEffect(() => {
    if (me.status === 401) router.push("/login");
  }, [me.status, router]);

  async function signOut() {
    try {
      await api.post("/api/v1/auth/logout");
    } catch {
      // Session already gone: still clear local state and leave.
    }
    setSelectedTenant(null);
    router.push("/login");
  }

  return (
    <AppShell
      nav={PORTAL_NAV}
      currentPath={pathname}
      tenant={me.data?.tenant_name ?? null}
      user={me.data?.patient.display_name ?? null}
      onSignOut={me.data || hasTenant ? signOut : undefined}
    >
      {children}
    </AppShell>
  );
}
