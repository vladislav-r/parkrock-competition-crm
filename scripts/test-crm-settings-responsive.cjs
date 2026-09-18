const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');

// Read-only UI review: fixtures replace responses in this browser only.
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const output = 'reports/crm-refinement';
  fs.mkdirSync(output, { recursive: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(String(error)));
    const login = await page.request.post('http://localhost:8001/api/v1/auth/login', { form: { username: 'admin@parkrock.test', password: 'demo1234' } });
    assert.ok(login.ok(), 'Login');
    const token = (await login.json()).access_token;
    const headers = { Authorization: `Bearer ${token}` };
    const me = await (await page.request.get('http://localhost:8001/api/v1/auth/me', { headers })).json();
    const event = await (await page.request.get('http://localhost:8001/api/v1/admin/event', { headers })).json();
    const existingGroups = await (await page.request.get('http://localhost:8001/api/v1/admin/route-groups', { headers })).json();
    const fixtureGroups = [{ id: 'qa-green', from_grade: '6A', to_grade: '6B', grade: '6A–6B', color: '#00aa55', points: 10, version: 1, route_count: 75, route_versions: {} }];
    const groups = existingGroups.length ? existingGroups : fixtureGroups;
    const routeFixtures = Array.from({ length: 75 }, (_, i) => ({ id: `qa-route-${i}`, number: i + 1, name: '', grade: groups[0].grade, group_id: groups[0].id, points: groups[0].points, is_active: true, version: 1 }));
    const useRouteFixtures = !event.routes.some(route => groups.some(group => group.id === route.group_id));
    let presenceRequests = 0;
    const presence = (full_name, status, latency_ms) => ({ full_name, role: 'secretary', status, latency_ms, last_seen: new Date().toISOString(), age_seconds: 1 });
    await page.addInitScript(value => localStorage.setItem('parkrock_admin_token', value), token);
    assert.ok(me.permissions.includes('users.presence'), 'Administrator has the real users.presence permission');
    await page.route('**/api/v1/admin/**', async route => {
      assert.equal(route.request().method(), 'GET', 'This review must never write admin data');
      const pathname = new URL(route.request().url()).pathname;
      if (pathname.endsWith('/users/presence')) {
        presenceRequests++;
        return route.fulfill({ json: {
          [me.id]: presence('QA Текущий сотрудник', 'online', 11),
          'qa-online': presence('QA Сотрудник онлайн', 'online', 84),
          'qa-unstable': presence('QA Медленное соединение', 'unstable', 1350),
          'qa-offline': presence('QA Сотрудник оффлайн', 'offline', null),
        } });
      }
      if (pathname.endsWith('/event') && useRouteFixtures) return route.fulfill({ json: { ...event, routes: routeFixtures } });
      if (pathname.endsWith('/route-groups')) return route.fulfill({ json: groups });
      if (pathname.endsWith('/applications')) {
        const response = await route.fetch();
        const items = await response.json();
        return route.fulfill({ response, json: items.length ? items : [{ id: 'qa-application', filename: 'Коллективная заявка очень длинное название клуба для проверки мобильной версии.xlsx', file_size: 20480, participant_count: 57, duplicate_rows: 0, overflow_sets: 0, status: 'pending', uploaded_at: new Date().toISOString(), imported_at: null, import_count: 0 }] });
      }
      return route.continue();
    });
    await page.goto('http://localhost:3000/admin');
    if (process.argv.includes('--source-css')) await page.addStyleTag({ content: fs.readFileSync('frontend/src/app/admin/components/routes-responsive.css', 'utf8') });
    await page.locator('.admin-header').waitFor();
    async function choose(label) {
      const toggle = page.locator('.admin-navigation-toggle');
      if (await toggle.isVisible()) {
        assert.equal(await toggle.evaluate(element => Boolean(element.closest('.admin-header'))), true);
        await toggle.click();
        assert.equal(await toggle.getAttribute('aria-expanded'), 'true');
      }
      await page.locator('#admin-navigation').getByRole('button', { name: label, exact: true }).click();
      if (await toggle.isVisible()) assert.equal(await toggle.getAttribute('aria-expanded'), 'false');
    }
    async function checkLayout(name, selector, width) {
      await page.locator(selector).waitFor();
      await page.waitForTimeout(250);
      const result = await page.locator(selector).evaluate(root => {
        const failures = [];
        const selectors = '.applications-table-wrap,.applications-table,.category-config-table,.category-config-row,.compact-route-grid,.team-settings-grid';
        for (const element of [root, ...root.querySelectorAll(selectors)]) {
          if (element.clientWidth && element.scrollWidth > element.clientWidth + 2) failures.push(`${element.className}: ${element.scrollWidth}/${element.clientWidth}`);
        }
        for (const element of root.querySelectorAll('input:not([type=hidden]),select')) {
          if (!element.getClientRects().length) continue;
          const bounds = element.getBoundingClientRect();
          if (bounds.width < 20 || bounds.left < -1 || bounds.right > innerWidth + 1) failures.push(`input: ${element.getAttribute('aria-label')} ${bounds.left}/${bounds.right}`);
        }
        if (document.documentElement.scrollWidth > innerWidth + 1) failures.push(`page: ${document.documentElement.scrollWidth}/${innerWidth}`);
        return failures;
      });
      await page.screenshot({ path: `${output}/${name}-${width}.png`, fullPage: true });
      assert.deepEqual(result, [], `${name}, width=${width}`);
    }
    for (const width of [360, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const [label, name, selector] of [['Трассы', 'routes', '.routes-config-pane'], ['Категории', 'categories', '.categories-pane'], ['Заявки', 'applications', '.applications-section']]) {
        await choose(label);
        if (name === 'routes') {
          await page.locator('.route-static-number').first().waitFor();
          const sourceRoutes = useRouteFixtures ? routeFixtures : event.routes;
          const colored = sourceRoutes.find(route => groups.some(group => group.id === route.group_id));
          const group = groups.find(group => group.id === colored.group_id);
          const badge = page.locator('.route-static-number').filter({ hasText: new RegExp(`^${colored.number}$`) });
          const actual = await badge.evaluate(element => getComputedStyle(element).backgroundColor);
          const expected = `rgb(${[1, 3, 5].map(offset => parseInt(group.color.slice(offset, offset + 2), 16)).join(', ')})`;
          assert.equal(actual, expected, 'Route number uses its category color');
        }
        if (name === 'categories') await page.locator('.category-config-row').first().waitFor();
        if (name === 'applications') await page.locator('.applications-table tbody tr').first().waitFor();
        await checkLayout(name, selector, width);
      }
      await choose('Настройки');
      await page.locator('.settings-relief-sidebar').getByRole('button', { name: 'Командный зачёт', exact: true }).click();
      await page.getByText('Проверяем готовность результатов…', { exact: true }).waitFor({ state: 'hidden' });
      await checkLayout('team-settings', '.team-settings-grid', width);
      assert.ok(await page.locator('.team-settings-grid').evaluate(root => root.querySelector('form').getBoundingClientRect().bottom <= root.querySelector('.team-rules-card').getBoundingClientRect().top), 'Input settings precede rules');
      if (width <= 760) {
        const toggle = page.locator('.admin-navigation-toggle');
        await toggle.click();
        await page.keyboard.press('Escape');
        assert.equal(await toggle.getAttribute('aria-expanded'), 'false', 'Escape closes navigation');
      }
      await choose('Трассы'); // Stop the users settings poll before testing the menu poll.
      await page.locator('.admin-user-menu summary').click();
      await page.waitForTimeout(300);
      await page.locator('.online-staff .user-connection.online').waitFor();
      const staff = await page.locator('.online-staff').innerText();
      assert.match(staff, /QA Сотрудник онлайн/);
      assert.match(staff, /Онлайн · 84 мс/);
      assert.match(staff, /Нестабильно · 1\s?350 мс/);
      assert.doesNotMatch(staff, /QA Текущий сотрудник|QA Сотрудник оффлайн/);
      await checkLayout('profile', '.admin-user-dropdown', width);
      await page.keyboard.press('Escape');
      await page.locator('.online-staff').waitFor({ state: 'detached' });
      const closedCount = presenceRequests;
      await page.waitForTimeout(5400);
      assert.equal(presenceRequests, closedCount, 'Profile stops polling when closed');
    }
    assert.deepEqual(errors, []);
    console.log('PASS: routes, categories, applications, team settings; 360/390/768/1440; colored route numbers; profile presence; mobile navigation. No admin writes.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
