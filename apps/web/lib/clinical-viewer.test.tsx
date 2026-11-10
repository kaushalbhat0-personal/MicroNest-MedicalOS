import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ClinicalImageViewer } from "@healthcare-os/ui";

const IMG = {
  src: "https://storage.test/signed/viewer?token=ZZZ",
  title: "Image xray (11111111)",
  subtitle: "Image 1 of 2",
  meta: [
    { label: "Type", value: "xray" },
    { label: "Content type", value: "image/png" },
  ],
};

describe("ClinicalImageViewer rendering (D1c read-only contract)", () => {
  it("announces loading accessibly", () => {
    render(<ClinicalImageViewer image={null} status="loading" />);
    expect(screen.getByText("Loading image...")).toBeTruthy();
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
  });

  it("shows the empty state when no authorized image is present", () => {
    render(<ClinicalImageViewer image={null} status="empty" />);
    expect(screen.getByText("No image selected")).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("shows retrieval errors accessibly with a retry action", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(
      <ClinicalImageViewer
        image={null}
        status="error"
        errorMessage="The image could not be loaded. Try again."
        onRetry={onRetry}
      />,
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("renders the authorized image with display metadata and working controls", async () => {
    const user = userEvent.setup();
    render(<ClinicalImageViewer image={IMG} status="ready" />);
    const img = screen.getByRole("img", {
      name: "Image xray (11111111)",
    }) as HTMLImageElement;
    expect(img.getAttribute("src")).toBe(IMG.src);
    expect(img.getAttribute("referrerpolicy")).toBe("no-referrer");
    expect(screen.getByText("Image 1 of 2")).toBeTruthy();
    expect(
      screen.getByText(
        (_, el) =>
          el?.tagName === "LI" && (el.textContent ?? "").includes("xray"),
      ),
    ).toBeTruthy();

    await user.click(screen.getByRole("button", { name: /zoom in/i }));
    expect(screen.getByText("125%")).toBeTruthy();
    await user.click(
      screen.getByRole("button", { name: /reset view/i }),
    );
    expect(screen.getByText("100%")).toBeTruthy();
  });

  it("supports the documented viewer keyboard map on the stage", () => {
    render(<ClinicalImageViewer image={IMG} status="ready" />);
    const stage = screen.getByRole("group", { name: /image stage/i });
    stage.focus();
    fireEvent.keyDown(stage, { key: "+" });
    expect(screen.getByText("125%")).toBeTruthy();
    fireEvent.keyDown(stage, { key: "0" });
    expect(screen.getByText("100%")).toBeTruthy();
  });

  it("steps through a same-encounter collection without touching storage", async () => {
    const user = userEvent.setup();
    const onIndexChange = vi.fn();
    render(
      <ClinicalImageViewer
        image={IMG}
        images={[
          IMG,
          { ...IMG, src: "https://storage.test/signed/other?token=YYY" },
        ]}
        currentIndex={0}
        onIndexChange={onIndexChange}
        status="ready"
      />,
    );
    expect(screen.getAllByText("Image 1 of 2")).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: /next image/i }));
    expect(onIndexChange).toHaveBeenCalledWith(1);
  });

  it("recovers from an expired-URL image load failure via a fresh-grant retry", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(
      <ClinicalImageViewer image={IMG} status="ready" onRetry={onRetry} />,
    );
    const img = screen.getByRole("img");
    fireEvent.error(img);
    expect(await screen.findByText("Image unavailable")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("exposes no download action and constrains the stage", () => {
    render(<ClinicalImageViewer image={IMG} status="ready" />);
    expect(screen.queryByRole("button", { name: /download/i })).toBeNull();
    expect(screen.queryByRole("link", { name: /download/i })).toBeNull();
    const stage = screen.getByRole("group", { name: /image stage/i });
    expect((stage as HTMLElement).style.overflow).toBe("hidden");
    const img = screen.getByRole("img") as HTMLImageElement;
    expect(img.style.maxWidth).toBe("100%");
  });
});
