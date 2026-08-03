/**
 * Responsive UI checks across phone / tablet / desktop.
 *
 *   1. streamlit run app.py --server.port 8532 --server.headless true
 *   2. npm i playwright && npx playwright install chromium
 *   3. node tests/test_responsive.mjs [baseUrl] [screenshotDir]
 *
 * Asserts: no horizontal page scroll, no element overflowing the viewport,
 * tap targets >= 44px on touch viewports, readable font sizes, and a usable
 * tab strip. Writes one screenshot per viewport per tab.
 */

import { chromium, devices } from 'playwright';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

const BASE = process.argv[2] || 'http://localhost:8532';
const SHOTS = process.argv[3] || join(process.cwd(), 'screenshots');

const VIEWPORTS = [
  { name: 'phone',          width: 390,  height: 844,  touch: true,  dpr: 3 },
  { name: 'phone-small',    width: 320,  height: 568,  touch: true,  dpr: 2 },
  { name: 'phone-landscape',width: 844,  height: 390,  touch: true,  dpr: 3 },
  { name: 'tablet',         width: 820,  height: 1180, touch: true,  dpr: 2 },
  { name: 'tablet-landscape', width: 1180, height: 820, touch: true, dpr: 2 },
  { name: 'laptop',         width: 1366, height: 768,  touch: false, dpr: 1 },
  { name: 'desktop',        width: 1920, height: 1080, touch: false, dpr: 1 },
];

const TABS = ['Article', 'Plan', 'Sources', 'Images', 'Export', 'Run log'];

let failures = 0;
const results = [];

function check(label, ok, detail = '') {
  if (!ok) failures++;
  results.push({ label, ok, detail });
  const mark = ok ? 'PASS' : 'FAIL';
  console.log(`  [${mark}] ${label}${detail ? ` — ${detail}` : ''}`);
}

/**
 * Elements whose painted box escapes the viewport in a way the user would feel.
 *
 * Two things are deliberately NOT failures:
 *   - content inside an element that scrolls horizontally (a wide code block or
 *     dataframe in its own `overflow-x: auto` box is correct behaviour);
 *   - the collapsed sidebar, which is parked off-canvas via a negative
 *     translate on purpose.
 */
async function overflowingElements(page) {
  return page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const bad = [];

    const insideScrollContainer = (el) => {
      for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) {
        if (['auto', 'scroll'].includes(getComputedStyle(n).overflowX)) return true;
      }
      return false;
    };
    const insideCollapsedSidebar = (el) =>
      !!el.closest('section[data-testid="stSidebar"][aria-expanded="false"]');

    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      const style = getComputedStyle(el);
      if (style.visibility === 'hidden' || style.display === 'none') continue;
      if (['auto', 'scroll'].includes(style.overflowX)) continue;
      if (insideScrollContainer(el)) continue;
      if (insideCollapsedSidebar(el)) continue;

      if (r.right > vw + 2 || r.left < -2) {
        bad.push({
          tag: el.tagName.toLowerCase(),
          cls: (el.className || '').toString().slice(0, 60),
          testid: el.getAttribute('data-testid') || '',
          left: Math.round(r.left),
          right: Math.round(r.right),
          vw,
        });
      }
    }
    // Report only the outermost offenders; children inherit the problem.
    return bad.slice(0, 6);
  });
}

/**
 * Interactive controls smaller than the 32px touch floor.
 *
 * Native checkbox/radio inputs are skipped when they are visually hidden behind
 * a styled label — the label is the real tap target, so measuring the input
 * would report a control the user never touches.
 */
async function smallTapTargets(page) {
  return page.evaluate(() => {
    const bad = [];
    const sel = 'button, [role="tab"], a, input[type="checkbox"], input[type="radio"], summary';

    for (const el of document.querySelectorAll(sel)) {
      const style = getComputedStyle(el);
      if (style.visibility === 'hidden' || style.display === 'none') continue;
      if (el.closest('section[data-testid="stSidebar"][aria-expanded="false"]')) continue;

      let box = el.getBoundingClientRect();

      // A hidden native input delegates its hit area to the wrapping label.
      if (el.tagName === 'INPUT' && (parseFloat(style.opacity) === 0 || box.height < 20)) {
        const label = el.closest('label');
        if (!label) continue;
        box = label.getBoundingClientRect();
      }
      if (box.width === 0 || box.height === 0) continue;

      if (box.height < 32) {
        bad.push({
          tag: el.tagName.toLowerCase(),
          text: (el.innerText || el.getAttribute('aria-label') || '').trim().slice(0, 32),
          h: Math.round(box.height),
        });
      }
    }
    return bad.slice(0, 8);
  });
}

async function tinyText(page) {
  return page.evaluate(() => {
    const bad = [];
    for (const el of document.querySelectorAll('p, li, span, div, label, td')) {
      if (!el.innerText || !el.innerText.trim()) continue;
      if (el.children.length > 0) continue;             // leaf nodes only
      const fs = parseFloat(getComputedStyle(el).fontSize);
      if (fs && fs < 11) bad.push({ text: el.innerText.trim().slice(0, 30), fs });
    }
    return bad.slice(0, 6);
  });
}

/** True when the sidebar drawer sits on top of the main content area. */
async function sidebarCoversContent(page) {
  return page.evaluate(() => {
    const sb = document.querySelector('section[data-testid="stSidebar"]');
    const hero = document.querySelector('.bwa-hero');
    if (!sb || !hero) return false;
    const s = sb.getBoundingClientRect();
    const h = hero.getBoundingClientRect();
    if (s.width === 0 || getComputedStyle(sb).visibility === 'hidden') return false;
    return s.right > h.left + 4;   // overlapping rather than docked beside it
  });
}

async function collapseSidebar(page) {
  const close = page.locator(
    '[data-testid="stSidebarCollapseButton"] button, [data-testid="stSidebarCollapsedControl"] button',
  );
  if (await close.count()) {
    await close.first().click({ force: true });
    await page.waitForTimeout(600);
  }
}

/** Wait for Streamlit to finish its websocket render, not just DOMContentLoaded. */
async function settle(page) {
  await page.waitForSelector('[data-testid="stAppViewContainer"]', { timeout: 30000 });
  // The hero is the first thing our own script draws, so it proves the Python
  // side has run — waiting on Streamlit's shell alone races the render.
  await page.waitForSelector('.bwa-hero', { state: 'visible', timeout: 30000 });
  await page
    .waitForFunction(() => !document.querySelector('[data-testid="stStatusWidget"]'), null, {
      timeout: 30000,
    })
    .catch(() => {});
  await page.waitForTimeout(600);
}

async function run() {
  mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();

  for (const vp of VIEWPORTS) {
    console.log(`\n=== ${vp.name}  ${vp.width}x${vp.height} ===`);
    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      deviceScaleFactor: vp.dpr,
      hasTouch: vp.touch,
      // isMobile is what makes Chromium report `pointer: coarse` / `hover: none`,
      // which is how a real tablet or phone identifies itself to CSS.
      isMobile: vp.touch,
      userAgent: vp.touch
        ? devices['iPhone 13'].userAgent
        : undefined,
    });
    const page = await context.newPage();

    const consoleErrors = [];
    page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
    page.on('pageerror', (e) => consoleErrors.push(String(e)));

    await page.goto(BASE, { waitUntil: 'domcontentloaded' });
    await settle(page);

    // On phones the sidebar must NOT cover the app on first load. Assert that,
    // then collapse it if it does so the rest of the run can proceed.
    const covers = await sidebarCoversContent(page);
    if (vp.width <= 640) {
      check(`${vp.name}: sidebar does not cover the app on load`, !covers);
    }
    if (covers) await collapseSidebar(page);

    // ---- load the sample article so the full result UI is on screen ----
    const sampleBtn = page.locator('button', { hasText: /sample article/i });
    if (await sampleBtn.count()) {
      await sampleBtn.first().click();
      await settle(page);
      await page.waitForSelector('[data-testid="stTab"]', { timeout: 30000 });
    } else {
      throw new Error('sample-article button not found — the result UI cannot be tested');
    }

    // ---- landing / article view ----
    let bad = await overflowingElements(page);
    check(`${vp.name}: no element overflows the viewport`, bad.length === 0, JSON.stringify(bad));

    const hScroll = await page.evaluate(() => {
      const d = document.documentElement;
      return { scrollWidth: d.scrollWidth, clientWidth: d.clientWidth };
    });
    check(
      `${vp.name}: page does not scroll horizontally`,
      hScroll.scrollWidth <= hScroll.clientWidth + 2,
      `scrollWidth=${hScroll.scrollWidth} clientWidth=${hScroll.clientWidth}`,
    );

    const tiny = await tinyText(page);
    check(`${vp.name}: no text under 11px`, tiny.length === 0, JSON.stringify(tiny));

    // Streamlit's header is opaque and absolutely positioned. If the page's top
    // padding is too small the first heading disappears behind it.
    const headerClash = await page.evaluate(() => {
      // Measure from the top of the document — a scrolled page would make a
      // correctly-padded title look like it is behind the header. Streamlit
      // scrolls an inner container, not the window, so reset every ancestor.
      window.scrollTo(0, 0);
      const hero = document.querySelector('.bwa-hero');
      for (let n = hero; n; n = n.parentElement) {
        if (n.scrollTop) n.scrollTop = 0;
      }
      const header = document.querySelector('[data-testid="stHeader"]');
      const h1 = document.querySelector('.bwa-hero h1');
      if (!header || !h1) return null;
      const hr = header.getBoundingClientRect();
      const tr = h1.getBoundingClientRect();
      return { headerBottom: Math.round(hr.bottom), titleTop: Math.round(tr.top) };
    });
    if (headerClash) {
      check(
        `${vp.name}: page title is not hidden behind the header`,
        headerClash.titleTop >= headerClash.headerBottom - 1,
        JSON.stringify(headerClash),
      );
    }

    if (vp.touch) {
      const small = await smallTapTargets(page);
      check(`${vp.name}: tap targets >= 32px tall`, small.length === 0, JSON.stringify(small));
    }

    // ---- images scale down ----
    const oversizeImg = await page.evaluate(() => {
      const vw = document.documentElement.clientWidth;
      return [...document.querySelectorAll('img')]
        .filter((i) => i.getBoundingClientRect().width > vw + 2)
        .map((i) => ({ src: (i.src || '').slice(0, 40), w: Math.round(i.getBoundingClientRect().width) }));
    });
    check(`${vp.name}: images fit the viewport`, oversizeImg.length === 0, JSON.stringify(oversizeImg));

    // ---- stat strip wraps instead of squashing ----
    const statOverflow = await page.evaluate(() => {
      const strip = document.querySelector('.bwa-stats');
      if (!strip) return null;
      const r = strip.getBoundingClientRect();
      const kids = [...strip.children].map((c) => c.getBoundingClientRect());
      return {
        stripRight: Math.round(r.right),
        vw: document.documentElement.clientWidth,
        widest: Math.round(Math.max(...kids.map((k) => k.width))),
        rows: new Set(kids.map((k) => Math.round(k.top))).size,
      };
    });
    if (statOverflow) {
      check(
        `${vp.name}: stat strip fits (${statOverflow.rows} row(s))`,
        statOverflow.stripRight <= statOverflow.vw + 2,
        JSON.stringify(statOverflow),
      );
    }

    // ---- tab strip must be reachable, scrolling if needed ----
    const tabInfo = await page.evaluate(() => {
      const list = document.querySelector('div[data-testid="stTabs"] [role="tablist"]');
      if (!list) return null;
      return {
        clientWidth: list.clientWidth,
        scrollWidth: list.scrollWidth,
        overflowX: getComputedStyle(list).overflowX,
        tabs: list.querySelectorAll('[role="tab"]').length,
      };
    });
    if (tabInfo) {
      const usable = tabInfo.scrollWidth <= tabInfo.clientWidth + 2 || ['auto', 'scroll'].includes(tabInfo.overflowX);
      check(`${vp.name}: tab strip usable (${tabInfo.tabs} tabs)`, usable, JSON.stringify(tabInfo));
    }

    // ---- walk every tab, screenshot, and re-check overflow ----
    for (const tabName of TABS) {
      const tab = page.locator('[data-testid="stTab"]', { hasText: new RegExp(tabName, 'i') });
      if (!(await tab.count())) continue;
      await tab.first().scrollIntoViewIfNeeded();
      await tab.first().click();
      await page.waitForTimeout(500);

      bad = await overflowingElements(page);
      check(`${vp.name} / ${tabName}: no overflow`, bad.length === 0, JSON.stringify(bad));

      await page.screenshot({
        path: join(SHOTS, `${vp.name}--${tabName.toLowerCase().replace(/\s+/g, '-')}.png`),
        fullPage: false,
      });
    }

    // ---- sidebar: drawer on phones, docked on wide screens ----
    const sidebar = await page.evaluate(() => {
      const el = document.querySelector('section[data-testid="stSidebar"]');
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { width: Math.round(r.width), left: Math.round(r.left), vw: document.documentElement.clientWidth };
    });
    if (sidebar && sidebar.width > 0) {
      check(
        `${vp.name}: sidebar does not exceed the viewport`,
        sidebar.width <= sidebar.vw + 2,
        JSON.stringify(sidebar),
      );
    }

    check(`${vp.name}: no console errors`, consoleErrors.length === 0, consoleErrors.slice(0, 2).join(' | '));

    await context.close();
  }

  await browser.close();

  console.log('\n' + '='.repeat(60));
  const passed = results.filter((r) => r.ok).length;
  console.log(`${passed}/${results.length} checks passed`);
  if (failures) {
    console.log('\nFailures:');
    for (const r of results.filter((x) => !x.ok)) console.log(`  - ${r.label}: ${r.detail}`);
  }
  console.log(`Screenshots: ${SHOTS}`);
  process.exit(failures ? 1 : 0);
}

run().catch((e) => { console.error(e); process.exit(1); });
