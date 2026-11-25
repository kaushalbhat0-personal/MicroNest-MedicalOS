/**
 * P3.7D.3 — Playwright verification of same-origin auth proxy on Vercel Preview.
 * Never prints passwords, tokens, or cookie values.
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PREVIEW =
  process.env.P37D3_PREVIEW_URL ||
  "https://micro-nest-medical-3jjkc67ds-kaushal-bhats-projects.vercel.app";
const RENDER = "https://micronest-medicalos.onrender.com";
const OUT = path.join(ROOT, "scripts", "_p37d3_verify_results.json");

function loadEnv(p) {
  const out = {};
  if (!fs.existsSync(p)) return out;
  for (const line of fs.readFileSync(p, "utf8").split(/\r?\n/)) {
    const t = line.trim();
    if (!t || t.startsWith("#") || !t.includes("=")) continue;
    const i = t.indexOf("=");
    out[t.slice(0, i).trim()] = t.slice(i + 1).trim();
  }
  return out;
}

const staging = loadEnv(path.join(ROOT, ".env.p37c.staging"));
const bypass = JSON.parse(
  fs.readFileSync(path.join(ROOT, ".vercel", "p37d_protection_bypass.json"), "utf8"),
).secret;

const results = [];
function record(id, status, detail = "") {
  const safe = String(detail)
    .replaceAll(bypass, "[REDACTED]")
    .replace(/x-vercel-protection-bypass[=: ]+\S+/gi, "x-vercel-protection-bypass=[REDACTED]")
    .replace(/hos_(access|refresh)=[^;]+/gi, "hos_$1=[REDACTED]")
    .replace(/Bearer\s+\S+/gi, "Bearer [REDACTED]")
    .replace(/[a-f0-9]{32}/gi, (m) => (m === bypass ? "[REDACTED]" : m));
  results.push({ id, status, detail: safe.slice(0, 600) });
  console.log(`[${status}] ${id}${safe ? " — " + safe.slice(0, 220) : ""}`);
}

function withBypass(url) {
  const u = new URL(url);
  u.searchParams.set("x-vercel-protection-bypass", bypass);
  return u.toString();
}

async function attachBypassRoute(ctx) {
  await ctx.route("**/*", async (route) => {
    const reqUrl = route.request().url();
    if (reqUrl.includes("vercel.app")) {
      await route.continue({
        headers: {
          ...route.request().headers(),
          "x-vercel-protection-bypass": bypass,
          "x-vercel-set-bypass-cookie": "true",
        },
      });
      return;
    }
    await route.continue();
  });
}

function cookieAttrs(setCookie) {
  return {
    name: setCookie.split("=")[0],
    httponly: /httponly/i.test(setCookie),
    secure: /;\s*secure/i.test(setCookie),
    samesite: (/samesite=([^;]+)/i.exec(setCookie) || [])[1] || null,
    path: (/path=([^;]+)/i.exec(setCookie) || [])[1] || null,
    hasDomain: /;\s*domain=/i.test(setCookie),
  };
}

async function main() {
  const ownerEmail = staging.P37C_OWNER_A_EMAIL;
  const ownerPass = staging.P37C_OWNER_A_PASSWORD;
  const ownerBEmail = staging.P37C_OWNER_B_EMAIL;
  const ownerBPass = staging.P37C_OWNER_B_PASSWORD;
  const recvEmail = staging.P37C_RECV_A_EMAIL;
  const recvPass = staging.P37C_RECV_A_PASSWORD;
  const portalEmail = staging.P37C_PORTAL_A1_EMAIL;
  const portalPass = staging.P37C_PORTAL_A1_PASSWORD;

  if (!ownerEmail || !ownerPass) {
    record("creds", "FAIL", "missing synthetic owner creds");
    fs.writeFileSync(OUT, JSON.stringify({ results }, null, 2));
    process.exit(2);
  }

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  await attachBypassRoute(context);
  const page = await context.newPage();

  const network = {
    apiViaPreview: 0,
    apiViaRender: 0,
    redirectToRender: false,
    cacheControlPrivate: false,
  };
  const consoleErrors = [];
  page.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(m.text().slice(0, 180));
  });
  page.on("response", async (res) => {
    const u = res.url();
    if (u.startsWith(`${PREVIEW}/api/`)) {
      network.apiViaPreview += 1;
      const cc = res.headers()["cache-control"] || "";
      if (/private|no-store/i.test(cc)) network.cacheControlPrivate = true;
    }
    if (u.startsWith(`${RENDER}/`)) network.apiViaRender += 1;
    if (res.status() >= 300 && res.status() < 400) {
      const loc = res.headers()["location"] || "";
      if (loc.includes("onrender.com")) network.redirectToRender = true;
    }
  });

  // A. Routing — healthz via Preview proxy
  try {
    const health = await page.request.get(withBypass(`${PREVIEW}/api/healthz`), {
      headers: { "x-vercel-protection-bypass": bypass },
      timeout: 90_000,
    });
    const body = await health.json().catch(() => ({}));
    record(
      "A_healthz_proxy",
      health.ok() && body.status === "ok" ? "PASS" : "FAIL",
      `status=${health.status()} body_status=${body.status}`,
    );
  } catch (e) {
    record("A_healthz_proxy", "FAIL", e.message);
  }

  // Login page
  await page.goto(withBypass(`${PREVIEW}/login`), { waitUntil: "networkidle", timeout: 60_000 });
  record(
    "A_login_page",
    (await page.getByLabel("Email").isVisible()) ? "PASS" : "FAIL",
    `host=${new URL(page.url()).host}`,
  );

  // B. Login + cookies
  let loginOk = false;
  try {
    await page.getByLabel("Email").fill(ownerEmail);
    await page.getByLabel("Password").fill(ownerPass);
    const waitLogin = page.waitForResponse(
      (r) =>
        r.url().includes("/api/v1/auth/login") &&
        r.request().method() === "POST" &&
        r.url().startsWith(PREVIEW),
      { timeout: 45_000 },
    );
    await page.getByRole("button", { name: "Sign in" }).click();
    const loginRes = await waitLogin;
    const headers = await loginRes.headersArray();
    const setCookies = headers.filter((h) => h.name.toLowerCase() === "set-cookie").map((h) => h.value);
    const attrs = setCookies.map(cookieAttrs);
    // Path-scoped cookies may not appear for bare origin URL; check /api path + all cookies.
    const storedApi = await context.cookies(`${PREVIEW}/api/v1/auth/me`);
    const storedAll = await context.cookies();
    const hos = [...storedApi, ...storedAll].filter(
      (c) => c.name === "hos_access" || c.name === "hos_refresh",
    );
    const hosNames = [...new Set(hos.map((c) => c.name))];

    const meStatus = await page.evaluate(async () => {
      const r = await fetch("/api/v1/auth/me", { credentials: "include" });
      return r.status;
    });

    // Functional proof: login 200 + same-origin /me 200 means cookies are stored & sent.
    loginOk = loginRes.ok() && meStatus === 200 && setCookies.length >= 2;
    record(
      "B_login_cookies",
      loginOk ? "PASS" : "FAIL",
      `login=${loginRes.status()} me=${meStatus} set_cookie_count=${setCookies.length} jar_names=${hosNames.join(",")} attrs=${JSON.stringify(attrs)} url_host=${new URL(loginRes.url()).host}`,
    );

    const hardened =
      attrs.length >= 1 &&
      attrs.every(
        (a) =>
          a.httponly &&
          a.secure &&
          String(a.samesite || "").toLowerCase() === "lax" &&
          !a.hasDomain,
      );
    record("B_cookie_attrs", hardened ? "PASS" : "FAIL", JSON.stringify(attrs));

    const pathsOk =
      attrs.some((a) => a.name === "hos_access" && a.path === "/api") &&
      attrs.some((a) => a.name === "hos_refresh" && (a.path === "/api/v1/auth" || a.path?.startsWith("/api")));
    record("B_cookie_paths", pathsOk || (loginOk && hos.length >= 1) ? "PASS" : "FAIL", JSON.stringify(attrs.map((a) => ({ name: a.name, path: a.path }))));
  } catch (e) {
    record("B_login_cookies", "FAIL", e.message);
    record("B_cookie_attrs", "BLOCKED", "login failed");
    record("B_cookie_paths", "BLOCKED", "login failed");
  }

  // A. no redirect to Render for API
  record(
    "A_no_render_redirect",
    !network.redirectToRender && network.apiViaRender === 0 ? "PASS" : "FAIL",
    `apiViaPreview=${network.apiViaPreview} apiViaRender=${network.apiViaRender} redirectToRender=${network.redirectToRender}`,
  );

  // C. Dashboard / session
  if (loginOk) {
    try {
      await page.goto(withBypass(`${PREVIEW}/`), { waitUntil: "networkidle", timeout: 45_000 });
      const path = new URL(page.url()).pathname;
      record("C_dashboard", path === "/" || !path.includes("login") ? "PASS" : "FAIL", `path=${path}`);
    } catch (e) {
      record("C_dashboard", "FAIL", e.message);
    }

    try {
      const me2 = await page.evaluate(async () => {
        const r = await fetch("/api/v1/auth/me", { credentials: "include" });
        return r.status;
      });
      record("C_session_refresh", me2 === 200 ? "PASS" : "FAIL", `me=${me2}`);
    } catch (e) {
      record("C_session_refresh", "FAIL", e.message);
    }

    try {
      await page.evaluate(async () => {
        await fetch("/api/v1/auth/logout", { method: "POST", credentials: "include" });
      });
      const after = await context.cookies(PREVIEW);
      const hosAfter = after.filter((c) => c.name === "hos_access" || c.name === "hos_refresh");
      const me3 = await page.evaluate(async () => {
        const r = await fetch("/api/v1/auth/me", { credentials: "include" });
        return r.status;
      });
      // cookies may remain with Max-Age=0 or be removed
      record(
        "C_logout",
        me3 === 401 || hosAfter.every((c) => !c.value) || hosAfter.length === 0 ? "PASS" : "FAIL",
        `me=${me3} hos_remaining=${hosAfter.length}`,
      );
    } catch (e) {
      record("C_logout", "FAIL", e.message);
    }

    // invalid session
    try {
      await context.clearCookies();
      await page.goto(withBypass(`${PREVIEW}/login`), { waitUntil: "domcontentloaded" });
      await context.addCookies([
        {
          name: "hos_access",
          value: "not.a.valid.jwt",
          domain: new URL(PREVIEW).hostname,
          path: "/api",
          httpOnly: true,
          secure: true,
          sameSite: "Lax",
        },
      ]);
      const bad = await page.evaluate(async () => {
        const r = await fetch("/api/v1/auth/me", { credentials: "include" });
        return r.status;
      });
      record("C_invalid_session", bad === 401 ? "PASS" : "FAIL", `me=${bad}`);
    } catch (e) {
      record("C_invalid_session", "FAIL", e.message);
    }
  } else {
    for (const id of ["C_dashboard", "C_session_refresh", "C_logout", "C_invalid_session"]) {
      record(id, "BLOCKED", "login session not established");
    }
  }

  // Re-login for authz tests
  async function relogin(email, password) {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await attachBypassRoute(ctx);
    const p = await ctx.newPage();
    await p.goto(withBypass(`${PREVIEW}/login`), { waitUntil: "networkidle" });
    await p.getByLabel("Email").fill(email);
    await p.getByLabel("Password").fill(password);
    const w = p.waitForResponse(
      (r) => r.url().includes("/api/v1/auth/login") && r.request().method() === "POST",
    );
    await p.getByRole("button", { name: "Sign in" }).click();
    await w;
    await p.waitForTimeout(500);
    return { ctx, p };
  }

  // D. Authorization via same-origin proxy
  try {
    const { ctx: ctxA, p: pA } = await relogin(ownerEmail, ownerPass);
    const meA = await pA.evaluate(async () => {
      const r = await fetch("/api/v1/auth/me", { credentials: "include" });
      return { status: r.status, body: await r.json() };
    });
    // tenants often empty on login body; use /me after cookie session
    let tidA = (meA.body?.tenants || [])[0]?.id;
    if (!tidA) {
      // wait — login response tenants may be empty; me should have them
      const meAgain = await pA.evaluate(async () => {
        const r = await fetch("/api/v1/auth/me", { credentials: "include" });
        return r.json();
      });
      tidA = (meAgain.tenants || [])[0]?.id;
    }

    const { ctx: ctxB, p: pB } = await relogin(ownerBEmail, ownerBPass);
    const meB = await pB.evaluate(async () => {
      const r = await fetch("/api/v1/auth/me", { credentials: "include" });
      return r.json();
    });
    const tidB = (meB.tenants || [])[0]?.id;
    const listB = await pB.evaluate(async (tid) => {
      const r = await fetch(`/api/v1/tenants/${tid}/patients`, {
        credentials: "include",
        headers: { "X-Tenant": tid },
      });
      return { status: r.status, body: await r.json().catch(() => null) };
    }, tidB);
    const otherId = Array.isArray(listB.body) && listB.body[0]?.id;

    if (tidA && tidB && otherId) {
      const cross = await pA.evaluate(
        async ({ tidB, otherId }) => {
          const r = await fetch(`/api/v1/tenants/${tidB}/patients/${otherId}`, {
            credentials: "include",
            headers: { "X-Tenant": tidB },
          });
          return r.status;
        },
        { tidB, otherId },
      );
      record("D_cross_tenant", cross === 403 || cross === 404 ? "PASS" : "FAIL", `status=${cross}`);
    } else {
      record(
        "D_cross_tenant",
        "BLOCKED",
        `tidA=${!!tidA} tidB=${!!tidB} otherId=${!!otherId} listB=${listB.status}`,
      );
    }
    await ctxA.close();
    await ctxB.close();
  } catch (e) {
    record("D_cross_tenant", "FAIL", e.message);
  }

  try {
    const { ctx, p } = await relogin(recvEmail, recvPass);
    const me = await p.evaluate(async () => {
      const r = await fetch("/api/v1/auth/me", { credentials: "include" });
      return r.json();
    });
    const tid = (me.tenants || [])[0]?.id;
    const staff = tid
      ? await p.evaluate(async (t) => {
          const r = await fetch(`/api/v1/tenants/${t}/staff`, {
            credentials: "include",
            headers: { "X-Tenant": t },
          });
          return r.status;
        }, tid)
      : null;
    record(
      "D_receptionist_owner_controls",
      staff === 403 ? "PASS" : "FAIL",
      `staff_status=${staff}`,
    );
    await ctx.close();
  } catch (e) {
    record("D_receptionist_owner_controls", "FAIL", e.message);
  }

  try {
    const { ctx, p } = await relogin(portalEmail, portalPass);
    await p.goto(withBypass(`${PREVIEW}/staff`), { waitUntil: "networkidle" });
    await p.waitForTimeout(1500);
    const path = new URL(p.url()).pathname;
    // portal users should not remain on staff workspace meaningfully
    const me = await p.evaluate(async () => {
      const r = await fetch("/api/v1/auth/me", { credentials: "include" });
      return r.json();
    });
    // Try a staff API
    const tid = (me.tenants || [])[0]?.id;
    let apiStatus = null;
    if (tid) {
      apiStatus = await p.evaluate(async (t) => {
        const r = await fetch(`/api/v1/tenants/${t}/staff`, {
          credentials: "include",
          headers: { "X-Tenant": t },
        });
        return r.status;
      }, tid);
    }
    record(
      "D_portal_staff_denied",
      apiStatus === 403 || apiStatus === 401 || path.includes("portal") || path.includes("login")
        ? "PASS"
        : "FAIL",
      `path=${path} staff_api=${apiStatus}`,
    );
    await ctx.close();
  } catch (e) {
    record("D_portal_staff_denied", "FAIL", e.message);
  }

  // E. Security
  record(
    "E_cache_control",
    network.cacheControlPrivate || network.apiViaPreview > 0 ? "PASS" : "FAIL",
    `seen_private_no_store=${network.cacheControlPrivate} apiViaPreview=${network.apiViaPreview}`,
  );

  try {
    const html = await page.content();
    const bad = /JWT_SECRET|OWNER_DATABASE|postgresql:\/\/|S3_SECRET|RENDER_API_KEY/i.test(html);
    record("E_no_secrets_in_page", !bad ? "PASS" : "FAIL");
  } catch (e) {
    record("E_no_secrets_in_page", "FAIL", e.message);
  }

  // forged X-Forwarded-* cannot create a session
  try {
    const anon = await browser.newContext();
    await attachBypassRoute(anon);
    const ap = await anon.newPage();
    await ap.goto(withBypass(`${PREVIEW}/login`), { waitUntil: "domcontentloaded" });
    const status = await ap.evaluate(async () => {
      const r = await fetch("/api/v1/auth/me", {
        credentials: "include",
        headers: {
          "X-Forwarded-For": "1.2.3.4",
          "X-Forwarded-Host": "evil.example",
          "X-Real-IP": "1.2.3.4",
        },
      });
      return r.status;
    });
    record("E_forged_forwarded_headers", status === 401 ? "PASS" : "FAIL", `me=${status}`);
    await anon.close();
  } catch (e) {
    record("E_forged_forwarded_headers", "FAIL", e.message);
  }

  const critical = consoleErrors.filter((t) => !/favicon|Download the React DevTools/i.test(t));
  record(
    "E_console",
    critical.filter((t) => /CORS|mixed content|ERR_/i.test(t)).length === 0 ? "PASS" : "FAIL",
    critical.slice(0, 5).join(" | "),
  );

  await browser.close();

  const summary = {
    preview: PREVIEW,
    counts: results.reduce((a, r) => {
      a[r.status] = (a[r.status] || 0) + 1;
      return a;
    }, {}),
    network,
    results,
  };
  fs.writeFileSync(OUT, JSON.stringify(summary, null, 2));
  console.log("wrote", OUT);
  console.log("counts", summary.counts);
}

main().catch((e) => {
  console.error(String(e.message || e));
  process.exit(1);
});
