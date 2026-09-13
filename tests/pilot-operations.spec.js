// Isolated browser fixtures. Every request is intercepted; no real cloud data.
const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const ROOT = path.resolve(__dirname, '..');
const ORIGIN = 'https://pilot.example.test';
const NAV = [['dashboard', 'Resumen', 'dashboard'], ['jobs', 'Tareas', 'jobs'], ['missions', 'Misiones', 'missions'], ['processing', 'Procesamiento', 'processing'], ['reports_qa', 'Calidad de informes', 'reports-qa'], ['integrations', 'Integraciones', 'integrations']];
const stamp = '2026-09-13T00:00:00Z';

async function setup(page, { pilot = true, failure = null, view = 'jobs' } = {}) {
  const seen = [];
  await page.addInitScript(({ origin, pilot }) => {
    window.API_BASE = origin + '/_pilot/api';
    if (pilot) window.GV_RUNTIME = Object.freeze({ mode: 'pilot', locale: 'es' });
    if (!location.pathname.startsWith('/.auth/')) localStorage.setItem('gv_token', 'offline-fixture-not-a-credential');
  }, { origin: ORIGIN, pilot });
  await page.route('**/*', async route => {
    const req = route.request(), url = new URL(req.url());
    if (url.origin !== ORIGIN) return route.abort();
    if (url.pathname.startsWith('/.auth/')) return route.fulfill({ contentType: 'text/html', body: '<p>Offline identity destination</p>' });
    if (url.pathname.startsWith('/_pilot/api')) {
      const target = url.pathname.slice('/_pilot/api'.length);
      seen.push({ method: req.method(), path: target });
      if (failure === 'network') return route.abort('failed');
      if (failure === 'denied') return route.fulfill({ status: 403, contentType: 'application/json', body: '{}' });
      let body;
      if (target === '/operations/experience') body = {
        surface: 'INTERNAL_OPERATIONS', actor: { user_id: 'fixture-user', roles: ['GV_SUPER_ADMIN'], permissions: ['operations:access', 'platform:admin', 'report:review', 'report:publish'] },
        capabilities: NAV.map(([key]) => key), navigation: NAV.map(([key, label, dest]) => ({ key, label, path: '/admin.html?view=' + dest, capability: key })),
      };
      else if (target === '/operations/dashboard') body = { generated_at: stamp, totals: { jobs: 1 }, attention: {}, recent: [] };
      else if (target === '/operations/jobs') body = [{ id: 'job-1', job_number: 'PRUEBA-001', title: 'Inspección de prueba · España', state: 'READY', priority: 'NORMAL', scheduled_start: stamp }];
      else if (target === '/missions/internal') body = [{ id: 'mission-1', title: 'Misión de prueba', state: 'DRAFT' }];
      else if (target === '/operations/queues') body = { processing: [{ id: 'process-1', status: 'FAILED', retries_remaining: 1 }], reports_qa: [{ id: 'report-1', title: 'Informe de prueba', status: 'REVIEW_REQUIRED' }, { id: 'report-2', title: 'Revisión aprobada', status: 'APPROVED' }], integrations: [] };
      else if (target === '/operations/providers') body = { items: [
        { key: 'copernicus', label: 'Copernicus Data Space', family: 'Satélite', state: 'configured_unverified', next_step: 'Catálogo público; descarga pendiente.', public_check_available: true },
        { key: 'miteco', label: 'MITECO', family: 'Medio ambiente', state: 'configured_unverified', next_step: 'Colección ambiental de España.', public_check_available: true },
        { key: 'aemet', label: 'AEMET OpenData', family: 'Meteorología', state: 'configured_unverified', next_step: 'Clave solo en servidor.', public_check_available: false, credentialed_check_available: true },
        { key: 'arcgis', label: 'ArcGIS', family: 'GIS del cliente', state: 'not_implemented', next_step: 'Adaptador pendiente.', public_check_available: false },
      ] };
      else if (target === '/operations/providers/miteco/check') body = { provider: 'miteco', status: 'reachable_no_data', records: 0, checked_at: stamp };
      else if (target === '/operations/providers/aemet/check') body = { provider: 'aemet', status: 'response_verified', records: 1, metric_count: 6, observed_at: stamp, checked_at: stamp };
      else if (target === '/operations/providers/copernicus/check') return route.fulfill({ status: 503, contentType: 'application/json', body: '{}' });
      else return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' });
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
    }
    const relative = url.pathname.slice(1);
    if (!(relative === 'admin.html' || relative.startsWith('assets/')) || relative.includes('..')) return route.abort();
    const file = path.resolve(ROOT, relative);
    if (!file.startsWith(ROOT + path.sep) || !fs.existsSync(file)) return route.abort();
    const type = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css' }[path.extname(file)] || 'application/octet-stream';
    return route.fulfill({ contentType: type, body: fs.readFileSync(file), headers: { 'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'" } });
  });
  await page.goto(ORIGIN + '/admin.html?view=' + view);
  return seen;
}

for (const width of [390, 1280]) {
  test(`provider catalogue is honest and fits ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 844 });
    const seen = await setup(page, { view: 'integrations' });
    await expect(page.getByRole('heading', { name: 'APIs y proveedores' })).toBeVisible();
    await expect(page.getByText('Configurado; falta validación')).toHaveCount(3);
    await expect(page.getByRole('button', { name: 'Comprobar fuente pública' })).toHaveCount(2);
    expect(seen.every(item => item.method === 'GET')).toBe(true);
    await page.getByRole('button', { name: 'Comprobar fuente pública' }).nth(1).click();
    await expect(page.getByText(/Fuente accesible sin datos/)).toBeVisible();
    await page.getByRole('button', { name: 'Comprobar fuente pública' }).nth(0).click();
    await expect(page.getByText('No se ha podido verificar la fuente. No se ha repetido la solicitud.', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Comprobar observación AEMET' }).click();
    await expect(page.getByText(/Observación AEMET verificada · 6 variables/)).toBeVisible();
    expect(seen.filter(item => item.method === 'POST')).toHaveLength(3);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await page.screenshot({ path: info.outputPath(`provider-catalogue-${width}.png`), fullPage: true });
  });
}

for (const width of [360, 390, 1280]) {
  test(`pilot operations is honest and fits ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 844 });
    const seen = await setup(page);
    await expect(page.getByText('Inspección de prueba · España')).toBeVisible();
    await expect(page.locator('#operations-pilot-notice')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Gestionar' })).toHaveCount(0);
    await expect(page.getByText('Solo consulta', { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    if (width < 640) expect(await page.locator('.table-scroll').evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath(`pilot-operations-${width}.png`), fullPage: true });
    expect(seen.every(req => req.method === 'GET')).toBe(true);
  });
}

for (const view of ['processing', 'reports-qa', 'missions']) {
  test(`pilot ${view} offers no unsupported mutation`, async ({ page }) => {
    const seen = await setup(page, { view });
    await expect(page.locator('#operations-view')).toContainText('Solo consulta');
    for (const name of ['Reintentar', 'Aprobar', 'Publicar', 'Aplicar']) await expect(page.getByRole('button', { name, exact: true })).toHaveCount(0);
    expect(seen.every(req => req.method === 'GET')).toBe(true);
  });
}

test('public operations retains its existing management actions', async ({ page }) => {
  await setup(page, { pilot: false });
  await expect(page.getByRole('button', { name: 'Gestionar' })).toBeVisible();
  await expect(page.locator('#operations-pilot-notice')).toBeHidden();
});

test('network failure is not mislabeled as a role denial and has explicit revalidation', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const seen = await setup(page, { failure: 'network' });
  await expect(page.locator('#operations-denied')).toBeVisible();
  await expect(page.locator('#operations-denied-message')).toContainText('No se ha podido confirmar el acceso');
  await expect(page.locator('#pilot-revalidate')).toHaveAttribute('href', '/.auth/login/aad?post_login_redirect_uri=%2Flogin.html%3Freturn%3D%2Fadmin.html');
  expect(seen).toHaveLength(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: info.outputPath('pilot-revalidate-390.png'), fullPage: true });
});

test('actual permission denial does not offer a misleading revalidation', async ({ page }) => {
  await setup(page, { failure: 'denied' });
  await expect(page.locator('#operations-denied-message')).toContainText('no tiene permiso');
  await expect(page.locator('#pilot-revalidate')).toHaveCount(0);
});

test('pilot logout clears app session and navigates to Microsoft session logout', async ({ page }) => {
  await setup(page);
  await expect(page.locator('#operations-app')).toBeVisible();
  await page.locator('#operations-logout').click();
  await expect(page).toHaveURL(ORIGIN + '/.auth/logout');
  expect(await page.evaluate(() => localStorage.getItem('gv_token'))).toBeNull();
});
