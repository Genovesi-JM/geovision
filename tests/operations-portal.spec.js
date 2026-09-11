const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const BASE = process.env.TEST_BASE_URL || 'http://127.0.0.1:8001';
const API = 'http://127.0.0.1:8010';
const NAV = {
  dashboard: ['Dashboard', 'dashboard'], organizations: ['Customers / Organizations', 'organizations'],
  assets: ['Assets', 'assets'], orders: ['Orders', 'orders'], jobs: ['Jobs', 'jobs'],
  missions: ['Missions', 'missions'], processing: ['Processing', 'processing'],
  reports_qa: ['Reports QA', 'reports-qa'], contractors: ['Contractors', 'contractors'],
  inventory: ['Suppliers / Inventory', 'inventory'], finance_sync: ['Finance sync', 'finance-sync'],
  integrations: ['Integrations', 'integrations'], system_health: ['System health', 'system-health'],
};

const now = '2026-09-10T10:00:00Z';
const emptyDashboard = () => ({
  generated_at: now,
  totals: { organizations: 0, assets: 0, orders: 0, jobs: 0, missions: 0, processing_jobs: 0, reports_review: 0, contractors: 0 },
  attention: { failed_jobs: 0, blocked_jobs: 0, failed_processing: 0, retry_wait_processing: 0, needs_review_processing: 0, reports_awaiting_review: 0, dead_letter_integrations: 0 },
  health: { status: 'HEALTHY', event_dead_letters: 0, notification_dead_letters: 0, integration_dead_letters: 0, processing_failures: 0 },
  recent: [],
});
const emptyQueues = () => ({ generated_at: now, jobs: [], processing: [], reports_qa: [], integrations: [] });

function internalExperience(keys, permissions = ['operations:access'], roles = ['GV_OPERATIONS_MANAGER']) {
  return {
    surface: 'INTERNAL_OPERATIONS', actor: { user_id: 'staff-user', roles, permissions }, capabilities: keys,
    navigation: keys.map((key) => ({ key, label: NAV[key][0], path: `/admin.html?view=${NAV[key][1]}`, capability: key })),
    generated_at: now,
  };
}

function contractorExperience(overrides = {}) {
  const keys = overrides.keys || ['my_jobs', 'job_status', 'uploads', 'profile', 'documents'];
  const paths = { my_jobs: ['My Jobs', 'jobs'], profile: ['Profile', 'profile'], documents: ['Documents', 'documents'] };
  const navigation = ['my_jobs', 'profile', 'documents'].filter((key) => keys.includes(key)).map((key) => ({ key, label: paths[key][0], path: `/contractor.html?view=${paths[key][1]}`, capability: key }));
  return {
    surface: 'CONTRACTOR', contractor: { id: 'contractor-1', display_name: 'Field Partner', resource_type: 'DRONE_OPERATOR', status: 'ACTIVE', availability: 'AVAILABLE' },
    capabilities: keys, navigation,
    job_counts: overrides.counts || { offered: 0, scheduled: 0, active: 0, review: 0, completed: 0 }, generated_at: now,
  };
}

async function mockApi(page, responder, storedRole = 'cliente') {
  await page.addInitScript(({ role }) => {
    localStorage.setItem('gv_token', 'phase24-access-token');
    localStorage.setItem('gv_role', role);
  }, { role: storedRole });
  await page.route(`${API}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const result = await responder({ route, request, path: url.pathname, search: url.search, method: request.method() });
    if (result === 'handled') return;
    if (!result) {
      await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'Unexpected test request' }) });
      return;
    }
    const status = result.status || 200;
    if (result.raw !== undefined) await route.fulfill({ status, body: result.raw, headers: result.headers || {} });
    else await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(result.body ?? result) });
  });
}

function job(overrides = {}) {
  return {
    id: 'job-1', job_number: 'GVJ-2026-001', title: 'Thermal inspection', job_type: 'DRONE_CAPTURE', priority: 'HIGH', state: 'READY',
    scheduled_start: '2026-09-12T08:00:00Z', scheduled_end: '2026-09-12T10:00:00Z', actual_start: null, completed_at: null,
    requirements: { equipment: ['Thermal camera'], capabilities: ['Certified pilot'] }, lifecycle_version: 3,
    created_at: now, updated_at: now, order_id: 'order-internal-1', order_item_id: null, asset_id: 'asset-internal-1',
    assigned_contractor_id: null, assigned_user_id: null, direct_cost_amount: null, cost_currency: null, cost_reference: null,
    plan_key: null, resume_state: null, dependencies: [], ...overrides,
  };
}

test.describe('Phase 24 Operations authorization', () => {
  test('fails closed for a local admin role when server access is denied', async ({ page }) => {
    const requests = [];
    await mockApi(page, ({ path }) => {
      requests.push(path);
      if (path === '/operations/experience') return { status: 403, body: { detail: { code: 'internal_access_denied', message: 'Internal role required' } } };
      return null;
    }, 'admin');
    await page.goto(`${BASE}/admin.html`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#operations-denied')).toBeVisible();
    await expect(page.locator('#operations-app')).toBeHidden();
    expect(requests).toEqual(['/operations/experience']);
  });

  test('renders only the intersection of server capabilities and server navigation', async ({ page }) => {
    await mockApi(page, ({ path }) => {
      if (path === '/operations/experience') return { body: internalExperience(['dashboard', 'jobs', 'processing']) };
      if (path === '/operations/dashboard') return { body: emptyDashboard() };
      if (path === '/operations/queues') return { body: emptyQueues() };
      return null;
    }, 'admin');
    await page.goto(`${BASE}/admin.html`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#operations-app')).toBeVisible();
    await expect(page.locator('#operations-navigation .nav-link')).toHaveCount(3);
    await expect(page.locator('#operations-navigation')).toContainText('Dashboard');
    await expect(page.locator('#operations-navigation')).toContainText('Jobs');
    await expect(page.locator('#operations-navigation')).not.toContainText('Finance sync');
    await expect(page.locator('[data-compatibility="platform-admin"]')).toHaveCount(0);
  });

  test('direct legacy navigation requires the new server platform-admin permission', async ({ page }) => {
    const requests = [];
    await mockApi(page, ({ path }) => {
      requests.push(path);
      if (path === '/operations/experience') return { body: internalExperience(['dashboard'], ['operations:access']) };
      return null;
    }, 'admin');
    await page.goto(`${BASE}/admin-legacy.html`, { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: 'Platform administration access required' })).toBeVisible();
    await expect(page.locator('.admin-sidebar')).toHaveCount(0);
    expect(requests).toEqual(['/operations/experience']);
  });

  test('fails closed for contractor navigation when the server has no contractor profile', async ({ page }) => {
    const requests = [];
    await mockApi(page, ({ path }) => {
      requests.push(path);
      if (path === '/operations/contractor/me/experience') return { status: 403, body: { detail: { code: 'contractor_access_denied', message: 'No active contractor profile' } } };
      return null;
    }, 'contractor');
    await page.goto(`${BASE}/contractor.html`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#contractor-denied')).toBeVisible();
    await expect(page.locator('#contractor-app')).toBeHidden();
    expect(requests).toEqual(['/operations/contractor/me/experience']);
  });
});

test.describe('Phase 24 internal workflows', () => {
  test('shows finance-only aggregate location usage without request details', async ({ page }) => {
    await mockApi(page, ({ path }) => {
      if (path === '/operations/experience') return { body: internalExperience(['finance_sync'], ['billing:internal'], ['GV_FINANCE']) };
      if (path === '/operations/queues') return { body: emptyQueues() };
      if (path === '/internal/economics/location-usage/summary') return { body: {
        items: [{ provider: 'google_maps', service: 'routes_compute', call_count: 7, quantity: '7', currency: null, total_cost: '0' }],
        total_calls: 7, generated_at: now,
      } };
      return null;
    });
    await page.goto(`${BASE}/admin.html?view=finance-sync`, { waitUntil: 'domcontentloaded' });
    await expect(page.getByText('Location API calls')).toBeVisible();
    await expect(page.getByText('7', { exact: true }).first()).toBeVisible();
    const usageTable = page.getByLabel('Location provider usage over the last 30 days');
    await expect(usageTable).toContainText('Google maps');
    await expect(usageTable).toContainText('Not priced');
    await expect(page.locator('#operations-view')).not.toContainText('query');
    await expect(page.locator('#operations-view')).not.toContainText('coordinates');
  });

  test('shows safe processing failure details and retries a retryable job', async ({ page }) => {
    let retried = false;
    let retryBody = null;
    await mockApi(page, ({ path, method, request }) => {
      if (path === '/operations/experience') return { body: internalExperience(['processing']) };
      if (path === '/operations/queues') return { body: { ...emptyQueues(), processing: retried ? [] : [{ id: 'process-1', status: 'FAILED', stage: 'ORTHOMOSAIC', retry_count: 1, max_retries: 3, retries_remaining: 2, next_poll_at: now, error_code: 'provider_timeout', error_message: 'Provider timed out; credentials redacted', updated_at: now }] } };
      if (path === '/processing/jobs/process-1/retry' && method === 'POST') { retryBody = request.postDataJSON(); retried = true; return { body: { id: 'process-1', status: 'RETRY_WAIT' } }; }
      return null;
    });
    await page.goto(`${BASE}/admin.html?view=processing`, { waitUntil: 'domcontentloaded' });
    await expect(page.getByText('Provider timed out; credentials redacted')).toBeVisible();
    await page.getByRole('button', { name: 'Retry' }).click();
    await expect(page.getByText('No processing work')).toBeVisible();
    expect(retryBody).toEqual({});
  });

  test('offers a contractor assignment without directly assigning or scheduling the job', async ({ page }) => {
    const seen = [];
    let offeredBody = null;
    await mockApi(page, ({ path, method, request }) => {
      seen.push(`${method} ${path}`);
      if (path === '/operations/experience') return { body: internalExperience(['jobs', 'contractors']) };
      if (path === '/operations/jobs') return { body: [job()] };
      if (path === '/operations/contractors') return { body: [{ id: 'contractor-1', display_name: 'Field Partner', resource_type: 'DRONE_OPERATOR', status: 'ACTIVE', availability: 'AVAILABLE', region: 'Luanda', capabilities: [{ code: 'THERMAL' }] }] };
      if (path === '/operations/assignments' && method === 'POST') { offeredBody = request.postDataJSON(); return { status: 201, body: { id: 'offer-1', status: 'OFFERED' } }; }
      return null;
    });
    await page.goto(`${BASE}/admin.html?view=jobs`, { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: 'Manage' }).click();
    await page.locator('#workflow-contractor').selectOption('contractor-1');
    await page.locator('#workflow-location').fill('North gate, Bay 2');
    await page.locator('#workflow-reason').fill('Capability match confirmed');
    await page.getByRole('button', { name: 'Save changes' }).click();
    await expect.poll(() => offeredBody).not.toBeNull();
    expect(offeredBody).toMatchObject({ contractor_id: 'contractor-1', order_id: 'order-internal-1', fulfilment_job_id: 'job-1', title: 'Thermal inspection', location: { label: 'North gate, Bay 2' }, requirements: { equipment: ['Thermal camera'], capabilities: ['Certified pilot'] }, internal_notes: 'Capability match confirmed' });
    expect(seen.some((value) => value.includes('/operations/jobs/job-1/assignment'))).toBe(false);
    expect(seen.some((value) => value.includes('/operations/jobs/job-1/schedule'))).toBe(false);
  });

  test('advances mission state with its lifecycle version and reason', async ({ page }) => {
    let payload = null;
    let transitioned = false;
    const mission = { id: 'mission-1', acquisition_number: 'GVM-001', title: 'Grid survey', acquisition_type: 'DRONE', state: 'PLANNED', scheduled_start: now, lifecycle_version: 4, updated_at: now };
    await mockApi(page, ({ path, method, request }) => {
      if (path === '/operations/experience') return { body: internalExperience(['missions']) };
      if (path === '/missions/internal' && method === 'GET') return { body: [transitioned ? { ...mission, state: 'IN_PROGRESS', lifecycle_version: 5 } : mission] };
      if (path === '/missions/internal/mission-1/state' && method === 'PATCH') { payload = request.postDataJSON(); transitioned = true; return { body: { ...mission, state: 'IN_PROGRESS', lifecycle_version: 5 } }; }
      return null;
    });
    await page.goto(`${BASE}/admin.html?view=missions`, { waitUntil: 'domcontentloaded' });
    await page.getByLabel('New state for GVM-001').selectOption('IN_PROGRESS');
    await page.getByLabel('Reason for changing GVM-001').fill('Crew checked in');
    await page.getByRole('button', { name: 'Apply' }).click();
    await expect.poll(() => payload).not.toBeNull();
    expect(payload).toEqual({ state: 'IN_PROGRESS', reason: 'Crew checked in', expected_version: 4 });
  });

  test('gates report approve and publish actions by server permissions', async ({ page }) => {
    let reportStatus = 'REVIEW_REQUIRED';
    const actions = [];
    await mockApi(page, ({ path, method, request }) => {
      if (path === '/operations/experience') return { body: internalExperience(['reports_qa'], ['report:review', 'report:publish']) };
      if (path === '/operations/queues') return { body: { ...emptyQueues(), reports_qa: [{ id: 'report-1', title: 'Thermal findings', status: reportStatus, qa_level: 'SPECIALIST', revision: 2, lifecycle_version: reportStatus === 'REVIEW_REQUIRED' ? 5 : 6, asset_id: 'asset-internal', updated_at: now }] } };
      if (path === '/reports/report-1/approve' && method === 'POST') { actions.push({ action: 'approve', body: request.postDataJSON() }); reportStatus = 'APPROVED'; return { body: { id: 'report-1', status: reportStatus } }; }
      if (path === '/reports/report-1/publish' && method === 'POST') { actions.push({ action: 'publish', body: request.postDataJSON() }); reportStatus = 'PUBLISHED'; return { body: { id: 'report-1', status: reportStatus } }; }
      return null;
    });
    await page.goto(`${BASE}/admin.html?view=reports-qa`, { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: 'Approve' }).click();
    await expect(page.getByRole('button', { name: 'Publish' })).toBeVisible();
    await page.getByRole('button', { name: 'Publish' }).click();
    expect(actions).toEqual([
      { action: 'approve', body: { expected_lifecycle_version: 5, note: null } },
      { action: 'publish', body: { expected_lifecycle_version: 6, note: null } },
    ]);
  });

  test('does not render report lifecycle actions without server permissions', async ({ page }) => {
    await mockApi(page, ({ path }) => {
      if (path === '/operations/experience') return { body: internalExperience(['reports_qa'], ['analytics:read']) };
      if (path === '/operations/queues') return { body: { ...emptyQueues(), reports_qa: [{ id: 'report-1', title: 'Restricted review', status: 'REVIEW_REQUIRED', qa_level: 'SPECIALIST', revision: 1, lifecycle_version: 2, asset_id: 'asset-1', updated_at: now }] } };
      return null;
    });
    await page.goto(`${BASE}/admin.html?view=reports-qa`, { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('button', { name: 'Approve' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Publish' })).toHaveCount(0);
  });
});

test.describe('Phase 24 restricted contractor workspace', () => {
  test('shows a fresh offer before job assignment and acceptance makes the job visible', async ({ page }) => {
    let accepted = false;
    let decisionBody = null;
    const offer = { id: 'offer-1', assignment_number: 'GVA-2026-001', title: 'Thermal inspection offer', status: 'OFFERED', location: { label: 'North gate', customer_id: 'must-not-render' }, window_start: '2026-09-12T08:00:00Z', window_end: '2026-09-12T10:00:00Z', requirements: { equipment: ['Thermal camera'] }, upload_area: {}, required_documents: [{ name: 'Pilot licence' }], document_profile: [], lifecycle_version: 2, created_at: now, updated_at: now };
    await mockApi(page, ({ path, method, request }) => {
      if (path === '/operations/contractor/me/experience') return { body: contractorExperience({ counts: { offered: accepted ? 0 : 1, scheduled: 0, active: accepted ? 1 : 0, review: 0, completed: 0 } }) };
      if (path === '/operations/contractor/me/assignments' && method === 'GET') return { body: accepted ? [] : [offer] };
      if (path === '/operations/contractor/me/assignments/offer-1/decision' && method === 'POST') { decisionBody = request.postDataJSON(); accepted = true; return { body: { ...offer, status: 'ACCEPTED', lifecycle_version: 3 } }; }
      if (path === '/operations/contractor/me/jobs' && method === 'GET') return { body: accepted ? [job({ order_id: undefined, asset_id: undefined, assigned_contractor_id: undefined, scheduled_start: null, scheduled_end: null, state: 'ASSIGNED' })] : [] };
      if (path === '/operations/contractor/me/jobs/job-1' && method === 'GET') return { body: { ...job({ order_id: 'secret-order', asset_id: 'secret-asset', state: 'ASSIGNED', scheduled_start: null, scheduled_end: null }), customer_id: 'secret-customer', organization_id: 'secret-org', location: { label: 'North gate' }, assignment: { ...offer, status: 'ACCEPTED' }, upload_targets: [], allowed_transitions: ['IN_PROGRESS'] } };
      return null;
    });
    await page.goto(`${BASE}/contractor.html`, { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: 'New work offers' })).toBeVisible();
    await page.getByRole('button', { name: 'Accept assignment' }).click();
    await expect(page.getByRole('heading', { name: 'Thermal inspection' })).toBeVisible();
    expect(decisionBody).toEqual({ decision: 'ACCEPTED', expected_version: 2 });
    await page.getByRole('button', { name: 'View details' }).click();
    await expect(page.getByText('North gate', { exact: true })).toBeVisible();
    await expect(page.getByText(/Sep 12, 2026/).first()).toBeVisible();
    const visibleText = await page.locator('#contractor-app').innerText();
    expect(visibleText).not.toContain('secret-order');
    expect(visibleText).not.toContain('secret-asset');
    expect(visibleText).not.toContain('secret-customer');
    expect(visibleText).not.toContain('secret-org');
  });

  test('requires a reason for waiting and uploads only to a server-provided accepted target', async ({ page }) => {
    const stateBodies = [];
    let initiatedBody = null;
    let completedBody = null;
    let uploadedBytes = 0;
    const assignment = { id: 'assignment-1', assignment_number: 'GVA-1', title: 'Accepted work', status: 'ACCEPTED', location: { label: 'Approved field point' }, window_start: now, window_end: '2026-09-10T12:00:00Z', requirements: { equipment: ['RTK kit'] }, required_documents: [], lifecycle_version: 2 };
    const detail = { ...job({ state: 'IN_PROGRESS', scheduled_start: null, scheduled_end: null, order_id: undefined, asset_id: undefined, assigned_contractor_id: undefined }), location: { label: 'Approved field point' }, assignment, upload_targets: [{ dataset_id: 'dataset-1', name: 'Raw captures', status: 'active', file_count: 0 }], allowed_transitions: ['WAITING_INPUT', 'QA_REVIEW'] };
    await mockApi(page, async ({ path, method, request, route }) => {
      if (path === '/operations/contractor/me/experience') return { body: contractorExperience() };
      if (path === '/operations/contractor/me/jobs/job-1' && method === 'GET') return { body: detail };
      if (path === '/operations/contractor/me/jobs/job-1/state' && method === 'PATCH') { stateBodies.push(request.postDataJSON()); return { body: { ...detail, state: 'WAITING_INPUT', lifecycle_version: 4, allowed_transitions: ['IN_PROGRESS'] } }; }
      if (path === '/operations/contractor/me/jobs/job-1/uploads/initiate' && method === 'POST') { initiatedBody = request.postDataJSON(); return { status: 201, body: { upload_url: `${API}/signed/upload-1`, upload_reference: 'upload-1', expires_in: 900, required_headers: { 'Content-Type': 'text/plain' } } }; }
      if (path === '/signed/upload-1' && method === 'PUT') { uploadedBytes = request.postDataBuffer()?.length || 0; await route.fulfill({ status: 200, body: '' }); return 'handled'; }
      if (path === '/operations/contractor/me/jobs/job-1/uploads/complete' && method === 'POST') { completedBody = request.postDataJSON(); return { body: { upload_reference: 'upload-1', dataset_id: 'dataset-1', filename: 'field.txt', size_bytes: 10, status: 'CONFIRMED', sha256_hash: completedBody.sha256_hash, confirmed_at: now } }; }
      return null;
    });
    await page.goto(`${BASE}/contractor.html?view=jobs&job=job-1`, { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: 'Mark waiting for input' }).click();
    await expect(page.locator('#contractor-status')).toContainText('Add a reason');
    expect(stateBodies).toHaveLength(0);
    await page.getByLabel('Reason for waiting for input').fill('Weather hold');
    await page.getByRole('button', { name: 'Mark waiting for input' }).click();
    expect(stateBodies).toEqual([{ state: 'WAITING_INPUT', reason: 'Weather hold', expected_version: 3 }]);
    await page.getByRole('button', { name: 'Upload deliverable' }).click();
    await expect(page.locator('#upload-dataset option')).toHaveCount(2);
    await page.locator('#upload-dataset').selectOption('dataset-1');
    await page.locator('#upload-file').setInputFiles({ name: 'field.txt', mimeType: 'text/plain', buffer: Buffer.from('field-data') });
    await page.getByRole('button', { name: 'Upload deliverable' }).last().click();
    await expect.poll(() => completedBody).not.toBeNull();
    expect(initiatedBody).toMatchObject({ dataset_id: 'dataset-1', filename: 'field.txt', content_type: 'text/plain', size_bytes: 10, object_area: 'raw' });
    expect(uploadedBytes).toBe(10);
    expect(completedBody.dataset_id).toBe('dataset-1');
    expect(completedBody.upload_reference).toBe('upload-1');
    expect(completedBody.sha256_hash).toMatch(/^[a-f0-9]{64}$/);
  });

  test('does not show an upload action for an unaccepted assignment even with a target', async ({ page }) => {
    const offered = { id: 'offer-1', assignment_number: 'GVA-1', title: 'Offer', status: 'OFFERED', location: {}, window_start: now, window_end: null, requirements: {}, required_documents: [], lifecycle_version: 1 };
    await mockApi(page, ({ path }) => {
      if (path === '/operations/contractor/me/experience') return { body: contractorExperience() };
      if (path === '/operations/contractor/me/jobs/job-1') return { body: { ...job({ order_id: undefined, asset_id: undefined, assigned_contractor_id: undefined }), location: {}, assignment: offered, upload_targets: [{ dataset_id: 'dataset-1', name: 'Output', status: 'active', file_count: 0 }], allowed_transitions: [] } };
      return null;
    });
    await page.goto(`${BASE}/contractor.html?view=jobs&job=job-1`, { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('button', { name: 'Upload deliverable' })).toHaveCount(0);
  });

  test('saves contractor profile without granting document editing', async ({ page }) => {
    let saved = null;
    const profile = { id: 'contractor-1', display_name: 'Field Partner', resource_type: 'DRONE_OPERATOR', status: 'ACTIVE', availability: 'AVAILABLE', contact_email: 'field@example.test', contact_phone: '+244 900 000', country_code: 'AO', region: 'Luanda', service_area: ['Luanda'], certifications: [], equipment: [], document_refs: [], capabilities: [] };
    await mockApi(page, ({ path, method, request }) => {
      if (path === '/operations/contractor/me/experience') return { body: contractorExperience({ keys: ['my_jobs', 'profile', 'documents'] }) };
      if (path === '/operations/contractor/me/profile' && method === 'GET') return { body: profile };
      if (path === '/operations/contractor/me/profile' && method === 'PATCH') { saved = request.postDataJSON(); return { body: { ...profile, ...saved } }; }
      return null;
    });
    await page.goto(`${BASE}/contractor.html?view=profile`, { waitUntil: 'domcontentloaded' });
    await page.locator('#profile-region').fill('Bengo');
    await page.getByRole('button', { name: 'Save profile' }).click();
    await expect.poll(() => saved).not.toBeNull();
    expect(saved.region).toBe('Bengo');
    expect(saved).not.toHaveProperty('document_refs');
  });
});

test.describe('Phase 24 responsive accessibility', () => {
  for (const width of [320, 390]) {
    test(`both portals have no page overflow and no serious accessibility violations at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 780 });
      await mockApi(page, ({ path }) => {
        if (path === '/operations/experience') return { body: internalExperience(['dashboard', 'jobs', 'processing']) };
        if (path === '/operations/dashboard') return { body: emptyDashboard() };
        if (path === '/operations/queues') return { body: emptyQueues() };
        if (path === '/operations/contractor/me/experience') return { body: contractorExperience({ counts: { offered: 1, scheduled: 0, active: 0, review: 0, completed: 0 } }) };
        if (path === '/operations/contractor/me/jobs') return { body: [] };
        if (path === '/operations/contractor/me/assignments') return { body: [{ id: 'offer-mobile', assignment_number: 'GVA-MOBILE', title: 'Mobile field offer', status: 'OFFERED', location: { label: 'Field point' }, window_start: now, window_end: '2026-09-10T12:00:00Z', requirements: { equipment: ['RTK kit'], capabilities: ['Survey'] }, upload_area: {}, required_documents: [{ name: 'Licence' }], document_profile: [], lifecycle_version: 1, created_at: now, updated_at: now }] };
        return null;
      });
      await page.goto(`${BASE}/admin.html`, { waitUntil: 'domcontentloaded' });
      await expect(page.locator('#operations-app')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      let results = await new AxeBuilder({ page }).analyze();
      expect(results.violations.filter((item) => item.impact === 'critical' || item.impact === 'serious')).toEqual([]);
      await page.goto(`${BASE}/contractor.html`, { waitUntil: 'domcontentloaded' });
      await expect(page.locator('#contractor-app')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      results = await new AxeBuilder({ page }).analyze();
      expect(results.violations.filter((item) => item.impact === 'critical' || item.impact === 'serious')).toEqual([]);
    });
  }

  test('both portals render their desktop shell without page overflow', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockApi(page, ({ path }) => {
      if (path === '/operations/experience') return { body: internalExperience(['dashboard', 'jobs', 'processing', 'system_health']) };
      if (path === '/operations/dashboard') return { body: emptyDashboard() };
      if (path === '/operations/queues') return { body: emptyQueues() };
      if (path === '/operations/contractor/me/experience') return { body: contractorExperience() };
      if (path === '/operations/contractor/me/jobs' || path === '/operations/contractor/me/assignments') return { body: [] };
      return null;
    });
    await page.goto(`${BASE}/admin.html`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#operations-app')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.goto(`${BASE}/contractor.html`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('#contractor-app')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
});
