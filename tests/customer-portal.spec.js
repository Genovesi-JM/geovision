const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const BASE = process.env.TEST_BASE_URL || 'http://127.0.0.1:8001';
const API_ORIGIN = 'http://127.0.0.1:8010';

const CAPABILITIES = [
  'overview', 'assets', 'actions', 'monitoring', 'services', 'map',
  'analytics', 'reports', 'catalog', 'orders', 'billing', 'team',
  'integrations', 'settings',
];

const NAVIGATION = [
  ['overview', [['overview', 'Overview']]],
  ['operations', [['assets', 'Assets'], ['actions', 'Actions'], ['monitoring', 'Monitoring'], ['services', 'Services']]],
  ['intelligence', [['map', 'Map'], ['analytics', 'Analytics'], ['reports', 'Reports']]],
  ['commercial', [['catalog', 'Products & Services'], ['orders', 'Orders'], ['billing', 'Billing']]],
  ['management', [['team', 'Team'], ['integrations', 'Integrations'], ['settings', 'Settings']]],
].map(([key, items]) => ({
  key,
  label: key[0].toUpperCase() + key.slice(1),
  items: items.map(([itemKey, label]) => ({
    key: itemKey,
    label,
    capability: itemKey,
    route: itemKey === 'catalog' ? '/loja.html' : `/dashboard.html?view=${itemKey}`,
  })),
}));

const DESTINATIONS = {
  WORKSPACE: ['overview', '/dashboard.html?view=overview&workspace_id={workspace_id}'],
  ASSET: ['assets', '/dashboard.html?view=asset&target_id={target_id}'],
  ACTION: ['actions', '/dashboard.html?view=action&target_id={target_id}'],
  SERVICE: ['services', '/dashboard.html?view=service&target_id={target_id}'],
  SERVICE_RESULT: ['services', '/dashboard.html?view=service-result&target_id={target_id}'],
  ORDER: ['orders', '/dashboard.html?view=order&target_id={target_id}'],
  REPORT: ['reports', '/dashboard.html?view=report&target_id={target_id}'],
};

const workspaces = [
  {
    id: 'workspace-a', organization_id: 'organization-a', name: 'River Operations',
    organization_name: 'Acme Environment', role: 'owner', sector: 'environment',
    sectors: ['environment', 'mining'],
    modules_enabled: ['assets', 'actions', 'iot', 'services', 'maps', 'analytics', 'reports', 'store', 'orders', 'integrations'],
  },
  {
    id: 'workspace-b', organization_id: 'organization-b', name: 'Solar Portfolio',
    organization_name: 'Acme Energy', role: 'manager', sector: 'infrastructure',
    modules_enabled: ['assets', 'actions', 'iot', 'services', 'maps', 'analytics', 'reports', 'store', 'orders'],
  },
];

function experience(workspaceId = 'workspace-a', overrides = {}) {
  const workspace = workspaces.find((item) => item.id === workspaceId) || workspaces[0];
  const capabilities = overrides.capabilities || CAPABILITIES;
  const featureFlags = Object.fromEntries(CAPABILITIES.map((key) => [key, capabilities.includes(key)]));
  const navigation = (overrides.navigation || NAVIGATION)
    .map((group) => ({ ...group, items: group.items.filter((item) => capabilities.includes(item.key)) }))
    .filter((group) => group.items.length);
  const assetPrefix = workspaceId === 'workspace-a' ? 'river' : 'solar';
  return {
    active_workspace_id: workspace.id,
    active_organization_id: workspace.organization_id,
    organization_name: workspace.organization_name,
    active_workspace: workspace,
    permissions: overrides.permissions || [
      'organization:read', 'organization:manage', 'organization:manage_members',
      'workspace:read', 'workspace:manage', 'workspace:operate', 'asset:read',
      'report:read', 'billing:read',
    ],
    capabilities,
    feature_flags: { ...featureFlags, ...(overrides.feature_flags || {}) },
    subscription: overrides.subscription || {
      plan: 'Enterprise', status: 'active', tier: 'enterprise',
      valid_until: '2027-01-01T00:00:00Z', source: 'entitlement',
    },
    workspaces,
    navigation,
    asset_tree: [{
      id: `${assetPrefix}-root`, parent_asset_id: null,
      name: workspaceId === 'workspace-a' ? 'River Basin' : 'Solar Estate',
      sector: workspace.sector, asset_type: 'portfolio', status: 'active',
      children: [{
        id: `${assetPrefix}-child`, parent_asset_id: `${assetPrefix}-root`,
        name: workspaceId === 'workspace-a' ? 'North Sensor Zone' : 'Array A',
        sector: workspace.sector, asset_type: 'site', status: 'active', children: [],
      }],
    }],
    deep_link_contract: {
      version: 'geovision.portal-destination.v1',
      destinations: Object.entries(DESTINATIONS).map(([target_type, [capability, route_template]]) => ({
        target_type, capability, route_template,
      })).filter((rule) => capabilities.includes(rule.capability)),
    },
    ...overrides.extra,
  };
}

function summary(workspaceId = 'workspace-a', assetId = null) {
  const prefix = workspaceId === 'workspace-a' ? 'river' : 'solar';
  const candidates = [
    {
      id: `${prefix}-root`, parent_asset_id: null,
      name: workspaceId === 'workspace-a' ? 'River Basin' : 'Solar Estate',
      sector: workspaceId === 'workspace-a' ? 'environment' : 'infrastructure',
      asset_type: 'portfolio', status: 'active', location_label: 'Luanda',
      center: { lat: -8.84, lng: 13.23 }, children_count: 1,
      decision_status: 'WARNING', confidence: 0.94,
      measured_at: '2026-09-10T08:00:00Z',
      primary_kpis: [{
        key: 'operational_risk', name: 'Operational risk', value: 2,
        display_value: '2 warnings', unit: null, status: 'WARNING',
        confidence: 0.94, measured_at: '2026-09-10T08:00:00Z', change_percent: -12.5,
      }],
      secondary_kpis: [{
        key: 'coverage', name: 'Data coverage', value: 88,
        display_value: '88%', unit: '%', status: 'OK', confidence: 0.98,
      }],
      technical_metric_count: 12,
      technical_metrics_path: `/assets/${prefix}-root/kpis?importance=TECHNICAL`,
      open_action_count: 2, critical_observation_count: 0,
      warning_observation_count: 2, unvalidated_observation_count: 0,
      latest_observation_at: '2026-09-10T08:00:00Z',
      destination: { target_type: 'ASSET', target_id: `${prefix}-root` },
    },
    {
      id: `${prefix}-child`, parent_asset_id: `${prefix}-root`,
      name: workspaceId === 'workspace-a' ? 'North Sensor Zone' : 'Array A',
      sector: workspaceId === 'workspace-a' ? 'environment' : 'infrastructure',
      asset_type: 'site', status: 'active', location_label: 'North',
      center: { lat: -8.8, lng: 13.3 }, children_count: 0,
      decision_status: 'OK', confidence: 0.9,
      primary_kpis: [{ key: 'health', name: 'Asset health', value: 96, display_value: '96%', status: 'OK', confidence: 0.9 }],
      secondary_kpis: [], technical_metric_count: 4,
      technical_metrics_path: `/assets/${prefix}-child/kpis?importance=TECHNICAL`,
      open_action_count: 0, critical_observation_count: 0,
      warning_observation_count: 0, unvalidated_observation_count: 0,
      destination: { target_type: 'ASSET', target_id: `${prefix}-child` },
    },
  ];
  const items = assetId ? candidates.filter((item) => item.id === assetId) : candidates;
  return {
    workspace_id: workspaceId,
    generated_at: '2026-09-10T09:00:00Z',
    totals: { assets: items.length, active: items.length, attention: 1, open_actions: 2, published_reports: 1, offline_devices: 0 },
    items,
  };
}

function mapLayers(workspaceId = 'workspace-a') {
  const prefix = workspaceId === 'workspace-a' ? 'river' : 'solar';
  return {
    workspace_id: workspaceId,
    generated_at: '2026-09-10T09:00:00Z',
    bounds: [13.2, -8.9, 13.4, -8.7],
    layers: [{
      id: 'assets', label: 'Assets', kind: 'ASSET', default_visible: true,
      geometry_types: ['Point'],
      feature_collection: {
        type: 'FeatureCollection',
        features: [{
          type: 'Feature', id: `${prefix}-root`,
          geometry: { type: 'Point', coordinates: [13.23, -8.84] },
          properties: { target_type: 'ASSET', target_id: `${prefix}-root`, name: `${prefix} asset`, status: 'active' },
        }],
      },
    }],
  };
}

async function installApi(page, options = {}) {
  const requests = [];
  await page.addInitScript((workspaceId) => {
    localStorage.setItem('gv_token', 'portal-access-token');
    localStorage.setItem('gv_workspace_id', workspaceId);
    localStorage.setItem('gv_account_id', workspaceId);
    localStorage.setItem('gv_role', 'admin');
    localStorage.setItem('gv_user', JSON.stringify({ email: 'customer@example.test', role: 'admin', name: 'Customer User' }));
  }, options.workspaceId || 'workspace-a');

  await page.route(`${API_ORIGIN}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const workspaceId = request.headers()['x-workspace-id'] || 'workspace-a';
    requests.push({ path: url.pathname, workspaceId, method: request.method() });
    if (options.delayExperience && url.pathname === '/portal/experience') {
      await new Promise((resolve) => setTimeout(resolve, options.delayExperience));
    }
    if (url.pathname === '/portal/experience') {
      if (options.experienceStatus) {
        return route.fulfill({ status: options.experienceStatus, body: '{}' });
      }
      const custom = options.experienceOverrides?.[workspaceId] || options.experienceOverrides?.default || {};
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(experience(workspaceId, custom)) });
    }
    if (url.pathname === '/portal/assets/summary') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(summary(workspaceId, url.searchParams.get('asset_id'))) });
    }
    if (url.pathname === '/portal/map-layers') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mapLayers(workspaceId)) });
    }
    if (url.pathname === '/actions') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        total: 1,
        items: [{
          id: 'action-a', workspace_id: workspaceId, asset_id: workspaceId === 'workspace-a' ? 'river-root' : 'solar-root',
          title: 'Inspect warning', description: 'Validate the latest observation',
          status: 'OPEN', priority: 'CRITICAL', due_date: null,
        }],
      }) });
    }
    if (url.pathname === '/mobile/devices') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        items: [{ id: 'device-a', name: `${workspaceId} sensor`, status: 'online', last_seen_at: '2026-09-10T09:00:00Z' }],
      }) });
    }
    if (url.pathname === '/mobile/service-requests' || url.pathname.startsWith('/mobile/service-requests/')) {
      const item = {
        id: 'service-a', site_id: 'site-a', site_name: 'North Zone', type: 'Aerial survey',
        urgency: 'normal', description: 'Quarterly survey', status: 'COMPLETED',
        progress_percent: 100, result: { title: 'Survey result', summary: 'Ready for review' },
      };
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(url.pathname.endsWith('/service-a') ? item : [item]) });
    }
    if (url.pathname === '/reports') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        total: 1,
        items: [{ id: 'report-a', workspace_id: workspaceId, title: 'Water quality', report_type: 'environment', status: 'PUBLISHED', published_at: '2026-09-10T08:00:00Z' }],
      }) });
    }
    if (url.pathname === '/orders') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([{
        id: 'order-a', order_number: 'GV-100', fulfilment_status: 'IN_PROGRESS', payment_status: 'PAID',
        currency: 'AOA', total: 125000, item_count: 1, created_at: '2026-09-10T08:00:00Z',
      }]) });
    }
    if (url.pathname === '/orders/order-a') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        id: 'order-a', workspace_id: workspaceId, order_number: 'GV-100', fulfilment_status: 'IN_PROGRESS',
        payment_status: 'PAID', currency: 'AOA', total: 125000,
        items: [{ quantity: 1, name: 'Survey', line_total: 125000, currency: 'AOA' }],
      }) });
    }
    if (url.pathname === '/notifications/unread-count') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ unread: 1 }) });
    }
    if (url.pathname === '/notifications') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ total: 0, unread: 0, items: [] }) });
    }
    if (url.pathname === '/notifications/notification-a/target') {
      const target = options.notificationTarget || {
        notification_id: 'notification-a', target_type: 'ASSET', target_id: 'river-child',
        workspace_id: 'workspace-a', app_path: '/assets/river-child', portal_path: '/assets/river-child',
      };
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(target) });
    }
    if (url.pathname === '/notifications/notification-a/read') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    }
    if (url.pathname === '/auth/me') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        email: 'customer@example.test', name: 'Customer User', role: 'admin', account_id: workspaceId,
      }) });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
  return requests;
}

async function openPortal(page, path = '/dashboard.html') {
  await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('body')).toHaveAttribute('data-portal-state', 'ready');
}

test.describe('contextual customer portal', () => {
  test('renders the five backend-authorized groups and never exposes internal operations', async ({ page }) => {
    const requests = await installApi(page);
    await openPortal(page);

    const groupLabels = await page.locator('.portal-nav-group:not([hidden]) .sidebar-section-title').allTextContents();
    expect(groupLabels).toEqual(['Overview', 'Operations', 'Intelligence', 'Commercial', 'Management']);
    await expect(page.getByRole('link', { name: 'Assets', exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Products & Services', exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: /Painel Admin|Internal Operations/i })).toHaveCount(0);

    await page.getByRole('link', { name: 'Monitoring', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Monitoring', exact: true })).toBeVisible();
    await expect(page.getByText('workspace-a sensor')).toBeVisible();
    expect(requests.some((request) => request.path === '/mobile/devices' && request.workspaceId === 'workspace-a')).toBeTruthy();
    expect(requests.some((request) => request.path === '/iot/devices')).toBeFalsy();
    expect(requests.some((request) => request.path.startsWith('/shop/'))).toBeFalsy();
    expect(requests.some((request) => request.path.startsWith('/me/documents'))).toBeFalsy();

    await page.getByRole('link', { name: 'Orders', exact: true }).click();
    await expect(page.getByText('GV-100')).toBeVisible();
    expect(requests.some((request) => request.path === '/orders' && request.workspaceId === 'workspace-a')).toBeTruthy();
  });

  test('hides navigation before authorization and fails closed on inconsistent permissions and flags', async ({ page }) => {
    await installApi(page, {
      delayExperience: 350,
      experienceOverrides: {
        default: {
          permissions: ['organization:read', 'workspace:read', 'asset:read', 'report:read'],
          feature_flags: { map: false },
        },
      },
    });
    await page.goto(`${BASE}/dashboard.html`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('[data-portal-group="operations"]')).toBeHidden();
    await expect(page.locator('body')).toHaveAttribute('data-portal-state', 'ready');
    await expect(page.getByRole('link', { name: 'Team', exact: true })).toBeHidden();
    await expect(page.getByRole('link', { name: 'Map', exact: true })).toBeHidden();
    await expect(page.getByRole('link', { name: 'Settings', exact: true })).toBeHidden();
    await expect(page.getByRole('link', { name: 'Assets', exact: true })).toBeVisible();
  });

  test('shows no contextual modules when the experience contract cannot be validated', async ({ page }) => {
    await installApi(page, { experienceStatus: 403 });
    await page.goto(`${BASE}/dashboard.html`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('body')).toHaveAttribute('data-portal-state', 'error');
    await expect(page.getByRole('heading', { name: 'Customer portal unavailable' })).toBeVisible();
    await expect(page.locator('.portal-nav-group:not([hidden])')).toHaveCount(0);
  });

  test('switches workspace once and replaces all hierarchy and summary state', async ({ page }) => {
    const requests = await installApi(page);
    await openPortal(page, '/dashboard.html?view=assets');
    await expect(page.getByText('River Basin').first()).toBeVisible();

    await page.locator('#account-switcher').selectOption('workspace-b');
    await expect(page.locator('#portal-workspace-meta')).toContainText('Acme Energy');
    await expect(page.getByText('Solar Estate').first()).toBeVisible();
    await expect(page.getByText('River Basin')).toHaveCount(0);
    expect(requests.filter((request) => request.path === '/portal/experience' && request.workspaceId === 'workspace-b')).toHaveLength(1);
    expect(requests.some((request) => request.path === '/portal/assets/summary' && request.workspaceId === 'workspace-b')).toBeTruthy();
    expect(await page.evaluate(() => localStorage.getItem('gv_workspace_id'))).toBe('workspace-b');
  });

  test('renders a multi-sector workspace as canonical labels without a CSV pseudo-sector', async ({ page }) => {
    await installApi(page);
    await openPortal(page);
    await expect(page.locator('#portal-workspace-meta')).toContainText(
      'Ambiente · Mineração',
    );
    await expect(page.locator('.page-subtitle').first()).toContainText(
      'Ambiente · Mineração',
    );
  });

  test('opens a legacy invitation asset target, canonicalizes it, and preserves back navigation', async ({ page }) => {
    await installApi(page);
    await openPortal(page, '/dashboard.html?asset=river-child');
    await expect(page.getByRole('heading', { name: 'Assets', exact: true })).toBeVisible();
    await expect(page.locator('#asset-summary')).toContainText('North Sensor Zone');
    await expect(page).toHaveURL(/view=assets&asset=river-child/);

    await page.getByRole('link', { name: 'Overview', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'River Operations' })).toBeVisible();
    await page.goBack();
    await expect(page.locator('#asset-summary')).toContainText('North Sensor Zone');
  });

  test('resolves only an opaque notification id and rejects a mismatched portal path', async ({ page }) => {
    await installApi(page);
    await openPortal(page, '/dashboard.html?notification=notification-a');
    await expect(page.getByRole('heading', { name: 'Assets', exact: true })).toBeVisible();
    await expect(page.locator('#asset-summary')).toContainText('North Sensor Zone');
    await expect(page).toHaveURL(/view=assets&asset=river-child/);

    const unsafe = await page.context().newPage();
    await installApi(unsafe, {
      notificationTarget: {
        notification_id: 'notification-a', target_type: 'ASSET', target_id: 'river-child',
        workspace_id: 'workspace-a', app_path: '/assets/river-child', portal_path: '/admin',
      },
    });
    await openPortal(unsafe, '/dashboard.html?notification=notification-a');
    await expect(unsafe.getByRole('heading', { name: 'Destination unavailable' })).toBeVisible();
    await expect(unsafe).toHaveURL(/dashboard\.html$/);
  });

  test('preserves a validated service-result destination through authentication', async ({ page }) => {
    await page.goto(`${BASE}/dashboard.html?request=service-a`, { waitUntil: 'domcontentloaded' });
    await page.waitForURL(/login\.html\?return=/);
    const destination = new URL(page.url()).searchParams.get('return');
    expect(destination).toBe('/dashboard.html?view=services&service_result=service-a');
    expect(await page.evaluate(() => sessionStorage.getItem('gv_portal_return'))).toBe(destination);
  });

  test('puts decision KPIs before technical drilldown and renders standardized map layers', async ({ page }) => {
    const requests = await installApi(page);
    await openPortal(page, '/dashboard.html?view=analytics');
    await expect(page.getByRole('heading', { name: 'Decision KPIs' })).toBeVisible();
    await expect(page.getByText('Operational risk')).toBeVisible();
    const order = await page.evaluate(() => {
      const primary = document.querySelector('#analytics-content .portal-decision-grid');
      const technical = document.querySelector('#analytics-content details');
      return primary.compareDocumentPosition(technical) & Node.DOCUMENT_POSITION_FOLLOWING;
    });
    expect(order).toBeTruthy();

    await page.getByRole('link', { name: 'Map', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Assets (1)' })).toBeVisible();
    expect(requests.some((request) => request.path === '/portal/map-layers' && request.workspaceId === 'workspace-a')).toBeTruthy();
  });

  test('is keyboard/mobile navigable with no serious accessibility violations', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await installApi(page);
    await openPortal(page);
    const layout = await page.evaluate(() => ({
      innerWidth: window.innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }));
    expect(layout.scrollWidth).toBeLessThanOrEqual(layout.innerWidth);
    const menu = page.locator('#btn-menu-toggle');
    await expect(menu).toHaveAttribute('aria-expanded', 'false');
    await menu.click();
    await expect(menu).toHaveAttribute('aria-expanded', 'true');
    await expect(page.locator('#sidebar')).toHaveClass(/open/);
    await page.locator('#sidebar-close').click();
    await expect(menu).toHaveAttribute('aria-expanded', 'false');

    const accessibility = await new AxeBuilder({ page }).analyze();
    expect(accessibility.violations.filter((item) => ['critical', 'serious'].includes(item.impact))).toEqual([]);
  });
});
