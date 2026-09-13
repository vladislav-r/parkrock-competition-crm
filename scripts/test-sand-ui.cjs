// Browser-only fixtures: never writes to the database.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const output = path.join(__dirname, '../reports/sand-ui');
fs.mkdirSync(output, { recursive:true });
(async () => {
  const browser = await chromium.launch({ channel:'chrome', headless:true });
  try {
    const page = await browser.newPage();
    const errors=[]; page.on('pageerror', error => errors.push(error.message));
    const groups=['Мальчики 7-9','Девочки 7-9','Мальчики 10-12','Девочки 10-12','Юноши 13-14','Девушки 13-14','Юноши 15-16','Девушки 15-16','Юноши 17-18','Девушки 17-18','Мужчины','Женщины'];
    const names=['Соколов Данил','Кузнецов Егор','Морозов Артём','Лебедев Никита','Константинопольский-Крестовоздвиженский Александр','Сафронов Максим','Никитин Алексей','Крылов Дмитрий','Захаров Павел'];
    const rows=names.map((full_name,i)=>({ participant_id:String(i),place:i+1,start_number:104+i,full_name,club:i===4?'Спортивный клуб скалолазания и альпинизма «Длинное название команды»':'СК Вертикаль',group_name:'Мужчины',points:3320-i*150,completed_count:24-i,has_result:true,is_finalist:i<2,medal:i<4?'gold':i<7?'silver':'bronze',is_finisher:true }));
    const data={ groups,results:rows,stage:'qualification',final_groups:[],details_enabled:true };
    await page.route('**/api/v1/**', route => {
      const url=new URL(route.request().url());
      const body=url.pathname.includes('/final-results') ? {category_name:'Мужчины',routes:[{number:1,name:'Трасса 1'},{number:2,name:'Трасса 2'},{number:3,name:'Трасса 3'},{number:4,name:'Трасса 4'}],results:rows.slice(0,4).map((row,i)=>({...row,score:95-i,exit_order:4-i,qualification_place:i+1,top_count:4,zone_count:4,attempts:[{route_number:1,top_attempt:1,zone_attempt:1}]}))} : url.pathname.includes('/participants/')?{...rows[0],completed_routes:[]} : data;
      return route.fulfill({json:body});
    });
    for(const width of [360,390,760,1440]) {
      await page.setViewportSize({width,height:1000});
      await page.goto('http://localhost:3000/');
      await page.locator('.sand-category').first().waitFor();
      assert.equal(await page.locator('.sand-category').count(),12);
      assert.ok(await page.locator('.sand-category').evaluateAll(items=>items.every(item=>item.getBoundingClientRect().height>=44)));
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`home overflow ${width}`);
      await page.screenshot({path:path.join(output,`home-${width}.png`),fullPage:true});
      await page.goto('http://localhost:3000/results/muzhchiny');
      await page.locator('.sand-protocol tbody tr').first().waitFor();
      assert.equal(await page.locator('.sand-protocol .finisher-medal.gold').count(),4);
      assert.equal(await page.locator('.sand-protocol tr.finalist').count(),2);
      assert.equal(await page.locator('.sand-protocol .sand-place').first().innerText(),'1');
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`results overflow ${width}`);
      await page.screenshot({path:path.join(output,`results-${width}.png`),fullPage:true});
      await page.getByPlaceholder('Найти участника…').fill('Морозов');
      assert.equal(await page.locator('.sand-protocol tbody tr').count(),1);
      await page.getByPlaceholder('Найти участника…').fill('');
      await page.getByRole('button',{name:'Соколов Данил',exact:true}).click();
      await page.getByRole('dialog').waitFor();
      assert.ok(await page.getByRole('dialog').getByText('Медаль финишера').count());
      await page.keyboard.press('Escape');
      assert.equal(await page.getByRole('dialog').count(),0);
    }
    data.stage='final'; data.final_groups=['Мужчины'];
    for(const width of [360,1440]) {
      await page.setViewportSize({width,height:1000});
      await page.goto('http://localhost:3000/results/muzhchiny');
      await page.locator('.final-public-table').waitFor({state:'visible'});
      if(width===360) {
        await page.locator('.final-attempt-cell').first().waitFor({state:'visible'});
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      }
      await page.screenshot({path:path.join(output,`final-${width}.png`),fullPage:true});
      await page.getByRole('button',{name:'Квалификация',exact:true}).click();
      assert.equal(await page.locator('.sand-protocol tbody tr').count(),9);
    }
    assert.deepEqual(errors,[]);
    console.log('PASS: 360/390/760/1440px, 12 categories, touch targets, overflow, independent finalist/medal states, search, participant dialog.');
    await page.unrouteAll();
    await page.setViewportSize({width:1440,height:1000});
    await page.goto('http://localhost:3000/');
    await page.locator('.sand-category').first().waitFor();
    await page.screenshot({path:path.join(output,'live-home.png'),fullPage:true});
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
