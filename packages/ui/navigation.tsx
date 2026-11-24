"use client";

import * as React from "react";
import { Menu, X } from "lucide-react";

export function SkipLink({ target = "main-content" }: { target?: string }) {
  return (
    <a href={`#${target}`} className="hos-skip-link">
      Skip to content
    </a>
  );
}

export type NavItem = {
  href: string;
  label: string;
  /** Optional IA section label (e.g. "Patient Care"). Flat lists omit this. */
  group?: string;
};

export type AppShellVariant = "clinic" | "portal";

/** Prefix-aware active match without colliding sibling roots. */
export function isNavActive(href: string, currentPath: string): boolean {
  if (href === "/" || href === "/portal") {
    return currentPath === href;
  }
  if (currentPath === href) return true;
  return currentPath.startsWith(`${href}/`);
}

function groupNav(items: NavItem[]): { group: string | null; items: NavItem[] }[] {
  const sections: { group: string | null; items: NavItem[] }[] = [];
  for (const item of items) {
    const g = item.group ?? null;
    const last = sections[sections.length - 1];
    if (last && last.group === g) {
      last.items.push(item);
    } else {
      sections.push({ group: g, items: [item] });
    }
  }
  return sections;
}

function NavLinks({
  nav,
  currentPath,
  onNavigate,
}: {
  nav: NavItem[];
  currentPath: string;
  onNavigate?: () => void;
}) {
  const sections = groupNav(nav);
  const hasGroups = sections.some((s) => s.group);

  return (
    <nav className="hos-app-nav" aria-label="Primary">
      {sections.map((section, idx) => (
        <div key={section.group ?? `ungrouped-${idx}`} className="hos-nav-section">
          {hasGroups && section.group ? (
            <p className="hos-nav-group-label">{section.group}</p>
          ) : null}
          <ul className="hos-nav-list">
            {section.items.map((item) => {
              const active = isNavActive(item.href, currentPath);
              return (
                <li key={item.href}>
                  <a
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    onClick={onNavigate}
                  >
                    {item.label}
                  </a>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

/**
 * Application shell: skip link, labeled nav with aria-current, tenant
 * context area, and a labeled main landmark.
 *
 * Clinic variant uses a compact sidebar on large screens and a drawer on
 * small screens. Portal variant keeps a calmer top navigation on desktop
 * with the same drawer pattern on small screens.
 */
export function AppShell({
  nav,
  currentPath,
  tenant,
  user,
  onSignOut,
  brand = "Healthcare OS",
  variant = "clinic",
  children,
}: {
  nav: NavItem[];
  currentPath: string;
  tenant?: string | null;
  user?: string | null;
  onSignOut?: () => void;
  brand?: string;
  variant?: AppShellVariant;
  children: React.ReactNode;
}) {
  const [menuOpen, setMenuOpen] = React.useState(false);
  const closeMenu = React.useCallback(() => setMenuOpen(false), []);

  React.useEffect(() => {
    setMenuOpen(false);
  }, [currentPath]);

  React.useEffect(() => {
    if (!menuOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setMenuOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  const density = variant === "portal" ? "comfortable" : "compact";
  const homeHref = variant === "portal" ? "/portal" : "/";

  return (
    <div className="hos-app-shell" data-variant={variant} data-density={density}>
      <SkipLink />
      <header className="hos-app-header">
        <button
          type="button"
          className="hos-nav-menu-btn"
          aria-expanded={menuOpen}
          aria-controls="hos-primary-nav"
          onClick={() => setMenuOpen((o) => !o)}
        >
          {menuOpen ? <X size={20} aria-hidden /> : <Menu size={20} aria-hidden />}
          <span className="hos-nav-menu-label">{menuOpen ? "Close menu" : "Open menu"}</span>
        </button>
        <a href={homeHref} className="hos-app-brand">
          {brand}
        </a>
        {variant === "portal" ? (
          <div className="hos-app-nav-inline" aria-hidden={menuOpen}>
            <NavLinks nav={nav} currentPath={currentPath} />
          </div>
        ) : null}
        <div className="hos-app-meta">
          {tenant ? (
            <span className="hos-app-meta-item" title={tenant}>
              <span className="hos-app-meta-label">
                {variant === "portal" ? "Clinic" : "Workspace"}
              </span>
              <span className="hos-app-meta-value">{tenant}</span>
            </span>
          ) : null}
          {user ? (
            <span className="hos-app-meta-item" title={user}>
              <span className="hos-app-meta-label">
                {variant === "portal" ? "Patient" : "Signed in"}
              </span>
              <span className="hos-app-meta-value">{user}</span>
            </span>
          ) : null}
          {onSignOut ? (
            <button
              type="button"
              className="hos-btn"
              data-variant="secondary"
              data-size="sm"
              onClick={onSignOut}
            >
              Sign out
            </button>
          ) : null}
        </div>
      </header>

      <div className="hos-app-body">
        {menuOpen ? (
          <button
            type="button"
            className="hos-nav-backdrop"
            aria-label="Close navigation"
            onClick={closeMenu}
          />
        ) : null}
        <aside
          id="hos-primary-nav"
          className="hos-app-sidebar"
          data-open={menuOpen ? "true" : "false"}
          aria-label={variant === "portal" ? "Patient navigation" : "Clinic navigation"}
        >
          <NavLinks nav={nav} currentPath={currentPath} onNavigate={closeMenu} />
        </aside>
        <main id="main-content" className="hos-app-main" tabIndex={-1}>
          {children}
        </main>
      </div>
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
    <div className="hos-page-header">
      <div className="hos-page-header-text">
        <h1 className="hos-page-title">{title}</h1>
        {description ? <p className="hos-page-description">{description}</p> : null}
      </div>
      {actions ? <div className="hos-page-actions">{actions}</div> : null}
    </div>
  );
}
