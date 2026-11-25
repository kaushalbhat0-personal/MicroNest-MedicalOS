import {
  apiNoStoreHeaderRules,
  apiRewriteRules,
  resolveApiRewriteUpstream,
} from "./lib/apiProxyConfig.mjs";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Allow Playwright / local tools that hit 127.0.0.1 while `next dev` binds localhost.
  allowedDevOrigins: ["127.0.0.1", "localhost"],

  /**
   * P3.7D.2 — same-origin API proxy (fixed upstream allowlist).
   * Browser: /api/* on the Vercel (or local Next) origin.
   * Upstream: allowlisted FastAPI only (no open proxy).
   */
  async rewrites() {
    const upstream = resolveApiRewriteUpstream(process.env);
    return apiRewriteRules(upstream);
  },

  // P4.8 hardening + P3.7D.2 no-store on proxied API.
  async headers() {
    const hsts = process.env.COOKIE_SECURE === "true";
    const base = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
      { key: "Referrer-Policy", value: "no-referrer" },
      {
        key: "Permissions-Policy",
        value:
          "camera=(), microphone=(), geolocation=(), payment=(), usb=(), magnetometer=(), gyroscope=(), accelerometer=()",
      },
    ];
    if (hsts) {
      base.push({
        key: "Strict-Transport-Security",
        value: "max-age=31536000; includeSubDomains",
      });
    }
    return [
      ...apiNoStoreHeaderRules(),
      { source: "/:path*", headers: base },
    ];
  },
};

export default nextConfig;
