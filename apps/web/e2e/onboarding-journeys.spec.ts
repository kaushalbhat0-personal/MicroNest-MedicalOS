import { test, expect } from "@playwright/test";
import { capture, loginViaUi, requireApi, requireOwnerCreds } from "./helpers";

/**
 * P3.1-C public pages + thin seeded-owner smoke.
 * Full authenticated journeys live in authenticated-journeys.spec.ts.
 * Missing API/creds fail with BLOCKED (not silent skip).
 */
test.describe("P3.1-C / P3.2 public onboarding pages", () => {
  test("invite and password-reset pages render", async ({ page }, testInfo) => {
    await page.goto("/invite");
    await expect(page.getByRole("heading", { name: /Accept clinic invitation/i })).toBeVisible({
      timeout: 15_000,
    });
    await capture(page, `${testInfo.project.name}-invite-public`);

    await page.goto("/password-reset");
    await expect(page.getByRole("heading", { name: /Reset password/i })).toBeVisible({
      timeout: 15_000,
    });
    await capture(page, `${testInfo.project.name}-password-reset-public`);
  });

  test("login page links to invite and password reset", async ({ page }, testInfo) => {
    await page.goto("/login");
    await expect(page.getByRole("link", { name: /Accept invitation/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /Reset password/i })).toBeVisible();
    await capture(page, `${testInfo.project.name}-login`);
  });
});

test.describe("P3.2 seeded owner smoke", () => {
  test.beforeEach(async ({ request }, testInfo) => {
    await requireApi(request, testInfo);
  });

  test("owner can open setup, admin, dashboard", async ({ page }, testInfo) => {
    const creds = await requireOwnerCreds(testInfo);
    await loginViaUi(page, creds.email, creds.password);
    await page.goto("/onboarding");
    await expect(page.getByRole("heading", { name: /Clinic setup/i })).toBeVisible();
    await capture(page, `${testInfo.project.name}-onboarding-smoke`);

    await page.goto("/admin");
    await expect(page.locator("body")).toContainText(/Practitioner|Admin|Clinic|workspace|setup/i);
    await capture(page, `${testInfo.project.name}-admin-smoke`);

    await page.goto("/");
    await expect(page.getByRole("heading", { name: /Clinic dashboard|Welcome|Clinic setup/i })).toBeVisible();
    await capture(page, `${testInfo.project.name}-dashboard-smoke`);
  });
});
