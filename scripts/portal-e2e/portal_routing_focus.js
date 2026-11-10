const { chromium } = require('playwright-core');

const BASE = process.env.PW_BASE || 'http://localhost:3002';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch();
  const out = { hydrationErrors: [], routing: {}, focus: {}, overflow: {}, errors: [] };
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(120000);
  page.setDefaultNavigationTimeout(120000);
  page.on('pageerror', (e) => {
    const msg = e.message.slice(0, 120);
    out.errors.push('pageerror: ' + msg);
    if (msg.includes('Hydration')) out.hydrationErrors.push(msg);
  });
  page.on('console', (m) => {
    if (m.type() === 'error' && !m.text().includes('401')) out.errors.push('console: ' + m.text().slice(0, 160));
  });

  // login as portal-only user -> must land on /portal (not provider /)
  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#email', { timeout: 60000 });
  await sleep(4000);
  await page.fill('#email', 'maya@example.com');
  await page.fill('#password', 'Portal-pass-12345');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/portal', { timeout: 60000 });
  await sleep(3000);
  out.routing.portalOnly = await page.evaluate(() => ({ url: location.pathname }));

  // header identity + sign out affordance
  out.routing.identity = await page.evaluate(() => ({
    hasTenant: document.querySelector('header').innerText.includes('Demo Clinic'),
    hasUser: document.querySelector('header').innerText.includes('Maya Rao'),
    hasSignOut: !!document.querySelector('header button'),
  }));

  // viewport matrix (authenticated): overflow check on key pages
  for (const w of [320, 390, 768, 1280, 1536]) {
    await page.setViewportSize({ width: w, height: 844 });
    await sleep(500);
    const snap = {};
    for (const path of ['/portal', '/portal/appointments', '/portal/billing', '/portal/visits']) {
      await page.goto(BASE + path, { waitUntil: 'domcontentloaded' });
      await sleep(2500);
      snap[path] = await page.evaluate(() => ({
        bad: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      }));
    }
    out.overflow[w] = snap;
  }
  await page.setViewportSize({ width: 390, height: 844 });

  // focus return on Escape (explicit trigger focus)
  await page.goto(BASE + '/portal/appointments', { waitUntil: 'domcontentloaded' });
  await sleep(3000);
  const link = await page.evaluate(() => {
    const a = [...document.querySelectorAll('a')].find(
      (x) => x.href.includes('/portal/appointments/') && !x.href.endsWith('/appointments'),
    );
    return a ? a.getAttribute('href') : null;
  });
  await page.goto(BASE + link, { waitUntil: 'domcontentloaded' });
  await sleep(3000);
  await page.fill('#portal-cancel-reason', 'feeling better');
  await page.click('text=Cancel visit');
  await sleep(1500);
  await page.keyboard.press('Escape');
  await sleep(1500);
  out.focus.escapeReturn = await page.evaluate(() => ({
    gone: !document.querySelector('[role="dialog"]'),
    onTrigger: ((document.activeElement || {}).id || '') === 'portal-cancel-trigger',
  }));

  // staff login -> provider home (unchanged behavior)
  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded' });
  await sleep(3000);
  await page.fill('#email', 'portal-admin@example.com');
  await page.fill('#password', 'Admin-pass-12345');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/', { timeout: 60000 });
  await sleep(2000);
  out.routing.staff = await page.evaluate(() => ({ url: location.pathname }));

  // sign out as portal user -> /login, portal data gone
  await page.goto(BASE + '/login', { waitUntil: 'domcontentloaded' });
  await sleep(2000);
  await page.fill('#email', 'maya@example.com');
  await page.fill('#password', 'Portal-pass-12345');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/portal', { timeout: 60000 });
  await sleep(2000);
  await page.click('header button');
  await page.waitForURL('**/login', { timeout: 60000 });
  out.routing.signout = await page.evaluate(() => ({ url: location.pathname }));

  await browser.close();
  console.log(JSON.stringify(out, null, 1));
})().catch((e) => { console.error('FATAL', e); process.exit(1); });
