/** Capture preflight status/headers via Playwright route. */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PREVIEW = "https://micro-nest-medical-8eeq5wwe6-kaushal-bhats-projects.vercel.app";
const API = "https://micronest-medicalos.onrender.com";
const sec = JSON.parse(
  fs.readFileSync(path.join(ROOT, ".vercel", "p37d_protection_bypass.json"), "utf8"),
).secret;

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  extraHTTPHeaders: {
    "x-vercel-protection-bypass": sec,
    "x-vercel-set-bypass-cookie": "true",
  },
});
const page = await context.newPage();

const preflights = [];
page.on("response", async (res) => {
  if (res.request().method() === "OPTIONS" && res.url().includes("/auth/login")) {
    const headers = res.headers();
    preflights.push({
      status: res.status(),
      url: res.url(),
      acao: headers["access-control-allow-origin"] || null,
      acac: headers["access-control-allow-credentials"] || null,
      acah: headers["access-control-allow-headers"] || null,
      acam: headers["access-control-allow-methods"] || null,
      server: headers["server"] || null,
      contentType: headers["content-type"] || null,
    });
  }
});

await page.goto(`${PREVIEW}/login?x-vercel-protection-bypass=${sec}`, {
  waitUntil: "domcontentloaded",
  timeout: 60_000,
});

await page.evaluate(async (api) => {
  try {
    await fetch(`${api}/api/v1/auth/login`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: "cors-diag@example.com", password: "x" }),
    });
  } catch {
    /* expected */
  }
}, API);

await page.waitForTimeout(1500);
console.log("preflights", JSON.stringify(preflights, null, 2));

// Also issue OPTIONS from Playwright request context (not browser CORS)
const apiReq = await context.request.fetch(`${API}/api/v1/auth/login`, {
  method: "OPTIONS",
  headers: {
    Origin: PREVIEW,
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "content-type",
  },
});
console.log("playwright_request_options", apiReq.status(), {
  acao: apiReq.headers()["access-control-allow-origin"],
  acac: apiReq.headers()["access-control-allow-credentials"],
});

await browser.close();
