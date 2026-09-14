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
    const people = await (await page.request.get('http://localhost:8001/api/v1/admin/participants', { headers })).json();
    assert.ok(people.length, 'Use existing data read-only for UI shape');
    const person = { ...people[0], surname: 'Проверочный', name: 'Участник', patronymic: '', club: 'Проверочный клуб' };
    const club = { id: '00000000-0000-4000-8000-000000000099', version: 1, name: 'Проверочный клуб', representative: 'Представитель', participant_count: 1, collective_count: 0, checked_in_count: 0, paid_count: 0, merch_issued_count: 0, members: [{ id: person.id, version: person.version, start_number: person.start_number, full_name: 'Проверочный Участник', set_id: person.set_id, set_name: 'Сет 1', application_type: 'individual', checked_in: false, is_paid: false, merch_size: null, merch_issued: false }] };
    let stage = 'preparation', participantDeleted = false, clubDeleted = false, uploads = 0;
    let applications = [];
    const mutations = [];
    await page.addInitScript(t => localStorage.setItem('parkrock_admin_token', t), token);
    await page.route('**/api/v1/admin/**', async route => {
      const req = route.request(), path = new URL(req.url()).pathname;
      if (req.method() !== 'GET') {
        mutations.push({ method: req.method(), path, body: req.postDataJSON && req.headers()['content-type']?.includes('application/json') ? req.postDataJSON() : null });
        if (req.method() === 'DELETE' && path.includes('/participants/')) { participantDeleted = true; return route.fulfill({ json: { status: 'deleted' } }); }
        if (req.method() === 'DELETE' && path.includes('/clubs/')) { clubDeleted = true; return route.fulfill({ json: { status: 'deleted', deleted_participants: 1 } }); }
        if (req.method() === 'POST' && path === '/api/v1/admin/applications') {
          uploads++;
          if (uploads === 1) return route.fulfill({ status: 422, json: { detail: { message: 'В заявке есть ошибки', rows: [{ row_number: 10, errors: { Пол: 'Укажите М или Ж' }, values: {}, duplicate: false, valid: false }] } } });
          applications = [{ id: 'application-test', filename: 'Заявка.xlsx', file_size: 123, participant_count: 1, duplicate_rows: 0, overflow_sets: 0, status: 'pending', uploaded_at: new Date().toISOString(), imported_at: null, import_count: 0 }];
          return route.fulfill({ status: 201, json: applications[0] });
        }
        throw Error(`Unexpected write blocked: ${req.method()} ${path}`);
      }
      if (path.endsWith('/event')) return route.fulfill({ json: { ...event, stage, qualification_started_at: stage === 'preparation' ? null : new Date().toISOString(), final_started_at: null } });
      if (path.endsWith('/participants')) return route.fulfill({ json: participantDeleted ? [] : [person] });
      if (path.endsWith('/clubs')) return route.fulfill({ json: clubDeleted ? [] : [club] });
      if (path.endsWith('/applications')) return route.fulfill({ json: applications });
      return route.continue();
    });
    fs.mkdirSync('reports/crm-deletion-upload', { recursive: true });
    await page.goto('http://localhost:3000/admin');
    await page.getByRole('button', { name: `Действия участника №${person.start_number}` }).click();
    await page.getByRole('menuitem', { name: 'Удалить', exact: true }).click();
    await page.getByRole('alertdialog').waitFor();
    assert.match(await page.getByRole('alertdialog').innerText(), /Проверочный Участник/);
    await page.screenshot({ path: 'reports/crm-deletion-upload/participant-delete.png' });
    await page.getByRole('button', { name: 'Удалить участника', exact: true }).click();
    await page.getByRole('alertdialog').waitFor({ state: 'detached' });
    assert.equal(participantDeleted, true);
    await page.getByRole('button', { name: 'Клубы', exact: true }).click();
    const menu = () => page.getByRole('button', { name: 'Действия клуба Проверочный клуб', exact: true });
    await menu().click();
    await page.locator('.club-menu-popup:popover-open').getByRole('button', { name: 'Редактировать клуб' }).click();
    await page.getByRole('alertdialog').waitFor();
    assert.equal(await page.getByRole('alertdialog').getByRole('textbox').first().inputValue(), club.name);
    await page.getByRole('button', { name: 'Отмена', exact: true }).click();
    await menu().click();
    await page.locator('.club-menu-popup:popover-open').getByRole('button', { name: 'Удалить', exact: true }).click();
    assert.match(await page.getByRole('alertdialog').innerText(), /независимо от выбранных строк/);
    await page.screenshot({ path: 'reports/crm-deletion-upload/club-delete.png' });
    await page.getByRole('button', { name: 'Удалить клуб и участников', exact: true }).click();
    await page.getByRole('alertdialog').waitFor({ state: 'detached' });
    assert.equal(clubDeleted, true);
    assert.deepEqual(mutations.find(m => m.path.includes('/clubs/')).body.expected_versions, { [person.id]: person.version });
    stage = 'qualification'; participantDeleted = false; clubDeleted = false;
    await page.reload();
    await page.getByRole('button', { name: `Действия участника №${person.start_number}` }).click();
    assert.ok(await page.getByRole('menuitem', { name: 'Удалить', exact: true }).isDisabled());
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Клубы', exact: true }).click();
    await menu().click();
    assert.ok(await page.locator('.club-menu-popup:popover-open').getByRole('button', { name: 'Удалить', exact: true }).isDisabled());
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Заявки', exact: true }).click();
    await page.getByRole('button', { name: 'Импорт', exact: true }).click();
    await page.getByRole('dialog').waitFor();
    await page.getByLabel('Файл заявки').setInputFiles({ name: 'Заявка.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('mock') });
    await page.getByRole('alert').filter({ hasText: 'Укажите М или Ж' }).waitFor();
    await page.screenshot({ path: 'reports/crm-deletion-upload/upload-validation.png' });
    const dataTransfer = await page.evaluateHandle(() => { const dt = new DataTransfer(); dt.items.add(new File(['mock'], 'Заявка.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })); return dt; });
    await page.locator('.application-drop-zone').dispatchEvent('drop', { dataTransfer });
    await page.getByRole('dialog').waitFor({ state: 'detached' });
    await page.locator('.applications-table').getByText('Заявка.xlsx', { exact: true }).waitFor();
    assert.equal(uploads, 2);
    assert.ok(!mutations.some(m => m.path.endsWith('/import')));
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('button', { name: 'Импорт', exact: true }).click();
    await page.getByRole('dialog').waitFor();
    await page.screenshot({ path: 'reports/crm-deletion-upload/upload-mobile.png' });
    const box = await page.getByRole('dialog').boundingBox();
    assert.ok(box.x >= 0 && box.x + box.width <= 390);
    console.log('OK: deletion menus, confirmation payloads, stage guards, club editor, file selection, validation, drag and drop, mobile. All CRM writes mocked.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
