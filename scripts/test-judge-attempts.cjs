// Uses mocked API data only; NODE_PATH must include Playwright.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 320, height: 568 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const participant = { final_result_id: 'test-result', participant_id: 'p1', category_id: 'g1', category_name: 'М 19+', start_number: 101, full_name: 'Александр Константинопольский', club: 'Тест', qualification_place: 1, exit_order: 1, version: 1, locked: false, zone_attempt: null, top_attempt: null, score: 0 };
    const workspace = { event_id: 'test-event', stage: 'final', route: { id: 'r1', number: 5, name: 'Финал 5' }, participants: [participant], conflicts: [] };
    const submissions = [];
    await page.addInitScript(() => localStorage.setItem('parkrock_admin_token', 'mock-token'));
    await page.route('**/api/v1/**', async route => {
      const pathname = new URL(route.request().url()).pathname;
      let body = {};
      if (pathname.endsWith('/auth/me')) body = { id: 'judge', full_name: 'Судья', role: 'route_judge', permissions: ['judge.results'] };
      if (pathname.endsWith('/judge/workspace')) body = workspace;
      if (pathname.includes('/judge/results/')) { submissions.push(route.request().postDataJSON()); body = workspace; }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });
    await page.goto('http://127.0.0.1:3000/judge');
    const choose = () => page.locator('.judge-participants button').click();
    const button = name => page.getByRole('button', { name, exact: true });
    const count = async n => assert.equal(await page.locator('.judge-attempt strong').innerText(), String(n));
    const enabled = async names => {
      for (const name of ['СТАРТ (принял старт)', 'ПОПЫТКА (срыв)', 'ЗОНА', 'ТОП']) assert.equal(await button(name).isEnabled(), names.includes(name), name);
    };
    const summary = async (zone, top) => {
      const values = await page.locator('.judge-summary strong').allTextContents();
      assert.deepEqual(values.slice(1, 3), [zone, top]);
    };
    if (process.env.SCREENSHOT_DIR) {
      fs.mkdirSync(process.env.SCREENSHOT_DIR, { recursive:true });
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({path:`${process.env.SCREENSHOT_DIR}/judge-list.png`,fullPage:true});
    }
    await choose();
    assert.equal(await page.locator('.judge-route-mark').innerText(), '1');
    assert((await page.locator('.judge-header').innerText()).includes('Поток 2'));
    await page.evaluate(() => document.fonts.ready);
    await count(0); await enabled(['СТАРТ (принял старт)']);
    await button('СТАРТ (принял старт)').click(); await count(1); await enabled(['ПОПЫТКА (срыв)', 'ЗОНА', 'ТОП']);
    if (process.env.SCREENSHOT_DIR) {
      await page.setViewportSize({width:456,height:986});
      await page.screenshot({path:`${process.env.SCREENSHOT_DIR}/judge-active.png`,fullPage:true});
      await page.setViewportSize({width:1440,height:1000});
      await page.screenshot({path:`${process.env.SCREENSHOT_DIR}/judge-desktop.png`,fullPage:true});
      await page.setViewportSize({width:320,height:568});
    }
    await button('ПОПЫТКА (срыв)').click(); await count(1); await enabled(['СТАРТ (принял старт)']);
    await button('СТАРТ (принял старт)').click(); await count(2);
    await button('ЗОНА').click(); await count(2); await summary('2', '—'); await enabled(['ПОПЫТКА (срыв)', 'ТОП']);
    await page.reload(); await choose(); await count(2); await enabled(['ПОПЫТКА (срыв)', 'ТОП']);
    await button('ТОП').click(); await count(2); await summary('2', '2'); await enabled([]);
    await button('Отменить последнее действие').click(); await enabled(['ПОПЫТКА (срыв)', 'ТОП']);
    await button('ПОПЫТКА (срыв)').click(); await button('СТАРТ (принял старт)').click(); await count(3); await enabled(['ПОПЫТКА (срыв)', 'ТОП']);
    await button('ТОП').click(); await summary('2', '3');
    for (const [width, height] of [[456,986],[320,568],[360,640],[390,664],[430,740],[568,320],[844,390],[768,1024]]) {
      await page.setViewportSize({ width, height });
      const boxes = await page.locator('.judge-bib.large, .judge-attempt, .judge-actions button, .judge-save').evaluateAll(nodes => nodes.map(node => { const r = node.getBoundingClientRect(); return { top:r.top, bottom:r.bottom, left:r.left, right:r.right }; }));
      assert(boxes.every(r => r.top >= 0 && (height < 800 && height > 500 || r.bottom <= height) && r.left >= 0 && r.right <= width), `Controls outside viewport ${width}x${height}: ${JSON.stringify(boxes)}`);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), JSON.stringify(await page.locator('body *').evaluateAll(nodes => nodes.filter(n => n.getBoundingClientRect().right > innerWidth).map(n => ({tag:n.tagName, cls:n.className, right:n.getBoundingClientRect().right})))));
      if (width <= 700 && height > 500) {
        for (const selector of ['.judge-actions', '.judge-controls']) {
          const rects = await page.locator(`${selector} button`).evaluateAll(nodes => nodes.map(n => { const r = n.getBoundingClientRect(); return { left:r.left, top:r.top, bottom:r.bottom, width:r.width }; }));
          assert(rects.every((r, i) => r.left === rects[0].left && r.width === rects[0].width && (!i || r.top >= rects[i-1].bottom)), `Single column required: ${selector}`);
        }
        assert.equal(await page.locator('.judge-athlete h1').evaluate(n => getComputedStyle(n).fontSize), '20px');
      }
      assert.equal(await page.locator('.judge-bib.large').evaluate(n => getComputedStyle(n).borderRadius), '20px');
      if (process.env.SCREENSHOT_DIR) {
        fs.mkdirSync(process.env.SCREENSHOT_DIR, { recursive: true });
        await page.screenshot({ path: `${process.env.SCREENSHOT_DIR}/judge-${width}x${height}.png`, fullPage: true });
      }
    }
    await page.setViewportSize({ width:456, height:986 });
    await button('Сохранить').click();
    if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.SCREENSHOT_DIR}/judge-confirm.png`, fullPage:true });
    assert.equal(submissions.length, 0);
    await button('Подтвердить').click();
    await page.waitForFunction(() => JSON.parse(localStorage.getItem('parkrock_judge_queue') || '[]').length === 0);
    assert.equal(submissions.length, 1);
    assert.equal(submissions[0].zone_attempt, 2); assert.equal(submissions[0].top_attempt, 3);
    await choose(); await button('СТАРТ (принял старт)').click(); await button('ТОП').click(); await summary('1', '1');
    await button('Отменить последнее действие').click(); await button('Отменить последнее действие').click();
    await count(0); await enabled(['СТАРТ (принял старт)']);
    await page.evaluate(() => localStorage.setItem('parkrock_judge_drafts', JSON.stringify({ 'test-result': ['attempt','zone','top'] })));
    await page.reload(); await choose(); await count(3); await summary('2', '3'); await enabled([]);
    assert.deepEqual(errors, []);
    console.log('PASS: start-only counter, zone/top on same attempt, retained zone, undo, reload, old drafts, confirmed save, mobile layout.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
