"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { AppShell, LoadingState } from "@healthcare-os/ui";
import type { NavItem } from "@healthcare-os/ui";
import { api, type Me } from "@/lib/api";
import { NAV, filterNavByPermissions } from "@/lib/nav";
import { getSelectedTenant, setSelectedTenant } from "@/lib/tenant";
import { fetchWorkspaceContext } from "@/lib/workspace";

const SAFE_NAV: NavItem[] = NAV.filter(
  (i) => i.href === "/" || i.href === "/onboarding" || i.href === "/sessions",
);

type NavState =
  | { status: "loading" }
  | { status: "ready"; items: NavItem[] }
  | { status: "error"; items: NavItem[] };

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [navState, setNavState] = useState<NavState>({ status: "loading" });
  const [tenantName, setTenantName] = useState<string | null>(null);
  const [userName, setUserName] = useState<string | null>(null);
  const [tenants, setTenants] = useState<Me["tenants"]>([]);

  useEffect(() => {
    api
      .get<Me>("/api/v1/auth/me")
      .then((m) => {
        setUserName(m.display_name);
        setTenants(m.tenants);
      })
      .catch(() => {
        setUserName(null);
        setTenants([]);
      });
  }, []);

  useEffect(() => {
    const tid = getSelectedTenant();
    if (!tid) {
      setNavState({ status: "ready", items: SAFE_NAV });
      setTenantName(null);
      return;
    }
    const named = tenants.find((t) => t.id === tid);
    if (named) setTenantName(named.name);

    let cancelled = false;
    setNavState({ status: "loading" });
    fetchWorkspaceContext(tid)
      .then((ctx) => {
        if (cancelled) return;
        setNavState({
          status: "ready",
          items: filterNavByPermissions(NAV, ctx.permissions),
        });
      })
      .catch(() => {
        // Fail soft: keep Dashboard/Sessions only. APIs still enforce authz.
        if (!cancelled) setNavState({ status: "error", items: SAFE_NAV });
      });
    return () => {
      cancelled = true;
    };
  }, [pathname, tenants]);

  async function signOut() {
    try {
      await api.post("/api/v1/auth/logout");
    } catch {
      // Session already gone.
    }
    setSelectedTenant(null);
    router.push("/login");
  }

  const nav = navState.status === "loading" ? SAFE_NAV : navState.items;

  return (
    <AppShell
      variant="clinic"
      brand="Healthcare OS"
      nav={nav}
      currentPath={pathname}
      tenant={tenantName}
      user={userName}
      onSignOut={signOut}
    >
      {navState.status === "loading" ? (
        <div aria-live="polite" style={{ marginBottom: "0.75rem" }}>
          <LoadingState label="Loading workspace" />
        </div>
      ) : null}
      {navState.status === "error" ? (
        <p role="status" className="hos-helper" style={{ marginBottom: "0.75rem" }}>
          Workspace permissions could not be loaded. Showing limited navigation.
        </p>
      ) : null}
      {children}
    </AppShell>
  );
}
