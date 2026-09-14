const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1536, height: 960 } });
    const login = await page.request.post('http://localhost:8001/api/v1/auth/login', { form: { username: 'admin@parkrock.test', password: 'demo1234' } });
    assert.ok(login.ok());
    const token = (await login.json()).access_token;
    const headers = { Authorization: `Bearer ${token}` };
    const event = await (await page.request.get('http://localhost:8001/api/v1/admin/event', { headers })).json();
    let uploads = 0;
    let applications = [];
    const mutations = [];
    await page.addInitScript(t => localStorage.setItem('parkrock_admin_token', t), token);
    await page.route('**/api/v1/admin/**', async route => {
      const req = route.request(), path = new URL(req.url()).pathname;
      if (req.method() !== 'GET') {
        mutations.push({ method: req.method(), path, body: req.postDataJSON && req.headers()['content-type']?.includes('application/json') ? req.postDataJSON() : null });
        if (req.method() === 'POST' && path === '/api/v1/admin/applications') {
          uploads++;
          if (uploads === 1) return route.fulfill({ status: 422, json: { detail: { message: 'В заявке есть ошибки', rows: [{ row_number: 10, errors: { Пол: 'Укажите М или Ж' }, values: {}, duplicate: false, valid: false }] } } });
          applications = [{ id: 'application-test', filename: 'Заявка.xlsx', file_size: 123, participant_count: 1, duplicate_rows: 0, overflow_sets: 0, status: 'pending', uploaded_at: new Date().toISOString(), imported_at: null, import_count: 0 }];
          return route.fulfill({ status: 201, json: applications[0] });
        }
        throw Error(`Unexpected write blocked: ${req.method()} ${path}`);
      }
      if (path.endsWith('/event')) return route.fulfill({ json: event });
      if (path.endsWith('/applications')) return route.fulfill({ json: applications });
      return route.continue();
    });
    fs.mkdirSync('reports/crm-applications', { recursive: true });
    await page.goto('http://localhost:3000/admin');
    await page.getByRole('button', { name: 'Заявки', exact: true }).click();
    await page.getByRole('button', { name: 'Импорт', exact: true }).click();
    await page.getByRole('dialog').waitFor();
    await page.getByLabel('Файл заявки').setInputFiles({ name: 'Заявка.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('mock') });
    await page.getByRole('alert').filter({ hasText: 'Укажите М или Ж' }).waitFor();
    await page.screenshot({ path: 'reports/crm-applications/upload-validation.png' });
    const dataTransfer = await page.evaluateHandle(() => { const dt = new DataTransfer(); dt.items.add(new File(['mock'], 'Заявка.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })); return dt; });
    await page.locator('.application-drop-zone').dispatchEvent('drop', { dataTransfer });
    await page.getByRole('dialog').waitFor({ state: 'detached' });
    await page.locator('.applications-table').getByText('Заявка.xlsx', { exact: true }).waitFor();
    assert.equal(uploads, 2);
    assert.ok(!mutations.some(m => m.path.endsWith('/import')));
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('button', { name: 'Импорт', exact: true }).click();
    await page.getByRole('dialog').waitFor();
    await page.screenshot({ path: 'reports/crm-applications/upload-mobile.png' });
    const box = await page.getByRole('dialog').boundingBox();
    assert.ok(box.x >= 0 && box.x + box.width <= 390);
    console.log('OK: application file selection, validation, drag and drop, no participant import, mobile. All CRM writes mocked.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
