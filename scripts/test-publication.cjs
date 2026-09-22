// Browser publication contract tests. All public API responses are mocked; no database writes.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const output = path.resolve(__dirname, '../reports/publication');
const version = '10000000-0000-4000-8000-000000000001';
const meta = { publication_version: version, published_at: '2026-01-01T04:05:06Z' };
const row = { participant_id: '20000000-0000-4000-8000-000000000001', place: 1, start_number: 7,
  full_name: 'Проверочный Участник', club: 'Скалолазы', group_name: 'Мужчины', points: 200,
  has_result: true, completed_count: 2, is_finalist: true, is_finisher: false, medal: null, set_id: null };
const main = { ...meta, event_id: '30000000-0000-4000-8000-000000000001', event_title: 'Проверка публикации',
  location: 'Скалодром', starts_on: '2026-01-01', stage: 'final', details_enabled: true,
  groups: ['Мужчины'], final_groups: ['Мужчины'], results: [row], sets: [],
  qualification_refresh_seconds: 300, final_refresh_seconds: 300, updated_at: '2026-01-01T01:02:03Z' };
const final = { ...meta, category_name: 'Мужчины', routes: [5,6,7,8].map(number => ({number, name:`Финал ${number}`})), updated_at: main.updated_at,
  results: [{ ...row, qualification_place: 1, exit_order: 1, score: 49.9, top_count: 2, zone_count: 2, attempts: [5,6,7,8].map(route_number => ({route_number, top_attempt:route_number-4, zone_attempt:1})) }] };

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const logs = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, timezoneId: 'UTC' });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let failFinal = false;
    let withdrawn = false;
    const requests = [];
    await page.route('**/api/v1/public/**', async route => {
      const url = new URL(route.request().url());
      requests.push(url);
      if (withdrawn) return route.fulfill({ status: 404, json: { detail: 'Нет опубликованного фестиваля' } });
      const endpoint = url.pathname.split('/').at(-1);
      let json;
      if (endpoint === 'results') json = main;
      else {
        assert.equal(url.searchParams.get('publication_version'), version, `Pinned version for ${url}`);
        if (endpoint === 'final-results') {
          if (failFinal) return route.fulfill({ status: 503, json: { detail: 'Тестовая потеря связи' } });
          json = final;
        } else if (endpoint === 'absolute-results') json = { ...meta, stage: url.searchParams.get('stage'),
          event_stage: 'final', available: true, provisional: true, results: [{ ...row, score: 200, qualification_points: 200, final_points: 49.9 }] };
        else if (endpoint === 'team-results') json = { ...meta, stage: url.searchParams.get('stage'), available: true,
          quota: 3, reason: '', issues: [], sources: [], results: [{ club_id: 'club', club: 'Скалолазы', place: 1, points: 100, points_exact: '100', groups: [] }] };
        else json = { ...meta, ...row, completed_routes: [] };
      }
      await route.fulfill({ json });
    });
    const noOverflow = async label => {
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${label}: page overflow`);
    };
    await page.goto('http://localhost:3000/results/muzhchiny');
    await page.getByText('49,9', { exact: true }).waitFor();
    assert.deepEqual(await page.locator('.final-route-head>span').allTextContents(), ['1','2','3','4']);
    assert.deepEqual(await page.locator('.final-route-head>small').allTextContents(), ['Финал 1','Финал 2','Финал 3','Финал 4']);
    assert.deepEqual(await page.locator('.final-attempt-cell .attempt-top').allTextContents(), ['1','2','3','4']);
    await page.getByRole('button', { name: 'Квалификация', exact: true }).click();
    await page.getByRole('button', { name: row.full_name, exact: true }).click();
    await page.getByRole('dialog').waitFor();
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Финал', exact: true }).click();
    await page.getByText(/Результаты опубликованы:.*04:05:06/).waitFor();
    await noOverflow('category desktop');
    await page.screenshot({ path: path.join(output, 'category-desktop.png'), fullPage: true });
    failFinal = true;
    await page.getByTitle('Обновить', { exact: true }).click();
    await page.getByText('Тестовая потеря связи', { exact: true }).waitFor();
    assert.equal(await page.getByText('49,9', { exact: true }).count(), 1, 'Keep last successful final after failed refresh');
    await page.setViewportSize({ width: 360, height: 900 });
    await noOverflow('category mobile');
    await page.screenshot({ path: path.join(output, 'category-mobile-offline.png'), fullPage: true });
    logs.push('PASS category: pinned final/detail requests, desktop/mobile layout, failed refresh retains final.');
    failFinal = false;
    for (const view of ['absolute', 'teams']) {
      await page.goto(`http://localhost:3000/${view}`);
      await page.getByRole('cell', { name: 'Скалолазы', exact: false }).waitFor();
      await noOverflow(`${view} mobile`);
      await page.setViewportSize({ width: 1440, height: 1000 });
      await noOverflow(`${view} desktop`);
      await Promise.all([
        page.waitForResponse(response => response.url().includes(`${view === 'teams' ? 'team' : 'absolute'}-results`) && response.url().includes('stage=final')),
        page.getByRole('button', { name: 'Финал', exact: true }).click(),
      ]);
      logs.push(`PASS ${view}: qualification/final dependent requests pinned; desktop/mobile layout.`);
      await page.setViewportSize({ width: 360, height: 900 });
    }
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto('http://localhost:3000/tv?stage=final&groups=all&teams=1&autoplay=1&interval=120');
    await page.locator('.tv-table:visible').last().waitFor();
    await page.getByText(/Результаты опубликованы.*04:05:06/).waitFor({ state: 'attached' });
    await noOverflow('TV desktop');
    await page.screenshot({ path: path.join(output, 'tv-desktop.png'), fullPage: true });
    logs.push('PASS TV: final and teams pinned to results publication; server published time 04:05:06, not client time.');
    main.qualification_refresh_seconds = main.final_refresh_seconds = 3;
    main.sets = [{ id: 'set', name: 'Проверочный сет', scheduled_on: '2026-01-01', time_label: '10:00', capacity: 20, participant_count: 1, checked_in_count: 1, status: 'draft', confirmed_at: null }];
    for (const [url, content] of [
      ['/results/muzhchiny', 'Проверочный Участник'],
      ['/', null], ['/sets', 'Проверочный сет'],
      ['/absolute', 'Проверочный Участник'], ['/teams', 'Скалолазы'],
      ['/tv?stage=final&groups=all&teams=1&autoplay=1&interval=120', 'Проверочный Участник'],
    ]) {
      withdrawn = false;
      await page.goto(`http://localhost:3000${url}`);
      if (content) await page.getByText(content, { exact: true }).last().waitFor();
      else await page.locator('.sand-category').waitFor();
      withdrawn = true;
      if (url.startsWith('/tv')) {
        await page.getByText('Нет опубликованного соревнования. Ожидаем данные.').waitFor({ timeout: 10000 });
        assert.equal(await page.getByText(/Результаты опубликованы/).count(), 0, 'Withdrawn TV must not invent publication time');
      } else {
        await page.getByText('Нет опубликованного фестиваля', { exact: false }).waitFor({ timeout: 10000 });
        if (content) assert.equal(await page.getByText(content, { exact: true }).count(), 0, `Clear withdrawn ${url} content`);
        else assert.equal(await page.locator('.sand-category').count(), 0, 'Clear withdrawn home categories');
      }
      logs.push(`PASS withdrawal 404: ${url.split('?')[0]} clears previously published content.`);
    }
    assert.deepEqual(errors, [], 'No browser runtime errors');
    assert.ok(requests.some(url => url.pathname.includes('/participants/')));
    fs.writeFileSync(path.join(output, 'browser-check.txt'), [...logs, `Checked ${requests.length} mocked public API requests. No database writes.`].join('\n') + '\n');
    console.log(logs.join('\n'));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
