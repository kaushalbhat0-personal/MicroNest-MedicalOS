/** Check whether login Set-Cookie is present but rejected cross-site. */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PREVIEW = "https://micro-nest-medical-8eeq5wwe6-kaushal-bhats-projects.vercel.app";
const API = "https://micronest-medicalos.onrender.com";
const sec = JSON.parse(fs.readFileSync(path.join(ROOT, ".vercel/p37d_protection_bypass.json"), "utf8")).secret;
const st = Object.fromEntries(
  fs
    .readFileSync(path.join(ROOT, ".env.p37c.staging"), "utf8")
    .split(/\r?\n/)
    .filter((l) => l && !l.startsWith("#") && l.includes("="))
    .map((l) => {
      const i = l.indexOf("=");
      return [l.slice(0, i).trim(), l.slice(i + 1).trim()];
    }),
);

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
await context.route("**/*", async (route) => {
  if (route.request().url().includes("vercel.app")) {
    await route.continue({
      headers: {
        ...route.request().headers(),
        "x-vercel-protection-bypass": sec,
        "x-vercel-set-bypass-cookie": "true",
      },
    });
    return;
  }
  await route.continue();
});
const page = await context.newPage();
await page.goto(`${PREVIEW}/login?x-vercel-protection-bypass=${sec}`, { waitUntil: "networkidle" });

const loginRespPromise = page.waitForResponse(
  (r) => r.url().includes("/api/v1/auth/login") && r.request().method() === "POST",
);
await page.getByLabel("Email").fill(st.P37C_OWNER_A_EMAIL);
await page.getByLabel("Password").fill(st.P37C_OWNER_A_PASSWORD);
await page.getByRole("button", { name: "Sign in" }).click();
const loginResp = await loginRespPromise;
const headers = await loginResp.headersArray();
const setCookies = headers.filter((h) => h.name.toLowerCase() === "set-cookie");
console.log("login_status", loginResp.status());
console.log("set_cookie_count", setCookies.length);
for (const c of setCookies) {
  const v = c.value;
  const name = v.split("=")[0];
  const attrs = {
    name,
    httponly: /httponly/i.test(v),
    secure: /;\s*secure/i.test(v),
    samesite: (/samesite=([^;]+)/i.exec(v) || [])[1] || null,
    path: (/path=([^;]+)/i.exec(v) || [])[1] || null,
    // never print token value
  };
  console.log("cookie_attrs", JSON.stringify(attrs));
}
const stored = await context.cookies(API);
console.log(
  "stored_for_api",
  stored.map((c) => ({ name: c.name, sameSite: c.sameSite, secure: c.secure, domain: c.domain })),
);
const me = await page.evaluate(async (api) => {
  const r = await fetch(`${api}/api/v1/auth/me`, { credentials: "include" });
  return r.status;
}, API);
console.log("me_status", me);
await browser.close();
