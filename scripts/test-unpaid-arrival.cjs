const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const page=await browser.newPage({viewport:{width:1440,height:900}});
 const login=await page.request.post('http://localhost:8001/api/v1/auth/login',{form:{username:'admin@parkrock.test',password:'demo1234'}});
 const token=(await login.json()).access_token,headers={Authorization:`Bearer ${token}`};
 const event=await(await page.request.get('http://localhost:8001/api/v1/admin/event',{headers})).json();
 const people=await(await page.request.get('http://localhost:8001/api/v1/admin/participants',{headers})).json();
 const clubs=await(await page.request.get('http://localhost:8001/api/v1/admin/clubs',{headers})).json();
 event.sets.forEach(s=>s.status='draft');event.final_started_at=null;event.stage='qualification';
 let person={...people[0],is_paid:false,checked_in_at:null};
 const club=clubs.find(c=>c.members.length>1);club.members=club.members.slice(0,2).map(m=>({...m,is_paid:false,checked_in:false,application_type:'collective'}));
 club.collective_count=club.participant_count=2;let writes=0;
 await page.addInitScript(t=>localStorage.setItem('parkrock_admin_token',t),token);
 await page.route('**/api/v1/admin/**',async route=>{
  const request=route.request(),url=new URL(request.url());
  if(request.method()!=='GET'){
   assert.ok(/\/(check-in|reception|bulk)$/.test(url.pathname));
   assert.equal(request.postDataJSON().allow_unpaid,true);writes++;
   if(url.pathname.endsWith('/bulk'))return route.fulfill({json:{updated:2}});
   return route.fulfill({json:{...person,checked_in_at:new Date().toISOString()}});
  }
  if(url.pathname.endsWith('/event'))return route.fulfill({json:event});
  if(url.pathname.endsWith('/participants'))return route.fulfill({json:[person]});
  if(url.pathname.endsWith('/clubs'))return route.fulfill({json:[club]});
  return route.continue();
 });
 await page.goto('http://localhost:3000/admin');await page.locator('.participant-row').first().click();
 await page.getByRole('button',{name:'Подтвердить прибытие',exact:true}).click();
 const dialog=page.getByRole('alertdialog');await dialog.getByText('Подтвердить прибытие без оплаты?',{exact:true}).waitFor();
 fs.mkdirSync('reports/unpaid-arrival',{recursive:true});await page.screenshot({path:'reports/unpaid-arrival/participant.png'});
 await dialog.getByRole('button',{name:'Отмена',exact:true}).click();assert.equal(writes,0);
 await page.getByRole('button',{name:'Подтвердить прибытие',exact:true}).click();
 await dialog.getByRole('button',{name:'Подтвердить прибытие без оплаты',exact:true}).click();await dialog.waitFor({state:'hidden'});assert.equal(writes,1);
 await page.getByRole('button',{name:'Клубы',exact:true}).click();
 await page.getByRole('button',{name:'Подтвердить прибытие',exact:true}).click();
 await dialog.waitFor();assert.ok((await dialog.innerText()).includes('не отмечена оплата у 2'));
 await page.screenshot({path:'reports/unpaid-arrival/club.png'});
 await dialog.getByRole('button',{name:'Подтвердить прибытие без оплаты',exact:true}).click();await dialog.waitFor({state:'hidden'});assert.equal(writes,2);
 await page.getByRole('button',{name:'Не прибыл',exact:true}).first().click();
 await dialog.waitFor();assert.ok((await dialog.innerText()).includes('не отмечена оплата у 1'));
 await dialog.getByRole('button',{name:'Подтвердить прибытие без оплаты',exact:true}).click();await dialog.waitFor({state:'hidden'});assert.equal(writes,3);
 console.log('PASS unpaid arrival: participant, club row, bulk, warning count, cancellation; all writes mocked.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
