/**
 * P3.7D.2 — Fixed allowlist for same-origin API rewrite destinations.
 * Used by next.config.mjs (build-time). Never accept arbitrary upstreams.
 */

export const STAGING_RENDER_UPSTREAM = "https://micronest-medicalos.onrender.com";

/** Local FastAPI defaults for `next dev` / local `next start` with rewrite. */
export const LOCAL_UPSTREAMS = Object.freeze([
  "http://127.0.0.1:8000",
  "http://localhost:8000",
]);

export const ALLOWED_API_REWRITE_UPSTREAMS = Object.freeze([
  STAGING_RENDER_UPSTREAM,
  ...LOCAL_UPSTREAMS,
]);

/**
 * Resolve the rewrite upstream. Open-proxy safe: only allowlisted hosts.
 * @param {NodeJS.ProcessEnv | Record<string, string | undefined>} [env]
 * @returns {string} origin with no trailing slash
 */
export function resolveApiRewriteUpstream(env = process.env) {
  const raw = String(env.API_REWRITE_UPSTREAM ?? "")
    .trim()
    .replace(/\/$/, "");
  if (!raw) {
    return "http://127.0.0.1:8000";
  }
  if (!ALLOWED_API_REWRITE_UPSTREAMS.includes(raw)) {
    throw new Error(
      `API_REWRITE_UPSTREAM is not allowlisted (refusing open proxy). Got a non-allowed origin.`,
    );
  }
  return raw;
}

/**
 * Path-preserving rewrite: browser /api/* → upstream /api/*.
 * @param {string} upstream
 */
export function apiRewriteRules(upstream) {
  const base = String(upstream).replace(/\/$/, "");
  return [
    {
      source: "/api/:path*",
      destination: `${base}/api/:path*`,
    },
  ];
}

/** Prevent CDN/shared caching of private API responses on the Vercel host. */
export function apiNoStoreHeaderRules() {
  return [
    {
      source: "/api/:path*",
      headers: [
        {
          key: "Cache-Control",
          value: "private, no-store, no-cache, must-revalidate",
        },
        { key: "Pragma", value: "no-cache" },
      ],
    },
  ];
}

/**
 * Assert cookie security attributes are not weakened (unit/regression aid).
 * @param {string} setCookieHeader
 */
export function assertAuthCookieHardening(setCookieHeader) {
  const v = String(setCookieHeader);
  const lower = v.toLowerCase();
  const problems = [];
  if (!/httponly/i.test(v)) problems.push("missing HttpOnly");
  if (!/;\s*secure/i.test(v) && !lower.includes("secure")) problems.push("missing Secure");
  if (!/samesite=lax/i.test(v)) problems.push("SameSite must be Lax");
  if (/samesite=none/i.test(v)) problems.push("SameSite=None is forbidden");
  if (/;\s*domain=/i.test(v)) problems.push("Domain attribute must remain unset (host-only)");
  return problems;
}
