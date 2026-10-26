const { test, expect } = require('@playwright/test');
const BASE = process.env.TEST_BASE_URL || 'http://127.0.0.1:8001';

test('GAIA sends the signed-in session and selected workspace with context and chat', async ({ page }) => {
  const calls = [];
  await page.addInitScript(() => {
    localStorage.setItem('gv_token', 'test-customer-token');
    localStorage.setItem('gv_workspace_id', 'workspace-selected');
    localStorage.setItem('gv_user', JSON.stringify({id:'customer-1',email:'qa@example.com',role:'cliente'}));
  });
  await page.route('http://127.0.0.1:8010/**', async route => {
    const request = route.request();
    const endpoint = new URL(request.url()).pathname;
    if (endpoint === '/auth/me') return route.fulfill({json:{id:'customer-1',email:'qa@example.com',role:'cliente'}});
    if (endpoint === '/kpi/context' || endpoint === '/ai/chat') {
      calls.push({endpoint,headers:request.headers()});
      if (request.headers().authorization !== 'Bearer test-customer-token' || request.headers()['x-workspace-id'] !== 'workspace-selected') {
        return route.fulfill({status:403,json:{detail:'Unauthorized context'}});
      }
      return route.fulfill({json:endpoint === '/kpi/context'
        ? {summary_text:'Synthetic site',kpis:[],alerts:[],sectors:[]}
        : {reply:'Synthetic site response for the selected workspace.'}});
    }
    return route.fulfill({json:[]});
  });
  await page.goto(`${BASE}/index.html`, {waitUntil:'domcontentloaded'});
  await page.locator('#gv-chat-toggle').click();
  await page.locator('#gv-chat-input').fill('Summarize the current site.');
  await page.locator('#gv-chat-send').click();
  await expect(page.locator('.gv-msg-bot').last()).toHaveText('Synthetic site response for the selected workspace.');
  expect(calls.map(call=>call.endpoint)).toEqual(['/kpi/context','/ai/chat']);
  await expect(page.locator('#gv-chat-input')).toBeEnabled();
});

test('GAIA tells visitors to sign in before requesting private customer assistance', async ({ page }) => {
  const chatCalls = [];
  await page.route('http://127.0.0.1:8010/**', async route => {
    const endpoint = new URL(route.request().url()).pathname;
    if (endpoint === '/ai/chat' || endpoint === '/kpi/context') chatCalls.push(endpoint);
    return route.fulfill({json:[]});
  });
  await page.goto(`${BASE}/index.html`, {waitUntil:'domcontentloaded'});
  await page.locator('#gv-chat-toggle').click();
  await page.locator('#gv-chat-input').fill('Summarize the current site.');
  await page.locator('#gv-chat-send').click();
  await expect(page.locator('.gv-msg-bot').last()).toContainText('Inicie sessão');
  expect(chatCalls).toEqual([]);
  await expect(page.locator('#gv-chat-input')).toBeEnabled();
});
