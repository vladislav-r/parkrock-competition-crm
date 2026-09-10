// NODE_PATH must include Playwright. All API responses are isolated test fixtures.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1050 } });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let role = 'secretary';
    let downloaded = [];
    const item = (key, title, block, reason = '', warnings = []) => ({ key, title, block, reason, warnings, row_count: 2, available: !reason });
    const items = [
      item('qualification:g1', 'М 10–12', 'qualification'), item('qualification:g2', 'Женщины', 'qualification'),
      item('final:g1', 'М 10–12', 'final', 'Финал ещё не начат'),
      item('absolute:qualification', 'Абсолют · квалификация', 'absolute', '', ['Без результата: 1 участник; его место останется пустым.']),
      item('absolute:final', 'Абсолют · финал', 'absolute', 'Финал ещё не начат'),
      item('absolute:overall', 'Абсолют · соревнование', 'absolute', 'Итог соревнования доступен после завершения фестиваля'),
      ...['Все участники', 'Участники по клубам', 'Финалисты', 'Финишеры с медалями', 'Оплатившие участники', 'Неоплатившие участники', 'Участники с выданным мерчем'].map((name, i) => item(`other:${i}`, name, 'other')),
    ];
    await page.route('**/api/v1/**', async route => {
      const url = new URL(route.request().url());
      const respond = body => route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
      if (route.request().method() === 'OPTIONS') return respond({});
      if (url.pathname === '/api/v1/auth/me') return respond({ id: 'staff', role, full_name: 'Секретарь', permissions: ['dashboard.view', 'participants.view', 'exports.create'] });
      if (url.pathname === '/api/v1/admin/event') return respond({ id: 'event', title: 'ПаркРок', location: 'Хабаровск', stage: 'qualification', version: 1, sets: [], routes: [], groups: [], participant_count: 0 });
      if (url.pathname === '/api/v1/admin/participants') return respond([]);
      if (url.pathname === '/api/v1/admin/exports/catalog') return respond({ stage: 'qualification', items });
      if (url.pathname.startsWith('/api/v1/admin/exports/files/')) {
        downloaded.push(url);
        return route.fulfill({ contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', body: Buffer.from('test-download') });
      }
      if (url.pathname === '/api/v1/public/absolute-results') {
        const stage = url.searchParams.get('stage');
        return respond({ stage, event_stage: 'final', available: true, provisional: true, results: [
          { participant_id: 'p1', start_number: 10, full_name: 'Иванов Александр', club: 'Клуб скалолазания', group_name: 'М 10–12', qualification_points: 300, final_points: 24.9, score: stage === 'overall' ? 324.9 : stage === 'final' ? 24.9 : 300, place: 1, has_result: true },
          { participant_id: 'p2', start_number: 42, full_name: 'Петрова Мария', club: 'Ерофей', group_name: 'Женщины', qualification_points: 200, final_points: null, score: stage === 'overall' ? 200 : stage === 'final' ? null : 200, place: stage === 'final' ? null : 2, has_result: stage !== 'final' },
        ] });
      }
      throw new Error(`Unexpected API request: ${url.pathname}`);
    });
    await page.goto('http://127.0.0.1:3000/admin');
    await page.evaluate(() => localStorage.setItem('parkrock_admin_token', 'test-token'));
    await page.reload();
    await page.getByRole('button', { name: 'Выгрузки', exact: true }).click();
    await page.getByRole('heading', { name: 'Абсолют · квалификация', exact: true }).waitFor();
    const finalCard = page.locator('.export-card').filter({ has: page.getByRole('heading', { name: 'Абсолют · финал', exact: true }) });
    assert(await finalCard.getByRole('button').isDisabled());
    const qualificationCard = page.locator('.export-card').filter({ has: page.getByRole('heading', { name: 'Абсолют · квалификация', exact: true }) });
    if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: path.join(process.env.SCREENSHOT_DIR, 'exports-results.png'), fullPage: true });
    await qualificationCard.getByRole('button').click();
    await page.getByRole('alertdialog').getByText('Данных недостаточно', { exact: false }).waitFor();
    assert.equal(downloaded.length, 0);
    await page.getByRole('alertdialog').getByRole('button', { name: 'Отмена', exact: true }).click();
    assert.equal(downloaded.length, 0);
    await qualificationCard.getByRole('button').click();
    const download = page.waitForEvent('download');
    await page.getByRole('alertdialog').getByRole('button', { name: 'Скачать XLSX', exact: true }).click();
    await download;
    assert.equal(downloaded[0].searchParams.get('confirm_incomplete'), 'true');
    await page.getByRole('button', { name: 'Другие выгрузки', exact: true }).click();
    assert.equal(await page.locator('.export-card').count(), 7);
    if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: path.join(process.env.SCREENSHOT_DIR, 'exports-other.png'), fullPage: true });
    role = 'reception';
    await page.reload();
    await page.getByRole('button', { name: 'Участники', exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Выгрузки', exact: true }).count(), 0);
    await page.goto('http://127.0.0.1:3000/absolute');
    await page.getByText('Иванов Александр', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Соревнование', exact: true }).click();
    await page.getByText('324,9', { exact: true }).waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: path.join(process.env.SCREENSHOT_DIR, 'absolute-mobile.png'), fullPage: true });
    assert.deepEqual(errors, []);
    console.log('PASS: exports sections, stage restrictions, partial-data confirmation/download, role visibility and mobile absolute standings.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
