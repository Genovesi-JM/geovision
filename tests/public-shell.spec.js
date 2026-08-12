const { test, expect } = require('@playwright/test');

const BASE = process.env.TEST_BASE_URL || 'http://127.0.0.1:8001';
const PUBLIC_PAGES = [
  'index.html',
  'about.html',
  'sectors.html',
  'technology.html',
  'loja.html',
  'login.html',
];

test.describe('Shared public shell', () => {
  test('loads the shared stylesheet on every public page', async ({ page }) => {
    for (const path of PUBLIC_PAGES) {
      await test.step(path, async () => {
        await page.goto(`${BASE}/${path}`, { waitUntil: 'domcontentloaded' });
        await expect(page.locator('.navbar')).toHaveCSS('position', 'fixed');
        await expect(page.locator('.navbar-nav')).toHaveCSS('display', 'flex');

        const shellLoaded = await page.evaluate(() =>
          [...document.styleSheets].some(sheet => sheet.href?.includes('/assets/css/public-shell.css'))
        );
        expect(shellLoaded).toBe(true);

        const brokenImages = await page.locator('img').evaluateAll(images =>
          images.filter(image => image.complete && image.naturalWidth === 0).map(image => image.getAttribute('src'))
        );
        expect(brokenImages).toEqual([]);
      });
    }
  });

  test('keeps the menu and language controls correct across viewport changes', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${BASE}/index.html`, { waitUntil: 'domcontentloaded' });

    const nav = page.locator('.navbar-nav');
    const menu = page.locator('#menu-toggle');
    const languages = page.locator('.lang-toggle');

    await expect(nav).toBeHidden();
    await expect(menu).toBeVisible();
    await expect(page.locator('.navbar-nav > .lang-toggle')).toHaveCount(1);

    await menu.click();
    await expect(nav).toBeVisible();
    await expect(menu).toHaveAttribute('aria-expanded', 'true');
    await expect(languages).toBeVisible();

    await page.setViewportSize({ width: 1280, height: 800 });
    await expect(nav).toBeVisible();
    await expect(menu).toHaveAttribute('aria-expanded', 'false');
    await expect(page.locator('.navbar > .lang-toggle')).toBeVisible();
  });

  test('reuses shared password and overlay interactions on the portal', async ({ page }) => {
    await page.goto(`${BASE}/login.html`, { waitUntil: 'domcontentloaded' });

    const password = page.locator('#login-password');
    const toggle = page.locator('.toggle-password').first();
    await expect(password).toHaveAttribute('type', 'password');
    await toggle.click();
    await expect(password).toHaveAttribute('type', 'text');
    await expect(toggle).toHaveAttribute('aria-pressed', 'true');

    const overlay = page.locator('#forgot-email-overlay');
    await page.locator('#forgot-email-link').click();
    await expect(overlay).toBeVisible();
    await expect(overlay).toHaveAttribute('aria-hidden', 'false');
    await page.locator('#close-forgot-email').click();
    await expect(overlay).toBeHidden();
  });
});
