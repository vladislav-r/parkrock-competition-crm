const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const page=await browser.newPage({viewport:{width:1536,height:864}});const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 const response=await page.request.post('http://localhost:8001/api/v1/auth/login',{form:{username:'admin@parkrock.test',password:'demo1234'}});
 assert.ok(response.ok());await page.addInitScript(t=>localStorage.setItem('parkrock_admin_token',t),(await response.json()).access_token);
 await page.route('**/api/v1/admin/**',r=>{assert.equal(r.request().method(),'GET');return r.continue();});
 await page.goto('http://localhost:3000/admin');await page.getByRole('button',{name:'Клубы',exact:true}).click();await page.locator('.club-member-row:not(.table-head)').first().waitFor();
 assert.ok(await page.locator('.club-members-table').evaluate(e=>e.clientHeight>=498),'table must be at least twice its former 249px height');
 fs.mkdirSync('reports/relief-clubs',{recursive:true});await page.screenshot({path:'reports/relief-clubs/desktop.png',fullPage:true});
 await page.locator('.club-menu-trigger').first().click();
 const clubMenu=page.locator('.club-menu-popup:popover-open');await clubMenu.waitFor();
 await clubMenu.getByRole('button',{name:'Объединить',exact:true}).hover();
 await page.screenshot({path:'reports/relief-clubs/club-menu.png',fullPage:true});
 await page.keyboard.press('Escape');await clubMenu.waitFor({state:'hidden'});
 assert.equal(await page.locator('.club-member-row.table-head button').count(),6);

 await page.locator('.admin-user-menu summary').click();await page.screenshot({path:'reports/relief-clubs/user-menu.png',fullPage:true});
 assert.ok((await page.locator('.admin-user-copy').innerText()).includes('Администратор'));
 await page.getByRole('button',{name:'Инструкция по роли',exact:true}).click();await page.getByRole('dialog').waitFor();await page.getByRole('dialog').getByTitle('Закрыть').click();
 await page.locator('.admin-user-menu summary').click();await page.keyboard.press('Escape');assert.equal(await page.locator('.admin-user-menu').getAttribute('open'),null);
 await page.getByRole('button',{name:'Редактировать клуб',exact:true}).click();await page.getByRole('alertdialog').waitFor();await page.getByRole('button',{name:'Отмена',exact:true}).click();
 await page.getByRole('button',{name:'Подтвердить прибытие',exact:true}).click();await page.getByRole('alertdialog').waitFor();await page.getByRole('button',{name:'Отмена',exact:true}).click();
 const name=await page.locator('.club-list-item strong').first().innerText();await page.getByLabel('Найти клуб',{exact:true}).fill(name);assert.equal(await page.locator('.club-list-item').count(),1);await page.getByLabel('Найти клуб',{exact:true}).fill('');
 await page.locator('.club-list-item').nth(1).click();const bib=await page.locator('.member-number').first().innerText();await page.getByLabel('Поиск участников клуба').fill(bib.replace('№',''));assert.ok(await page.locator('.club-member-row:not(.table-head)').count()>0);await page.getByLabel('Поиск участников клуба').fill('');
 await page.locator('.club-member-row.table-head button').nth(1).click();
 const all=page.getByLabel('Выбрать всех показанных участников');await all.check();assert.equal(await page.locator('.club-member-row:not(.table-head) input:not(:checked)').count(),0);await all.uncheck();assert.equal(await page.locator('.club-member-row:not(.table-head) input:checked').count(),0);
 await page.locator('.club-list-item').first().click();

 for(const width of [1920,1440,1100,760,390,360]){await page.setViewportSize({width,height:900});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`overflow ${width}`);if(width>760)assert.ok(await page.evaluate(()=>document.body.scrollHeight<=innerHeight),`vertical overflow ${width}`);}
 await page.screenshot({path:'reports/relief-clubs/mobile.png',fullPage:true});
 assert.deepEqual(errors,[]);console.log('PASS clubs: six sizes, selection, search, sorting, edit/bulk dialogs, user menu, Escape; no data writes.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
