const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  fs.mkdirSync('reports/crm-refinement', { recursive: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const errors = [];
    page.on('pageerror', error => errors.push(String(error)));
    const login = await page.request.post('http://localhost:8001/api/v1/auth/login', { form: { username: 'admin@parkrock.test', password: 'demo1234' } });
    assert.ok(login.ok(), 'Login');
    await page.addInitScript(token => localStorage.setItem('parkrock_admin_token', token), (await login.json()).access_token);
    await page.route('**/api/v1/admin/**', async route => {
      assert.equal(route.request().method(), 'GET', 'Browser test must not write competition data');
      if (new URL(route.request().url()).pathname.endsWith('/event')) {
        const response = await route.fetch();
        const event = await response.json();
        return route.fulfill({ response, json: { ...event, stage: 'qualification', qualification_started_at: event.qualification_started_at || new Date().toISOString(), final_started_at: null } });
      }
      return route.continue();
    });
    const screenshot = name => page.screenshot({ path: `reports/crm-refinement/${name}.png`, fullPage: true });
    async function noOverflow(label) {
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${label}: document horizontal overflow`);
    }
    async function focusSearch(locator) {
      await locator.focus();
      const style = await locator.evaluate(input => ({ outline: getComputedStyle(input).outlineStyle, shadow: getComputedStyle(input).boxShadow }));
      assert.equal(style.outline, 'none', 'Search input has no inner outline');
      assert.equal(style.shadow, 'none', 'Search input has no inner shadow');
    }
    async function section(name) {
      const button = page.getByRole('button', { name, exact: true });
      if (!(await button.isVisible())) await page.locator('.admin-navigation-toggle').click();
      await button.click();
    }
    await page.goto('http://localhost:3000/admin');
    if (process.env.CRM_REFINEMENT_CSS_PREVIEW) await page.addStyleTag({ path: 'frontend/src/app/admin/components/participant-club-details.css' });
    await page.locator('.participant-row.checked-in').first().waitFor();
    await page.locator('.participant-row.checked-in').first().click();
    await page.locator('.route-toggle-number').first().waitFor();
    assert.equal(await page.locator('.route-toggle-number').first().evaluate(el => getComputedStyle(el).fontSize), '30px');
    assert.equal(await page.locator('.route-toggle-meta').first().evaluate(el => getComputedStyle(el).fontSize), '11px');
    assert.match(await page.locator('.participant-row.checked-in .person-score small').first().innerText(), /^\d+ трасс(?:а|ы)?$/);
    assert.equal(await page.locator('.participant-row.selected').evaluate(el => getComputedStyle(el).boxShadow), 'none');
    await focusSearch(page.getByLabel('Поиск по всем участникам фестиваля'));
    await noOverflow('desktop participants');
    await screenshot('participants-desktop');
    await page.locator('.route-toggle-number').first().scrollIntoViewIfNeeded();
    await screenshot('participant-routes-desktop');
    await section('Клубы');
    await page.locator('.club-bulk-actions').waitFor();
    assert.equal(await page.locator('.club-bulk-actions .reception-confirm').count(), 2);
    const backgrounds = await page.locator('.club-bulk-actions .reception-confirm').evaluateAll(items => items.map(el => getComputedStyle(el).backgroundImage));
    assert.equal(backgrounds[0], backgrounds[1]);
    for (const name of ['Отменить прибытие', 'Отменить оплату']) assert.equal(await page.getByRole('button', { name, exact: true }).locator('svg.lucide-x').count(), 1);
    await focusSearch(page.getByLabel('Найти клуб', { exact: true }));
    await screenshot('clubs-desktop');

    for (const width of [390, 360]) {
      await page.setViewportSize({ width, height: 844 });
      await section('Участники');
      await page.locator('.participant-row').first().waitFor();
      assert.equal(await page.locator('.participant-card').isVisible(), false, 'Mobile starts with list only');
      const list = page.locator('.participant-list');
      await list.evaluate(el => { el.scrollTop = 350; });
      const visibleIndex = await list.evaluate(el => [...el.querySelectorAll('.participant-row')].findIndex(row => { const r = row.getBoundingClientRect(), box = el.getBoundingClientRect(); return r.top >= box.top && r.bottom <= box.bottom; }));
      assert.ok(visibleIndex >= 0);
      const scroll = await list.evaluate(el => el.scrollTop);
      await page.locator('.participant-row').nth(visibleIndex).click();
      const dialog = page.getByRole('dialog', { name: 'Карточка участника' });
      await dialog.waitFor();
      assert.equal(await page.evaluate(() => document.body.style.overflow), 'hidden');
      await noOverflow(`participant ${width}`);
      await screenshot(`participant-mobile-${width}`);
      if (await dialog.locator('.route-toggle-number').count()) {
        await dialog.locator('.participant-card').evaluate(el => { const heading = el.querySelector('.routes-heading'); el.scrollTop += heading.getBoundingClientRect().top - el.getBoundingClientRect().top; });
        assert.equal(await dialog.locator('.route-grid').evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').length), 3);
        await screenshot(`participant-routes-mobile-${width}`);
      }
      await dialog.getByRole('button', { name: 'Закрыть: Карточка участника', exact: true }).click();
      await dialog.waitFor({ state: 'hidden' });
      assert.equal(await list.evaluate(el => el.scrollTop), scroll, 'Participant list scroll preserved');
      await screenshot(`participants-list-${width}`);
      await page.locator('.participant-row').nth(visibleIndex).click();
      await dialog.waitFor();
      await page.keyboard.press('Escape');
      await dialog.waitFor({ state: 'hidden' });
      await section('Клубы');
      const clubList = page.locator('.clubs-list');
      await page.locator('.club-list-item').first().waitFor();
      await clubList.evaluate(el => { el.scrollTop = 90; });
      await page.locator('.club-list-item').first().click();
      const clubScroll = await clubList.evaluate(el => el.scrollTop);
      const clubDialog = page.getByRole('dialog', { name: 'Карточка клуба' });
      await clubDialog.waitFor();
      await noOverflow(`club ${width}`);
      await screenshot(`club-mobile-${width}`);
      for (const selector of ['.club-detail-pane', '.club-members-table', '.responsive-detail-panel']) {
        const dimensions = await page.locator(`${selector}:visible`).evaluate(el => ({ scroll: el.scrollWidth, client: el.clientWidth, children: [...el.children].slice(0, 3).map(child => ({ width: child.getBoundingClientRect().width, scroll: child.scrollWidth, min: getComputedStyle(child).minWidth, grid: getComputedStyle(child).gridTemplateColumns })) }));
        assert.ok(dimensions.scroll <= dimensions.client + 1, `Club content ${selector} fits ${width}: ${JSON.stringify(dimensions)}`);
      }
      await screenshot(`club-mobile-${width}`);
      await page.getByRole('button', { name: 'Подтвердить прибытие', exact: true }).click();
      const confirm = page.getByRole('alertdialog');
      await confirm.waitFor();
      assert.ok(await confirm.evaluate(el => { const r = el.getBoundingClientRect(); return el.contains(document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)); }), 'Confirmation appears above card');
      assert.ok(await confirm.evaluate(el => el.contains(document.activeElement)), 'Confirmation initially receives focus');
      for (let index = 0; index < 7; index++) {
        await page.keyboard.press('Tab');
        assert.ok(await confirm.evaluate(el => el.contains(document.activeElement)), 'Tab stays inside confirmation');
      }
      await page.keyboard.press('Escape');
      await confirm.waitFor({ state: 'hidden' });
      assert.ok(await clubDialog.isVisible(), 'Escape only closes the top confirmation');
      await clubDialog.getByRole('button', { name: 'Закрыть: Карточка клуба', exact: true }).click();
      assert.equal(await clubList.evaluate(el => el.scrollTop), clubScroll, 'Club list scroll preserved');
    }
    assert.deepEqual(errors, []);
    console.log('PASS CRM participant/club desktop 1440 and mobile 390/360; route hierarchy, labels, search focus, modal scroll restoration, no horizontal overflow, reception buttons and layered confirmation; GET-only competition access.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
