// Run after rebuilding the frontend. Settings writes and all public data are mocked.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const output = path.resolve(__dirname, '../reports/public-display');
const origin = process.env.TEST_ORIGIN || 'http://localhost:3000';
const api = process.env.TEST_API_ORIGIN || 'http://localhost:8001';
const defaults = { tv_interval_seconds: 23, tv_stage: 'final', tv_teams: true, tv_rows_per_column: 5,
  tv_max_columns: 1, tv_controls_hide_seconds: 3, tv_highlight_top: 3, sponsors_enabled: false,
  tv_sponsors_enabled: false, sponsor_featured_seconds: 61, sponsor_regular_seconds: 79,
  tv_sponsor_featured_seconds: 83, tv_sponsor_regular_seconds: 97 };
const meta = { publication_version: '10000000-0000-4000-8000-000000000001', published_at: '2026-01-01T04:05:06Z' };
const rows = Array.from({ length: 18 }, (_, i) => ({ participant_id: `participant-${i}`, place: i + 1,
  start_number: i + 1, full_name: `Участник Проверочный ${i + 1}`, club: 'Скалолазы', group_name: 'Мужчины',
  points: 200 - i, score: 90 - i, has_result: true, completed_count: 2, is_finalist: i < 3,
  is_finisher: false, medal: null, set_id: null, qualification_place: i + 1, exit_order: i + 1, attempts: [] }));
const main = { ...meta, event_id: '30000000-0000-4000-8000-000000000001', event_title: 'Проверка настроек показа',
  location: 'Скалодром', starts_on: '2026-01-01', stage: 'final', details_enabled: true,
  groups: ['Мужчины'], final_groups: ['Мужчины'], results: rows, sets: [],
  qualification_refresh_seconds: 3, final_refresh_seconds: 3, public_display_settings: defaults };

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const logs = [], errors = [];
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'no-preference' });
    const login = await context.request.post(`${api}/api/v1/auth/login`, { form: { username: 'admin@parkrock.test', password: 'demo1234' } });
    assert.ok(login.ok(), `Login ${login.status()}`);
    const { access_token: token } = await login.json();
    const eventResponse = await context.request.get(`${api}/api/v1/admin/event`, { headers: { Authorization: `Bearer ${token}` } });
    assert.ok(eventResponse.ok(), `Read event ${eventResponse.status()}`);
    let event = await eventResponse.json();
    const originalVersion = event.version;
    let payload;
    await context.addInitScript(value => localStorage.setItem('parkrock_admin_token', value), token);
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/v1/admin/event', route => route.fulfill({ json: event }));
    await page.route('**/api/v1/admin/event/public-refresh', route => {
      assert.equal(route.request().method(), 'PATCH');
      payload = route.request().postDataJSON();
      assert.ok(route.request().headers()['x-operation-id']);
      event = { ...event, ...payload, version: event.version + 1 };
      delete event.expected_version;
      return route.fulfill({ json: event });
    });
    const noOverflow = async label => assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${label}: horizontal overflow`);
    const shot = name => page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
    await page.goto(`${origin}/admin`);
    await page.getByRole('button', { name: 'Настройки', exact: true }).click();
    await page.getByRole('button', { name: 'Сайт и ТВ', exact: true }).click();
    const input = page.getByLabel('Время одного экрана, сек.', { exact: true });
    await input.waitFor();
    for (const label of ['Квалификация, сек.', 'Финал, сек.', 'Начальный этап', 'Максимум строк в колонке', 'Максимум колонок', 'Выделять первые места', 'Скрывать управление через, сек.', 'Цикл верхнего ряда, сек.', 'Цикл нижнего ряда, сек.', 'Цикл верхнего ряда ТВ, сек.', 'Цикл нижнего ряда ТВ, сек.']) {
      assert.equal(await page.getByLabel(label, { exact: true }).count(), 1, `Accessible label: ${label}`);
    }
    const help = page.getByRole('button', { name: 'О параметре «Время одного экрана, сек.»', exact: true });
    await help.hover();
    await page.getByRole('tooltip').waitFor();
    assert.match(await page.getByRole('tooltip').innerText(), /время смены экранов/);
    await shot('admin-desktop-tooltip');
    await input.click();
    await page.getByRole('tooltip').waitFor({ state: 'hidden' });
    await help.click();
    await page.getByRole('tooltip').waitFor();
    await page.keyboard.press('Escape');
    await page.getByRole('tooltip').waitFor({ state: 'hidden' });
    await noOverflow('admin desktop');
    await input.fill('23');
    await page.getByRole('button', { name: 'Сохранить настройки показа', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('.public-settings-save button')?.disabled === true);
    assert.equal(payload.public_display_settings.tv_interval_seconds, 23);
    assert.equal(payload.expected_version, originalVersion);
    assert.equal(await input.inputValue(), '23');
    await shot('admin-desktop');
    await page.setViewportSize({ width: 375, height: 900 });
    await noOverflow('admin mobile');
    assert.ok((await page.locator('.settings-relief-sidebar').boundingBox()).height < 650, 'Compact settings navigation');
    await help.click();
    await page.getByRole('tooltip').waitFor();
    await noOverflow('admin mobile tooltip');
    await shot('admin-mobile-tooltip');
    await page.keyboard.press('Escape');
    logs.push('PASS admin: labelled fields, hover/click/Escape help, mocked versioned save, desktop/mobile 375px.');

    await page.route('**/api/v1/public/**', route => {
      const endpoint = new URL(route.request().url()).pathname.split('/').at(-1);
      if (endpoint === 'results') return route.fulfill({ json: main });
      if (endpoint === 'final-results') return route.fulfill({ json: { ...meta, category_name: 'Мужчины', routes: [], results: rows } });
      if (endpoint === 'team-results') return route.fulfill({ json: { ...meta, stage: 'final', available: true, quota: 3, reason: '', issues: [], sources: [], results: [] } });
      return route.fulfill({ status: 404, json: { detail: 'Mock endpoint not supplied' } });
    });
    await page.goto(origin);
    await page.locator('.sand-category').first().waitFor();
    assert.equal(await page.locator('.sponsor-strip').count(), 0);
    await noOverflow('public mobile hidden sponsors');
    await shot('site-mobile-hidden-partners');
    defaults.sponsors_enabled = true;
    await page.locator('.sponsor-strip').waitFor({ timeout: 10000 });
    assert.equal(await page.locator('.sponsor-featured .sponsor-track').evaluate(el => getComputedStyle(el).animationDuration), '61s');
    assert.equal(await page.locator('.sponsor-row:not(.sponsor-featured) .sponsor-track').evaluate(el => getComputedStyle(el).animationDuration), '79s');
    await page.setViewportSize({ width: 1440, height: 1000 });
    await shot('site-desktop-partners');
    logs.push('PASS website: live visibility and separate 61s/79s sponsor cycles.');

    await page.goto(`${origin}/tv`);
    await page.waitForFunction(() => document.querySelector('.tv-fields input')?.value === '23');
    assert.equal(await page.getByRole('combobox', { name: /^Этап/ }).inputValue(), 'final');
    assert.equal(await page.getByLabel('Командный зачёт', { exact: false }).isChecked(), true);
    assert.equal(await page.locator('.sponsor-strip').count(), 0);
    await shot('tv-defaults');
    await page.goto(`${origin}/tv?stage=qualification&interval=120&groups=all`);
    await page.getByText('Мужчины', { exact: true }).waitFor();
    assert.equal(await page.getByLabel('Время экрана, секунд', { exact: false }).inputValue(), '120');
    assert.equal(await page.getByRole('combobox', { name: /^Этап/ }).inputValue(), 'qualification');
    assert.equal(await page.getByLabel('Командный зачёт', { exact: false }).isChecked(), false);
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto(`${origin}/tv?stage=qualification&interval=120&groups=all&autoplay=1`);
    await page.locator('.tv-columns table').waitFor();
    assert.equal(await page.locator('.tv-columns table').count(), 1);
    assert.ok(await page.locator('.tv-columns tbody tr').count() <= 5);
    assert.equal(await page.locator('.tv-columns .tv-leader').count(), 3);
    assert.equal(await page.locator('.tv-partners, .sponsor-strip').count(), 0);
    await noOverflow('TV desktop');
    await shot('tv-desktop-five-rows');
    await page.setViewportSize({ width: 375, height: 900 });
    await noOverflow('TV mobile');
    await shot('tv-mobile-five-rows');
    logs.push('PASS TV: API defaults, explicit URL priority, legacy teams=false, one column/up to five rows/top three highlighted, hidden sponsors.');
    assert.deepEqual(errors, [], 'No browser runtime errors');
    fs.writeFileSync(path.join(output, 'browser-check.txt'), [...logs, 'No settings or competition data were written to the server. Login created an ordinary session.'].join('\n') + '\n');
    console.log(logs.join('\n'));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });


