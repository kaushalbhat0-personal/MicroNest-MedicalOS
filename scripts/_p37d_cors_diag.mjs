/** Capture full CORS error from Preview→API. Never print secrets. */
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
const context = await browser.newContext();
await context.route("**/*", async (route) => {
  const reqUrl = route.request().url();
  if (reqUrl.includes("vercel.app")) {
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
const logs = [];
page.on("console", (m) => logs.push(`[${m.type()}] ${m.text()}`));
page.on("requestfailed", (r) =>
  logs.push(`[requestfailed] ${r.method()} ${r.url()} ${r.failure()?.errorText}`),
);

await page.goto(`${PREVIEW}/login?x-vercel-protection-bypass=${sec}`, {
  waitUntil: "networkidle",
  timeout: 60_000,
});
console.log("page_host", new URL(page.url()).host);

const result = await page.evaluate(async (api) => {
  try {
    const post = await fetch(`${api}/api/v1/auth/login`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: "cors-diag@example.com", password: "x" }),
    });
    return {
      post_status: post.status,
      post_acao: post.headers.get("access-control-allow-origin"),
    };
  } catch (e) {
    return { error: String(e.message || e) };
  }
}, API);

console.log("fetch_result", JSON.stringify(result));
for (const line of logs) console.log(line.split(sec).join("[REDACTED]"));
await browser.close();
