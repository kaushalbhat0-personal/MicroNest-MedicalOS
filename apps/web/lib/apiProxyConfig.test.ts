import { describe, expect, it } from "vitest";
import {
  ALLOWED_API_REWRITE_UPSTREAMS,
  STAGING_RENDER_UPSTREAM,
  apiNoStoreHeaderRules,
  apiRewriteRules,
  assertAuthCookieHardening,
  resolveApiRewriteUpstream,
} from "./apiProxyConfig.mjs";

describe("resolveApiRewriteUpstream", () => {
  it("defaults to local FastAPI (not an open proxy)", () => {
    expect(resolveApiRewriteUpstream({})).toBe("http://127.0.0.1:8000");
  });

  it("accepts staging Render upstream", () => {
    expect(
      resolveApiRewriteUpstream({ API_REWRITE_UPSTREAM: STAGING_RENDER_UPSTREAM }),
    ).toBe(STAGING_RENDER_UPSTREAM);
  });

  it("accepts localhost variants", () => {
    expect(
      resolveApiRewriteUpstream({ API_REWRITE_UPSTREAM: "http://localhost:8000" }),
    ).toBe("http://localhost:8000");
  });

  it("rejects arbitrary upstream (no open proxy)", () => {
    expect(() =>
      resolveApiRewriteUpstream({
        API_REWRITE_UPSTREAM: "https://evil.example.com",
      }),
    ).toThrow(/not allowlisted/i);
  });

  it("rejects SSRF-style file/http oddities", () => {
    expect(() =>
      resolveApiRewriteUpstream({ API_REWRITE_UPSTREAM: "http://169.254.169.254" }),
    ).toThrow(/not allowlisted/i);
  });

  it("strips trailing slash", () => {
    expect(
      resolveApiRewriteUpstream({
        API_REWRITE_UPSTREAM: `${STAGING_RENDER_UPSTREAM}/`,
      }),
    ).toBe(STAGING_RENDER_UPSTREAM);
  });

  it("allowlist is closed and includes only known staging + local", () => {
    expect(ALLOWED_API_REWRITE_UPSTREAMS).toContain(STAGING_RENDER_UPSTREAM);
    expect(ALLOWED_API_REWRITE_UPSTREAMS.every((u) => u.startsWith("http"))).toBe(true);
    expect(ALLOWED_API_REWRITE_UPSTREAMS).not.toContain("*");
  });
});

describe("apiRewriteRules", () => {
  it("preserves /api path prefix to upstream", () => {
    const rules = apiRewriteRules(STAGING_RENDER_UPSTREAM);
    expect(rules).toEqual([
      {
        source: "/api/:path*",
        destination: `${STAGING_RENDER_UPSTREAM}/api/:path*`,
      },
    ]);
  });

  it("maps healthz and login paths without double prefix", () => {
    const { source, destination } = apiRewriteRules(STAGING_RENDER_UPSTREAM)[0];
    expect(source).toBe("/api/:path*");
    // Next substitutes :path* — destination template must already include /api/
    expect(destination).toBe("https://micronest-medicalos.onrender.com/api/:path*");
    expect(destination).not.toContain("/api/api/");
  });
});

describe("apiNoStoreHeaderRules", () => {
  it("marks all /api responses private no-store", () => {
    const rules = apiNoStoreHeaderRules();
    expect(rules[0].source).toBe("/api/:path*");
    const cc = rules[0].headers.find((h) => h.key === "Cache-Control")?.value ?? "";
    expect(cc).toMatch(/private/i);
    expect(cc).toMatch(/no-store/i);
  });
});

describe("assertAuthCookieHardening", () => {
  const access =
    "hos_access=token.example; Path=/api; HttpOnly; Secure; SameSite=Lax; Max-Age=600";
  const refresh =
    "hos_refresh=sid.secret; Path=/api/v1/auth; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000";
  const logout =
    "hos_access=; Path=/api; HttpOnly; Secure; SameSite=Lax; Max-Age=0";

  it("accepts hardened access cookie", () => {
    expect(assertAuthCookieHardening(access)).toEqual([]);
  });

  it("accepts hardened refresh cookie", () => {
    expect(assertAuthCookieHardening(refresh)).toEqual([]);
  });

  it("accepts logout deletion cookie shape", () => {
    expect(assertAuthCookieHardening(logout)).toEqual([]);
  });

  it("rejects SameSite=None", () => {
    const bad =
      "hos_access=x; Path=/api; HttpOnly; Secure; SameSite=None; Max-Age=600";
    expect(assertAuthCookieHardening(bad).join(" ")).toMatch(/None|Lax/i);
  });

  it("rejects missing HttpOnly", () => {
    const bad = "hos_access=x; Path=/api; Secure; SameSite=Lax";
    expect(assertAuthCookieHardening(bad)).toContain("missing HttpOnly");
  });

  it("rejects Domain attribute (must stay host-only)", () => {
    const bad =
      "hos_access=x; Path=/api; Domain=.vercel.app; HttpOnly; Secure; SameSite=Lax";
    expect(assertAuthCookieHardening(bad).join(" ")).toMatch(/Domain/i);
  });

  it("treats multiple Set-Cookie values independently", () => {
    for (const part of [access, refresh]) {
      expect(assertAuthCookieHardening(part)).toEqual([]);
    }
  });
});
