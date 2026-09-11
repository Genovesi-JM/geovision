const { test, expect } = require('@playwright/test');

const BASE = process.env.TEST_BASE_URL || 'http://127.0.0.1:8001';

test.describe('B2C and B2B capability balance', () => {
  test('a visitor can immediately find a purchasable path', async ({ page }) => {
    await page.goto(`${BASE}/index.html`, { waitUntil: 'domcontentloaded' });

    await expect(page.getByRole('heading', {
      name: 'Vea lo que está pasando. Sepa cuándo actuar.',
    })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Explorar dispositivos' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Agricultura y Ganadería' }).first()).toBeVisible();
    await expect(page.getByText('Rebaño · 184', { exact: true })).toBeVisible();
  });

  test('hero illustration gives every sector its own operational picture', async ({ page }) => {
    await page.goto(`${BASE}/index.html`, { waitUntil: 'domcontentloaded' });
    const map = page.locator('#hero-map');

    const sectors = [
      ['Agricultura y Ganadería', 'agriculture', 'Humedad', 'Rebaño · 184'],
      ['Construcción e Infraestructuras', 'construction_infrastructure', 'Progreso', 'Máquina · EX-04'],
      ['Medio ambiente', 'environment', 'Vegetación', 'Río · calidad buena'],
      ['Minería', 'mining', 'Volumen', 'Talud norte · estable'],
      ['Industria, Energía y Servicios Públicos', 'industry_energy_utilities', 'Disponibilidad', 'Subestación · normal'],
      ['Puertos y Logística', 'ports_logistics', 'Ocupación', 'Muelle 3 · ocupado'],
    ];

    for (const [tab, sector, metric, node] of sectors) {
      await page.getByRole('tab', { name: tab, exact: true }).click();
      await expect(map).toHaveAttribute('data-sector', sector);
      await expect(map.getByText(metric, { exact: true })).toBeVisible();
      await expect(map.getByText(node, { exact: true })).toBeVisible();
    }

    await page.getByRole('button', { name: 'EN', exact: true }).click();
    await expect(map.getByText('Occupancy', { exact: true })).toBeVisible();
    await expect(map.getByText('Berth 3 · occupied', { exact: true })).toBeVisible();
  });

  test('the sectors page exposes the six canonical public paths and keeps old anchors compatible', async ({ page }) => {
    await page.goto(`${BASE}/sectors.html`, { waitUntil: 'domcontentloaded' });

    const expected = [
      ['agriculture', 'agricultura-pecuaria', 'Agricultura y Ganadería'],
      ['construction_infrastructure', 'construcao-infraestruturas', 'Construcción e Infraestructuras'],
      ['environment', 'ambiente', 'Medio ambiente'],
      ['mining', 'mineracao', 'Minería'],
      ['industry_energy_utilities', 'industria-energia-utilities', 'Industria, Energía y Servicios Públicos'],
      ['ports_logistics', 'portos-logistica', 'Puertos y Logística'],
    ];
    for (const [sector, slug, label] of expected) {
      const section = page.locator(`#${slug}`);
      await expect(section).toHaveAttribute('data-sector-id', sector);
      await expect(section.getByRole('heading', { name: label, exact: true })).toBeVisible();
      await expect(page.locator(`.sector-jump a[href="#${slug}"]`)).toHaveCount(1);
    }

    const farm = page.locator('#agricultura-pecuaria');
    await expect(farm).toContainText('sensores, tracking, mapas y datos aéreos');
    await expect(farm).toContainText('Animales, GPS y geofences');

    const construction = page.locator('#construcao-infraestruturas');
    await expect(construction).toContainText('sensor en terreno a la visión aérea');
    await expect(construction).toContainText('Tracking y estado de equipos');
    await expect(construction).toContainText('Cronología, mapa, alertas e informes');

    for (const legacyAnchor of ['agropecuaria', 'construcao', 'infraestruturas', 'ambiental', 'industria', 'logistica']) {
      await expect(page.locator(`#${legacyAnchor}`)).toHaveCount(1);
    }
  });

  test('the homepage has one card for each canonical public sector', async ({ page }) => {
    await page.goto(`${BASE}/index.html`, { waitUntil: 'domcontentloaded' });
    const cards = page.locator('.sector-card[data-sector-id]');
    await expect(cards).toHaveCount(6);

    const expected = [
      ['agriculture', 'agricultura-pecuaria'],
      ['construction_infrastructure', 'construcao-infraestruturas'],
      ['environment', 'ambiente'],
      ['mining', 'mineracao'],
      ['industry_energy_utilities', 'industria-energia-utilities'],
      ['ports_logistics', 'portos-logistica'],
    ];
    for (const [sector, slug] of expected) {
      await expect(page.locator(`.sector-card[data-sector-id="${sector}"]`))
        .toHaveAttribute('href', `sectors.html#${slug}`);
    }
  });

  test('legacy browser sector IDs normalize to the canonical six', async ({ page }) => {
    await page.goto(`${BASE}/login.html`, { waitUntil: 'domcontentloaded' });
    const taxonomy = await page.evaluate(() => {
      const sectors = window.GV_SECTOR_TAXONOMY;
      return {
        ids: sectors.ids,
        labels: sectors.ids.map((id) => sectors.labels[id]),
        slugs: sectors.ids.map((id) => sectors.slugs[id]),
        aliasRegistry: sectors.aliases,
        aliases: [
          'agro',
          'infrastructure',
          'ambiental',
          'quarry',
          'industrial',
          'solar',
          'ports',
          'indústria, energia & utilities',
          'industria_energia_utilities',
          'indústria, energia e utilities',
        ].map((value) => sectors.normalizeSector(value)),
        labelAliases: sectors.ids.map((id) => sectors.normalizeSector(sectors.labels[id])),
        listAlias: sectors.normalizeSectors('indústria, energia & utilities'),
      };
    });
    expect(taxonomy.ids).toEqual([
      'agriculture',
      'construction_infrastructure',
      'environment',
      'mining',
      'industry_energy_utilities',
      'ports_logistics',
    ]);
    expect(taxonomy.labels).toEqual([
      'Agricultura & Pecuária',
      'Construção & Infraestruturas',
      'Ambiente',
      'Mineração',
      'Indústria, Energia & Utilities',
      'Portos & Logística',
    ]);
    expect(taxonomy.slugs).toEqual([
      'agricultura-pecuaria',
      'construcao-infraestruturas',
      'ambiente',
      'mineracao',
      'industria-energia-utilities',
      'portos-logistica',
    ]);
    expect(taxonomy.aliases).toEqual([
      'agriculture',
      'construction_infrastructure',
      'environment',
      'mining',
      'industry_energy_utilities',
      'industry_energy_utilities',
      'ports_logistics',
      'industry_energy_utilities',
      'industry_energy_utilities',
      'industry_energy_utilities',
    ]);
    expect(taxonomy.labelAliases).toEqual(taxonomy.ids);
    expect(taxonomy.listAlias).toEqual(['industry_energy_utilities']);
    expect(taxonomy.aliasRegistry).toEqual({
      agro: 'agriculture',
      agropecuaria: 'agriculture',
      agriculture: 'agriculture',
      agricultura: 'agriculture',
      agricultura_e_pecuaria: 'agriculture',
      agricultura_pecuaria: 'agriculture',
      agriculture_livestock: 'agriculture',
      livestock: 'agriculture',
      construction: 'construction_infrastructure',
      construction_and_infrastructure: 'construction_infrastructure',
      construction_infrastructure: 'construction_infrastructure',
      construcao_e_infraestruturas: 'construction_infrastructure',
      construcao_infraestrutura: 'construction_infrastructure',
      construcao_infraestruturas: 'construction_infrastructure',
      infrastructure: 'construction_infrastructure',
      infrastructures: 'construction_infrastructure',
      ambiente: 'environment',
      ambiental: 'environment',
      environment: 'environment',
      environmental: 'environment',
      mine: 'mining',
      mines: 'mining',
      mineracao: 'mining',
      mining: 'mining',
      quarry: 'mining',
      energy: 'industry_energy_utilities',
      energia: 'industry_energy_utilities',
      industrial: 'industry_energy_utilities',
      industria: 'industry_energy_utilities',
      industria_e_energia_utilities: 'industry_energy_utilities',
      industria_energia_e_utilities: 'industry_energy_utilities',
      industria_energia_utilities: 'industry_energy_utilities',
      industry: 'industry_energy_utilities',
      industry_energy: 'industry_energy_utilities',
      industry_energy_utilities: 'industry_energy_utilities',
      solar: 'industry_energy_utilities',
      utilities: 'industry_energy_utilities',
      logistics: 'ports_logistics',
      logistica: 'ports_logistics',
      port: 'ports_logistics',
      portos: 'ports_logistics',
      ports: 'ports_logistics',
      ports_and_logistics: 'ports_logistics',
      ports_industrial: 'ports_logistics',
      ports_logistics: 'ports_logistics',
      portos_e_logistica: 'ports_logistics',
      portos_logistica: 'ports_logistics',
    });
  });

  test('an enterprise buyer sees the five technology pillars and transparent statuses', async ({ page }) => {
    await page.goto(`${BASE}/technology.html`, { waitUntil: 'domcontentloaded' });

    for (const text of [
      '1 · Dispositivos y sensores',
      '2 · GPS y tracking',
      '3 · Inteligencia aérea',
      '4 · Plataforma y mapas',
      '5 · IA y análisis',
    ]) {
      await expect(page.getByText(text, { exact: true }).first()).toBeVisible();
    }
    await expect(page.getByText('GV Track', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('En desarrollo', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('DJI Matrice series', { exact: true }).first()).toBeVisible();
    for (const alt of ['DJI Mavic 3 Multispectral', 'DJI Matrice 350 RTK', 'DJI Agras T40']) {
      await expect(page.getByRole('img', { name: alt, exact: true })).toBeVisible();
    }
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
