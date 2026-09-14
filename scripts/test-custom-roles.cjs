const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1536, height: 960 } });
    const errors = [];
    page.on('pageerror', error => errors.push(String(error)));
    const login = await page.request.post('http://localhost:8001/api/v1/auth/login', { form: { username: 'admin@parkrock.test', password: 'demo1234' } });
    assert.equal(login.status(), 200);
    await page.addInitScript(token => localStorage.setItem('parkrock_admin_token', token), (await login.json()).access_token);
    let custom = null;
    await page.route('**/api/v1/admin/**', async route => {
      const request = route.request();
      const path = decodeURIComponent(new URL(request.url()).pathname);
      if (path.endsWith('/roles') && request.method() === 'POST') {
        assert.match(request.headers()['x-operation-id'] ?? '', /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i, 'Role creation must send X-Operation-Id');
        assert.equal(request.postDataJSON().name, 'Волонтёр');
        custom = { role: 'Волонтёр', permissions: [] };
        return route.fulfill({ status: 201, json: custom });
      }
      if (path.endsWith('/roles/Волонтёр/permissions')) {
        assert.equal(request.method(), 'PUT');
        custom.permissions = request.postDataJSON().permissions;
        return route.fulfill({ json: custom });
      }
      assert.equal(request.method(), 'GET', 'No writes to working data');
      if (path.endsWith('/roles')) {
        const response = await route.fetch();
        const matrix = await response.json();
        if (custom) matrix.roles.push(custom);
        return route.fulfill({ response, json: matrix });
      }
      return route.continue();
    });
    await page.goto('http://localhost:3000/admin');
    await page.getByRole('button', { name: 'Настройки', exact: true }).click();
    await page.getByRole('button', { name: 'Добавить роль', exact: true }).click();
    await page.getByLabel('Название роли').fill('Волонтёр');
    fs.mkdirSync('reports/custom-roles', { recursive: true });
    await page.screenshot({ path: 'reports/custom-roles/create.png' });
    await page.getByRole('button', { name: 'Создать роль', exact: true }).click();
    await page.locator('.role-list button.active').filter({ hasText: 'Волонтёр' }).waitFor();
    const checkbox = page.locator('.permission-group input[type=checkbox]').first();
    await checkbox.check();
    await page.getByRole('button', { name: /Сохранить/ }).last().click();
    await page.getByRole('alertdialog').waitFor();
    await page.getByRole('alertdialog').getByRole('button').last().click();
    await page.waitForFunction(() => !document.querySelector('[role=alertdialog]'));
    assert.ok(custom.permissions.length > 0);
    await page.screenshot({ path: 'reports/custom-roles/permissions.png', fullPage: true });
    await page.locator('.settings-relief-sidebar').getByRole('button', { name: 'Пользователи', exact: true }).click();
    await page.getByRole('button', { name: 'Добавить', exact: true }).click();
    await page.locator('select[name=role]').selectOption('Волонтёр');
    assert.equal(await page.locator('select[name=role]').inputValue(), 'Волонтёр');
    await page.screenshot({ path: 'reports/custom-roles/assignment.png' });
    await page.locator('.user-editor .dialog-close').click();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('button', { name: 'Добавить роль', exact: true }).click();
    await page.screenshot({ path: 'reports/custom-roles/mobile.png', fullPage: true });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.deepEqual(errors, []);
    console.log('PASS: role creation, permissions, assignment, mobile; writes mocked, working data untouched.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
