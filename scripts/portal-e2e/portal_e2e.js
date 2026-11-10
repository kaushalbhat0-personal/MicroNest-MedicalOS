const { chromium } = require('playwright-core');

const BASE = process.env.PW_BASE || 'http://localhost:3002';
const WIDTHS = [320, 390, 430, 768, 1024, 1280, 1536];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch();
  const out = { overflow: {}, dialog: {}, motion: {}, errors: [] };

  // login once, reuse storage
  const lctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const lp = await lctx.newPage();
  lp.setDefaultTimeout(120000);
  lp.setDefaultNavigationTimeout(120000);
  await lp.goto(BASE + '/login', { waitUntil: 'domcontentloaded' });
  await lp.waitForSelector('#email', { timeout: 60000 });
  await sleep(4000);
  await lp.fill('#email', 'maya@example.com');
  await lp.fill('#password', 'Portal-pass-12345');
  await lp.click('button[type="submit"]');
  await lp.waitForURL('**/portal', { timeout: 60000 });
  await sleep(2000);
  const state = await lctx.storageState();
  // tenant id for direct links
  const tid = await lp.evaluate(() => localStorage.getItem('hos.tenantId'));
  out.tenantSelected = !!tid;
  await lctx.close();

  for (const w of WIDTHS) {
    const ctx = await browser.newContext({
      viewport: { width: w, height: 844 },
      storageState: state,
      reducedMotion: 'reduce',
    });
    const page = await ctx.newPage();
    page.setDefaultTimeout(120000);
    page.setDefaultNavigationTimeout(120000);
    page.on('pageerror', (e) => out.errors.push(`[${w}] pageerror: ` + e.message.slice(0, 200)));
    page.on('console', (m) => {
      if (m.type() === 'error' && !m.text().includes('401'))
        out.errors.push(`[${w}] console: ` + m.text().slice(0, 160));
    });
    const snap = {};
    for (const path of ['/portal', '/portal/appointments', '/portal/billing', '/portal/visits']) {
      await page.goto(BASE + path, { waitUntil: 'domcontentloaded' });
      await sleep(2500);
      snap[path] = await page.evaluate(() => ({
        overflow: !(document.documentElement.scrollWidth <= document.documentElement.clientWidth),
        h1: ((document.querySelector('h1') || {}).innerText || '').slice(0, 40),
      }));
    }
    // visit detail (first link)
    await page.goto(BASE + '/portal/visits', { waitUntil: 'domcontentloaded' });
    await sleep(2500);
    const vlink = await page.evaluate(() => {
      const a = [...document.querySelectorAll('a')].find(
        (x) => x.href.includes('/portal/visits/') && !x.href.endsWith('/visits'),
      );
      return a ? a.getAttribute('href') : null;
    });
    if (vlink) {
      await page.goto(BASE + vlink, { waitUntil: 'domcontentloaded' });
      await sleep(2500);
      snap['visit-detail'] = await page.evaluate(() => ({
        overflow: !(document.documentElement.scrollWidth <= document.documentElement.clientWidth),
        hasNotes: document.body.innerText.includes('Patient recovering well'),
      }));
    }
    // reduced motion: button transition should be disabled under emulation
    snap.motion = await page.evaluate(() => {
      const b = document.querySelector('.hos-btn');
      if (!b) return { emulated: matchMedia('(prefers-reduced-motion: reduce)').matches, btn: false };
      const cs = getComputedStyle(b);
      return {
        emulated: matchMedia('(prefers-reduced-motion: reduce)').matches,
        transitionDuration: cs.transitionDuration,
        animationDuration: cs.animationDuration,
      };
    });
    out.overflow[w] = snap;
    await ctx.close();
  }

  // dialog focus semantics: return goes to pre-dialog focus (reason input)
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, storageState: state });
  const page = await ctx.newPage();
  page.setDefaultTimeout(120000);
  page.setDefaultNavigationTimeout(120000);
  page.on('pageerror', (e) => out.errors.push('[dlg] pageerror: ' + e.message.slice(0, 200)));
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
  const opened = await page.evaluate(() => ({
    dialog: !!document.querySelector('[role="dialog"]'),
    labelled: (document.querySelector('[role="dialog"] h2') || {}).innerText || null,
    described: !!document.querySelector('[role="dialog"] p'),
    focusInside: !!document.querySelector('[role="dialog"]') && document.querySelector('[role="dialog"]').contains(document.activeElement),
  }));
  // Escape closes and returns focus to the trigger (explicit focus return
  // in the page; Radix alone left focus on BODY in this setup).
  await page.keyboard.press('Escape');
  await sleep(1000);
  const escaped = await page.evaluate(() => ({
    gone: !document.querySelector('[role="dialog"]'),
    returnedToTrigger:
      ((document.activeElement || {}).innerText || '') === 'Cancel visit',
  }));
  // reopen, Tab through dialog buttons, confirm
  await page.click('text=Cancel visit');
  await sleep(1500);
  await page.keyboard.press('Tab');
  await sleep(300);
  const tabbed = await page.evaluate(() => ({
    active: ((document.activeElement || {}).innerText || '').slice(0, 20),
    inside: !!document.querySelector('[role="dialog"]') && document.querySelector('[role="dialog"]').contains(document.activeElement),
  }));
  await page.click('text=Yes, cancel');
  await sleep(3000);
  const done = await page.evaluate(() => ({
    cancelled: document.body.innerText.includes('Cancelled'),
    pendingGone: !document.body.innerText.includes('Yes, cancel'),
  }));
  out.dialog = { opened, escaped, tabbed, done };
  await browser.close();
  console.log(JSON.stringify(out, null, 1));
})().catch((e) => { console.error('FATAL', e); process.exit(1); });
