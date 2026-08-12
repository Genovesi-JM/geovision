const { test, expect } = require('@playwright/test');

const BASE = process.env.TEST_BASE_URL || 'http://127.0.0.1:8001';

test.describe('B2C and B2B capability balance', () => {
  test('a homeowner can immediately find a purchasable path', async ({ page }) => {
    await page.goto(`${BASE}/index.html`, { waitUntil: 'domcontentloaded' });

    await expect(page.getByRole('heading', {
      name: 'Veja o que está a acontecer. Saiba quando agir.',
    })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Explorar dispositivos' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Casa & Propriedade' })).toBeVisible();
    await expect(page.getByText('GV Air', { exact: true }).first()).toBeVisible();
  });

  test('farm and construction visitors see sensors, tracking, aerial and platform capability', async ({ page }) => {
    await page.goto(`${BASE}/sectors.html`, { waitUntil: 'domcontentloaded' });

    const farm = page.locator('#agropecuaria');
    await expect(farm).toContainText('sensores, tracking, mapas e dados aéreos');
    await expect(farm).toContainText('Animais, GPS e geofences');

    const construction = page.locator('#construcao');
    await expect(construction).toContainText('sensor no terreno à visão aérea');
    await expect(construction).toContainText('Tracking e estado de equipamentos');
    await expect(construction).toContainText('Timeline, mapa, alertas e relatórios');
  });

  test('an enterprise buyer sees the five technology pillars and transparent statuses', async ({ page }) => {
    await page.goto(`${BASE}/technology.html`, { waitUntil: 'domcontentloaded' });

    for (const text of [
      '1 · Dispositivos & sensores',
      '2 · GPS & tracking',
      '3 · Inteligência aérea',
      '4 · Plataforma & mapas',
      '5 · IA & análise',
    ]) {
      await expect(page.getByText(text, { exact: true }).first()).toBeVisible();
    }
    await expect(page.getByText('GV Track', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Em desenvolvimento', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('DJI Matrice series', { exact: true })).toBeVisible();
  });

  test('strong legacy claims are not visible on the redesigned public journey', async ({ page }) => {
    for (const path of ['index.html', 'sectors.html', 'technology.html']) {
      await page.goto(`${BASE}/${path}`, { waitUntil: 'domcontentloaded' });
      const visibleText = await page.locator('body').innerText();
      expect(visibleText).not.toContain('±1–2 cm');
      expect(visibleText).not.toContain('21 ha/h');
      expect(visibleText).not.toContain('55 min');
      expect(visibleText).not.toContain('20 km');
    }
  });

  test('new capability copy switches cleanly to English and Spanish', async ({ page }) => {
    await page.goto(`${BASE}/index.html`, { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: 'EN', exact: true }).click();
    await expect(page.getByRole('link', { name: 'Explore devices' })).toBeVisible();
    await expect(page.getByText('Aerial intelligence', { exact: true }).first()).toBeVisible();

    await page.getByRole('button', { name: 'ES', exact: true }).click();
    await expect(page.getByRole('link', { name: 'Explorar dispositivos' })).toBeVisible();
    await expect(page.getByText('Inteligencia aérea', { exact: true }).first()).toBeVisible();
  });
});
