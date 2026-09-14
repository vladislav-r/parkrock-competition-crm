const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1536, height: 864 } });
    const login = await page.request.post('http://localhost:8001/api/v1/auth/login', { form: { username: 'admin@parkrock.test', password: 'demo1234' } });
    assert.ok(login.ok());
    const token = (await login.json()).access_token;
    await page.addInitScript(t => localStorage.setItem('parkrock_admin_token', t), token);
    let mode = 'hang';
    let release = [];
    await page.route('**/api/v1/admin/**', async route => {
      assert.equal(route.request().method(), 'GET', 'No data writes');
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith('/event') && mode === 'hang') await new Promise(resolve => release.push(resolve));
      if (path.endsWith('/event') && mode === 'error') return route.fulfill({ status: 503, json: { detail: 'Сервер временно перегружен' } });
      if (path.endsWith('/final') && mode === 'section-error') return route.fulfill({ status: 500, json: { detail: 'Не удалось загрузить этап соревнования' } });
      return route.continue();
    });
    fs.mkdirSync('reports/crm-sync', { recursive: true });
    await page.goto('http://localhost:3000/admin');
    await page.locator('.crm-sync.is-pending').waitFor();
    await page.waitForTimeout(500);
    assert.equal(await page.locator('.crm-sync.is-current').count(), 0, 'No green status before the first response');
    mode = 'ok'; release.forEach(resolve => resolve()); release = [];
    await page.locator('.crm-sync.is-current').waitFor();
    await page.locator('.crm-sync summary').click();
    assert.match(await page.locator('.crm-sync-details').innerText(), /каждые 3 секунды/);
    await page.screenshot({ path: 'reports/crm-sync/online.png' });
    await page.locator('.crm-sync summary').click();
    mode = 'error';
    await page.locator('.crm-sync-alert').filter({ hasText: 'HTTP 503' }).waitFor();
    await page.getByRole('button', { name: 'Клубы', exact: true }).click();
    assert.match(await page.locator('.crm-sync-alert').innerText(), /Сервер временно перегружен/);
    await page.screenshot({ path: 'reports/crm-sync/server-error.png' });
    mode = 'ok';
    await page.locator('.crm-sync-alert').waitFor({ state: 'detached' });
    mode = 'section-error';
    await page.getByRole('button', { name: 'Квалификация', exact: true }).click();
    await page.locator('.crm-sync-alert').filter({ hasText: 'HTTP 500' }).waitFor();
    await page.waitForTimeout(3500);
    assert.equal(await page.locator('.crm-sync.has-error').count(), 1, 'Success of unrelated reads must not hide errors');
    mode = 'ok';
    await page.locator('.crm-sync-alert').waitFor({ state: 'detached' });
    await page.context().setOffline(true);
    await page.locator('.crm-sync-alert').filter({ hasText: 'Нет подключения' }).waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: 'reports/crm-sync/offline-mobile.png' });
    assert.ok(await page.locator('.crm-sync').isVisible());
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.context().setOffline(false);
    await page.locator('.crm-sync-alert').waitFor({ state: 'detached' });
    mode = 'hang';
    await page.locator('.crm-sync-alert').filter({ hasText: 'Обновление задерживается' }).waitFor({ timeout: 20000 });
    await page.screenshot({ path: 'reports/crm-sync/stale-mobile.png' });
    mode = 'ok';
    release.forEach(resolve => resolve());
    await page.locator('.crm-sync-alert').waitFor({ state: 'detached' });
    // Read-only visual role simulation: the common indicator must not depend on admin permissions.
    await page.route('**/api/v1/auth/me', async route => {
      const response = await route.fetch();
      const user = await response.json();
      await route.fulfill({ json: { ...user, role: 'reception', permissions: ['participants.view', 'participants.manage'] } });
    });
    mode = 'error';
    await page.reload();
    await page.locator('.crm-sync-alert').filter({ hasText: 'HTTP 503' }).waitFor();
    await page.screenshot({ path: 'reports/crm-sync/reception-error.png' });
    console.log('PASS: timings, HTTP 503, section HTTP 500, error persistence, offline, stale, recovery, mobile and reception role; no data writes.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
