// Browser fixtures only; no database reads or writes.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({channel:'chrome',headless:true});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    const group='Девушки 13-14';
    const row={participant_id:'test',full_name:'Шарова Жанна',club:'Тест',start_number:1,place:1,score:90,has_result:true,exit_order:1,qualification_place:1,top_count:4,zone_count:4,
      attempts:[{route_number:1,top_attempt:1,zone_attempt:2},{route_number:2,top_attempt:1,zone_attempt:2},{route_number:3,top_attempt:2,zone_attempt:3},{route_number:4,top_attempt:3,zone_attempt:4}]};
    await page.route('**/api/v1/**',route=>route.fulfill({json:route.request().url().includes('final-results')?{category_name:group,routes:row.attempts.map(a=>({number:a.route_number,name:`Трасса ${a.route_number}`})),results:[row]}:{groups:[group,'Мужчины'],results:[],stage:'final',final_groups:[group]}}));
    await page.goto('http://localhost:3000/');
    const category=page.locator('.sand-category').first(); await category.waitFor();
    assert.ok(await category.evaluate(el=>el.querySelector('strong').getBoundingClientRect().left-el.getBoundingClientRect().left>=8));
    await page.locator('.sand-navigation a').nth(1).hover(); await page.waitForTimeout(250);
    assert.equal(await page.locator('.sand-navigation a').nth(1).evaluate(el=>getComputedStyle(el,'::after').transform),'matrix(1, 0, 0, 1, 0, 0)');
    await page.screenshot({path:'reports/sand-ui/header-hover.png'});
    await category.hover(); await page.screenshot({path:'reports/sand-ui/category-hover.png'});
    await page.goto('http://localhost:3000/results/devushki-13-14');
    await page.locator('.final-counts').first().waitFor();
    assert.equal(await page.locator('.final-counts').first().innerText(),'7 / 11');
    await page.screenshot({path:'reports/sand-ui/attempt-totals.png'});
    await page.setViewportSize({width:360,height:900});
    await page.locator('.final-public-table').waitFor({state:'visible'});
    assert.equal(await page.locator('.final-counts').first().innerText(),'7 / 11');
    assert.equal(await page.locator('.final-public-table details').count(),0);
    assert.ok(await page.locator('.sand-final-athlete-meta .bib').first().isVisible());
    assert.ok(await page.locator('.final-place.place-1').first().isVisible());
    assert.ok(await page.locator('.final-public-table tbody td:nth-child(6)').first().isVisible());
    assert.equal(await page.locator('.final-attempt-cell:visible').count(),4);
    await page.screenshot({path:'reports/sand-ui/final-mobile-inline.png',fullPage:true});
    for (const width of [320,390,496,760,761,820,1024,1100,1101,1280,1440]) {
      await page.setViewportSize({width,height:900});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      assert.ok(await page.locator('.final-counts').first().isVisible());
      assert.ok(await page.locator('.final-public-table-wrap').evaluate(el=>el.scrollWidth<=el.clientWidth+1), `Table overflow at ${width}px`);
      if ([496,820,1101].includes(width)) await page.screenshot({path:`reports/sand-ui/final-spacing-${width}.png`,fullPage:true});
    }
    await page.setViewportSize({width:360,height:900});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.goto('http://localhost:3000/'); await page.locator('.sand-category').first().waitFor();
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.emulateMedia({reducedMotion:'reduce'});
    assert.equal(await page.locator('.sand-navigation a').first().evaluate(el=>getComputedStyle(el,'::after').transitionDuration),'0s');
    console.log('PASS: header hover, category padding, 7 / 11 attempt totals (desktop/mobile), mobile overflow, reduced motion.');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
