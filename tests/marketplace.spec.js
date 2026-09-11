const { test, expect } = require('@playwright/test');
const BASE = process.env.TEST_BASE_URL || 'http://127.0.0.1:8001';

test.describe('GeoVision first-party catalogue', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.clear();
      localStorage.setItem('gv_lang', 'pt');
      localStorage.setItem('gv_catalog_sector', 'environment');
    });
    await page.goto(`${BASE}/loja.html`);
    await page.locator('#sector-filters [data-sector="all"]').click();
  });

  test('renders only the active catalogue and localizes dynamic product copy', async ({ page }) => {
    const publicFilters = page.locator('#sector-filters [data-sector]:not([data-sector="all"])');
    await expect(publicFilters).toHaveCount(6);
    expect(await publicFilters.evaluateAll((buttons) => buttons.map((button) => button.dataset.sector))).toEqual([
      'agriculture',
      'construction_infrastructure',
      'environment',
      'mining',
      'industry_energy_utilities',
      'ports_logistics',
    ]);
    await page.locator('#sector-filters [data-sector="mining"]').click();
    await expect(page.locator('.loja-card')).toHaveCount(6);
    await expect(page.getByRole('heading', { name: 'Voo Volumétrico de Mina' })).toHaveCount(0);
    await page.locator('#sector-filters [data-sector="industry_energy_utilities"]').click();
    await expect(page.locator('.loja-card')).toHaveCount(8);
    await expect(page.getByRole('heading', { name: /GV Track/ })).toBeVisible();
    await page.locator('#sector-filters [data-sector="ports_logistics"]').click();
    await expect(page.locator('.loja-card')).toHaveCount(7);
    await expect(page.getByRole('heading', { name: /GV Power/ })).toHaveCount(0);
    await page.locator('#sector-filters [data-sector="all"]').click();
    await expect(page.locator('.loja-card')).toHaveCount(40);
    await expect(page.getByRole('heading', { name: /GV Power/ })).toHaveCount(0);
    await expect(page.getByText('Pulverização de Precisão')).toHaveCount(0);

    await page.getByRole('button', { name: 'EN', exact: true }).click();
    await expect(page.getByRole('heading', { name: /GV Track/ })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Essential Aerial Mapping' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Infrastructure Progress Survey' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Infrastructure Monitoring Plan' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Environmental Evidence Survey' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Targeted Drone Verification' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Mining Volumetry Survey' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Mining Repeat Monitoring Plan' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Asset Visual Inspection' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Asset Monitoring Plan' })).toBeVisible();
    await expect(page.locator('.btn-add').first()).toHaveText('Add');
    await expect(page.locator('.deliverables-preview').first())
      .toContainText('Mapped visual evidence');
    await expect(page.locator('#loja-account-recommendation'))
      .toContainText('Recommended solutions for your account');

    await page.getByRole('button', { name: 'ES', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Cartografía Aérea Esencial' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Cartografía 3D de Infraestructura' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Plan de Monitorización Ambiental' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Levantamiento Volumétrico Minero' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Inspección Visual de Activos' })).toBeVisible();
    await expect(page.locator('.btn-add').first()).toHaveText('Añadir');
  });

  test('keeps recommendation and featured badges separate', async ({ page }) => {
    const card = page.locator('.loja-card').filter({
      has: page.getByRole('heading', { name: 'Mapeamento Aéreo Essencial' }),
    });
    const recommendedBadge = card.locator('.recommended-badge');
    const featuredBadge = card.locator('.featured-badge');
    await expect(recommendedBadge).toBeVisible();
    await expect(featuredBadge).toBeVisible();
    const recommended = await recommendedBadge.boundingBox();
    const featured = await featuredBadge.boundingBox();
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
      .toContainText('Agricultura & Pecuária');
    await page.locator('#sector-warning-continue').click();
    await expect(page.locator('#sector-warning-modal')).toBeHidden();
    await expect(page.locator('#cart-count')).toContainText('1 item');
    await expect(page.locator('.loja-cart-item-name'))
      .toHaveText('Kit de Sondas de Solo');
  });

  test('normalizes legacy catalogue links into the six public sector filters', async ({ page }) => {
    await page.goto(`${BASE}/loja.html?sector=agro`);
    await expect(page.locator('#sector-filters [data-sector="agriculture"]')).toHaveClass(/active/);
    await expect.poll(() => page.evaluate(() => localStorage.getItem('gv_catalog_sector')))
      .toBe('environment');

    await page.goto(`${BASE}/loja.html?sector=ports`);
    await expect(page.locator('#sector-filters [data-sector="ports_logistics"]')).toHaveClass(/active/);

    await page.goto(`${BASE}/loja.html?sector=solar`);
    await expect(page.locator('#sector-filters [data-sector="industry_energy_utilities"]')).toHaveClass(/active/);

    const portugueseIndustry = encodeURIComponent('indústria, energia & utilities');
    await page.goto(`${BASE}/loja.html?sector=${portugueseIndustry}`);
    await expect(page.locator('#sector-filters [data-sector="industry_energy_utilities"]')).toHaveClass(/active/);

    expect(await page.evaluate(() => productPublicSectors({ sectors: ['industry'] })))
      .toEqual(['industry_energy_utilities']);
    expect(await page.evaluate(() => productPublicSectors({ sectors: ['ports_industrial'] })))
      .toEqual(['industry_energy_utilities', 'ports_logistics']);
  });
});
