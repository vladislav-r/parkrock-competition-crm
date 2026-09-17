const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1536, height: 1000 } });
    const login = await page.request.post('http://localhost:8001/api/v1/auth/login', { form: { username: 'admin@parkrock.test', password: 'demo1234' } });
    assert.ok(login.ok());
    const token = (await login.json()).access_token;
    await page.addInitScript(t => localStorage.setItem('parkrock_admin_token', t), token);
    let slow = false;
    await page.route('**/api/v1/auth/heartbeat', async route => {
      if (slow && route.request().method() === 'GET') await new Promise(resolve => setTimeout(resolve, 1200));
      return route.continue();
    });
    await page.goto('http://localhost:3000/admin');
    await page.getByRole('button', { name: 'Настройки', exact: true }).click();
    await page.locator('.users-with-presence').waitFor();
    const adminRow = page.locator('.user-row').filter({ hasText: 'admin@parkrock.test' });
    await adminRow.locator('.user-connection.online').waitFor({ timeout: 20000 });
    assert.match(await adminRow.innerText(), /Онлайн · [\d\s]+ мс/);
    fs.mkdirSync('reports/presence', { recursive: true });
    await page.screenshot({ path: 'reports/presence/online.png', fullPage: true });
    if (!process.argv.includes('--visual')) {
    slow = true;
    await adminRow.locator('.user-connection.unstable').waitFor({ timeout: 25000 });
    await page.screenshot({ path: 'reports/presence/unstable.png', fullPage: true });
    slow = false;
    await adminRow.locator('.user-connection.online').waitFor({ timeout: 25000 });
    // Stop this client's reports, but keep observing the server's real expiry.
    await page.route('**/api/v1/auth/heartbeat', route => route.abort());
    await adminRow.locator('.user-connection.offline').waitFor({ timeout: 105000 });
    assert.match(await adminRow.innerText(), /Оффлайн · был 1 мин. назад/);
    await page.screenshot({ path: 'reports/presence/offline.png', fullPage: true });
    await page.unroute('**/api/v1/auth/heartbeat');
    await adminRow.locator('.user-connection.online').waitFor({ timeout: 50000 });
    await page.route('**/api/v1/admin/users/presence', route => route.fulfill({ status: 503, json: { detail: 'Проверка недоступности' } }));
    await adminRow.locator('.user-connection.unknown').waitFor({ timeout: 10000 });
    await page.unroute('**/api/v1/admin/users/presence');
    await adminRow.locator('.user-connection.online').waitFor({ timeout: 10000 });
    }
    for (const width of [1280, 1024, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.screenshot({ path: `reports/presence/users-${width}.png`, fullPage: true });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `overflow at ${width}`);
    }
    console.log(process.argv.includes('--visual') ? 'PASS: real RTT and four viewport sizes.' : 'PASS: real measured RTT, slow response, expiry, recovery, observer failure, desktop/tablet/mobile.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
