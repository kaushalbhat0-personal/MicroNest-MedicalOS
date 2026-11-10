import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DocsTab } from "./docs-tab";

vi.mock("@/lib/tenant", () => ({ getSelectedTenant: () => "tenant-1" }));

const IMG1 = {
  id: "11111111-1111-4111-8111-111111111111",
  doc_type: "xray",
  storage_key: "tenant-enc/xray-a.png",
  content_type: "image/png",
  notes: null,
};
const IMG2 = {
  id: "22222222-2222-4222-8222-222222222222",
  doc_type: "photo",
  storage_key: "tenant-enc/photo-b.jpg",
  content_type: "image/jpeg",
  notes: "chair-side",
};
const PDF = {
  id: "33333333-3333-4333-8333-333333333333",
  doc_type: "report",
  storage_key: "tenant-enc/report-c.pdf",
  content_type: "application/pdf",
  notes: "lab report",
};
const UNTYPED = {
  id: "44444444-4444-4434-8444-444444444444",
  doc_type: "xray",
  storage_key: "tenant-enc/legacy.bin",
  content_type: null,
  notes: null,
};

const SIGNED_1 = "https://storage.test/signed/img1?token=AAA111";
const SIGNED_2 = "https://storage.test/signed/img2?token=BBB222";

function grantBody(url: string, contentType: string, documentId: string) {
  return {
    document_id: documentId,
    url,
    expires_in_seconds: 300,
    content_type: contentType,
  };
}

function okJson(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

function stubFetch(
  handler: (url: string) => { status: number; body: unknown },
) {
  const calls: { url: string; init: RequestInit }[] = [];
  const fn = vi.fn(async (url: string, init: RequestInit) => {
    calls.push({ url: String(url), init });
    const r = handler(String(url));
    return okJson(r.body, r.status);
  });
  vi.stubGlobal("fetch", fn);
  return { calls, fn };
}

function accessSuccess(url: string) {
  return stubFetch((raw) => {
    const id = raw.split("/documents/")[1]?.split("/access")[0] ?? "";
    return {
      status: 200,
      body: grantBody(
        url,
        id === IMG2.id ? "image/jpeg" : "image/png",
        id,
      ),
    };
  });
}

beforeEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
});

describe("DocsTab image eligibility", () => {
  it("mints no URL on render and never offers View for non-images", () => {
    const { calls } = stubFetch(() => ({
      status: 200,
      body: grantBody(SIGNED_1, "image/png", IMG1.id),
    }));
    render(
      <DocsTab encounterId="enc-1" docs={[IMG1, PDF, UNTYPED]} onChange={() => {}} />,
    );
    expect(calls).toHaveLength(0);
    expect(
      screen.getByRole("button", { name: /view image xray/i }),
    ).toBeTruthy();
    const pdfRow = screen
      .getByText("tenant-enc/report-c.pdf")
      .closest("tr")!;
    expect(
      within(pdfRow).queryByRole("button", { name: /view image/i }),
    ).toBeNull();
    expect(within(pdfRow).getByText("Not an image")).toBeTruthy();
    const untypedCells = screen.getAllByText("tenant-enc/legacy.bin");
    expect(untypedCells.length).toBeGreaterThan(0);
    const untypedRow = untypedCells[0].closest("tr")!;
    expect(
      within(untypedRow).queryByRole("button", { name: /view image/i }),
    ).toBeNull();
  });

  it("shows an empty state when no eligible images exist", () => {
    stubFetch(() => ({ status: 200, body: {} }));
    render(<DocsTab encounterId="enc-1" docs={[PDF]} onChange={() => {}} />);
    expect(screen.getByText("No eligible images")).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: /view image/i }),
    ).toBeNull();
  });
});

describe("DocsTab authorized viewing", () => {
  it("opens an eligible image: loading announces, then the image renders", async () => {
    const user = userEvent.setup();
    let release!: (value: unknown) => void;
    const gate = new Promise<unknown>((res) => {
      release = res;
    });
    const fn = vi.fn(async () => gate as unknown as Response);
    vi.stubGlobal("fetch", fn);

    render(
      <DocsTab encounterId="enc-1" docs={[IMG1, PDF]} onChange={() => {}} />,
    );
    await user.click(screen.getByRole("button", { name: /view image xray/i }));

    expect(await screen.findByText("Loading image...")).toBeTruthy();
    release(okJson(grantBody(SIGNED_1, "image/png", IMG1.id)));

    const img = (await screen.findByRole("img")) as HTMLImageElement;
    expect(img.getAttribute("src")).toBe(SIGNED_1);
    expect(img.getAttribute("referrerpolicy")).toBe("no-referrer");
    expect(screen.getByText("Image 1 of 1")).toBeTruthy();
    expect(fn).toHaveBeenCalledTimes(1);
    expect(String((fn.mock.calls[0] as unknown as [string, RequestInit])[0])).toContain(
      `/api/v1/tenants/tenant-1/documents/${IMG1.id}/access`,
    );
  });

  it("re-mints a fresh URL when navigating to another image", async () => {
    const user = userEvent.setup();
    const { calls } = accessSuccess(SIGNED_1);
    render(
      <DocsTab encounterId="enc-1" docs={[IMG1, IMG2]} onChange={() => {}} />,
    );

    await user.click(screen.getByRole("button", { name: /view image xray/i }));
    await screen.findByRole("img");
    expect(calls).toHaveLength(1);

    // Second mint returns the second image bytes.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (raw: string) => {
        calls.push({ url: String(raw), init: {} as RequestInit });
        return okJson(grantBody(SIGNED_2, "image/jpeg", IMG2.id));
      }),
    );
    await user.click(screen.getByRole("button", { name: /next image/i }));

    const img = (await screen.findByRole("img")) as HTMLImageElement;
    await waitFor(() =>
      expect(img.getAttribute("src")).toBe(SIGNED_2),
    );
    expect(screen.getByText("Image 2 of 2")).toBeTruthy();
    expect(calls).toHaveLength(2);
    expect(calls[1].url).toContain(IMG2.id);
  });

  it("shows retrieval errors accessibly and retries with a fresh grant", async () => {
    const user = userEvent.setup();
    let attempt = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        attempt += 1;
        if (attempt === 1) {
          return okJson(
            {
              type: "unavailable",
              title: "service unavailable",
              status: 503,
              detail: "document storage is unavailable",
            },
            503,
          );
        }
        return okJson(grantBody(SIGNED_1, "image/png", IMG1.id));
      }),
    );
    render(<DocsTab encounterId="enc-1" docs={[IMG1]} onChange={() => {}} />);

    await user.click(screen.getByRole("button", { name: /view image xray/i }));
    expect(await screen.findByText(/temporarily unavailable/i)).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();

    await user.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByRole("img")).toBeTruthy();
    expect(attempt).toBe(2);
  });

  it("maps a 403 to the permission summary and shows no image", async () => {
    const user = userEvent.setup();
    stubFetch(() => ({
      status: 403,
      body: {
        type: "forbidden",
        title: "forbidden",
        status: 403,
        detail: "missing DENTAL_READ",
      },
    }));
    render(<DocsTab encounterId="enc-1" docs={[IMG1]} onChange={() => {}} />);
    await user.click(screen.getByRole("button", { name: /view image xray/i }));
    expect(await screen.findByText(/permission/i)).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("closing returns to the document list without further requests", async () => {
    const user = userEvent.setup();
    const { calls, fn } = accessSuccess(SIGNED_1);
    render(<DocsTab encounterId="enc-1" docs={[IMG1, PDF]} onChange={() => {}} />);

    await user.click(screen.getByRole("button", { name: /view image xray/i }));
    await screen.findByRole("img");
    expect(calls).toHaveLength(1);

    await user.click(
      screen.getByRole("button", { name: /back to document list/i }),
    );
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.getByText("tenant-enc/report-c.pdf")).toBeTruthy();
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("supports keyboard open and focuses the back control", async () => {
    const user = userEvent.setup();
    accessSuccess(SIGNED_1);
    render(<DocsTab encounterId="enc-1" docs={[IMG1]} onChange={() => {}} />);

    const view = screen.getByRole("button", { name: /view image xray/i });
    view.focus();
    await user.keyboard("{Enter}");
    await screen.findByRole("img");
    expect(document.activeElement?.id).toBe("docs-viewer-back");
  });

  it("viewer stage keyboard controls remain functional inline", async () => {
    const user = userEvent.setup();
    accessSuccess(SIGNED_1);
    render(<DocsTab encounterId="enc-1" docs={[IMG1]} onChange={() => {}} />);
    await user.click(screen.getByRole("button", { name: /view image xray/i }));
    await screen.findByRole("img");

    const stage = screen.getByRole("group", { name: /image stage/i });
    stage.focus();
    fireEvent.keyDown(stage, { key: "+" });
    expect(await screen.findByText("125%")).toBeTruthy();
  });
});

describe("DocsTab signed-URL lifecycle and security", () => {
  it("sends only the opaque id and never persists, routes, or logs the URL", async () => {
    const user = userEvent.setup();
    const log = vi.spyOn(console, "log");
    const warn = vi.spyOn(console, "warn");
    const errSpy = vi.spyOn(console, "error");
    const { calls } = accessSuccess(SIGNED_1);
    render(<DocsTab encounterId="enc-1" docs={[IMG1]} onChange={() => {}} />);

    await user.click(screen.getByRole("button", { name: /view image xray/i }));
    const img = (await screen.findByRole("img")) as HTMLImageElement;
    expect(img.getAttribute("src")).toBe(SIGNED_1);

    expect(calls).toHaveLength(1);
    expect(calls[0].init.body).toBe("{}");
    expect(String(calls[0].init.body)).not.toContain("storage");
    expect(window.location.href).not.toContain("signed");
    expect(window.location.href).not.toContain(SIGNED_1);
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    for (const spy of [log, warn, errSpy]) {
      for (const args of spy.mock.calls) {
        expect(args.map(String).join(" ")).not.toContain(SIGNED_1);
      }
    }
    log.mockRestore();
    warn.mockRestore();
    errSpy.mockRestore();
  });

  it("keeps storage keys out of viewer props and offers no download", async () => {
    const user = userEvent.setup();
    accessSuccess(SIGNED_1);
    render(<DocsTab encounterId="enc-1" docs={[IMG1]} onChange={() => {}} />);
    await user.click(screen.getByRole("button", { name: /view image xray/i }));
    await screen.findByRole("img");

    const viewer = screen.getByLabelText("Clinical image viewer");
    expect(
      within(viewer).queryByText("tenant-enc/xray-a.png"),
    ).toBeNull();
    expect(
      screen.queryByRole("button", { name: /download/i }),
    ).toBeNull();
    expect(screen.queryByRole("link", { name: /download/i })).toBeNull();
  });

  it("viewer stage constrains rendering without horizontal overflow", async () => {
    const user = userEvent.setup();
    accessSuccess(SIGNED_1);
    render(<DocsTab encounterId="enc-1" docs={[IMG1]} onChange={() => {}} />);
    await user.click(screen.getByRole("button", { name: /view image xray/i }));
    const img = (await screen.findByRole("img")) as HTMLImageElement;
    const stage = screen.getByRole("group", { name: /image stage/i });
    expect((stage as HTMLElement).style.overflow).toBe("hidden");
    expect(img.style.maxWidth).toBe("100%");
  });
});
