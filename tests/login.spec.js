const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

// IMPORTANT: start a static server serving the repo root before running this test.
// Example: python3 -m http.server 8001 --bind 127.0.0.1
const BASE = process.env.TEST_BASE_URL || 'http://127.0.0.1:8001';

test.describe('Login smoke + a11y', () => {
  test('renders the sign-in form with no serious a11y violations', async ({ page }) => {
    const url = `${BASE}/login.html`;
    await page.goto(url, { waitUntil: 'domcontentloaded' });

    const btn = page.locator('#login-submit');
    await expect(btn).toBeVisible();

    // accessibility check using AxeBuilder (v4 API)
    const accessibilityScanResults = await new AxeBuilder({ page }).analyze();
    expect(accessibilityScanResults.violations.filter(v => 
      v.impact === 'critical' || v.impact === 'serious'
    )).toEqual([]);
  });

  test('can login with configured credentials', async ({ page }) => {
    const email = process.env.E2E_LOGIN_EMAIL;
    const password = process.env.E2E_LOGIN_PASSWORD;
    test.skip(!email || !password, 'Set E2E_LOGIN_EMAIL and E2E_LOGIN_PASSWORD to run the authenticated smoke test.');

    await page.goto(`${BASE}/login.html`, { waitUntil: 'domcontentloaded' });
    await page.fill('#login-email', email);
    await page.fill('#login-password', password);
    await page.locator('#login-submit').click();

    await page.waitForFunction(() => {
      const success = document.querySelector('#success-box');
      return /\/(admin|dashboard)\.html$/.test(window.location.pathname) || success?.classList.contains('show');
    }, null, { timeout: 5000 });
  });

  test('uses service-first account setup without an account-type choice', async ({ page }) => {
    await page.goto(`${BASE}/login.html`, { waitUntil: 'domcontentloaded' });
    await page.locator('#toggle-create').click();
    await page.fill('#create-email', 'profile-check@example.com');
    await page.fill('#create-email-confirm', 'profile-check@example.com');
    await page.locator('#wizard-next').click();
    await page.fill('#create-password', 'profile-check-123');
    await page.fill('#create-password-confirm', 'profile-check-123');
    await page.locator('#wizard-next').click();

    await expect(page.locator('#create-intent option')).toHaveCount(4);
    await expect(page.locator('#create-intent')).toContainText('Pedir um serviço');
    await expect(page.locator('#create-intent')).toContainText('Monitorizar um ativo');
    await expect(page.locator('#create-intent')).toContainText('Comprar um produto');
    await expect(page.locator('#create-intent')).toContainText('Ver um convite');
    await expect(page.locator('#create-form')).toContainText('Não precisa de escolher um tipo de conta');
    await expect(page.locator('#create-persona')).toHaveCount(0);
  });

  test('invitation fragment survives authentication context and opens existing work', async ({ page }) => {
    const invitationToken = 'phase6_secure_invitation_token_12345678901234567890';
    let acceptedBody = null;
    let acceptedAuthorization = null;
    await page.addInitScript(() => {
      localStorage.setItem('gv_token', 'recipient-access-token');
      localStorage.setItem('gv_user', JSON.stringify({
        id: 'recipient-1', email: 'recipient@example.test', role: 'cliente',
      }));
    });
    await page.route('**/invitations/preview', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          invitation_id: 'invite-1',
          organization_name: 'Existing Water Operations',
          workspace_name: 'River Monitoring',
          target_email_hint: 'r********@example.test',
          intended_role: 'viewer',
          status: 'pending',
          expires_at: '2026-09-10T12:00:00',
          destination: {
            kind: 'asset', organization_id: 'org-1', workspace_id: 'workspace-1',
            target_id: 'asset-existing-1', path: '/assets/asset-existing-1',
          },
        }),
      });
    });
    await page.route('**/invitations/accept', async (route) => {
      acceptedBody = route.request().postDataJSON();
      acceptedAuthorization = await route.request().headerValue('authorization');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          accepted: true,
          idempotent: false,
          invitation: {
            destination: {
              kind: 'asset', organization_id: 'org-1', workspace_id: 'workspace-1',
              target_id: 'asset-existing-1', path: '/assets/asset-existing-1',
            },
          },
        }),
      });
    });
    await page.route('**/dashboard.html?asset=*', async (route) => {
      await route.fulfill({ status: 200, contentType: 'text/html', body: '<title>Existing asset</title>' });
    });

    await page.goto(`${BASE}/onboarding.html#invitation=${invitationToken}`, {
      waitUntil: 'domcontentloaded',
    });
    await expect(page).toHaveURL(`${BASE}/onboarding.html`);
    await expect(page.locator('input[value="view_invitation"]')).toBeChecked();
    await expect(page.locator('#starter-fields')).toBeHidden();
    await expect(page.locator('#invitation-summary')).toContainText('Existing Water Operations');
    await page.locator('#submit-btn').click();
    await page.waitForURL(/dashboard\.html\?asset=asset-existing-1$/);

    expect(acceptedBody).toEqual({ token: invitationToken });
    expect(acceptedAuthorization).toBe('Bearer recipient-access-token');
    expect(await page.evaluate(() => sessionStorage.getItem('gv_pending_invitation'))).toBeNull();
    expect(await page.evaluate(() => localStorage.getItem('gv_account_id'))).toBe('workspace-1');
  });

  test('web password login requests an access-only session and clears stale refresh state', async ({ page }) => {
    let clientHeader = '';
    await page.route('**/auth/login', async (route) => {
      clientHeader = await route.request().headerValue('x-geovision-client') || '';
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'web-access-token',
          refresh_token: 'must-not-be-persisted',
          user: { email: 'web@example.test', role: 'cliente', name: 'Web User' },
          account: { id: 'web-account', name: 'Web Account' },
        }),
      });
    });
    await page.route('**/dashboard.html', async (route) => {
      await route.fulfill({ status: 200, contentType: 'text/html', body: '<title>Dashboard</title>' });
    });

    await page.goto(`${BASE}/login.html`, { waitUntil: 'domcontentloaded' });
    await page.evaluate(() => localStorage.setItem('gv_refresh_token', 'stale-family'));
    await page.fill('#login-email', 'web@example.test');
    await page.fill('#login-password', 'password-123');
    await page.locator('#login-submit').click();
    await page.waitForURL(/\/dashboard\.html$/, { timeout: 3000 });

    expect(clientHeader).toBe('web');
    expect(await page.evaluate(() => localStorage.getItem('gv_token'))).toBe('web-access-token');
    expect(await page.evaluate(() => localStorage.getItem('gv_refresh_token'))).toBeNull();
  });

  test('OAuth callback rejects query credentials and external redirects', async ({ page }) => {
    await page.goto(
      `${BASE}/auth-callback.html?token=forged&redirect=https://example.org`,
      { waitUntil: 'domcontentloaded' },
    );

    await page.waitForURL(/\/login\.html$/, { timeout: 3000 });
    expect(new URL(page.url()).origin).toBe(new URL(BASE).origin);
    expect(await page.evaluate(() => localStorage.getItem('gv_token'))).toBeNull();
  });

  test('OAuth callback validates the token and trusts server profile data only', async ({ page }) => {
    const browserNonce = 'b'.repeat(64);
    await page.route('**/dashboard.html', async (route) => {
      await route.fulfill({ status: 200, contentType: 'text/html', body: '<title>Dashboard</title>' });
    });
    await page.route('**/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '30000000-0000-4000-8000-000000000001',
          email: 'verified@example.test',
          name: 'Verified User',
          role: 'cliente',
          account_id: 'workspace-1',
          account_name: 'Verified Workspace',
        }),
      });
    });

    await page.goto(`${BASE}/login.html`, { waitUntil: 'domcontentloaded' });
    await page.evaluate((nonce) => {
      sessionStorage.setItem('gv_oauth_nonce_google', nonce);
    }, browserNonce);
    await page.goto(
      `${BASE}/auth-callback.html#token=verified-token&provider=google&browser_nonce=${browserNonce}&email=forged@example.test&role=admin&redirect=https://example.org`,
      { waitUntil: 'domcontentloaded' },
    );
    await page.waitForURL(/\/dashboard\.html$/, { timeout: 3000 });

    expect(new URL(page.url()).origin).toBe(new URL(BASE).origin);
    const stored = await page.evaluate(() => ({
      token: localStorage.getItem('gv_token'),
      email: localStorage.getItem('gv_email'),
      role: localStorage.getItem('gv_role'),
    }));
    expect(stored).toEqual({
      token: 'verified-token',
      email: 'verified@example.test',
      role: 'cliente',
    });
  });

  test('Password reset reads only a fragment secret and clears the address bar', async ({ page }) => {
    await page.goto(`${BASE}/reset-password.html#token=fragment-secret`, {
      waitUntil: 'domcontentloaded',
    });

    await expect(page.locator('#reset-token')).toHaveValue('fragment-secret');
    expect(page.url()).toBe(`${BASE}/reset-password.html`);

    await page.goto(`${BASE}/reset-password.html?token=query-secret`, {
      waitUntil: 'domcontentloaded',
    });
    await expect(page.locator('#reset-token')).toHaveValue('');
    expect(page.url()).toBe(`${BASE}/reset-password.html`);
  });
});
