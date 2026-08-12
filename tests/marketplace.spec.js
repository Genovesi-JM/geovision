const { test, expect } = require('@playwright/test');
const BASE = process.env.TEST_BASE_URL || 'http://127.0.0.1:8001';

test.describe('Controlled marketplace', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.clear();
      localStorage.setItem('gv_marketplace_sector', 'environment');
    });
    await page.goto(`${BASE}/loja.html`);
    await page.locator('#sector-filters [data-sector="all"]').click();
  });

  test('renders only the active catalogue and localizes dynamic product copy', async ({ page }) => {
    await expect(page.locator('.loja-card')).toHaveCount(17);
    await expect(page.getByText('Energy & Power Monitor')).toHaveCount(0);
    await expect(page.getByText('Pulverização de Precisão')).toHaveCount(0);

    await page.getByRole('button', { name: 'EN', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Essential Aerial Mapping' })).toBeVisible();
    await expect(page.locator('.btn-add').first()).toHaveText('Add');
    await expect(page.locator('.deliverables-preview').first())
      .toContainText('Mapped visual evidence');
    await expect(page.locator('#loja-account-recommendation'))
      .toContainText('Recommended solutions for your account');

    await page.getByRole('button', { name: 'ES', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Cartografía Aérea Esencial' })).toBeVisible();
    await expect(page.locator('.btn-add').first()).toHaveText('Añadir');
  });

  test('keeps recommendation and featured badges separate', async ({ page }) => {
    const card = page.locator('.loja-card').filter({
      has: page.getByRole('heading', { name: 'Mapeamento Aéreo Essencial' }),
    });
    const recommended = await card.locator('.recommended-badge').boundingBox();
    const featured = await card.locator('.featured-badge').boundingBox();
    expect(recommended).not.toBeNull();
    expect(featured).not.toBeNull();
    const overlaps = recommended.x < featured.x + featured.width &&
      recommended.x + recommended.width > featured.x &&
      recommended.y < featured.y + featured.height &&
      recommended.y + recommended.height > featured.y;
    expect(overlaps).toBe(false);
  });

  test('sector warning remains informative and continuing adds the product', async ({ page }) => {
    const product = page.locator('.loja-card').filter({
      has: page.getByRole('heading', { name: 'Kit de Sondas de Solo' }),
    });
    await product.locator('.btn-add').click();
    await expect(page.locator('#sector-warning-modal')).toBeVisible();
    await expect(page.locator('#sector-warning-message'))
      .toContainText('Agro e pecuária');
    await page.locator('#sector-warning-continue').click();
    await expect(page.locator('#sector-warning-modal')).toBeHidden();
    await expect(page.locator('#cart-count')).toContainText('1 item');
    await expect(page.locator('.loja-cart-item-name'))
      .toHaveText('Kit de Sondas de Solo');
  });
});
