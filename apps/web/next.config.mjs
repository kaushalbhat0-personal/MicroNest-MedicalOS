/** @type {import('next').NextConfig} */
const nextConfig = {
  // P4.8: same hardening headers as the API (see
  // backend/app/platform/security_headers.py). HSTS is gated on COOKIE_SECURE
  // so plain-HTTP dev never sends a false HTTPS promise.
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
    return [{ source: "/:path*", headers: base }];
  },
};
export default nextConfig;
