"use client";

import * as React from "react";

export function SkipLink({ target = "main-content" }: { target?: string }) {
  return (
    <a href={`#${target}`} className="hos-skip-link">
      Skip to content
    </a>
  );
}

export type NavItem = { href: string; label: string };

/**
 * Application shell: skip link, labeled nav with aria-current, tenant
 * context area, and a labeled main landmark. Screens supply content.
 */
export function AppShell({
  nav,
  currentPath,
  tenant,
  user,
  onSignOut,
  children,
}: {
  nav: NavItem[];
  currentPath: string;
  tenant?: string | null;
  user?: string | null;
  onSignOut?: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="hos-app-shell">
      <SkipLink />
      <header className="hos-app-header">
        <strong>Healthcare OS</strong>
        <nav className="hos-app-nav" aria-label="Primary">
          {nav.map((item) => (
            <a
              key={item.href}
              href={item.href}
              aria-current={item.href === currentPath ? "page" : undefined}
            >
              {item.label}
            </a>
          ))}
        </nav>
        <span
          style={{
            marginLeft: "auto",
            display: "flex",
            gap: 8,
            rowGap: 4,
            alignItems: "center",
            flexWrap: "wrap",
            justifyContent: "flex-end",
            minWidth: 0,
          }}
        >
          {tenant ? <small>{tenant}</small> : null}
          {user ? <small>{user}</small> : null}
          {onSignOut ? (
            <button type="button" className="hos-btn" data-variant="secondary" data-size="sm" onClick={onSignOut}>
              Sign out
            </button>
          ) : null}
        </span>
      </header>
      <main id="main-content" className="hos-app-main" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 16 }}>
      <div style={{ flex: 1 }}>
        <h1 style={{ fontSize: "var(--hos-text-h1)", margin: 0 }}>{title}</h1>
        {description ? <p style={{ color: "var(--hos-text-muted)", margin: "4px 0 0" }}>{description}</p> : null}
      </div>
      {actions}
    </div>
  );
}
