// Tenant selector for the UI only. This is NEVER an auth credential:
// the API resolves scope server-side from the session. Storing tokens here
// is forbidden (see repo hygiene test).

const KEY = "hos.tenantId";

export function getSelectedTenant(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(KEY);
}

export function setSelectedTenant(id: string | null): void {
  if (typeof window === "undefined") return;
  if (id) window.localStorage.setItem(KEY, id);
  else window.localStorage.removeItem(KEY);
}
