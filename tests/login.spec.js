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

  test('adapts account setup to the selected customer profile', async ({ page }) => {
    await page.goto(`${BASE}/login.html`, { waitUntil: 'domcontentloaded' });
    await page.locator('#toggle-create').click();
    await page.fill('#create-email', 'profile-check@example.com');
    await page.fill('#create-email-confirm', 'profile-check@example.com');
    await page.locator('#wizard-next').click();
    await page.fill('#create-password', 'profile-check-123');
    await page.fill('#create-password-confirm', 'profile-check-123');
    await page.locator('#wizard-next').click();

    await expect(page.locator('#create-persona option')).toHaveCount(6);
    await page.locator('#create-persona').selectOption('industry');
    await expect(page.locator('#create-sectors')).toContainText('Indústria & Mineração');
    await expect(page.locator('#create-use-cases')).toContainText('Inventário visual');
    await expect(page.locator('#create-dashboard-hint')).toHaveText('Console operacional para indústria ou mineração.');
  });
});
