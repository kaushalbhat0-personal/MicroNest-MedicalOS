/**
 * Browser API base URL resolution for same-origin proxy (P3.7D.2).
 *
 * - Unset / empty `NEXT_PUBLIC_API_URL` → same-origin relative paths ("").
 * - Explicit absolute URL → direct API (local override / Playwright helpers).
 * Paths passed to `api.*` already include `/api/...`; never append another `/api`.
 */

export function resolveApiBase(
  env: Record<string, string | undefined> = typeof process !== "undefined"
    ? (process.env as Record<string, string | undefined>)
    : {},
): string {
  if (!Object.prototype.hasOwnProperty.call(env, "NEXT_PUBLIC_API_URL")) {
    return "";
  }
  const raw = env.NEXT_PUBLIC_API_URL;
  if (raw === undefined || raw === null) return "";
  const trimmed = String(raw).trim().replace(/\/$/, "");
  return trimmed;
}

/** Join base + path without producing `//api` or double `/api/api`. */
export function apiUrl(path: string, base: string = resolveApiBase()): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  if (!base) return p;
  return `${base}${p}`;
}
