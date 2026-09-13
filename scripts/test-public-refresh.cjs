const { chromium } = require('playwright');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    await page.addInitScript(() => {
      window.refreshIntervals = [];
      const original = window.setInterval;
      window.setInterval = (fn, delay, ...args) => { window.refreshIntervals.push(delay); return original(fn, delay, ...args); };
    });
    await page.route('**/api/v1/public/**', route => route.fulfill({ json: route.request().url().includes('final-results')
      ? { category_name: 'Мужчины', routes: [], results: [] }
      : { groups: ['Мужчины'], results: [], sets: [], stage: 'final', final_groups: ['Мужчины'], qualification_refresh_seconds: 30, final_refresh_seconds: 10 } }));
    await page.goto('http://localhost:3000/results/muzhchiny');
    await page.getByRole('button', { name: 'Квалификация', exact: true }).waitFor();
    await page.waitForFunction(() => window.refreshIntervals.includes(10000));
    await page.getByRole('button', { name: 'Квалификация', exact: true }).click();
    await page.waitForFunction(() => window.refreshIntervals.at(-1) === 30000);
    await page.getByRole('button', { name: 'Финал', exact: true }).click();
    await page.waitForFunction(() => window.refreshIntervals.at(-1) === 10000);
    await page.unroute('**/api/v1/public/**');
    const login = await page.request.post('http://localhost:8001/api/v1/auth/login', { form: { username: 'admin@parkrock.test', password: 'demo1234' } });
    assert.equal(login.status(), 200);
    const { access_token } = await login.json();
    await page.addInitScript(token => localStorage.setItem('parkrock_admin_token', token), access_token);
    await page.goto('http://localhost:3000/admin');
    await page.getByRole('button', { name: 'Настройки', exact: true }).click();
    await page.getByRole('button', { name: 'Публичные результаты', exact: true }).click();
    await page.getByRole('heading', { name: 'Автообновление сайта' }).waitFor();
    assert.equal(await page.getByLabel('Квалификация, сек.').inputValue(), '30');
    assert.equal(await page.getByLabel('Финал, сек.').inputValue(), '10');
    await page.screenshot({ path: 'reports/public-refresh-desktop.png' });
    await page.setViewportSize({ width: 360, height: 900 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: 'reports/public-refresh-mobile.png' });
    console.log('PASS: qualification 30s, final 10s, CRM values and mobile layout; no settings written.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
