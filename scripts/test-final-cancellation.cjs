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
    let readonly = false, conflict = false, stage = "final", setupCount = 0, setupFailure = false, heldSetup = null, heldStatus = null, holdSetup = false, holdStatus = false;
    const statusBody = () => ({ stage, event_version:setup.event_version, qualification_started_at:'2026-09-21', final_started_at:'2026-09-21', categories:setup.categories.map(c=>({...c, participates_in_final:c.participates, result_count:8, final_result_count:0, confirmed:true, final_confirmed:false, expected_version:1})), all_categories_confirmed:true, all_final_categories_confirmed:false, snapshot_results:32, snapshot_finalists:32 });
    await page.addInitScript(() => localStorage.setItem('parkrock_admin_token','mock-token'));
    await page.route('**/api/v1/**', async route => {
      const req = route.request(), path = new URL(req.url()).pathname;
      const respond = (body, status=200) => route.fulfill({ status, contentType:'application/json', body:JSON.stringify(body) });
      if (path.endsWith('/auth/me')) return respond({ id:'admin', role:readonly?'viewer':'administrator', full_name:'Проверка', permissions:readonly?['system.read_only']:['dashboard.view','participants.view','final.manage'] });
      if (path.endsWith('/auth/heartbeat')) return respond({});
      if (path.endsWith('/admin/event')) return respond({ id:'event', title:'ПаркРок', stage, version:setup.event_version, sets:[], groups:[], routes:[], participant_count:0 });
      if (path.endsWith('/admin/participants') || path.endsWith('/judge-conflicts')) return respond([]);
      if (path.endsWith('/final/setup')) {
        setupCount++;
        if (holdSetup) { heldSetup = () => respond(setup); return; }
        if (setupFailure || stage !== 'final') return respond({detail:'Настройка финальных трасс доступна после запуска финала'},409);
        return respond(setup);
      }
      if (path.endsWith('/final/cancel')) {
        stage = 'qualification'; setup.event_version++;
        return respond(statusBody());
      }
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
      if (path.endsWith('/admin/final')) {
        const snapshot = statusBody();
        if (holdStatus) { heldStatus = () => respond(snapshot); return; }
        return respond(snapshot);
      }
      throw Error(`Unexpected API: ${path}`);
    });
    const pause = ms => page.waitForTimeout(ms);
    const waitUntil = async predicate => {
      for (let i=0;i<100;i++) { if (predicate()) return; await pause(100); }
      throw Error('Timed out waiting for mocked request');
    };
    const open = async () => {
      await page.goto('http://127.0.0.1:3000/admin');
      await page.getByRole('button',{name:'Финал',exact:true}).click();
      await page.locator('.final-stream-card').first().waitFor();
    };
    await open();
    // Another admin cancels: a 409 is received before the stage poll catches up.
    setupFailure = true;
    await page.locator('.crm-sync-alert').filter({hasText:'HTTP 409'}).waitFor();
    await page.evaluate(() => window.dispatchEvent(new CustomEvent('parkrock-admin-read-status', {
      detail:{path:'/api/v1/admin/unrelated',error:'OTHER_SECTION_FAILURE',at:Date.now()}
    })));
    holdSetup = true;
    await waitUntil(()=>heldSetup);
    stage = 'qualification'; setup.event_version++;
    await page.getByRole('button',{name:'Запустить финал',exact:true}).waitFor();
    void heldSetup().catch(()=>{}); heldSetup=null; holdSetup=false;
    await pause(500);
    assert.equal(await page.locator('.crm-sync-alert').filter({hasText:'HTTP 409'}).count(),0);
    assert.equal(await page.locator('.crm-sync-alert').filter({hasText:'OTHER_SECTION_FAILURE'}).count(),1);
    assert.equal(await page.locator('.final-stream-card').count(),0);
    const stoppedCount = setupCount;
    await pause(3500);
    assert.equal(setupCount, stoppedCount, 'Final setup polling must stop after remote cancellation');
    await page.evaluate(() => window.dispatchEvent(new CustomEvent('parkrock-admin-read-status', {
      detail:{path:'/api/v1/admin/unrelated',error:null,at:Date.now()}
    })));
    // Local cancellation while a stale status response is in flight.
    stage='final'; setup.event_version++; setupFailure=false;
    await page.locator('.final-stream-card').first().waitFor();
    holdStatus=true;
    await waitUntil(()=>heldStatus);
    await page.getByRole('button',{name:'Отменить финал',exact:true}).click();
    await page.getByRole('alertdialog').getByRole('button',{name:'Отменить финал',exact:true}).click();
    await page.getByRole('button',{name:'Запустить финал',exact:true}).waitFor();
    holdStatus=false; void heldStatus().catch(()=>{}); heldStatus=null;
    await pause(3500);
    assert.equal(await page.locator('.final-stream-card').count(),0,'Late final status must not restore cancelled stage');
    assert.equal(await page.locator('.crm-sync-alert').count(),0,'No lingering sync error');
    assert.deepEqual(errors,[]);
    fs.mkdirSync('reports/final-streams',{recursive:true});
    await page.screenshot({path:'reports/final-streams/cancel-clean.png',fullPage:true});
    console.log('PASS: remote and local cancellation, obsolete errors cleared, unrelated errors retained, late responses ignored.');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1});
