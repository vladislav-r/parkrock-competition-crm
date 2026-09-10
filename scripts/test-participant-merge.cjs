// Isolated API fixtures: never changes the working database.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    for (const width of [1440, 360]) {
      const context = await browser.newContext({ viewport: { width, height: 1000 } });
      await context.addInitScript(() => localStorage.setItem('parkrock_admin_token', 'isolated-test-token'));
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      const source = { id:'p1', club_id:'c1', set_id:'s1', start_number:11, surname:'Иванов', name:'Иван', patronymic:'Иванович', birth_year:2017, birth_date:'2017-01-01', sex:'male', sport_rank:'б/р', club:'Скала', representative:'Анна', checked_in_at:null, is_paid:false, merch_size:null, merch_issued:false, source:'manual', application_type:'individual', import_operation_id:null, version:1, completed_count:0, points:0, ascents:[], group_name:'Мальчики 7–9' };
      const target = {...source, id:'p2', club_id:'c2', set_id:'s2', start_number:22, birth_year:2018, birth_date:'2018-01-01', club:'Горы', representative:'Иван', sport_rank:'3 юношеский', is_paid:true};
      let people = [source, target], merges = 0;
      const sets = [1,2].map(n => ({id:`s${n}`,name:`Сет ${n}`,time_label:'08:30–10:30',capacity:30,participant_count:1,checked_in_count:0,version:1,status:'draft',scheduled_on:'2026-10-17'}));
      await page.route('**/api/v1/**', async route => {
        const req = route.request(), url = new URL(req.url());
        const reply = (body, status=200) => route.fulfill({status, contentType:'application/json', body:JSON.stringify(body)});
        if(req.method()==='OPTIONS') return reply({});
        if(url.pathname==='/api/v1/auth/me') return reply({id:'admin',role:'administrator',full_name:'Тест',permissions:['dashboard.view','participants.view','participants.edit','participants.merge']});
        if(url.pathname==='/api/v1/admin/event') return reply({id:'event',title:'Тест',starts_on:'2026-10-17',stage:'preparation',sets,routes:[],groups:[],version:1,participant_count:people.length});
        if(url.pathname==='/api/v1/admin/participants') return reply(people);
        if(url.pathname==='/api/v1/admin/clubs') return reply([]);
        if(req.method()==='PATCH' && url.pathname==='/api/v1/admin/participants/p1') return reply({detail:{code:'duplicate_participant',message:'Участник с таким ФИО и годом рождения уже существует. Изменения не сохранены.',participants:[target]}},409);
        if(url.pathname==='/api/v1/admin/participants/p1/merge') {
          merges++;
          const body = req.postDataJSON();
          assert.equal(body.primary_participant_id, 'p1');
          assert.equal(body.club_participant_id, 'p1');
          assert.equal(body.payment_participant_id, 'p2');
          const participant = {...source,birth_year:2018,is_paid:true,version:2};
          people = [participant];
          return reply({participant,removed_participant_id:'p2',backup_filename:'test.dump'});
        }
        throw new Error(`Unexpected API request: ${req.method()} ${url.pathname}`);
      });
      await page.goto('http://127.0.0.1:3000/admin');
      await page.locator('.participant-list > button').first().click();
      await page.getByRole('button',{name:'Редактировать данные',exact:true}).click();
      await page.getByLabel('Год рождения',{exact:true}).fill('2018');
      await page.getByRole('button',{name:'Продолжить',exact:true}).click();
      await page.getByRole('button',{name:'Подтвердить изменения',exact:true}).click();
      const alert = page.locator('#participant-edit-error');
      await alert.waitFor();
      assert.equal(await alert.evaluate(el => getComputedStyle(el).color), 'rgb(161, 28, 35)');
      assert.equal(await page.getByLabel('Год рождения',{exact:true}).getAttribute('aria-invalid'), 'true');
      assert.equal(await page.getByLabel('Год рождения',{exact:true}).evaluate(el => getComputedStyle(el).borderColor), 'rgb(180, 35, 44)');
      assert(await page.getByRole('button',{name:'Продолжить',exact:true}).isDisabled());
      const shots = process.env.SCREENSHOT_DIR;
      if(shots) { fs.mkdirSync(shots,{recursive:true}); await page.screenshot({path:path.join(shots,`duplicate-${width}.png`),fullPage:true}); }
      await page.getByRole('button',{name:'Объединить',exact:true}).click();
      await page.getByLabel(/^Основная запись: номер и сет/).selectOption('p1');
      await page.getByLabel(/^Клуб/).selectOption('p1');
      if(shots) await page.screenshot({path:path.join(shots,`choices-${width}.png`),fullPage:true});
      await page.getByRole('button',{name:'Объединить',exact:true}).click();
      assert.equal(merges,0);
      const cancel = page.getByRole('button',{name:'Отмена',exact:true});
      assert(await cancel.evaluate(el => el===document.activeElement));
      if(shots) await page.screenshot({path:path.join(shots,`confirm-${width}.png`),fullPage:true});
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.getByRole('button',{name:'Подтвердить объединение',exact:true}).click();
      await page.getByRole('alertdialog').waitFor({state:'detached'});
      assert.equal(merges,1);
      assert.equal(await page.locator('.participant-list > button').count(),1);
      assert.deepEqual(errors,[]);
      await context.close();
      console.log(`Participant merge UI ${width}px: passed`);
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode=1; });
