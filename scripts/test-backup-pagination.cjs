const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(String(error)));
    const items = Array.from({ length: 123 }, (_, i) => ({ filename: `fixture-${i + 1}.dump`, created_at: new Date(Date.UTC(2026, 8, 20, -i)).toISOString(), source: i % 2 ? 'manual' : 'automatic', size_bytes: 1024, note: `Копия ${i + 1}`, verified_at: null }));
    await page.addInitScript(() => localStorage.setItem('parkrock_admin_token', 'fixture'));
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname;
      assert.ok(route.request().method() === 'GET' || path.endsWith('/auth/heartbeat'));
      let json = [];
      if (path.endsWith('/auth/me')) json = { id: 'fixture', full_name: 'Тест', role: 'administrator', permissions: ['participants.view', 'backups.manage'] };
      if (path.endsWith('/admin/event')) json = { id: 'fixture', stage: 'preparation', sets: [], groups: [], routes: [], participant_count: 0 };
      if (path.endsWith('/admin/backups')) json = { items, current: { counts: {}, event: { stage: 'preparation' } } };
      await route.fulfill({ json });
    });
    await page.goto('http://127.0.0.1:3000/admin');
    await page.locator('#admin-navigation').getByRole('button', { name: 'Резервные копии', exact: true }).click();
    const nav = page.getByRole('navigation', { name: 'Страницы: Резервные копии' });
    const rows = page.locator('.backup-saved-table tbody tr');
    await page.waitForFunction(() => document.querySelectorAll('.backup-saved-table tbody tr').length === 50);
    await page.locator('.backup-table-scroll').evaluate(el => { el.scrollTop = 200; });
    await nav.getByLabel('Последняя страница', { exact: true }).click();
    assert.equal(await rows.count(), 23);
    assert.equal(await page.locator('.backup-table-scroll').evaluate(el => el.scrollTop), 0);
    assert.match(await rows.first().innerText(), /Копия 101/);
    await page.getByLabel('Найти резервную копию').fill('Копия 123');
    assert.equal(await rows.count(), 1);
    await page.getByLabel('Найти резервную копию').fill('');
    assert.match(await nav.innerText(), /1–50 из 123/);
    await nav.getByLabel('Записей на странице: Резервные копии').selectOption('25');
    assert.equal(await rows.count(), 25);
    await page.getByLabel('Тип копии', { exact: true }).selectOption('automatic');
    assert.match(await nav.innerText(), /1–25 из 62/);
    await page.setViewportSize({ width: 390, height: 844 });
    await nav.scrollIntoViewIfNeeded();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    fs.mkdirSync('reports/admin-pagination', { recursive: true });
    await page.screenshot({ path: 'reports/admin-pagination/backups-mobile.png', fullPage: true });
    assert.deepEqual(errors, []);
    console.log('Backup pagination: page navigation, size, search, source filter, mobile passed. Mock API only.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
