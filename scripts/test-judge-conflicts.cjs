// Run with NODE_PATH pointing to an installed Playwright package; uses only mocked API data.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1200, height: 900 } });
    const page = await context.newPage();
    const failures = [];
    page.on('pageerror', error => failures.push(error.message));
    const row = { final_result_id: 'result-1', participant_id: 'p1', category_id: 'g1', category_name: 'М 19+', start_number: 101, full_name: 'Тестовый Судья', club: 'Тест', qualification_place: 1, exit_order: 1, version: 3, locked: true, zone_attempt: 1, top_attempt: 2, score: 24.9 };
    const workspace = { event_id: 'event-1', event_title: 'Тест', stage: 'final', route: { id: 'route-1', number: 1, name: 'Финал 1' }, participants: [row], conflicts: [] };
    const queued = { id: 'stable-operation', actorId: 'judge-1', eventId: 'event-1', routeId: 'route-1', finalResultId: 'result-1', expectedVersion: 1, zoneAttempt: 2, topAttempt: 4, attemptCount: 4, startNumber: 101 };
    const conflict = { id: 'conflict-1', final_result_id: 'result-1', start_number: 101, full_name: row.full_name, route_name: 'Финал 1', judge_name: 'Судья трассы', submitted: { zone_attempt: 2, top_attempt: 4 }, server_at_submission: { zone_attempt: 1, top_attempt: 2 }, current: { zone_attempt: 1, top_attempt: 2 }, expected_version: 3, can_apply_judge: true };
    let mode = 'blocked';
    let role = 'route_judge';
    let sends = [];
    let resolutions = [];
    let conflicts = [conflict];
    await page.route('**/api/v1/**', async route => {
      const request = route.request();
      const url = new URL(request.url());
      const respond = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body), headers: { 'access-control-allow-origin': '*' } });
      if (request.method() === 'OPTIONS') return respond({});
      if (mode === 'offline') return route.abort('internetdisconnected');
      if (url.pathname === '/api/v1/auth/me') return respond({ id: 'judge-1', full_name: 'Сотрудник', role, permissions: ['dashboard.view', 'participants.view', 'final.manage'] });
      if (url.pathname === '/api/v1/judge/workspace') return respond(workspace);
      if (url.pathname.startsWith('/api/v1/judge/results/')) {
        sends.push({ id: request.headers()['x-operation-id'], body: request.postDataJSON() });
        if (mode === 'blocked') return respond({ detail: 'Конфликт проверки результата' }, 409);
        workspace.conflicts = [conflict];
        return respond({ ...workspace, submission_conflict_id: conflict.id });
      }
      if (url.pathname === '/api/v1/admin/final/judge-conflicts') return respond(conflicts);
      if (url.pathname.endsWith('/resolve')) { resolutions.push(request.postDataJSON()); conflicts = []; return respond({ id: conflict.id, resolution: request.postDataJSON().choice }); }
      if (url.pathname === '/api/v1/admin/event') return respond({ id: 'event-1', title: 'Тест', location: 'Тест', starts_on: '2026-10-17', stage: 'final', version: 1, participant_count: 0, sets: [], routes: [], groups: [] });
      if (url.pathname === '/api/v1/admin/participants') return respond([]);
      if (url.pathname === '/api/v1/admin/final') return respond({ event_id: 'event-1', stage: 'final', event_version: 1, categories: [], all_categories_confirmed: true, all_final_categories_confirmed: false, snapshot_results: 1, snapshot_finalists: 1 });
      if (url.pathname === '/api/v1/admin/final/setup') return respond({ event_id: 'event-1', stage: 'final', event_version: 1, routes: [], categories: [] });
      throw new Error(`Unexpected test API request: ${url.pathname}`);
    });
    await page.goto('http://127.0.0.1:3000/judge');
    await page.evaluate(({ queued }) => {
      localStorage.setItem('parkrock_admin_token', 'mock-token');
      localStorage.setItem('parkrock_judge_queue', JSON.stringify([queued]));
    }, { queued });
    await page.goto('http://127.0.0.1:3000/judge');
    await page.getByRole('button', { name: 'Повторить отправку' }).waitFor();
    const queue = () => page.evaluate(() => JSON.parse(localStorage.getItem('parkrock_judge_queue')));
    assert.equal((await queue())[0].id, queued.id);
    assert.equal(sends.length, 1);
    await page.reload();
    await page.getByRole('button', { name: 'Повторить отправку' }).waitFor();
    assert.equal(sends.length, 1, 'blocked commands must not be automatically retried');
    mode = 'offline';
    await page.reload();
    await page.getByRole('button', { name: 'Повторить отправку' }).waitFor();
    assert.equal((await queue())[0].topAttempt, 4, 'unsent result survives reload with API unavailable');
    mode = 'delivered';
    await page.reload();
    await page.getByPlaceholder('Стартовый номер или ФИО').waitFor();
    await page.getByRole('button', { name: 'Повторить отправку' }).click();
    await page.getByText('Конфликт №101', { exact: false }).waitFor();
    assert.deepEqual(await queue(), []);
    assert.equal(sends.length, 2);
    assert.deepEqual(sends[0], sends[1], 'retry must preserve operation ID and original version');
    await page.reload();
    await page.getByText('Конфликт №101', { exact: false }).waitFor();
    if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: path.join(process.env.SCREENSHOT_DIR, 'judge-conflict.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: path.join(process.env.SCREENSHOT_DIR, 'judge-conflict-mobile.png'), fullPage: true });
    await page.setViewportSize({ width: 1200, height: 900 });
    role = 'secretary';
    await page.goto('http://127.0.0.1:3000/admin');
    await page.getByRole('button', { name: 'Финал', exact: true }).click();
    await page.getByRole('button', { name: 'Принять результат судьи' }).click();
    assert.equal(resolutions.length, 0, 'choice requires explicit confirmation');
    await page.getByRole('button', { name: 'Отмена', exact: true }).click();
    assert.equal(resolutions.length, 0);
    if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: path.join(process.env.SCREENSHOT_DIR, 'staff-conflict.png'), fullPage: true });
    await page.getByRole('button', { name: 'Принять результат судьи' }).click();
    await page.getByRole('button', { name: 'Подтвердить выбор' }).click();
    await page.getByRole('button', { name: 'Принять результат судьи' }).waitFor({ state: 'detached' });
    assert.deepEqual(resolutions, [{ choice: 'judge', expected_version: 3 }]);
    // Storage exhaustion must leave the unsent draft open, without a success notice or a request.
    role = 'route_judge';
    workspace.conflicts = [];
    row.locked = false;
    await page.goto('http://127.0.0.1:3000/judge');
    await page.getByRole('button', { name: /101.*Тестовый Судья/ }).click();
    await page.getByRole('button', { name: 'ТОП', exact: true }).click();
    await page.getByRole('button', { name: 'Проверить и сохранить' }).click();
    await page.evaluate(() => {
      const original = Storage.prototype.setItem;
      Storage.prototype.setItem = function (key, value) {
        if (key === 'parkrock_judge_queue') throw new DOMException('Quota exceeded', 'QuotaExceededError');
        return original.call(this, key, value);
      };
    });
    await page.getByRole('button', { name: 'Подтвердить результат', exact: true }).click();
    await page.getByText('Не удалось сохранить результат на ноутбуке.', { exact: false }).waitFor();
    assert.equal(sends.length, 2);
    assert.deepEqual(await queue(), []);
    assert.deepEqual(await page.evaluate(() => JSON.parse(localStorage.getItem('parkrock_judge_drafts'))['result-1']), ['top']);
    assert.deepEqual(failures, []);
    console.log('PASS: queue survives 409 and offline reload; identical retry; delivered conflict persists; staff comparison and confirmed resolution; storage failure preserves draft.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
