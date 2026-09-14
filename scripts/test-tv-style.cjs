const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async()=>{
  fs.mkdirSync('reports/tv-style',{recursive:true});
  const browser=await chromium.launch({channel:'chrome',headless:true});
  const errors=[];
  try {
    const page=await browser.newPage();
    page.on('pageerror',e=>errors.push(e.message));
    let count=90;
    await page.route('**/api/v1/public/**',route=>{
      const rows=Array.from({length:count},(_,i)=>({participant_id:String(i),full_name:i%13===0?'Константинопольский-Крестовоздвиженский Александр':`${['Иванов Александр','Петрова Мария','Соколова Елизавета','Кузнецов Михаил'][i%4]}`,club:i%11===0?'Спортивный клуб скалолазания и альпинизма «Длинное название»':['Скала','Гранит','Высота'][i%3],place:i+1,points:1580-i*11,score:100-i/10,medal:i%3===0?'gold':i%3===1?'silver':'bronze',is_finalist:i<10,group_name:'Юноши 15–16',has_result:true,attempts:[]}));
      const url=new URL(route.request().url());
      route.fulfill({json:url.pathname.endsWith('team-results')?{stage:url.searchParams.get('stage'),quota:2,available:true,reason:'',issues:[],results:rows.map(r=>({club_id:r.participant_id,club:r.club,place:r.place,points:r.points})),sources:[]}:url.pathname.endsWith('final-results')?{results:rows,routes:[]}:{event_title:'ПаркРок',stage:'completed',groups:['Юноши 15–16'],final_groups:['Юноши 15–16'],results:rows,sets:[],qualification_refresh_seconds:3,final_refresh_seconds:3}});
    });
    for(const [width,height,stage,teams] of [[1920,1080,'qualification',false],[1366,768,'qualification',false],[1280,720,'final',false],[3840,2160,'qualification',false],[1920,1080,'final',true],[768,1024,'qualification',false],[360,800,'qualification',false],[1024,600,'qualification',false]]) {
      await page.setViewportSize({width,height});
      await page.goto(`http://localhost:3000/tv?stage=${stage}&interval=5&autoplay=1${teams?'&teams=1&group=':''}`);
      await page.locator('.tv-columns table').first().waitFor();
      await page.waitForTimeout(350);
      const geometry=await page.evaluate(()=>{
        const area=document.querySelector('.tv-results').getBoundingClientRect();
        const tables=[...document.querySelectorAll('.tv-columns table')];
        return {overflow:document.documentElement.scrollWidth>innerWidth||document.documentElement.scrollHeight>innerHeight,
          font:parseFloat(getComputedStyle(tables[0]).fontSize),rows:tables.reduce((n,t)=>n+t.querySelectorAll('tbody tr').length,0),
          fit:tables.every(t=>{const r=t.getBoundingClientRect();return r.bottom<=area.bottom+1&&r.right<=area.right+1&&r.left>=area.left-1;}),
          blocks:[...document.querySelectorAll('.tv-header,.tv-partners,.tv-highlight-note,.tv-results,.tv-footer')].map(e=>{const r=e.getBoundingClientRect();return {top:r.top,bottom:r.bottom,right:r.right};})};
      });
      assert.ok(!geometry.overflow&&geometry.fit,JSON.stringify({width,height,geometry}));
      assert.ok(geometry.font>=14,JSON.stringify(geometry));
      for(let i=1;i<geometry.blocks.length;i++) assert.ok(geometry.blocks[i].top-geometry.blocks[i-1].bottom>=5);
      console.log(`${width}x${height} ${stage}${teams?' teams':''}: ${geometry.rows} rows, ${geometry.font.toFixed(1)}px, fits`);
      if(width===1920||width===1366||width===360) await page.screenshot({path:`reports/tv-style/${width}-${stage}${teams?'-teams':''}.png`});
      const oldFirst=await page.locator('.tv-columns tbody tr').first().textContent();
      await page.waitForTimeout(5100);
      assert.notEqual(await page.locator('.tv-columns tbody tr').first().textContent(),oldFirst);
    }
    await page.setViewportSize({width:1440,height:1000});
    await page.goto('http://localhost:3000/tv');
    await page.getByRole('heading',{name:'Режим ТВ',exact:true}).waitFor();
    await page.screenshot({path:'reports/tv-style/settings.png',fullPage:true});
    assert.deepEqual(errors,[]);
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
