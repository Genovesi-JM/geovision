const { test, expect } = require('@playwright/test');
const { injectAxe, checkA11y } = require('@axe-core/playwright');

// IMPORTANT: start a static server serving the repo root before running this test.
// Example: python3 -m http.server 8001 --bind 127.0.0.1
const BASE = process.env.TEST_BASE_URL || 'http://127.0.0.1:8001';

test.describe('Login smoke + a11y', () => {
  test('can login with demo credentials and has no serious a11y violations', async ({ page }) => {
    const url = `${BASE}/login.html`;
    await page.goto(url, { waitUntil: 'domcontentloaded' });

    // inject axe for accessibility checks
    await injectAxe(page);

    // fill and submit the form
    await page.fill('#login-email', 'teste@admin.com');
    await page.fill('#login-password', '123456');

    // ensure button is present and click
    const btn = page.locator('button[type=submit]');
    await expect(btn).toBeVisible();

    await btn.click();

    // wait for either success or demo redirect text to appear
    const success = page.locator('#success-box');
    await expect(success).toBeVisible({ timeout: 5000 });

    // accessibility check - will throw if violations above thresholds are found
    await checkA11y(page, null, {
      detailedReport: true,
      detailedReportOptions: { html: true }
    });
  });
});
