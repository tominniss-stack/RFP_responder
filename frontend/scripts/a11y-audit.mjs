#!/usr/bin/env node
/**
 * Accessibility + visual audit.
 *
 * Visits every route in light and dark mode, runs axe-core (WCAG 2.2 A/AA),
 * opens each modal, captures full-page screenshots, and writes a JSON report.
 *
 * Usage:
 *   node frontend/scripts/a11y-audit.mjs                # defaults to http://localhost:3010
 *   BASE_URL=http://localhost:3010 node frontend/scripts/a11y-audit.mjs
 *
 * Exits non-zero if any serious/critical violation is found.
 */
import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..');
const BASE_URL = process.env.BASE_URL || 'http://localhost:3010';
const SHOTS = path.join(ROOT, 'plans', 'screenshots');
const REPORT = path.join(ROOT, 'plans', 'a11y-report.json');

const ROUTES = [
  { id: 'tracker', hash: '#/', ready: 'h1' },
  { id: 'new-rfp', hash: '#/new-rfp', ready: 'h1' },
  { id: 'kb', hash: '#/kb', ready: 'h1' },
  { id: 'settings', hash: '#/settings', ready: 'h1' },
  { id: 'services', hash: '#/services', ready: 'h1' },
  { id: 'pricing', hash: '#/pricing', ready: 'h1' },
  { id: 'rfp-detail', hash: '#/rfp/__RFP_ID__', ready: 'article, h1' },
];

/** Modals to open per route: [routeId, button text or aria-label regex, label] */
const MODALS = [
  { route: 'kb', trigger: 'button:has-text("Add document")', label: 'kb-add-modal' },
  { route: 'pricing', trigger: 'button:has-text("Add price item")', label: 'pricing-add-modal' },
  { route: 'rfp-detail', trigger: 'button:has-text("Edit details")', label: 'rfp-edit-details-modal' },
  { route: 'rfp-detail', trigger: 'button:has-text("Add section")', label: 'rfp-add-section-modal' },
  { route: 'services', trigger: '[aria-label^="Delete service"]', label: 'services-confirm-dialog' },
];

async function ensureFixtureRfp() {
  const api = `${BASE_URL}/api`;
  const list = await (await fetch(`${api}/rfps`)).json();
  if (Array.isArray(list) && list.length) return list[0].id;
  const created = await (
    await fetch(`${api}/rfps`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        client_name: 'Audit Fixture Client',
        value: 48000,
        service_ids: [1],
        raw_details: '1. Company overview\nDescribe your agency.\n\n2. Pricing\nProvide day rates.\n\n3. Accessibility approach\nDescribe WCAG experience.',
      }),
    })
  ).json();
  await fetch(`${api}/rfps/${created.id}/classify`, { method: 'POST' });
  await fetch(`${api}/rfps/${created.id}/generate-all`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
  return created.id;
}

async function setTheme(page, theme) {
  await page.evaluate((t) => {
    localStorage.setItem('rfp_theme', t);
    document.documentElement.classList.toggle('dark', t === 'dark');
  }, theme);
}

async function runAxe(page) {
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']).analyze();
  return results.violations.map((v) => ({
    id: v.id,
    impact: v.impact,
    help: v.help,
    helpUrl: v.helpUrl,
    nodes: v.nodes.slice(0, 5).map((n) => ({ target: n.target.join(' '), summary: n.failureSummary?.split('\n')[1]?.trim() })),
    count: v.nodes.length,
  }));
}

async function main() {
  await mkdir(SHOTS, { recursive: true });
  const rfpId = await ensureFixtureRfp();
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1360, height: 900 }, colorScheme: 'light' });
  const page = await context.newPage();
  const report = { baseUrl: BASE_URL, generatedAt: new Date().toISOString(), rfpId, pages: [] };
  let seriousOrCritical = 0;

  for (const theme of ['light', 'dark']) {
    for (const route of ROUTES) {
      const hash = route.hash.replace('__RFP_ID__', String(rfpId));
      await page.goto(`${BASE_URL}/`);
      await setTheme(page, theme);
      await page.goto(`${BASE_URL}/${hash}`);
      await page.waitForSelector(route.ready, { timeout: 15000 });
      await page.waitForTimeout(600);

      const shot = path.join(SHOTS, `${route.id}-${theme}.png`);
      await page.screenshot({ path: shot, fullPage: true });
      const violations = await runAxe(page);
      seriousOrCritical += violations.filter((v) => ['serious', 'critical'].includes(v.impact)).length;
      report.pages.push({ route: route.id, theme, url: hash, screenshot: path.relative(ROOT, shot), violations });
      console.log(`${theme.padEnd(5)} ${route.id.padEnd(12)} ${violations.length} violation type(s)`);

      for (const modal of MODALS.filter((m) => m.route === route.id)) {
        const trigger = page.locator(modal.trigger).first();
        if ((await trigger.count()) === 0) continue;
        await trigger.click();
        const dialog = page.locator('[role="dialog"]');
        if ((await dialog.count()) === 0) continue;
        await dialog.first().waitFor({ state: 'visible', timeout: 5000 });
        await page.waitForTimeout(300);
        const mshot = path.join(SHOTS, `${modal.label}-${theme}.png`);
        await page.screenshot({ path: mshot, fullPage: false });
        const mviol = await runAxe(page);
        seriousOrCritical += mviol.filter((v) => ['serious', 'critical'].includes(v.impact)).length;
        report.pages.push({ route: modal.label, theme, url: hash, screenshot: path.relative(ROOT, mshot), violations: mviol });
        console.log(`${theme.padEnd(5)} ${modal.label.padEnd(26)} ${mviol.length} violation type(s)`);
        await page.keyboard.press('Escape');
        await page.waitForTimeout(200);
      }
    }
  }

  await browser.close();
  report.summary = {
    pagesAudited: report.pages.length,
    totalViolationTypes: report.pages.reduce((a, p) => a + p.violations.length, 0),
    seriousOrCritical,
  };
  await writeFile(REPORT, JSON.stringify(report, null, 2));
  console.log(`\nReport: ${path.relative(ROOT, REPORT)}  |  serious/critical: ${seriousOrCritical}`);
  process.exit(seriousOrCritical > 0 ? 1 : 0);
}

main().catch((err) => {
  console.error(err);
  process.exit(2);
});
