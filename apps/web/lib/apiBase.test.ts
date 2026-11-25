import { describe, expect, it } from "vitest";
import { apiUrl, resolveApiBase } from "./apiBase";

describe("resolveApiBase", () => {
  it("defaults to same-origin relative when unset", () => {
    expect(resolveApiBase({})).toBe("");
  });

  it("treats empty string as same-origin relative", () => {
    expect(resolveApiBase({ NEXT_PUBLIC_API_URL: "" })).toBe("");
    expect(resolveApiBase({ NEXT_PUBLIC_API_URL: "   " })).toBe("");
  });

  it("strips trailing slash from absolute override", () => {
    expect(resolveApiBase({ NEXT_PUBLIC_API_URL: "http://localhost:8000/" })).toBe(
      "http://localhost:8000",
    );
  });

  it("preserves staging Render override when explicitly set", () => {
    expect(
      resolveApiBase({
        NEXT_PUBLIC_API_URL: "https://micronest-medicalos.onrender.com",
      }),
    ).toBe("https://micronest-medicalos.onrender.com");
  });
});

describe("apiUrl", () => {
  it("uses relative /api paths for same-origin", () => {
    expect(apiUrl("/api/v1/auth/login", "")).toBe("/api/v1/auth/login");
    expect(apiUrl("/api/healthz", "")).toBe("/api/healthz");
  });

  it("does not double /api when base is absolute origin", () => {
    expect(apiUrl("/api/v1/auth/me", "http://localhost:8000")).toBe(
      "http://localhost:8000/api/v1/auth/me",
    );
  });

  it("normalizes path without leading slash", () => {
    expect(apiUrl("api/v1/auth/login", "")).toBe("/api/v1/auth/login");
  });

  it("preserves query strings in the path", () => {
    expect(apiUrl("/api/v1/tenants/t1/patients?limit=10", "")).toBe(
      "/api/v1/tenants/t1/patients?limit=10",
    );
  });
});
