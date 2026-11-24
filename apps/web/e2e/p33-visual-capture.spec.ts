import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { API, loginViaUi, requireApi } from "./helpers";

/**
 * P3.3 visual capture for dentist/eye walkthrough guides.
 * Uses synthetic P33 DEMO owner only. No professional-session claims.
 */
const EMAIL = process.env.P33_DEMO_OWNER_EMAIL ?? "p33.demo.owner@example.com";
const PASSWORD = process.env.P33_DEMO_OWNER_PASSWORD ?? "P33-Demo-Owner-12345";
const FIXTURE = path.resolve(__dirname, "../../../docs/ui-ux/screenshots/p33-demo-fixture.json");

test.describe("P3.3 visual capture", () => {
  test.beforeEach(async ({ request }, testInfo) => {
    await requireApi(request, testInfo);
    test.skip(testInfo.project.name !== "desktop-1280", "Capture once at desktop-1280");
  });

  test("capture clinic and dental surfaces", async ({ page }, testInfo) => {
    test.setTimeout(120_000);
    const fixture = JSON.parse(fs.readFileSync(FIXTURE, "utf8")) as {
      patient_id: string;
      encounter_id?: string | null;
      plan_id?: string | null;
    };

    await loginViaUi(page, EMAIL, PASSWORD);

    const shots: Array<[string, string, RegExp]> = [
      ["/", "dashboard", /Clinic dashboard|Welcome|Operations/i],
      ["/onboarding", "onboarding", /Clinic setup/i],
      ["/patients", "patients", /Patients/i],
      [`/patients/${fixture.patient_id}`, "patient-360", /Patient|P33 DEMO/i],
      ["/schedule", "schedule", /Schedule|Appointment/i],
      ["/reception", "reception", /Reception/i],
      ["/encounters", "encounters", /Consultation|Encounter/i],
      ["/dental/plans", "dental-plans", /Treatment|Dental|Plan/i],
      ["/billing/invoices", "billing", /Billing|Invoice/i],
      ["/billing/estimates", "estimates", /Estimate/i],
      ["/follow-ups", "follow-ups", /Follow-up/i],
      ["/portal", "portal-redirect-or-home", /./],
    ];

    async function settleAndShot(route: string, name: string, ready: RegExp) {
      await page.goto(route);
      await expect(page.getByText(/Loading [^.]+\.\.\./i)).toHaveCount(0, { timeout: 20_000 }).catch(() => undefined);
      await expect(page.locator("body")).toContainText(ready, { timeout: 20_000 });
      await page.screenshot({
        path: `../../docs/ui-ux/screenshots/p33-${name}.png`,
        fullPage: true,
      });
    }

    for (const [route, name, heading] of shots) {
      await settleAndShot(route, name, heading);
    }

    if (fixture.encounter_id) {
      await page.goto(`/encounters/${fixture.encounter_id}`);
      await expect(page.getByText(/Loading [^.]+\.\.\./i)).toHaveCount(0, { timeout: 20_000 }).catch(() => undefined);
      await expect(page.getByText(/P33 DEMO Patient/i)).toBeVisible({ timeout: 20_000 });
      await page.screenshot({
        path: `../../docs/ui-ux/screenshots/p33-encounter-notes.png`,
        fullPage: true,
      });
      const dentalTab = page.getByRole("tab", { name: /^Dental$/i }).or(page.getByRole("button", { name: /^Dental$/i }));
      if (await dentalTab.first().isVisible().catch(() => false)) {
        await dentalTab.first().click();
      } else {
        await page.getByText(/^Dental$/i).first().click();
      }
      await expect(page.locator("body")).toContainText(/Tooth|Odontogram|Finding|FDI|chart/i, {
        timeout: 15_000,
      });
      await page.screenshot({
        path: `../../docs/ui-ux/screenshots/p33-dental-chart.png`,
        fullPage: true,
      });
    }

    // Mobile spot-check of patients
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/patients");
    await expect(page.getByRole("heading", { name: /Patients/i })).toBeVisible();
    await page.screenshot({
      path: `../../docs/ui-ux/screenshots/p33-mobile-patients.png`,
      fullPage: true,
    });
  });
});
