import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Blocker = { code: string; detail: string };

export function ownerCreds(): { email: string; password: string } | null {
  const email = process.env.PLAYWRIGHT_OWNER_EMAIL;
  const password = process.env.PLAYWRIGHT_OWNER_PASSWORD;
  if (!email || !password) return null;
  return { email, password };
}

/** Fail the suite with an explicit BLOCKED annotation instead of silent skip. */
export function block(testInfo: { annotations: { type: string; description?: string }[] }, reason: Blocker): never {
  testInfo.annotations.push({
    type: "BLOCKED",
    description: `${reason.code}: ${reason.detail}`,
  });
  throw new Error(`BLOCKED: ${reason.code} — ${reason.detail}`);
}

export async function apiHealth(request: APIRequestContext): Promise<boolean> {
  try {
    const res = await request.get(`${API}/api/healthz`);
    return res.ok();
  } catch {
    return false;
  }
}

export async function requireApi(request: APIRequestContext, testInfo: { annotations: { type: string; description?: string }[] }) {
  const up = await apiHealth(request);
  if (!up) {
    block(testInfo, {
      code: "API_UNREACHABLE",
      detail: `API not reachable at ${API}. Start uvicorn against healthcare_os before authenticated journeys.`,
    });
  }
}

export async function requireOwnerCreds(testInfo: { annotations: { type: string; description?: string }[] }) {
  const creds = ownerCreds();
  if (!creds) {
    block(testInfo, {
      code: "MISSING_OWNER_CREDS",
      detail: "Set PLAYWRIGHT_OWNER_EMAIL and PLAYWRIGHT_OWNER_PASSWORD (see scripts/p32_seed_owner.py).",
    });
  }
  return creds;
}

export async function loginViaUi(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  const loginResponse = page.waitForResponse(
    (res) => res.url().includes("/api/v1/auth/login") && res.request().method() === "POST",
    { timeout: 20_000 },
  );
  await page.getByRole("button", { name: "Sign in" }).click();
  const res = await loginResponse;
  if (!res.ok()) {
    throw new Error(`UI login failed: ${res.status()} ${await res.text()}`);
  }
  await expect(page).not.toHaveURL(/\/login$/, { timeout: 20_000 });
  // Ensure session cookie is usable for subsequent client fetches.
  await expect
    .poll(async () => {
      return page.evaluate(async (api) => {
        const r = await fetch(`${api}/api/v1/auth/me`, { credentials: "include" });
        return r.status;
      }, API);
    }, { timeout: 15_000 })
    .toBe(200);
}

export async function loginViaApi(request: APIRequestContext, email: string, password: string) {
  let lastText = "";
  for (let attempt = 0; attempt < 4; attempt++) {
    const res = await request.post(`${API}/api/v1/auth/login`, {
      data: { email, password },
    });
    if (res.ok()) return res.json();
    lastText = await res.text();
    if (res.status() === 401 && /too many attempts/i.test(lastText)) {
      await new Promise((r) => setTimeout(r, 2_000 * (attempt + 1)));
      continue;
    }
    throw new Error(`login failed: ${res.status()} ${lastText}`);
  }
  throw new Error(`login failed after retries: ${lastText}`);
}

export async function signupViaApi(
  request: APIRequestContext,
  opts: { email: string; password: string; display_name: string },
) {
  const res = await request.post(`${API}/api/v1/auth/signup`, {
    data: {
      email: opts.email,
      password: opts.password,
      display_name: opts.display_name,
    },
  });
  if (res.status() !== 202) {
    throw new Error(`signup failed: ${res.status()} ${await res.text()}`);
  }
}

export function uniqueSlug(prefix: string): string {
  const stamp = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 8);
  return `${prefix}-${stamp}-${rand}`.slice(0, 60);
}

export async function capture(page: Page, name: string) {
  await page.screenshot({
    path: `../../docs/ui-ux/screenshots/p32-${name}.png`,
    fullPage: true,
  });
}

/** Capture without embedding invite tokens in the filename or path. */
export async function captureSafe(page: Page, name: string) {
  // Mask query tokens in the address bar area by navigating hash-only if needed — screenshots
  // may still show the URL chrome; prefer pages that do not surface raw tokens in the DOM.
  await capture(page, name);
}
