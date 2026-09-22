// Isolated browser checks: every API request is mocked; no festival writes.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({ channel:'chrome', headless:true });
  try {
    const page = await browser.newPage({ viewport:{ width:1440, height:1000 } });
    const errors = [], commands = [], resultRequests = [];
    page.on('pageerror', e => errors.push(e.message));
    const names = ['Девочки 10–12', 'Мальчики 10–12', 'Девушки 13–14', 'Юноши 13–14'];
    const routes = Array.from({ length:8 }, (_,i) => ({ id:`r${i+1}`, number:i+1, name:`Финал ${i+1}`, assigned_categories:[] }));
    const setup = { event_version:1, routes, categories:names.map((name,i) => ({ id:`g${i}`, name, short_name:name, participates:true, participation_configurable:false, finalist_limit:10, finalist_count:8, route_ids:i===0?routes.slice(0,4).map(r=>r.id):[], stream_number:i===0?1:null, stream_order:i===0?0:null, assignment_locked:false })) };
    let readonly = false, conflict = false;
    await page.addInitScript(() => localStorage.setItem('parkrock_admin_token','mock-token'));
    await page.route('**/api/v1/**', async route => {
      const req = route.request(), path = new URL(req.url()).pathname;
      const respond = (body, status=200) => route.fulfill({ status, contentType:'application/json', body:JSON.stringify(body) });
      if (path.endsWith('/auth/me')) return respond({ id:'admin', role:readonly?'viewer':'administrator', full_name:'Проверка', permissions:readonly?['system.read_only']:['dashboard.view','participants.view','final.manage'] });
      if (path.endsWith('/auth/heartbeat')) return respond({});
      if (path.endsWith('/admin/event')) return respond({ id:'event', title:'ПаркРок', stage:'final', version:setup.event_version, sets:[], groups:[], routes:[], participant_count:0 });
      if (path.endsWith('/admin/participants') || path.endsWith('/judge-conflicts')) return respond([]);
      if (path.endsWith('/final/setup')) return respond(setup);
      if (path.endsWith('/stream')) {
        commands.push(req.postDataJSON());
        if (conflict) return respond({ detail:'Порядок уже изменён другим сотрудником' },409);
        const id = path.split('/').at(-2), body = req.postDataJSON();
        assert.equal(body.expected_event_version, setup.event_version);
        const category = setup.categories.find(c=>c.id===id);
        category.stream_number = body.stream_number;
        category.route_ids = body.stream_number ? routes.slice((body.stream_number-1)*4,body.stream_number*4).map(r=>r.id):[];
        const list = setup.categories.filter(c=>c.stream_number===body.stream_number && c.id!==id).sort((a,b)=>a.stream_order-b.stream_order);
        list.splice(body.before_category_id?list.findIndex(c=>c.id===body.before_category_id):list.length,0,category);
        list.forEach((c,i)=>c.stream_order=i); setup.event_version++;
        return respond(setup);
      }
      if (path.endsWith('/final-results')) {
        const category = setup.categories.find(c=>c.id===path.split('/').at(-2));
        resultRequests.push(category.id);
        return respond({ category_id:category.id, category_name:category.name, routes:routes.filter(r=>category.route_ids.includes(r.id)), results:[] });
      }
      if (path.endsWith('/admin/final')) return respond({ stage:'final', event_version:setup.event_version, qualification_started_at:'2026-09-21', final_started_at:'2026-09-21', categories:setup.categories.map(c=>({...c, participates_in_final:c.participates, result_count:8, final_result_count:0, confirmed:true, final_confirmed:false, expected_version:1})), all_categories_confirmed:true, all_final_categories_confirmed:false, snapshot_results:32, snapshot_finalists:32 });
      throw Error(`Unexpected API: ${path}`);
    });
    const open = async () => {
      await page.goto('http://127.0.0.1:3000/admin');
      await page.getByRole('button',{ name:'Финал', exact:true }).click();
      await page.locator('.final-sidebar button.active').filter({hasText:'Распределение'}).waitFor();
      assert.equal(await page.locator('.final-sidebar').getByRole('button',{name:'Главное',exact:true}).count(),0);
      await page.locator('.final-lifecycle-actions').getByRole('button',{name:'Отменить финал',exact:true}).waitFor();
      await page.locator('.final-stream-card').first().waitFor();
      await page.evaluate(()=>document.fonts.ready);
    };
    const card = id => page.locator(`[data-category-id="${id}"]`);
    const column = number => page.locator(`[data-stream="${number}"]`);
    const order = number => column(number).locator('.final-stream-card').evaluateAll(nodes=>nodes.map(n=>n.dataset.categoryId));
    await open();
    assert.deepEqual(await page.locator('.final-stream-column').evaluateAll(nodes=>nodes.map(n=>n.dataset.stream)), ['unassigned','1','2']);
    const tops = await page.locator('.final-stream-column').evaluateAll(nodes=>nodes.map(n=>n.getBoundingClientRect().top));
    assert(tops.every(top=>top===tops[0]), 'Three columns must be side by side on desktop');
    assert((await column(2).innerText()).includes('5(1) → 6(2) → 7(3) → 8(4)'));
    assert.deepEqual(resultRequests, [], 'Distribution must not fetch results for removed overview');
    await card('g1').dragTo(column(2).locator('.final-stream-empty'));
    await page.waitForFunction(()=>document.querySelector('[data-stream="2"] [data-category-id="g1"]'));
    assert.equal(commands.at(-1).stream_number,2);
    await card('g2').dragTo(card('g0'));
    await page.waitForFunction(()=>document.querySelector('[data-stream="1"] .final-stream-card')?.getAttribute('data-category-id')==='g2');
    assert.deepEqual(await order(1),['g2','g0']);
    await card('g2').getByRole('button',{name:`Ниже: ${names[2]}`}).click();
    await page.waitForFunction(()=>document.querySelector('[data-stream="1"] .final-stream-card')?.getAttribute('data-category-id')==='g0');
    await page.reload(); await page.getByRole('button',{ name:'Финал', exact:true }).click();
    await page.locator('.final-sidebar').getByRole('button',{name:'Распределение',exact:true}).click();
    assert.deepEqual(await order(1),['g0','g2']);
    await page.setViewportSize({width:390,height:844});
    await card('g3').getByRole('combobox').selectOption('2');
    await page.waitForFunction(()=>document.querySelector('[data-stream="2"] [data-category-id="g3"]'));
    setup.categories[0].assignment_locked = true;
    await page.waitForFunction(()=>document.querySelector('[data-category-id="g0"] select')?.disabled);
    assert.equal(await card('g0').getAttribute('draggable'),'false');
    conflict = true;
    await card('g3').getByRole('combobox').selectOption('1');
    await page.getByRole('status').filter({hasText:'Порядок уже изменён'}).waitFor();
    assert.equal(await card('g3').getByRole('combobox').inputValue(),'2');
    conflict = false;
    await card('g3').getByRole('button',{name:`Выше: ${names[3]}`}).click();
    await page.waitForFunction(()=>document.querySelector('[data-stream="2"] .final-stream-card')?.getAttribute('data-category-id')==='g3');
    fs.mkdirSync('reports/final-streams',{recursive:true});
    for (const width of [360,390,768,1440]) {
      await page.setViewportSize({width,height:1000});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`overflow ${width}`);
      await page.screenshot({path:`reports/final-streams/streams-${width}.png`,fullPage:true});
    }
    // Move back onto an unassigned card, then into the empty unassigned column.
    setup.categories[0].assignment_locked = false;
    await page.waitForFunction(()=>!document.querySelector('[data-category-id="g0"] select')?.disabled);
    await card('g0').getByRole('combobox').selectOption('');
    await page.waitForFunction(()=>document.querySelector('[data-stream="unassigned"] [data-category-id="g0"]'));
    await card('g3').dragTo(card('g0'));
    await page.waitForFunction(()=>document.querySelector('[data-stream="unassigned"] [data-category-id="g3"]'));
    await page.waitForTimeout(300);
    const requestCount = resultRequests.length;
    await page.waitForTimeout(6500);
    assert(!resultRequests.slice(requestCount).some(id=>['g0','g3'].includes(id)), 'Unassigned categories must leave the polling loop');
    assert.equal(await page.getByText('Ошибка обновления. Данные могут быть устаревшими.', {exact:true}).count(), 0);
    await page.screenshot({path:'reports/final-streams/unassigned-no-errors.png',fullPage:true});
    await card('g3').getByRole('combobox').selectOption('2');
    await page.waitForFunction(()=>document.querySelector('[data-stream="2"] [data-category-id="g3"]'));
    await page.waitForTimeout(3500);
    assert.deepEqual(resultRequests, [], 'Reassignment must not restart removed overview polling');
    readonly=true; await open();
    assert(await card('g3').getByRole('combobox').isDisabled());
    const before=commands.length;
    await card('g3').dragTo(card('g2'));
    assert.equal(commands.length,before,'Read-only drag must not send a write');
    assert.deepEqual(errors,[]);
    console.log('PASS: drag across streams, drag before category, reorder, reload, mobile, live lock, conflict, read-only, four widths.');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1});
