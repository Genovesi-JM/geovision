// Fully intercepted browser QA: no cloud traffic, login or real credentials.
const { test, expect } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const ROOT = path.resolve(__dirname, '..');
const ORIGIN = 'https://pilot.example.test';
const runtimeScript = fs.readFileSync(path.join(ROOT, 'infra/azure/online_gateway/gateway.py'), 'utf8').match(/def runtime_script\(\):\s+return r"""([\s\S]*?)"""/)[1];
const unavailable = ['google-btn', 'microsoft-btn', 'forgot-link', 'forgot-email-link', 'toggle-create', 'create-form', 'forgot-email-overlay'];

async function mockPage(page, options = {}) {
  const requests = [];
  const posted = [];
  const postHeaders = [];
  if (options.pilot !== false) await page.addInitScript(runtimeScript);
  await page.addInitScript(({ origin, pilot }) => {
    window.API_BASE = origin + '/_pilot/api';
    if (pilot) window.GV_RUNTIME = Object.freeze({ mode: 'pilot', locale: 'es' });
    localStorage.setItem('gv_lang', 'pt');
  }, { origin: ORIGIN, pilot: options.pilot !== false });
  await page.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== ORIGIN) return route.abort();
    if (url.pathname.startsWith('/_pilot/api')) {
      requests.push({ method: request.method(), path: url.pathname });
      if (request.method() === 'POST') postHeaders.push(await request.allHeaders());
      if (url.pathname.endsWith('/ready')) return route.fulfill({ status: options.readyStatus || 200, contentType: 'application/json', body: '{"status":"ready"}' });
      if (url.pathname.endsWith('/_access-check')) {
        expect(request.postData()).toBe('{}');
        return route.fulfill({ status: options.accessStatus || 200, contentType: 'application/json', body: JSON.stringify({ status: options.accessBody || 'accepted' }) });
      }
      if (url.pathname.endsWith('/auth/login')) {
        posted.push(request.postDataJSON());
        return route.fulfill({ status: options.loginStatus || 503, contentType: options.htmlError ? 'text/html' : 'application/json', body: options.htmlError ? '<h1>PRIVATE_TECHNICAL_DETAIL</h1>' : '{"detail":"PRIVATE_TECHNICAL_DETAIL"}' });
      }
      return route.fulfill({ status: 403, contentType: 'application/json', body: '{}' });
    }
    let relative = url.pathname.replace(/^\//, '');
    if (relative === 'assets/js/chatbot.js' || relative === 'assets/js/contacts.js') return route.fulfill({ contentType: 'text/javascript', body: '/* disabled in hosted pilot */' });
    if (!(relative === 'login.html' || relative.startsWith('assets/')) || relative.includes('..')) return route.abort();
    const file = path.resolve(ROOT, relative);
    if (!file.startsWith(ROOT + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return route.abort();
    const types = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml', '.png': 'image/png' };
    const body = fs.readFileSync(file);
    const hashes = path.extname(file) === '.html' ? Array.from(body.toString().matchAll(/<script\b[^>]*>([\s\S]*?)<\/script\s*>/gi), match => match[1].trim() ? "'sha256-" + crypto.createHash('sha256').update(match[1]).digest('base64') + "'" : '').filter(Boolean) : [];
    return route.fulfill({ contentType: types[path.extname(file)] || 'application/octet-stream', body,
      headers: { 'Referrer-Policy': 'no-referrer', 'Content-Security-Policy': "default-src 'none'; script-src 'self' " + hashes.join(' ') + "; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'" } });
  });
  await page.goto(ORIGIN + '/login.html', { waitUntil: 'networkidle' });
  return { requests, posted, postHeaders };
}

for (const width of [360, 390, 1280]) {
  test(`pilot login is usable and Spanish at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 844 });
    const { requests } = await mockPage(page);
    await expect(page.locator('#login-submit')).toBeEnabled();
    await expect(page.locator('#pilot-notice')).toBeVisible();
    for (const id of unavailable) await expect(page.locator('#' + id)).toBeHidden();
    await expect(page.locator('#pilot-service-status')).toContainText('Servicio disponible');
    await expect(page.locator('#login-submit')).toHaveText('Iniciar Sesión');
    expect(await page.evaluate(() => localStorage.getItem('gv_lang'))).toBe('pt');
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    expect(await page.evaluate(() => document.body.scrollWidth)).toBeLessThanOrEqual(width);
    await page.screenshot({ path: info.outputPath(`pilot-login-${width}.png`), fullPage: true, animations: 'disabled' });
    expect(requests).toEqual([{ method: 'GET', path: '/_pilot/api/ready' }, { method: 'POST', path: '/_pilot/api/_access-check' }]);
  });
}

test('unavailable service blocks login without sending credentials', async ({ page }) => {
  const { requests } = await mockPage(page, { readyStatus: 503 });
  await expect(page.locator('#login-submit')).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Comprobar servicio' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Volver a validar acceso Microsoft' })).toHaveAttribute('href', '/.auth/login/aad?post_login_redirect_uri=%2Flogin.html%3Freturn%3D%2Fadmin.html');
  await page.locator('#login-form').evaluate(form => form.dispatchEvent(new Event('submit', { cancelable: true })));
  expect(requests.filter(request => request.method === 'POST')).toEqual([]);
  expect(requests.filter(request => request.path.endsWith('/ready'))).toHaveLength(1);
});

test('gateway failure is translated, blocks repeated submit and preserves password whitespace', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const { requests, posted } = await mockPage(page, { loginStatus: 503, htmlError: true });
  await expect(page.locator('#login-submit')).toBeEnabled();
  await page.fill('#login-email', 'synthetic@example.test');
  await page.fill('#login-password', ' synthetic-offline-only ');
  await page.locator('#login-submit').click();
  await expect(page.locator('#error-box')).toContainText('No se ha podido confirmar el acceso');
  await expect(page.locator('#error-box')).not.toContainText('PRIVATE_TECHNICAL_DETAIL');
  await expect(page.locator('#login-submit')).toBeDisabled();
  await page.locator('#login-form').evaluate(form => form.dispatchEvent(new Event('submit', { cancelable: true })));
  expect(requests.filter(request => request.path.endsWith('/auth/login'))).toHaveLength(1);
  expect(posted[0].password).toBe(' synthetic-offline-only ');
  await page.fill('#login-password', '');
  await page.screenshot({ path: info.outputPath('pilot-service-error-390.png'), fullPage: true, animations: 'disabled' });
});

test('invalid credentials remain distinct from service failure', async ({ page }) => {
  const { requests } = await mockPage(page, { loginStatus: 401 });
  await expect(page.locator('#login-submit')).toBeEnabled();
  await page.fill('#login-email', 'synthetic@example.test');
  await page.fill('#login-password', 'synthetic-offline-only');
  await page.locator('#login-submit').click();
  await expect(page.locator('#error-box')).toHaveText('El email o la contraseña no son correctos.');
  await expect(page.locator('#login-submit')).toBeEnabled();
  expect(requests.filter(request => request.path.endsWith('/auth/login'))).toHaveLength(1);
});

test('blocked connection stops before credentials and does not blame the account', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const { requests, posted } = await mockPage(page, { accessStatus: 403 });
  await expect(page.locator('#pilot-service-status')).toContainText('La protección del entorno no ha autorizado la conexión');
  await expect(page.locator('#login-submit')).toBeDisabled();
  await page.locator('#login-form').evaluate(form => form.dispatchEvent(new Event('submit', { cancelable: true })));
  expect(posted).toEqual([]);
  expect(requests).toEqual([{ method: 'GET', path: '/_pilot/api/ready' }, { method: 'POST', path: '/_pilot/api/_access-check' }]);
  await page.screenshot({ path: info.outputPath('pilot-access-blocked-390.png'), fullPage: true, animations: 'disabled' });
});

test('blocked login is not presented as an account denial and stops repeated submission', async ({ page }) => {
  const { postHeaders } = await mockPage(page, { loginStatus: 403 });
  await expect(page.locator('#login-submit')).toBeEnabled();
  await page.fill('#login-email', 'synthetic@example.test');
  await page.fill('#login-password', 'synthetic-offline-only');
  await page.locator('#login-submit').click();
  await expect(page.locator('#error-box')).toHaveText('La protección del entorno ha rechazado la solicitud. No se ha podido verificar tu acceso.');
  await expect(page.locator('#login-submit')).toBeDisabled();
  expect(postHeaders).toHaveLength(2);
  for (const headers of postHeaders) {
    expect(headers['x-geovision-client']).toBe('web');
  }
});

test('connection check must return the exact success marker', async ({ page }) => {
  const { posted } = await mockPage(page, { accessBody: 'unknown' });
  await expect(page.locator('#login-submit')).toBeDisabled();
  await expect(page.locator('#pilot-service-status')).toContainText('El servicio no está disponible');
  expect(posted).toEqual([]);
});

test('public mode preserves existing controls and language preference', async ({ page }) => {
  const { requests } = await mockPage(page, { pilot: false });
  await expect(page.locator('#google-btn')).toBeVisible();
  await expect(page.locator('#toggle-create')).toBeVisible();
  await expect(page.locator('#pilot-notice')).toBeHidden();
  await expect(page.locator('#pilot-service-status')).toHaveCount(0);
  expect(requests).toEqual([]);
});

test('theme and password controls work under hosted script restrictions', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockPage(page);
  await page.getByRole('button', { name: 'Mostrar contraseña', exact: true }).click();
  await expect(page.locator('#login-password')).toHaveAttribute('type', 'text');
  await page.getByRole('button', { name: 'Ocultar contraseña', exact: true }).click();
  await expect(page.locator('#login-password')).toHaveAttribute('type', 'password');
  await page.getByRole('button', { name: 'Activar modo claro', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await page.screenshot({ path: info.outputPath('pilot-login-light-390.png'), fullPage: true, animations: 'disabled' });
});
