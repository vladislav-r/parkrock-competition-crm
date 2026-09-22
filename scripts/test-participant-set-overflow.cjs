const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
 const browser = await chromium.launch({channel:'chrome',headless:true});
 try {
  const page = await browser.newPage({viewport:{width:1440,height:900}});
  const login = await page.request.post('http://localhost:8001/api/v1/auth/login',{form:{username:'admin@parkrock.test',password:'demo1234'}});
  const token=(await login.json()).access_token;
  const headers={Authorization:`Bearer ${token}`};
  const event=await (await page.request.get('http://localhost:8001/api/v1/admin/event',{headers})).json();
  const people=await (await page.request.get('http://localhost:8001/api/v1/admin/participants',{headers})).json();
  const target=event.sets[0], source=event.sets[1];
  target.capacity=target.participant_count;
  event.stage='qualification'; event.final_started_at=null;
  event.sets.forEach(s=>s.status='draft');
  let person={...people[0],set_id:source.id,checked_in_at:null};
  let writes=0;
  await page.addInitScript(t=>localStorage.setItem('parkrock_admin_token',t),token);
  await page.route('**/api/v1/admin/**',async route=>{
   const req=route.request(),url=new URL(req.url());
   if(req.method()==='PATCH' && url.pathname.endsWith('/set')){
    assert.equal(req.postDataJSON().allow_overflow,true);assert.equal(req.postDataJSON().set_id,target.id);
    writes++;person={...person,set_id:target.id,version:person.version+1};
    return route.fulfill({json:person});
   }
   assert.equal(req.method(),'GET');
   if(url.pathname.endsWith('/event'))return route.fulfill({json:event});
   if(url.pathname.endsWith('/participants'))return route.fulfill({json:[person]});
   return route.continue();
  });
  await page.goto('http://localhost:3000/admin');
  await page.locator('.participant-row').first().click();
  const select=page.getByLabel('Назначенный сет');
  await select.selectOption(target.id);
  const dialog=page.getByRole('alertdialog');
  await dialog.getByText('Перенести сверх вместимости сета?',{exact:true}).waitFor();
  assert.ok((await dialog.innerText()).includes(`будет ${target.participant_count+1} участников`));
  fs.mkdirSync('reports/participant-overflow',{recursive:true});
  await page.screenshot({path:'reports/participant-overflow/confirmation.png'});
  await dialog.getByRole('button',{name:'Отмена',exact:true}).click();assert.equal(writes,0);
  await select.selectOption(target.id);
  await page.getByRole('button',{name:'Подтвердить перенос сверх вместимости',exact:true}).click();
  await dialog.waitFor({state:'hidden'});assert.equal(writes,1);assert.equal(await select.inputValue(),target.id);
  console.log('PASS: full target selectable, warning with resulting count, cancellation sends no write, confirmation sends allow_overflow=true. API writes mocked.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
