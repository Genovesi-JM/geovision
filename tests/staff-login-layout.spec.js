const { test, expect } = require('@playwright/test');

const BASE = process.env.TEST_BASE_URL || 'http://127.0.0.1:8001';
const API = 'http://127.0.0.1:8010';
const stamp = '2026-09-12T20:00:00Z';
const profile = {
  id: 'synthetic-staff', email: 'staff@example.test', name: 'Prueba de diseño', role: 'cliente', account: null,
  account_id: '', account_name: '', company_id: '',
  authorization_context: { user_id: 'synthetic-staff', internal_roles: ['GV_OPERATIONS'], permissions: ['operations:access'] },
};
const navigation = [
  ['dashboard', 'Resumen', 'dashboard'], ['organizations', 'Clientes y organizaciones', 'organizations'],
  ['assets', 'Activos', 'assets'], ['orders', 'Pedidos', 'orders'], ['jobs', 'Tareas', 'jobs'],
  ['missions', 'Misiones', 'missions'], ['processing', 'Procesamiento', 'processing'],
  ['reports_qa', 'Calidad de informes', 'reports-qa'], ['contractors', 'Colaboradores', 'contractors'],
  ['system_health', 'Estado del sistema', 'system-health'],
];

for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 844 }, { width: 360, height: 800 }]) {
  test(`synthetic staff login and operations fit ${viewport.width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    await page.addInitScript(() => { window.API_BASE = 'http://127.0.0.1:8010'; });
    const unexpected = [];
    const mocked = [];
    const blocked = [];
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin === new URL(BASE).origin) return route.continue();
      if (url.origin !== API) { blocked.push(url.origin); return route.abort(); }
      let body;
      if (url.pathname === '/auth/login') body = { access_token: 'synthetic-access-only', user: { id: profile.id, email: profile.email, role: profile.role }, account: null };
      else if (url.pathname === '/auth/me') body = profile;
      else if (url.pathname === '/operations/experience') body = {
        surface: 'INTERNAL_OPERATIONS', actor: { user_id: profile.id, roles: ['GV_OPERATIONS'], permissions: ['operations:access'] },
        capabilities: navigation.map(([key]) => key),
        navigation: navigation.map(([key, label, view]) => ({ key, label, path: `/admin.html?view=${view}`, capability: key })), generated_at: stamp,
      };
      else if (url.pathname === '/operations/dashboard') body = {
        generated_at: stamp, totals: { organizations: 0, assets: 0, orders: 0, jobs: 0, missions: 0, processing_jobs: 0, reports_review: 0, contractors: 0 },
        attention: {}, recent: [], health: { status: 'HEALTHY', event_dead_letters: 0, notification_dead_letters: 0, integration_dead_letters: 0, processing_failures: 0 },
      };
      else if (url.pathname === '/operations/queues') body = { generated_at: stamp, jobs: [], processing: [], reports_qa: [], integrations: [] };
      else if (url.pathname === '/contacts/') body = [];
      else { unexpected.push(url.pathname); return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' }); }
      mocked.push({ method: route.request().method(), path: url.pathname + url.search, status: 200 });
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });
    await page.goto(`${BASE}/login.html`, { waitUntil: 'networkidle' });
    await expect(page.locator('#login-submit')).toBeVisible();
    await expectNoOverflow(page, viewport.width);
    await page.screenshot({ path: testInfo.outputPath(`synthetic-login-${viewport.width}.png`), fullPage: true, animations: 'disabled' });
    await page.fill('#login-email', 'staff@example.test');
    await page.fill('#login-password', 'synthetic-offline-only');
    await page.locator('#login-submit').click();
    await expect(page.locator('#operations-app')).toBeVisible();
    await expect(page.locator('#operations-view')).toHaveAttribute('aria-busy', 'false');
    await expect(page.locator('#operations-view')).toContainText('Operaciones de un vistazo');
    await expectNoOverflow(page, viewport.width);
    await page.screenshot({ path: testInfo.outputPath(`synthetic-operations-${viewport.width}.png`), fullPage: true, animations: 'disabled' });
    if (viewport.width < 768) {
      await page.locator('#operations-menu').click();
      await expect(page.locator('#operations-menu')).toHaveAttribute('aria-expanded', 'true');
      await expect(page.locator('#operations-sidebar')).toHaveCSS('transform', 'matrix(1, 0, 0, 1, 0, 0)');
      await expectNoOverflow(page, viewport.width);
      await page.screenshot({ path: testInfo.outputPath(`synthetic-operations-menu-${viewport.width}.png`), fullPage: true, animations: 'disabled' });
    }
    expect(unexpected).toEqual([]);
    await testInfo.attach(`synthetic-network-${viewport.width}`, { body: Buffer.from(JSON.stringify({ mocked, blockedOrigins: [...new Set(blocked)] }, null, 2)), contentType: 'application/json' });
    console.log(`Synthetic ${viewport.width}px requests: ${mocked.map(request => `${request.method} ${request.path} ${request.status}`).join(' | ')}`);
  });
}

async function expectNoOverflow(page, width) {
  const size = await page.evaluate(() => ({ document: document.documentElement.scrollWidth, body: document.body.scrollWidth, viewport: innerWidth }));
  expect(size.viewport).toBe(width);
  expect(size.document).toBeLessThanOrEqual(width);
  expect(size.body).toBeLessThanOrEqual(width);
}
