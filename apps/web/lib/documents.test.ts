import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  documentAccessErrorMessage,
  isEligibleImageDoc,
  requestDocumentAccess,
} from "./documents";

const TENANT = "tenant-1";
const DOC_ID = "11111111-2222-4333-8444-555555555555";

function okJson(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe("isEligibleImageDoc", () => {
  it("accepts image/* content types", () => {
    expect(isEligibleImageDoc({ content_type: "image/png" })).toBe(true);
    expect(isEligibleImageDoc({ content_type: "image/jpeg" })).toBe(true);
    expect(isEligibleImageDoc({ content_type: "image/dicom" })).toBe(true);
  });

  it("accepts case/whitespace variants the server also accepts", () => {
    expect(isEligibleImageDoc({ content_type: "IMAGE/PNG" })).toBe(true);
    expect(isEligibleImageDoc({ content_type: "  image/png  " })).toBe(true);
  });

  it("rejects non-image, missing, and untyped documents", () => {
    expect(isEligibleImageDoc({ content_type: "application/pdf" })).toBe(false);
    expect(isEligibleImageDoc({ content_type: "text/html" })).toBe(false);
    expect(isEligibleImageDoc({ content_type: null })).toBe(false);
    expect(isEligibleImageDoc({})).toBe(false);
    expect(isEligibleImageDoc({ content_type: "" })).toBe(false);
    expect(isEligibleImageDoc({ content_type: "image" })).toBe(false);
  });

  it("never consults doc_type: an xray-typed PDF is ineligible", () => {
    expect(
      isEligibleImageDoc({
        content_type: "application/pdf",
        doc_type: "xray",
      } as unknown as { content_type: string | null }),
    ).toBe(false);
    expect(
      isEligibleImageDoc({
        content_type: "image/png",
        doc_type: "report",
      } as unknown as { content_type: string | null }),
    ).toBe(true);
  });
});

describe("requestDocumentAccess", () => {
  it("posts to the D1b route with tenant and document identifiers", async () => {
    const fetchMock = vi.fn(async () =>
      okJson({
        document_id: DOC_ID,
        url: "https://storage.test/signed?token=abc",
        expires_in_seconds: 300,
        content_type: "image/png",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const out = await requestDocumentAccess(TENANT, DOC_ID);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(String(url)).toContain(
      `/api/v1/tenants/${TENANT}/documents/${DOC_ID}/access`,
    );
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["X-Tenant"]).toBe(TENANT);
    expect(init.credentials).toBe("include");
    expect(out.document_id).toBe(DOC_ID);
    expect(out.url).toBe("https://storage.test/signed?token=abc");
    expect(out.expires_in_seconds).toBe(300);
    expect(out.content_type).toBe("image/png");
  });

  it("sends an empty body: no storage key, no client-controlled expiry", async () => {
    const fetchMock = vi.fn(async () =>
      okJson({
        document_id: DOC_ID,
        url: "https://storage.test/signed?token=abc",
        expires_in_seconds: 300,
        content_type: "image/png",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await requestDocumentAccess(TENANT, DOC_ID);

    const [calledUrl, init] =
      fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.body).toBe("{}");
    expect(String(init.body)).not.toContain("storage");
    expect(String(init.body)).not.toContain("expir");
    expect(String(calledUrl)).not.toContain("expir");
  });

  it("propagates the HTTP status for the caller to map", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        okJson({ detail: "forbidden", status: 403, title: "x", type: "y" }, 403),
      ),
    );
    const err = await requestDocumentAccess(TENANT, DOC_ID).catch((e) => e);
    expect((err as Error & { status?: number }).status).toBe(403);
  });

  it("requires tenant and document identifiers without calling fetch", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    expect(() => requestDocumentAccess("", DOC_ID)).toThrow("tenant is required");
    expect(() => requestDocumentAccess(TENANT, "")).toThrow("document is required");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("documentAccessErrorMessage", () => {
  it("maps statuses to non-PHI summaries", () => {
    expect(documentAccessErrorMessage(403)).toContain("permission");
    expect(documentAccessErrorMessage(404)).toContain("no longer available");
    expect(documentAccessErrorMessage(422)).toContain("not an eligible image");
    expect(documentAccessErrorMessage(503)).toContain("temporarily unavailable");
    expect(documentAccessErrorMessage(undefined)).toContain("Try again");
  });

  it("never includes URLs or credential material", () => {
    for (const s of [403, 404, 422, 503, undefined]) {
      const m = documentAccessErrorMessage(s);
      expect(m).not.toContain("http");
      expect(m).not.toContain("token");
      expect(m).not.toContain("key/");
    }
  });
});
