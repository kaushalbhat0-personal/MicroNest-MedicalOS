import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";
import {
  API,
  capture,
  loginViaApi,
  loginViaUi,
  requireApi,
  signupViaApi,
  uniqueSlug,
} from "./helpers";

const REPO_ROOT = path.resolve(__dirname, "../../..");
const PYTHON = path.resolve(REPO_ROOT, ".venv/Scripts/python.exe");

function setUserPassword(email: string, password: string) {
  execFileSync(
    PYTHON,
    [path.join(REPO_ROOT, "scripts/p32_set_user_password.py"), "--email", email, "--password", password],
    { cwd: REPO_ROOT, stdio: ["ignore", "pipe", "pipe"], env: process.env },
  );
}

async function createWorkspace(
  request: import("@playwright/test").APIRequestContext,
  opts: { clinic: string; slug: string; practitioner: string },
) {
  const idem = crypto.randomUUID();
  const body = {
    clinic_name: opts.clinic,
    slug: opts.slug,
    location_name: "Main Clinic",
    timezone: "Asia/Kolkata",
    practitioner_display_name: opts.practitioner,
    specialty_codes: ["dental"],
  };
  const ws = await request.post(`${API}/api/v1/workspaces`, {
    headers: { "Idempotency-Key": idem },
    data: body,
  });
  expect(ws.ok(), await ws.text()).toBeTruthy();
  const workspace = await ws.json();

  const again = await request.post(`${API}/api/v1/workspaces`, {
    headers: { "Idempotency-Key": idem },
    data: body,
  });
  expect(again.ok(), await again.text()).toBeTruthy();
  const dup = await again.json();
  expect(dup.tenant.id).toBe(workspace.tenant.id);

  return workspace as {
    tenant: { id: string; name: string; slug: string };
    practitioner: { id: string; display_name: string };
  };
}

async function registerPatient(
  request: import("@playwright/test").APIRequestContext,
  tenantId: string,
  displayName: string,
  phone: string,
) {
  const res = await request.post(`${API}/api/v1/tenants/${tenantId}/patients`, {
    headers: { "X-Tenant": tenantId },
    data: { display_name: displayName, phone },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  const patient = await res.json();
  return { id: patient.id as string, ...patient };
}

test.describe("P3.2 owner workspace journey", () => {
  test.describe.configure({ mode: "serial" });
  test.beforeEach(async ({ request }, testInfo) => {
    await requireApi(request, testInfo);
  });

  test("owner creates workspace, approves practitioner, opens clinic screens", async ({
    page,
    request,
  }, testInfo) => {
    const stamp = Date.now().toString(36);
    const email = `p32.owner.${testInfo.project.name}.${stamp}@example.com`;
    const password = "P32-Owner-Pass-12345";
    const slug = uniqueSlug(`p32-${testInfo.project.name.slice(0, 8)}`);
    const clinicName = `P32 Clinic ${stamp}`;

    await signupViaApi(request, { email, password, display_name: `P32 Owner ${stamp}` });
    await loginViaUi(page, email, password);

    await page.goto("/onboarding");
    await expect(page.getByRole("heading", { name: /Clinic setup/i })).toBeVisible();
    await capture(page, `${testInfo.project.name}-onboarding`);

    await page.getByLabel(/Clinic name/i).fill(clinicName);
    await page.getByLabel(/Workspace URL slug/i).fill(slug);
    await page.getByLabel(/Primary location name/i).fill("Main Clinic");
    await page.getByLabel(/Primary practitioner display name/i).fill(`Dr P32 ${stamp}`);
    await page.getByRole("button", { name: /Create workspace/i }).click();

    await expect(page.getByRole("heading", { name: /Clinic created/i })).toBeVisible({
      timeout: 25_000,
    });
    await expect(page.getByText(clinicName)).toBeVisible();
    await capture(page, `${testInfo.project.name}-workspace-created`);

    await loginViaApi(request, email, password);
    const me = await (await request.get(`${API}/api/v1/auth/me`)).json();
    expect(me.tenants?.some((t: { slug: string }) => t.slug === slug)).toBeTruthy();

    await page.getByRole("button", { name: /Continue to practitioner approval/i }).click();
    await expect(page.getByText(/Practitioner verification/i)).toBeVisible();
    await expect(page.getByText(/pending/i).first()).toBeVisible({ timeout: 15_000 });
    await capture(page, `${testInfo.project.name}-practitioner-pending`);

    await page.getByRole("button", { name: /Approve practitioner/i }).first().click();
    await expect(page.getByText(/approved/i).first()).toBeVisible({ timeout: 15_000 });
    await capture(page, `${testInfo.project.name}-practitioner-approved`);

    await page.getByRole("button", { name: /^Continue$/i }).click();
    await page.getByRole("button", { name: /Continue to dashboard|Skip for now/i }).first().click();
    await page.getByRole("button", { name: /Go to dashboard/i }).click();
    await expect(page.getByRole("heading", { name: /Clinic dashboard|Welcome/i })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(/Loading workspace/i)).toHaveCount(0, { timeout: 15_000 });
    await capture(page, `${testInfo.project.name}-dashboard`);

    for (const [pathName, shot, heading] of [
      ["/patients", "patients", /Patients|Patient/i],
      ["/schedule", "schedule", /Schedule|Appointment|Calendar/i],
      ["/reception", "reception", /Reception/i],
    ] as const) {
      await page.goto(pathName);
      await expect(page.getByRole("heading", { name: heading }).first()).toBeVisible({
        timeout: 15_000,
      });
      await capture(page, `${testInfo.project.name}-${shot}`);
    }
  });
});

test.describe("P3.2 staff invitation + portal + isolation", () => {
  test.beforeEach(async ({ request }, testInfo) => {
    await requireApi(request, testInfo);
    test.skip(
      testInfo.project.name !== "desktop-1280",
      "Run invitation/portal/isolation once on desktop-1280",
    );
  });

  test("staff invitation accept and rejection paths", async ({ page, request, browser }, testInfo) => {
    test.setTimeout(120_000);
    const stamp = Date.now().toString(36);
    const ownerEmail = `p32.invowner.${stamp}@example.com`;
    const ownerPass = "P32-Owner-Pass-12345";
    const inviteEmail = `p32.invitee.${stamp}@example.com`;
    const invitePass = "P32-Invitee-Pass-12345";
    const slug = uniqueSlug("p32-inv");

    await signupViaApi(request, {
      email: ownerEmail,
      password: ownerPass,
      display_name: `Inv Owner ${stamp}`,
    });
    await loginViaApi(request, ownerEmail, ownerPass);
    const workspace = await createWorkspace(request, {
      clinic: `Invite Clinic ${stamp}`,
      slug,
      practitioner: `Dr Inv ${stamp}`,
    });
    const tenantId = workspace.tenant.id;

    const inviteRes = await request.post(`${API}/api/v1/tenants/${tenantId}/invites`, {
      headers: { "X-Tenant": tenantId },
      data: { email: inviteEmail, role: "receptionist", ttl_days: 7 },
    });
    expect(inviteRes.ok(), await inviteRes.text()).toBeTruthy();
    const invite = await inviteRes.json();
    expect(invite.token).toBeTruthy();

    await loginViaUi(page, ownerEmail, ownerPass);
    await page.goto("/staff");
    await expect(page.getByRole("heading", { name: /Staff|Team/i }).first()).toBeVisible({
      timeout: 15_000,
    });
    await capture(page, `${testInfo.project.name}-staff-invite`);

    const invitee = await browser.newContext();
    const inviteePage = await invitee.newPage();
    await inviteePage.goto(`/invite?token=${encodeURIComponent(invite.token)}`);
    await expect(inviteePage.getByRole("heading", { name: /Accept clinic invitation/i })).toBeVisible();
    await inviteePage.locator("#name").fill(`Invitee ${stamp}`);
    await inviteePage.locator("#password").fill(invitePass);
    await inviteePage.getByRole("button", { name: /Accept invitation/i }).click();
    await expect(inviteePage).not.toHaveURL(/\/invite/, { timeout: 25_000 });
    // Capture only after redirect so the raw token is not in docs screenshots.
    await capture(inviteePage, `${testInfo.project.name}-invite-accepted`);
    await invitee.close();

    // Invalid token (anonymous context — no session; do not screenshot tokenized URL)
    const anonInvite = await browser.newContext();
    const anonPage = await anonInvite.newPage();
    await anonPage.goto("/invite?token=not-a-real-token");
    await anonPage.locator("#name").fill("Nobody");
    await anonPage.locator("#password").fill(invitePass);
    await anonPage.getByRole("button", { name: /Accept invitation/i }).click();
    await expect(anonPage.getByText(/invalid or expired/i)).toBeVisible({ timeout: 15_000 });

    // Repeated acceptance of already-used token
    await anonPage.goto(`/invite?token=${encodeURIComponent(invite.token)}`);
    await anonPage.locator("#name").fill(`Invitee ${stamp}`);
    await anonPage.locator("#password").fill(invitePass);
    await anonPage.getByRole("button", { name: /Accept invitation/i }).click();
    await expect(anonPage.getByText(/invalid or expired/i)).toBeVisible({ timeout: 15_000 });
    await anonInvite.close();

    // Wrong authenticated account
    const wrongEmail = `p32.wrong.${stamp}@example.com`;
    await signupViaApi(request, {
      email: wrongEmail,
      password: ownerPass,
      display_name: "Wrong Account",
    });
    const invite2Res = await request.post(`${API}/api/v1/tenants/${tenantId}/invites`, {
      headers: { "X-Tenant": tenantId },
      data: { email: `p32.other.${stamp}@example.com`, role: "receptionist", ttl_days: 7 },
    });
    expect(invite2Res.ok(), await invite2Res.text()).toBeTruthy();
    const invite2 = await invite2Res.json();

    const wrong = await browser.newContext();
    const wrongPage = await wrong.newPage();
    await loginViaUi(wrongPage, wrongEmail, ownerPass);
    await wrongPage.goto(`/invite?token=${encodeURIComponent(invite2.token)}`);
    await wrongPage.getByRole("button", { name: /Join workspace/i }).click();
    await expect(
      wrongPage.getByText(/invitation email does not match authenticated user/i),
    ).toBeVisible({ timeout: 15_000 });
    await wrong.close();
  });

  test("patient portal enrollment and isolation controls", async ({ page, request, browser }, testInfo) => {
    const stamp = Date.now().toString(36);
    const pass = "P32-Owner-Pass-12345";
    const patientPass = "P32-Patient-Pass-12345";

    // Clinic A
    const ownerA = `p32.porta.${stamp}@example.com`;
    await signupViaApi(request, { email: ownerA, password: pass, display_name: "Portal A" });
    await loginViaApi(request, ownerA, pass);
    const wsA = await createWorkspace(request, {
      clinic: `Portal A ${stamp}`,
      slug: uniqueSlug("p32-pa"),
      practitioner: "Dr Portal A",
    });
    const tenantA = wsA.tenant.id;
    await request.post(`${API}/api/v1/tenants/${tenantA}/verification`, {
      headers: { "X-Tenant": tenantA },
      data: { practitioner_id: wsA.practitioner.id, status: "approved" },
    });
    const patientA = await registerPatient(request, tenantA, `Patient A ${stamp}`, "+919911110001");

    // Clinic B
    const ownerB = `p32.portb.${stamp}@example.com`;
    await signupViaApi(request, { email: ownerB, password: pass, display_name: "Portal B" });
    const ctxB = await browser.newContext();
    await loginViaApi(ctxB.request, ownerB, pass);
    const wsB = await createWorkspace(ctxB.request, {
      clinic: `Portal B ${stamp}`,
      slug: uniqueSlug("p32-pb"),
      practitioner: "Dr Portal B",
    });
    const tenantB = wsB.tenant.id;
    const patientB = await registerPatient(
      ctxB.request,
      tenantB,
      `Patient B ${stamp}`,
      "+919922220002",
    );

    // Cross-tenant patient read denied
    const cross = await request.get(`${API}/api/v1/tenants/${tenantA}/patients/${patientB.id}`, {
      headers: { "X-Tenant": tenantA },
    });
    expect([403, 404]).toContain(cross.status());

    // Cannot use foreign tenant header
    const foreign = await request.get(`${API}/api/v1/tenants/${tenantB}`, {
      headers: { "X-Tenant": tenantB },
    });
    expect([401, 403, 404]).toContain(foreign.status());

    // Enroll portal patient A
    const portalEmail = `p32.patient.${stamp}@example.com`;
    const enroll = await request.post(`${API}/api/v1/tenants/${tenantA}/portal-links`, {
      headers: { "X-Tenant": tenantA },
      data: {
        email: portalEmail,
        patient_id: patientA.id,
        display_name: `Patient A ${stamp}`,
      },
    });
    expect(enroll.ok(), await enroll.text()).toBeTruthy();

    await loginViaUi(page, ownerA, pass);
    await page.goto(`/patients/${patientA.id}`);
    await expect(page.getByText(/Patient|Chart|Details|portal/i).first()).toBeVisible({
      timeout: 15_000,
    });
    await capture(page, `${testInfo.project.name}-patient-360`);
    await capture(page, `${testInfo.project.name}-patient-enroll`);

    setUserPassword(portalEmail, patientPass);

    const portalCtx = await browser.newContext();
    const portalPage = await portalCtx.newPage();
    await loginViaUi(portalPage, portalEmail, patientPass);
    await portalPage.goto("/portal");
    await expect(portalPage.getByText(/portal|appointment|record|visit/i).first()).toBeVisible({
      timeout: 15_000,
    });
    await capture(portalPage, `${testInfo.project.name}-patient-portal`);

    // Patient must not reach clinic administration meaningfully
    await portalPage.goto("/admin");
    const adminText = await portalPage.locator("body").innerText();
    // Either redirected away or API-backed actions fail — no approve success path
    expect(adminText).not.toMatch(/Approve practitioner/i);

    // Unauthenticated portal
    const anon = await browser.newContext();
    const anonPage = await anon.newPage();
    await anonPage.goto("/portal");
    await expect(anonPage).toHaveURL(/\/login/);
    await capture(anonPage, `${testInfo.project.name}-portal-unauth`);
    await anon.close();

    // Receptionist cannot approve practitioners
    const recvEmail = `p32.recv.${stamp}@example.com`;
    const inviteRes = await request.post(`${API}/api/v1/tenants/${tenantA}/invites`, {
      headers: { "X-Tenant": tenantA },
      data: { email: recvEmail, role: "receptionist", ttl_days: 7 },
    });
    expect(inviteRes.ok(), await inviteRes.text()).toBeTruthy();
    const invite = await inviteRes.json();
    const recvCtx = await browser.newContext();
    const accept = await recvCtx.request.post(`${API}/api/v1/invites/accept`, {
      data: { token: invite.token, display_name: "Recv", password: pass },
    });
    expect(accept.ok(), await accept.text()).toBeTruthy();
    const denied = await recvCtx.request.post(`${API}/api/v1/tenants/${tenantA}/verification`, {
      headers: { "X-Tenant": tenantA },
      data: { practitioner_id: wsA.practitioner.id, status: "approved" },
    });
    expect([401, 403]).toContain(denied.status());

    await portalCtx.close();
    await recvCtx.close();
    await ctxB.close();
  });
});
