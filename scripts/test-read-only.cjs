const { chromium } = require('playwright');
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const assert = require('node:assert/strict');

(async () => {
  assert.ok(process.env.VIEWER_NAME, 'Set VIEWER_NAME to the existing read-only user');
  // Short-lived local session, without changing the account password or data.
  const token = execFileSync(path.resolve('backend/.venv/Scripts/python.exe'), ['-X', 'utf8', '-c', `import os
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Admin
from app.permissions import Permission, effective_permissions
from app.security import create_access_token
with SessionLocal() as db:
 user = db.scalars(select(Admin).where(Admin.full_name == os.environ['VIEWER_NAME'])).one()
 assert Permission.system_read_only in effective_permissions(db, user.role)
 print(create_access_token(str(user.id)))`], { cwd: path.resolve('backend'), encoding: 'utf8' }).trim();
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1536, height: 960 } });
    const errors = [], denied = [];
    page.on('pageerror', error => errors.push(String(error)));
    page.on('response', response => { if (response.url().includes('/api/v1/admin') && response.status() >= 400) denied.push([response.status(), response.url()]); });
    await page.addInitScript(t => localStorage.setItem('parkrock_admin_token', t), token);
    await page.route('**/api/v1/admin/**', route => { assert.equal(route.request().method(), 'GET', 'Read-only UI must not send writes'); return route.continue(); });
    fs.mkdirSync('reports/read-only', { recursive: true });
    const deniedWrite = await page.request.post('http://localhost:8001/api/v1/admin/roles', { headers: { Authorization: `Bearer ${token}` }, data: {} });
    assert.equal(deniedWrite.status(), 403);
    await page.goto('http://localhost:3000/admin');
    await page.getByText('Только просмотр', { exact: true }).waitFor();
    async function check(name) {
      await page.waitForTimeout(350);
      const active = await page.locator('main').locator('button:not([data-view-action]):enabled, input:not([data-view-action]):enabled, select:not([data-view-action]):enabled, textarea:not([data-view-action]):enabled').evaluateAll(elements => elements.filter(e => !e.closest('form[data-view-action]') && e.getBoundingClientRect().width > 0 && !e.closest('nextjs-portal')).map(e => e.outerHTML.slice(0,130)));
      assert.deepEqual(active, [], name);
      await page.screenshot({ path: `reports/read-only/${name}.png`, fullPage: true });
    }
    for (const label of ['Участники', 'Клубы', 'Заявки', 'Квалификация', 'Финал', 'Выгрузки', 'Трассы', 'Категории', 'Резервные копии', 'Настройки']) {
      await page.getByRole('button', { name: label, exact: true }).first().click();
      await check(label);
      if (label === 'Участники') { await page.locator('.participant-row').first().click(); await check('participant-card'); }
      if (label === 'Финал') { for (const button of await page.locator('.final-sidebar button').all()) { if (await button.isEnabled()) { await button.click(); await check(`final-${await button.innerText()}`); } } }
      if (label === 'Квалификация') { for (const button of await page.locator('.qualification-sidebar button[data-view-action]').all()) { if (await button.isEnabled()) await button.click(); } }
    }
    for (const label of ['Пользователи','Права','Журнал','Публичные результаты','Командный зачёт','Настройка выгрузок','Соревнования','Демо-данные']) {
      await page.locator('.settings-relief-sidebar').getByRole('button', { name: label, exact: true }).click();
      await check(`settings-${label}`);
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await check('mobile');
    assert.deepEqual(errors, []);
    assert.deepEqual(denied, []);
    console.log('PASS: real viewer session; all CRM sections and eight settings tabs; controls disabled; GET only.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
