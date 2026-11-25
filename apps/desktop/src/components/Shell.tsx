import { ReactNode, useMemo, useState } from "react";
import { Alert, Button, EmptyState } from "@healthcare-os/ui";
import { fetchMe } from "../lib/api";
import { filterNavByPermissions, NAV } from "../lib/nav";
import { useSession } from "../lib/session";

export function Shell({
  route,
  onNavigate,
  onLogout,
  onSwitchWorkspace,
  onSessionExpired,
  children,
}: {
  route: string;
  onNavigate: (href: string) => void;
  onLogout: () => void;
  onSwitchWorkspace: () => void;
  onSessionExpired: () => void;
  children: ReactNode;
}) {
  const { profile, tenant, workspace } = useSession();
  const [busy, setBusy] = useState(false);
  const [probe, setProbe] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const nav = useMemo(
    () => filterNavByPermissions(NAV, workspace?.permissions),
    [workspace?.permissions],
  );

  const groups = useMemo(() => {
    const map = new Map<string, typeof nav>();
    for (const item of nav) {
      const list = map.get(item.group) ?? [];
      list.push(item);
      map.set(item.group, list);
    }
    return [...map.entries()];
  }, [nav]);

  async function verify() {
    setBusy(true);
    setErr(null);
    try {
      const me = await fetchMe(tenant?.id);
      setProbe(me.email);
    } catch (e) {
      if (String(e).includes("session_expired")) onSessionExpired();
      else if (String(e).includes("forbidden")) setErr("Forbidden (403).");
      else setErr("Verification failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="hos-desktop-shell">
      <aside className="hos-desktop-sidebar" aria-label="Clinic navigation">
        <div className="hos-desktop-brand">Healthcare OS</div>
        <nav>
          {groups.map(([group, items]) => (
            <div key={group} className="hos-nav-group">
              <p className="hos-nav-group-label">{group}</p>
              {items.map((item) => (
                <button
                  key={item.href}
                  type="button"
                  className={
                    route === item.href ? "hos-nav-active hos-nav-btn" : "hos-nav-btn"
                  }
                  onClick={() => onNavigate(item.href)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          ))}
        </nav>
      </aside>
      <div className="hos-desktop-main">
        <header className="hos-desktop-toolbar">
          <div>
            <strong>{tenant?.name ?? "No clinic"}</strong>
            <span className="hos-muted">
              {" "}
              · {profile?.display_name}
              {workspace?.role ? ` · ${workspace.role}` : ""}
            </span>
          </div>
          <div className="hos-desktop-toolbar-actions">
            <span className="hos-notif" title="Notifications coming later" aria-hidden>
              ○
            </span>
            {(profile?.tenants?.length ?? 0) > 1 && (
              <Button type="button" variant="secondary" onClick={onSwitchWorkspace}>
                Switch clinic
              </Button>
            )}
            <Button type="button" variant="secondary" disabled={busy} onClick={verify}>
              Verify session
            </Button>
            <Button type="button" variant="secondary" disabled={busy} onClick={onLogout}>
              Sign out
            </Button>
          </div>
        </header>
        <div className="hos-desktop-crumbs">
          <span>Clinic</span>
          <span aria-hidden>/</span>
          <span>{route === "/" ? "Dashboard" : route.replace(/^\//, "")}</span>
        </div>
        <main className="hos-desktop-content">
          {err && (
            <Alert tone="danger" title="Error">
              {err}
            </Alert>
          )}
          {probe && (
            <p className="hos-caption" data-testid="auth-probe">
              Authenticated as {probe}
            </p>
          )}
          {children}
        </main>
      </div>
    </div>
  );
}

export function ModulePlaceholder({ title }: { title: string }) {
  return (
    <EmptyState title={title}>
      This module is deferred to a later milestone. Navigation is permission-filtered;
      the API remains the authorization boundary.
    </EmptyState>
  );
}
