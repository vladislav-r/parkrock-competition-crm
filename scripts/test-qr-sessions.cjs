// Uses only the disposable climbhub_qr_ui_test backend on :8002.
// QR decoding requires zxing-cpp on PYTHONPATH (test-only, not an app dependency).
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const report = path.resolve('reports/qr-sessions');
const python = path.resolve('backend/.venv/Scripts/python.exe');
const site = 'http://localhost:3000';
const api = 'http://localhost:8002';

(async () => {
  fs.mkdirSync(report, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const errors = [];
  async function context(viewport = { width: 1536, height: 1000 }) {
    const ctx = await browser.newContext({ viewport });
    await ctx.route('http://localhost:8001/**', async route => {
      const response = await route.fetch({ url: route.request().url().replace('http://localhost:8001', api) });
      await route.fulfill({ response });
    });
    ctx.on('page', page => page.on('pageerror', error => errors.push(error.message)));
    return ctx;
  }
  async function dismissGuide(page) {
    const close = page.getByRole('button', { name: 'Перейти к работе', exact: true });
    if (await close.isVisible().catch(() => false)) await close.click();
  }
  try {
    const ownerContext = await context();
    const owner = await ownerContext.newPage();
    await owner.goto(`${site}/admin`);
    await owner.locator('input[name=email]').fill('admin@test.local');
    await owner.locator('input[name=password]').fill('test-password');
    await owner.getByRole('button', { name: 'Войти', exact: true }).click();
    await owner.locator('.admin-header').waitFor();
    await dismissGuide(owner);
    await owner.getByRole('button', { name: 'Настройки', exact: true }).click();
    const row = owner.locator('.user-row').filter({ hasText: 'qr-ui@staff.test' });
    await row.waitFor();
    async function menu(name) {
      await row.getByRole('button', { name: 'Действия пользователя Судья QR Проверка' }).click();
      await row.getByRole('button', { name, exact: true }).click();
    }
    await menu('Настройки QR');
    await owner.getByLabel('Длительность сеанса, часов').fill('2');
    await owner.getByRole('button', { name: 'Сохранить', exact: true }).click();
    await owner.getByRole('alertdialog').waitFor({ state: 'hidden' });
    await menu('Настройки QR');
    assert.equal(await owner.getByLabel('Длительность сеанса, часов').inputValue(), '2');
    await owner.screenshot({ path: `${report}/settings.png` });
    await owner.getByRole('button', { name: 'Отмена', exact: true }).click();
    await menu(/^(Выпустить|Перевыпустить) QR$/);
    const issuedResponse = owner.waitForResponse(response => response.url().endsWith('/admin/users/qr/issue') && response.status() === 200);
    await owner.getByRole('alertdialog').getByRole('button', { name: /^(Выпустить|Перевыпустить) QR$/ }).click();
    const issued = await (await issuedResponse).json();
    await owner.getByText('QR-карточки готовы', { exact: true }).waitFor();
    await owner.locator('.qr-card img[alt^="Персональный QR"]').screenshot({ path: `${report}/qr.png` });
    fs.writeFileSync(`${report}/cards.pdf`, Buffer.from(issued.pdf_base64, 'base64'));
    const qrUrl = execFileSync(python, ['-c', 'from PIL import Image; import zxingcpp,sys; result=zxingcpp.read_barcode(Image.open(sys.argv[1])); assert result; print(result.text)', `${report}/qr.png`], { encoding: 'utf8' }).trim();
    assert.ok(qrUrl.startsWith(`${site}/login/qr#key=`));
    await owner.screenshot({ path: `${report}/cards.png` });
    await owner.getByRole('alertdialog').locator('.dialog-actions').getByRole('button', { name: 'Закрыть', exact: true }).click();

    const device1 = await context({ width: 390, height: 844 });
    const first = await device1.newPage();
    await first.goto(qrUrl);
    await first.getByText('Судья QR Проверка', { exact: true }).waitFor();
    assert.equal(new URL(first.url()).hash, '');
    assert.ok((await first.locator('.login-panel').innerText()).includes('2 ч.'));
    await first.screenshot({ path: `${report}/login-mobile.png` });
    await first.getByRole('button', { name: 'Войти', exact: true }).click();
    await first.locator('.admin-header').waitFor();
    const firstToken = await first.evaluate(() => localStorage.getItem('parkrock_admin_token'));

    const device2 = await context();
    const second = await device2.newPage();
    await second.goto(qrUrl);
    await second.getByRole('button', { name: 'Войти', exact: true }).click();
    await second.locator('.admin-header').waitFor();
    await first.locator('.login-panel').waitFor({ timeout: 20000 });
    assert.match(await first.locator('.form-error').innerText(), /другом устройстве/);
    assert.equal((await owner.request.get(`${api}/api/v1/auth/me`, { headers: { Authorization: `Bearer ${firstToken}` } })).status(), 401);
    await first.screenshot({ path: `${report}/replaced-session.png` });

    // Wait for live session status to reach the menu, then terminate it without revoking QR.
    await row.getByText('QR выпущен · Сеанс активен').waitFor();
    await menu('Завершить сеанс');
    await owner.getByRole('alertdialog').getByRole('button', { name: 'Завершить сеанс', exact: true }).click();
    await second.locator('.login-panel').waitFor({ timeout: 20000 });
    assert.match(await second.locator('.form-error').innerText(), /администратором/);
    await second.goto(qrUrl);
    await second.getByRole('button', { name: 'Войти', exact: true }).click();
    await second.locator('.admin-header').waitFor();
    await menu('Отозвать QR');
    await owner.getByLabel('Также завершить текущие сеансы').check();
    await owner.getByRole('alertdialog').getByRole('button', { name: 'Отозвать QR', exact: true }).click();
    await second.locator('.login-panel').waitFor({ timeout: 20000 });
    await second.goto(qrUrl);
    await second.locator('.form-error').waitFor();
    assert.match(await second.locator('.form-error').innerText(), /недействителен/);
    await second.screenshot({ path: `${report}/revoked.png` });

    await row.getByRole('button', { name: 'Действия пользователя Судья QR Проверка' }).click();
    assert.ok(await row.getByRole('button', { name: 'Завершить сеанс', exact: true }).isDisabled());
    await owner.screenshot({ path: `${report}/menu.png` });
    await owner.keyboard.press('Escape');
    for (const width of [1024, 390]) {
      await owner.setViewportSize({ width, height: 1000 });
      await row.getByRole('button', { name: 'Действия пользователя Судья QR Проверка' }).click();
      await owner.screenshot({ path: `${report}/menu-${width}.png` });
      assert.ok(await owner.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `overflow at ${width}`);
      await owner.keyboard.press('Escape');
    }
    await owner.setViewportSize({ width: 1536, height: 1000 });
    await owner.getByRole('checkbox', { name: 'Выбрать QR: Судья QR Проверка' }).check();
    await owner.getByRole('checkbox', { name: 'Выбрать QR: Тестовый администратор' }).check();
    await owner.getByRole('button', { name: 'Выпустить QR выбранным (2)' }).click();
    const batchResponse = owner.waitForResponse(response => response.url().endsWith('/admin/users/qr/issue') && response.status() === 200);
    await owner.getByRole('alertdialog').getByRole('button', { name: /^(Выпустить|Перевыпустить) QR$/ }).click();
    const batch = await (await batchResponse).json();
    assert.equal(batch.cards.length, 2);
    fs.writeFileSync(`${report}/batch.pdf`, Buffer.from(batch.pdf_base64, 'base64'));
    await owner.getByText('QR-карточки готовы', { exact: true }).waitFor();
    await owner.screenshot({ path: `${report}/batch.png` });
    assert.deepEqual(errors, []);
    console.log('PASS: real QR decode, settings, two devices, automatic logout, forced logout, revoke, batch PDF, mobile/tablet, no JS errors.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
